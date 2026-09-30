"""Integração com banco: importação da Receita, da base de clientes, deduplicação e mudanças."""
from __future__ import annotations

import io
from dataclasses import replace

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from prospeccao.models import Company, CompanyChange, Customer, Job
from prospeccao.services.customer_import import ImportError_, import_customers
from prospeccao.services.jobs import JobRunner
from prospeccao.services.receita_import import ImportFilters, import_receita_files
from prospeccao.services.tasks import task_import_receita

from .conftest import FakeSources, emp_row, est_row, make_cnpj, write_zip


class Ctx:
    """Contexto mínimo de job para chamar serviços diretamente."""

    def __init__(self):
        self.errors, self.infos = [], []

    def info(self, m):
        self.infos.append(m)

    def error(self, m):
        self.errors.append(m)

    def progress(self, *a, **k):
        pass


def test_receita_import_filters_and_enriches(db, receita_dir):
    d, c = receita_dir
    ctx = Ctx()
    stats = import_receita_files(db, d, ImportFilters(set(), ("4321", "4673"), True), "2026-09", ctx)
    cnpjs = set(db.scalars(select(Company.cnpj)).all())
    # restaurante (CNAE fora do filtro) e baixada (situação) não entram
    assert cnpjs == {c["c1"], c["c1_filial"], c["c2"]}
    assert stats["invalid"] == 1 and any("colunas" in e for e in ctx.errors)
    e1 = db.scalar(select(Company).where(Company.cnpj == c["c1"]))
    assert e1.razao_social == "ELETRICA TESTE INSTALACOES LTDA"
    assert e1.municipio == "SAO PAULO" and e1.region == "Sudeste"
    assert e1.cnae_principal_desc == "Instalação e manutenção elétrica"
    assert e1.natureza_juridica == "Sociedade Empresária Limitada"
    assert e1.simples_opcao is True and e1.porte == "03" and float(e1.capital_social) == 150000
    assert e1.has_phone and e1.has_email
    filial = db.scalar(select(Company).where(Company.cnpj == c["c1_filial"]))
    assert not filial.is_matriz and filial.razao_social == e1.razao_social  # dados do CNPJ básico
    assert db.scalar(select(Company).where(Company.cnpj == c["c2"])).simples_opcao is False


def test_receita_reimport_is_idempotent_and_detects_changes(db, receita_dir, tmp_path):
    d, c = receita_dir
    filters = ImportFilters(set(), ("4321", "4673"), True)
    import_receita_files(db, d, filters, "2026-09", Ctx())
    n1 = db.scalar(select(func.count(Company.id)))
    import_receita_files(db, d, filters, "2026-09", Ctx())
    assert db.scalar(select(func.count(Company.id))) == n1  # sem duplicidades
    assert db.scalar(select(func.count(CompanyChange.id))) == 0

    # mês seguinte: c1 foi baixada e mudou de endereço; nova empresa aparece
    d2 = tmp_path / "2026-10"
    d2.mkdir()
    new = make_cnpj("77777777")
    write_zip(d2 / "Estabelecimentos0.zip", "ESTABELE", [
        est_row(c["c1"], fantasia="ELETRICA TESTE", situacao="08", cnae="4321500"),
        est_row(new, fantasia="NOVA INSTALADORA", cnae="4321500", uf="BA", municipio="3849"),
    ])
    import_receita_files(db, d2, filters, "2026-10", Ctx())
    e1 = db.scalar(select(Company).where(Company.cnpj == c["c1"]))
    assert e1.situacao_cadastral == "08" and e1.source_reference == "2026-10"
    changes = {ch.field for ch in db.scalars(select(CompanyChange).where(
        CompanyChange.company_id == e1.id))}
    assert "situacao_cadastral" in changes
    assert db.scalar(select(Company).where(Company.cnpj == new)).region == "Nordeste"
    # e-mail que não veio no arquivo novo não é apagado
    assert e1.has_email


def test_receita_uf_filter(db, receita_dir):
    d, c = receita_dir
    import_receita_files(db, d, ImportFilters({"PR"}, (), True), "2026-09", Ctx())
    assert set(db.scalars(select(Company.cnpj)).all()) == {c["c2"]}


