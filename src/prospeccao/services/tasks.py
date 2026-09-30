"""Funções executadas como jobs em background (e pela CLI/cron)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from ..config import Settings
from ..models import Company, Customer
from ..sources.base import SourceError, SourceNotConfigured
from ..sources.cnpj_api import CnpjApiSource, CnpjNotFound
from ..sources.receita import ReceitaOpenDataSource
from ..sources.sefaz import SefazIcmsSource
from ..sources.website import WebsiteSource
from . import sources_status
from .companies import mark_customers, rebuild_profile, rescore_all
from .customer_import import import_customers, relink_customers
from .enrichment import check_icms, enrich_website, lookup_cnpj
from .jobs import JobContext
from .receita_import import ImportFilters, default_cnae_prefixes, import_receita_files


class Sources:
    """Fábrica das fontes a partir da configuração (facilita substituição em testes)."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def receita(self) -> ReceitaOpenDataSource:
        return ReceitaOpenDataSource(self.settings.rf_base_url, self.settings.data_dir / "receita",
                                     self.settings.http_user_agent)

    def cnpj_api(self) -> CnpjApiSource:
        return CnpjApiSource(self.settings.cnpj_api_provider, self.settings.http_user_agent,
                             self.settings.cnpj_api_min_interval)

    def website(self) -> WebsiteSource:
        return WebsiteSource(self.settings.http_user_agent, self.settings.website_min_interval,
                             enabled=self.settings.website_enrichment_enabled)

    def sefaz(self) -> SefazIcmsSource:
        return SefazIcmsSource(self.settings.icms_endpoints, self.settings.icms_cert_file,
                               self.settings.icms_key_file)


def _rescore(ctx: JobContext) -> int:
    s = ctx.session
    relink_customers(s)
    mark_customers(s)
    profile = rebuild_profile(s)
    s.commit()
    ctx.info(f"Perfil de cliente ideal recalculado com {profile.n} cliente(s)")
    total = s.scalar(select(func.count(Company.id))) or 0
    ctx.set_total(total)
    n = rescore_all(s, progress=lambda done: ctx.progress(done, f"{done} empresas pontuadas"))
    return n


def task_rescore(ctx: JobContext, params: dict) -> str:
    n = _rescore(ctx)
    return f"{n} empresas reclassificadas e pontuadas"


def task_import_customers(ctx: JobContext, params: dict) -> str:
    path = Path(params["path"])
    try:
        report = import_customers(ctx.session, params["filename"], path.read_bytes())
        ctx.session.commit()
    finally:
        path.unlink(missing_ok=True)  # não manter cópia da planilha privada
    sources_status.record_success(ctx.session, "customer_import", report.imported + report.updated)
    ctx.session.commit()
    ctx.job.params = {**params, "report": report.to_dict()}
    ctx.session.commit()
    for inv in report.invalid_cnpj[:50]:
        ctx.error(f"Linha {inv['linha']}: CNPJ inválido ({inv['valor']})")
    ctx.info(f"Importados {report.imported}, atualizados {report.updated}, "
             f"duplicados no arquivo {report.duplicates_in_file}, sem CNPJ {report.without_cnpj}, "
             f"inválidos {len(report.invalid_cnpj)}, vinculados à base {report.linked}, "
             f"não encontrados na base {report.not_found}")
    _rescore(ctx)
    return "Base de clientes importada e perfil recalculado"


