"""Linha de comando (administração e agendamento via cron).

Exemplos:
  python -m prospeccao.cli init
  python -m prospeccao.cli set-password paulo
  python -m prospeccao.cli import-customers clientes.xlsx
  python -m prospeccao.cli import-receita --dir data/receita/2026-09
  python -m prospeccao.cli update            # mensal (cron): baixa mês mais recente, importa, recalcula
  python -m prospeccao.cli enrich --limit 100
  python -m prospeccao.cli check-sources
  python -m prospeccao.cli seed-mock         # somente desenvolvimento
"""
from __future__ import annotations

import argparse
import getpass
import shutil
import sys
import uuid
from functools import partial
from pathlib import Path

from .config import get_settings
from .db import create_all, init_engine, new_session
from .services.bootstrap import bootstrap, set_password
from .services.jobs import JobRunner
from .services.tasks import (
    Sources,
    task_enrich_websites,
    task_import_customers,
    task_import_receita,
    task_lookup_customers,
    task_rescore,
)


def _setup():
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_engine(settings.database_url)
    create_all()
    with new_session() as s:
        bootstrap(s, settings)
    return settings


def _run(kind: str, params: dict, func) -> int:
    runner = JobRunner(synchronous=True)
    with new_session() as s:
        job = runner.submit(s, kind, params, func)
        s.refresh(job)
        for line in (job.log or [])[-30:]:
            print("  ", line)
        print(f"[{job.status}] {job.message}")
        return 0 if job.status == "done" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prospeccao")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Cria tabelas e dados iniciais")
    p = sub.add_parser("set-password", help="Cria/atualiza o usuário e a senha")
    p.add_argument("username", nargs="?", default=None)
    p = sub.add_parser("import-customers", help="Importa a base de clientes (CSV/XLSX)")
    p.add_argument("file")
    p = sub.add_parser("import-receita", help="Importa arquivos da Receita de uma pasta")
    p.add_argument("--dir", default=None)
    p.add_argument("--download", action="store_true", help="Baixa o mês mais recente antes")
    p.add_argument("--month", default=None, help="AAAA-MM (com --download)")
    sub.add_parser("update", help="Rotina periódica: baixa, importa e recalcula")
    sub.add_parser("rescore", help="Recalcula classificação e pontuações")
    p = sub.add_parser("enrich", help="Enriquece contatos pelos sites")
    p.add_argument("--limit", type=int, default=100)
    sub.add_parser("lookup-customers", help="Consulta clientes não encontrados na API pública")
    sub.add_parser("check-sources", help="Verifica disponibilidade/configuração das fontes")
    p = sub.add_parser("seed-mock", help="Gera dados FICTÍCIOS (somente desenvolvimento)")
    p.add_argument("--companies", type=int, default=400)
    sub.add_parser("clear-mock", help="Remove todos os dados fictícios")
    p = sub.add_parser("forget", help="LGPD: remove contatos, lead e histórico de um CNPJ")
    p.add_argument("cnpj")
    args = parser.parse_args(argv)

    try:
        settings = _setup()
    except RuntimeError as exc:  # configuração inválida (.env): mensagem clara, sem traceback
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2
    sources = Sources(settings)

    if args.cmd == "init":
        print("Banco inicializado em", settings.database_url.split("@")[-1])
        return 0
    if args.cmd == "set-password":
        username = args.username or settings.admin_username
        pw = getpass.getpass("Nova senha: ")
        if pw != getpass.getpass("Repita a senha: "):
            print("As senhas não conferem", file=sys.stderr)
            return 1
        try:
            with new_session() as s:
                set_password(s, username, pw)
                s.commit()
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Senha definida para {username}")
        return 0
    if args.cmd == "import-customers":
        src = Path(args.file)
        if not src.is_file():
            print("Arquivo não encontrado", file=sys.stderr)
            return 1
        upload = settings.data_dir / "uploads" / f"{uuid.uuid4().hex}{src.suffix.lower()}"
        upload.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, upload)
        return _run("import_customers", {"path": str(upload), "filename": src.name},
                    task_import_customers)
    if args.cmd == "import-receita":
        return _run("import_receita", {"dir": args.dir, "download": args.download,
                                       "month": args.month},
                    partial(task_import_receita, sources=sources))
    if args.cmd == "update":
        code = _run("import_receita", {"download": True}, partial(task_import_receita, sources=sources))
        if settings.website_enrichment_enabled:
            _run("enrich_websites", {"limit": 100}, partial(task_enrich_websites, sources=sources))
        return code
    if args.cmd == "rescore":
        return _run("rescore", {}, task_rescore)
    if args.cmd == "enrich":
        return _run("enrich_websites", {"limit": args.limit},
                    partial(task_enrich_websites, sources=sources))
    if args.cmd == "lookup-customers":
        return _run("lookup_customers", {"limit": 200}, partial(task_lookup_customers, sources=sources))
    if args.cmd == "check-sources":
        for src in (sources.receita(), sources.cnpj_api(), sources.sefaz(), sources.website()):
            st = src.check()
            print(f"{'OK ' if st.ok else 'NOK'} {src.name}: {st.message}")
        return 0
    if args.cmd == "seed-mock":
        from .services.mock_seed import seed_mock

        with new_session() as s:
            try:
                print("Gerado (MOCK):", seed_mock(s, settings, n_companies=args.companies))
            except PermissionError as exc:
                print(exc, file=sys.stderr)
                return 1
        return 0
    if args.cmd == "forget":
        from sqlalchemy import delete, select

        from .domain.cnpj import clean
        from .models import Company, CompanyChange, Lead

        with new_session() as s:
            company = s.scalar(select(Company).where(Company.cnpj == clean(args.cnpj)))
            if company is None:
                print("CNPJ não encontrado na base", file=sys.stderr)
                return 1
            company.contacts.clear()
            company.website = company.logo_url = company.site_title = None
            company.site_description = company.website_status = None
            company.has_phone = company.has_email = company.has_website = False
            s.execute(delete(Lead).where(Lead.company_id == company.id))
            s.execute(delete(CompanyChange).where(CompanyChange.company_id == company.id))
            s.commit()
        print("Contatos, lead e histórico removidos. Obs.: a próxima importação da Receita "
              "trará novamente os dados públicos cadastrais.")
        return 0
    if args.cmd == "clear-mock":
        from .services.mock_seed import clear_mock

        with new_session() as s:
            print("Removidas:", clear_mock(s))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