def test_receita_missing_files_marks_source_failure(app, settings, tmp_path):
    from prospeccao.db import new_session
    from prospeccao.models import DataSource

    with new_session() as s:
        job = JobRunner(synchronous=True).submit(
            s, "import_receita", {"dir": str(tmp_path / "vazio")},
            lambda ctx, p: task_import_receita(ctx, p, FakeSources(settings)))
        assert job.status == "failed"
        src = s.scalar(select(DataSource).where(DataSource.key == "receita_open_data"))
        assert src.consecutive_failures == 1 and "Estabelecimentos" in src.last_error


def test_receita_full_task_scores_companies(app, settings, receita_dir, db):
    d, c = receita_dir
    s2 = replace(settings, rf_filter_cnae_prefixes=["4321", "4673"])
    job = JobRunner(synchronous=True).submit(
        db, "import_receita", {"dir": str(d)},
        lambda ctx, p: task_import_receita(ctx, p, FakeSources(s2)))
    assert job.status == "done", job.log
    e1 = db.scalar(select(Company).where(Company.cnpj == c["c1"]))
    db.refresh(e1)
    assert e1.segment.name == "Instaladores" and e1.potential > 0
    assert e1.icms_status == "nao_verificado"  # instalação = serviço, sem indício de ICMS
    e2 = db.scalar(select(Company).where(Company.cnpj == c["c2"]))
    assert e2.icms_status == "provavel"  # comércio atacadista


# ---------------------------------------------------------------- base de clientes


def _csv(lines: list[str]) -> bytes:
    return ("\n".join(lines)).encode("utf-8")


def test_customer_import_csv_validation_and_dedup(db):
    c1, c2 = make_cnpj("11111111"), make_cnpj("22222222")
    content = _csv([
        "Razão Social;CNPJ;Cidade;Estado;CNAE;Ramo",
        f"Cliente Um;{c1};São Paulo;SP;4321-5/00;Instaladores",
        f"Cliente Um repetido;{c1[:2]}.{c1[2:5]}.{c1[5:8]}/{c1[8:12]}-{c1[12:]};São Paulo;SP;;",
        "Cliente Inválido;11.111.111/1111-11;Rio;RJ;;",
        "Pessoa Física;123.456.789-09;Rio;RJ;;",
        "Cliente sem CNPJ;;Curitiba;Paraná;4673700;Distribuidores",
        ";;;;;",
        f"Cliente Dois;{c2};Curitiba;PR;;",
    ])
    rep = import_customers(db, "clientes.csv", content)
    db.commit()
    assert rep.total_rows == 6 and rep.imported == 3 and rep.duplicates_in_file == 1
    assert len(rep.invalid_cnpj) == 2 and rep.invalid_cnpj[0]["linha"] == 4
    assert "CPF" in rep.invalid_cnpj[1]["valor"]
    assert rep.without_cnpj == 1 and rep.not_found == 2 and rep.ignored_empty == 1
    assert rep.columns["cnpj"] == "CNPJ" and rep.columns["segmento"] == "Ramo"
    semcnpj = db.scalar(select(Customer).where(Customer.cnpj.is_(None)))
    assert semcnpj.uf == "PR" and semcnpj.cnae == "4673700" and semcnpj.status == "sem_cnpj"
    one = db.scalar(select(Customer).where(Customer.cnpj == c1))
    assert one.cnae == "4321500"

    # reimportação atualiza em vez de duplicar
    rep2 = import_customers(db, "clientes.csv", content)
    db.commit()
    assert rep2.imported == 0 and rep2.updated == 3  # sem CNPJ: deduplicado pelo nome
    assert db.scalar(select(func.count(Customer.id))) == 3
    assert db.scalar(select(func.count(Customer.id)).where(Customer.cnpj.is_not(None))) == 2


