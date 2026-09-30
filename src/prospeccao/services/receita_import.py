"""Importação filtrada dos Dados Abertos do CNPJ para o banco.

Passos:
 1. tabelas auxiliares (CNAE, municípios, naturezas);
 2. Estabelecimentos → upsert por CNPJ, filtrando por UF/CNAE/situação. Estabelecimentos já
    existentes no banco são SEMPRE processados, para detectar baixas e mudanças;
 3. Empresas → razão social, natureza, capital e porte (somente para os CNPJ básicos importados);
 4. Simples → opção pelo Simples/MEI;
 5. vínculo com clientes, recálculo de pontuações.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import cnpj as cnpj_mod
from ..models import Cnae, Company, Customer, Municipio, NaturezaJuridica, Segment
from ..sources.receita import (
    LayoutError,
    classify_files,
    iter_rows,
    parse_empresa,
    parse_estabelecimento,
    parse_lookup,
    parse_simples,
)
from .companies import Lookups, upsert_company

BATCH = 1000


@dataclass
class ImportFilters:
    ufs: set[str]
    cnae_prefixes: tuple[str, ...]
    only_active: bool

    def accepts(self, rec: dict) -> bool:
        if self.only_active and rec.get("situacao_cadastral") != "02":
            return False
        if self.ufs and rec.get("uf") not in self.ufs:
            return False
        if self.cnae_prefixes:
            codes = [rec.get("cnae_principal") or "", *rec.get("cnaes_secundarios", [])]
            # CNAE principal casa com qualquer prefixo; secundário só com prefixos específicos (>=4)
            if not any(codes[0].startswith(p) for p in self.cnae_prefixes) and not any(
                c.startswith(p) for c in codes[1:] for p in self.cnae_prefixes if len(p) >= 4
            ):
                return False
        return True


def default_cnae_prefixes(session: Session) -> tuple[str, ...]:
    """Sem configuração explícita: classes CNAE (4 dígitos) dos clientes + prefixos específicos
    (>= 4 dígitos) dos segmentos ativos. Mantém a base focada e de tamanho controlado."""
    prefixes: set[str] = set()
    for code in session.scalars(select(Customer.cnae).where(Customer.cnae.is_not(None))).all():
        prefixes.add(code[:4])
    for code in session.scalars(
        select(Company.cnae_principal).join(Customer, Customer.company_id == Company.id)
    ).all():
        if code:
            prefixes.add(code[:4])
    for seg in session.scalars(select(Segment).where(Segment.active.is_(True))).all():
        prefixes.update(p.strip() for p in seg.cnae_prefixes.split(",") if len(p.strip()) >= 4)
    return tuple(sorted(prefixes))


def _load_lookup(session: Session, model, paths: list[Path], ctx) -> int:
    count = 0
    for path in paths:
        existing = {row.code: row for row in session.scalars(select(model)).all()}
        for row in iter_rows(path):
            try:
                code, desc = parse_lookup(row)
            except LayoutError as exc:
                ctx.error(f"{path.name}: {exc}")
                continue
            if model is Cnae:
                code = code.zfill(7)
            obj = existing.get(code)
            if obj is None:
                obj = model(code=code, description=desc) if model is not Municipio else \
                    model(code=code, name=desc)
                session.add(obj)
                existing[code] = obj
            elif model is Municipio:
                obj.name = desc
            else:
                obj.description = desc
            count += 1
        session.commit()
    return count


def import_receita_files(session: Session, files_dir: Path, filters: ImportFilters,
                         reference: str, ctx) -> dict:
    files = classify_files(files_dir)
    if not files["estabelecimentos"]:
        raise FileNotFoundError(f"Nenhum arquivo de Estabelecimentos em {files_dir}")
    stats = {"lookups": 0, "read": 0, "accepted": 0, "created": 0, "updated": 0, "changes": 0,
             "invalid": 0, "empresas": 0, "simples": 0}

    stats["lookups"] += _load_lookup(session, Cnae, files["cnaes"], ctx)
    stats["lookups"] += _load_lookup(session, Municipio, files["municipios"], ctx)
    stats["lookups"] += _load_lookup(session, NaturezaJuridica, files["naturezas"], ctx)
    lookups = Lookups(session)
    ctx.info(f"Tabelas auxiliares: {stats['lookups']} registros")

    existing = set(session.scalars(select(Company.cnpj)).all())
    basicos: set[str] = set()
    batch: list[dict] = []

    def flush() -> None:
        if not batch:
            return
        cnpjs = [r["cnpj"] for r in batch]
        known = {c.cnpj: c for c in session.scalars(select(Company).where(Company.cnpj.in_(cnpjs)))}
        for rec in batch:
            company, created, changes = upsert_company(
                session, rec, "receita_open_data", reference, lookups,
                existing=known.get(rec["cnpj"]), known_absent=True,
            )
            known[rec["cnpj"]] = company  # CNPJ repetido no mesmo lote vira atualização
            stats["created" if created else "updated"] += 1
            stats["changes"] += changes
        session.commit()
        batch.clear()

    for path in files["estabelecimentos"]:
        ctx.info(f"Lendo {path.name}")
        for row in iter_rows(path):
            stats["read"] += 1
            try:
                rec = parse_estabelecimento(row)
            except (LayoutError, cnpj_mod.InvalidCNPJ) as exc:
                stats["invalid"] += 1
                if stats["invalid"] <= 50:
                    ctx.error(f"{path.name} linha {stats['read']}: {exc}")
                continue
            if rec["cnpj"] not in existing and not filters.accepts(rec):
                continue
            stats["accepted"] += 1
            basicos.add(rec["cnpj_basico"])
            batch.append(rec)
            if len(batch) >= BATCH:
                flush()
                ctx.progress(stats["accepted"], f"{stats['accepted']} estabelecimentos processados "
                                                f"({stats['read']} lidos)")
        flush()

    # Empresas e Simples: atualizam todos os estabelecimentos do mesmo CNPJ básico
    for kind, parser in (("empresas", parse_empresa), ("simples", parse_simples)):
        for path in files[kind]:
            ctx.info(f"Lendo {path.name}")
            pending: dict[str, dict] = {}
            for row in iter_rows(path):
                try:
                    rec = parser(row)
                except LayoutError as exc:
                    ctx.error(f"{path.name}: {exc}")
                    continue
                if rec["cnpj_basico"] in basicos:
                    pending[rec["cnpj_basico"]] = rec
                if len(pending) >= BATCH:
                    stats[kind] += _apply_basico(session, pending, reference, lookups)
                    pending.clear()
            stats[kind] += _apply_basico(session, pending, reference, lookups)
    ctx.info(f"Importação concluída: {stats}")
    return stats


def _apply_basico(session: Session, pending: dict[str, dict], reference: str,
                  lookups: Lookups) -> int:
    if not pending:
        return 0
    count = 0
    companies = session.scalars(
        select(Company).where(Company.cnpj_basico.in_(list(pending)))
    ).all()
    for company in companies:
        rec = {"cnpj": company.cnpj, **pending[company.cnpj_basico]}
        rec.pop("cnpj_basico", None)
        upsert_company(session, rec, "receita_open_data", reference, lookups, existing=company)
        count += 1
    session.commit()
    return count