def task_import_receita(ctx: JobContext, params: dict, sources: Sources) -> str:
    settings = sources.settings
    source = sources.receita()
    s = ctx.session
    files_dir = Path(params.get("dir") or source.files_dir)
    reference = params.get("reference") or files_dir.name
    try:
        if params.get("download"):
            month = params.get("month") or source.latest_month()
            names = source.list_remote_files(month)
            wanted = [n for n in names if any(k in n.lower() for k in
                                              ("estabele", "empresa", "simples", "cnae", "munic",
                                               "natureza"))]
            ctx.info(f"Baixando {len(wanted)} arquivo(s) de {month}")
            source.download(month, wanted, progress=lambda i, t, n: ctx.info(f"{i}/{t} {n}"))
            files_dir, reference = source.files_dir / month, month
        prefixes = tuple(settings.rf_filter_cnae_prefixes) or default_cnae_prefixes(s)
        filters = ImportFilters(set(settings.rf_filter_ufs), prefixes, settings.rf_only_active)
        ctx.info(f"Filtros: UFs={sorted(filters.ufs) or 'todas'}; "
                 f"CNAEs={len(prefixes)} prefixos; somente ativas={filters.only_active}")
        stats = import_receita_files(s, files_dir, filters, reference, ctx)
    except (SourceError, FileNotFoundError, OSError) as exc:
        s.rollback()
        sources_status.record_failure(s, "receita_open_data", str(exc))
        s.commit()
        raise
    sources_status.record_success(s, "receita_open_data", stats["accepted"], reference)
    s.commit()
    _rescore(ctx)
    return (f"{stats['created']} novas, {stats['updated']} atualizadas, "
            f"{stats['changes']} mudanças cadastrais, {stats['invalid']} linhas inválidas")


def task_lookup_customers(ctx: JobContext, params: dict, sources: Sources) -> str:
    """Consulta na API pública os clientes sem correspondência na base local (1 por vez)."""
    s = ctx.session
    api = sources.cnpj_api()
    pending = s.scalars(select(Customer).where(Customer.status == "nao_encontrado")
                        .limit(int(params.get("limit", 200)))).all()
    ctx.set_total(len(pending))
    found = 0
    for i, customer in enumerate(pending, 1):
        try:
            company, _ = lookup_cnpj(s, api, customer.cnpj)
            customer.company_id = company.id
            customer.status = "ok"
            found += 1
            s.commit()
        except CnpjNotFound:
            s.rollback()
            ctx.error(f"CNPJ {customer.cnpj} não encontrado na fonte")
        except SourceError as exc:
            s.rollback()
            ctx.error(f"CNPJ {customer.cnpj}: {exc}")
            if "429" in str(exc):
                ctx.info("Limite da API atingido — interrompido; tente mais tarde")
                break
        ctx.progress(i)
    _rescore(ctx)
    return f"{found} de {len(pending)} clientes localizados"


def task_enrich_websites(ctx: JobContext, params: dict, sources: Sources) -> str:
    s = ctx.session
    source = sources.website()
    if not source.is_enabled():
        raise SourceNotConfigured("Enriquecimento por site desativado (WEBSITE_ENRICHMENT_ENABLED)")
    ids = params.get("company_ids")
    stmt = select(Company).where(Company.is_mock.is_(False))
    if ids:
        stmt = stmt.where(Company.id.in_(ids))
    else:
        stmt = stmt.where(Company.enriched_at.is_(None), Company.situacao_cadastral == "02",
                          Company.is_customer.is_(False)) \
            .order_by(Company.potential.desc()).limit(int(params.get("limit", 100)))
    companies = s.scalars(stmt).unique().all()
    ctx.set_total(len(companies))
    for i, company in enumerate(companies, 1):
        msg = enrich_website(s, source, company)
        s.commit()  # confirmar antes de registrar o progresso (SQLite: um escritor por vez)
        if msg.startswith("Falha"):
            ctx.error(f"{company.cnpj}: {msg}")
        ctx.progress(i, f"{company.display_name}: {msg}")
    return f"{len(companies)} empresa(s) processada(s)"


def task_icms(ctx: JobContext, params: dict, sources: Sources) -> str:
    s = ctx.session
    sefaz = sources.sefaz()
    if not sefaz.is_enabled():
        raise SourceNotConfigured("Consulta SEFAZ não configurada (certificado e endpoints)")
    companies = s.scalars(select(Company).where(Company.id.in_(params["company_ids"]))).unique().all()
    ctx.set_total(len(companies))
    for i, company in enumerate(companies, 1):
        try:
            msg = check_icms(s, sefaz, company)
            s.commit()
            ctx.info(f"{company.cnpj}: {msg}")
        except SourceError as exc:
            s.commit()  # registra a falha da fonte
            ctx.error(f"{company.cnpj}: {exc}")
        ctx.progress(i)
    return f"{len(companies)} consulta(s) de ICMS"