def test_customer_import_xlsx_with_title_rows(db):
    wb = Workbook()
    ws = wb.active
    ws.append(["Relatório de clientes"])
    ws.append([])
    ws.append(["Cliente", "CNPJ/CPF", "UF", "Porte"])
    ws.append(["Empresa X", int(make_cnpj("01234567")), "sp", "EPP"])
    buf = io.BytesIO()
    wb.save(buf)
    rep = import_customers(db, "base.xlsx", buf.getvalue())
    assert rep.imported == 1 and not rep.invalid_cnpj
    cust = db.scalar(select(Customer))
    assert cust.cnpj == make_cnpj("01234567") and cust.uf == "SP" and cust.porte == "03"


def test_customer_import_rejects_bad_files(db):
    with pytest.raises(ImportError_, match="Formato"):
        import_customers(db, "x.pdf", b"%PDF")
    with pytest.raises(ImportError_, match="Cabeçalho"):
        import_customers(db, "x.csv", b"a;b;c\n1;2;3")
    with pytest.raises(ImportError_, match="XLSX"):
        import_customers(db, "x.xlsx", b"nao e xlsx")


def test_customer_import_links_existing_company_and_builds_profile(client, db, receita_dir):
    d, c = receita_dir
    import_receita_files(db, d, ImportFilters(set(), ("4321", "4673"), True), "2026-09", Ctx())
    db.commit()
    content = _csv(["CNPJ;Razão social", f"{c['c1']};Eletrica Teste"])
    r = client.post("/api/customers/import", files={"file": ("c.csv", content, "text/csv")})
    assert r.status_code == 202
    job = r.json()
    assert job["status"] == "done", job["log"]
    assert job["relatorio"]["linked"] == 1
    prof = client.get("/api/profile").json()["perfil"]
    assert prof["n"] == 1 and prof["uf"] == {"SP": 1}
    # cliente não aparece como lead; a filial do mesmo grupo aparece sinalizada
    items = client.get("/api/companies?situacao=").json()["items"]
    by_cnpj = {i["cnpj"]: i for i in items}
    assert c["c1"] not in by_cnpj
    assert by_cnpj[c["c1_filial"]]["grupo_ja_atendido"] is True
    assert by_cnpj[c["c1_filial"]]["compatibilidade"] > by_cnpj[c["c2"]]["compatibilidade"]
    # arquivo enviado não é mantido em disco
    assert not list((client.app.state.settings.data_dir / "uploads").glob("*"))
    assert db.scalar(select(Job).where(Job.kind == "import_customers")).status == "done"


def test_upsert_truncates_oversized_fields(db):
    from prospeccao.services.companies import upsert_company

    rec = {"cnpj": make_cnpj("88888888"), "numero": "KM 12 " * 20, "razao_social": "X" * 400}
    company, created, _ = upsert_company(db, rec, "teste", "t")
    db.commit()
    assert created and len(company.numero) == 30 and len(company.razao_social) == 255


def test_receita_duplicate_row_in_same_file(db, tmp_path):
    d = tmp_path / "dup"
    d.mkdir()
    c = make_cnpj("66666666")
    write_zip(d / "Estabelecimentos0.zip", "ESTABELE", [
        est_row(c, fantasia="PRIMEIRA", cnae="4321500"),
        est_row(c, fantasia="SEGUNDA", cnae="4321500"),
    ])
    stats = import_receita_files(db, d, ImportFilters(set(), ("4321",), True), "x", Ctx())
    assert stats["created"] == 1 and stats["updated"] == 1
    assert db.scalar(select(Company).where(Company.cnpj == c)).nome_fantasia == "SEGUNDA"


# ---------------------------------------------------------------- clientes informados só pelo nome
# (mesmo formato da planilha real: 1 coluna "Clientes que já tiveram cotação"; nomes fictícios)


def _names_xlsx(names: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Cliente que já tiveram cotação"])
    for n in names:
        ws.append([n])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_name_only_list_import_and_dedup(db):
    content = _names_xlsx(["ELETRICA TESTE INSTALACOES LTDA", "Elétrica Teste Instalações Ltda.",
                           "DISTRIBUIDORA TESTE DE MATERIAIS ELETRICOS LTDA", "  ", "AGRO FICTICIA S/A"])
    rep = import_customers(db, "clientes.xlsx", content)
    db.commit()
    assert rep.columns == {"razao_social": "Cliente que já tiveram cotação"}
    assert rep.total_rows == 4 and rep.imported == 3 and rep.duplicates_in_file == 1
    assert rep.without_cnpj == 3 and rep.ignored_empty == 1
    assert {c.status for c in db.scalars(select(Customer))} == {"sem_cnpj"}
    rep2 = import_customers(db, "clientes.xlsx", content)
    db.commit()
    assert rep2.imported == 0 and db.scalar(select(func.count(Customer.id))) == 3


def test_name_only_customers_matched_in_receita_files(db, receita_dir):
    d, c = receita_dir
    import_customers(db, "c.xlsx", _names_xlsx([
        "ELETRICA TESTE INSTALACOES LTDA",                     # exato
        "DISTRIBUIDORA TESTE DE MATERIAIS ELETRICOS L",        # truncado pelo ERP
        "EMPRESA QUE NAO EXISTE NA RECEITA LTDA",
    ]))
    db.commit()
    ctx = Ctx()
    # filtro de CNAE que NÃO inclui as empresas: elas entram por serem clientes identificados
    stats = import_receita_files(db, d, ImportFilters(set(), ("0115",), True), "2026-09", ctx)
    assert stats["clientes_por_nome"] == 2
    by_name = {cu.razao_social: cu for cu in db.scalars(select(Customer))}
    exact = by_name["ELETRICA TESTE INSTALACOES LTDA"]
    assert exact.status == "ok" and exact.cnpj == c["c1"] and exact.match_method == "nome_receita"
    assert exact.company.is_matriz  # vincula à matriz, não à filial
    trunc = by_name["DISTRIBUIDORA TESTE DE MATERIAIS ELETRICOS L"]
    assert trunc.cnpj == c["c2"]
    assert by_name["EMPRESA QUE NAO EXISTE NA RECEITA LTDA"].status == "sem_cnpj"


def test_name_match_ambiguous_is_not_linked(db, tmp_path):
    d = tmp_path / "amb"
    d.mkdir()
    a, b = make_cnpj("12121212"), make_cnpj("34343434")
    write_zip(d / "Estabelecimentos0.zip", "ESTABELE", [est_row(a), est_row(b)])
    write_zip(d / "Empresas0.zip", "EMPRE", [emp_row("12121212", "HOMONIMA LTDA"),
                                              emp_row("34343434", "HOMONIMA EIRELI")])
    import_customers(db, "c.xlsx", _names_xlsx(["Homônima Ltda"]))
    db.commit()
    import_receita_files(db, d, ImportFilters(set(), ("0115",), True), "x", Ctx())
    cu = db.scalar(select(Customer))
    assert cu.status == "ambiguo" and cu.company_id is None and "CNPJ" in cu.match_note


def test_name_only_relink_against_local_base(db, receita_dir):
    from prospeccao.services.customer_import import relink_customers

    d, c = receita_dir
    import_receita_files(db, d, ImportFilters(set(), ("4321", "4673"), True), "2026-09", Ctx())
    import_customers(db, "c.xlsx", _names_xlsx(["Elétrica Teste Instalações Ltda."]))
    db.commit()
    assert relink_customers(db) == 1
    cu = db.scalar(select(Customer))
    assert cu.cnpj == c["c1"] and cu.match_method == "nome_exato"


def test_reimport_with_cnpj_upgrades_name_only_customer(db):
    import_customers(db, "c.xlsx", _names_xlsx(["ALFA INSTALACOES LTDA", "BETA LTDA"]))
    db.commit()
    c = make_cnpj("14141414")
    rep = import_customers(db, "c.csv", _csv(["Razão social;CNPJ;UF",
                                              f"Alfa Instalações Ltda.;{c};GO"]))
    db.commit()
    assert rep.imported == 0 and rep.updated == 1
    rows = {cu.razao_social: cu for cu in db.scalars(select(Customer))}
    assert len(rows) == 2 and rows["Alfa Instalações Ltda."].cnpj == c
    assert rows["Alfa Instalações Ltda."].uf == "GO" and rows["Alfa Instalações Ltda."].status == "nao_encontrado"
