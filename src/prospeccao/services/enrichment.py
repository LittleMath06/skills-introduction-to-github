"""Enriquecimento: consulta de CNPJ sob demanda, site oficial e ICMS (SEFAZ)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import cnpj as cnpj_mod
from ..models import Company, FiscalInfo, utcnow
from ..sources.base import SourceError, SourceNotConfigured
from ..sources.cnpj_api import CnpjApiSource, CnpjNotFound
from ..sources.sefaz import SefazIcmsSource
from ..sources.website import WebsiteSource, candidate_from_email, normalize_url
from . import sources_status
from .companies import Lookups, ScoringContext, _add_contact, refresh_flags, score_company, \
    upsert_company

CACHE_DAYS = 30


def lookup_cnpj(session: Session, api: CnpjApiSource, raw_cnpj: str,
                force: bool = False) -> tuple[Company, bool]:
    """Retorna (empresa, consultou_fonte?). Usa cache de 30 dias."""
    cnpj = cnpj_mod.validate(raw_cnpj)
    company = session.scalar(select(Company).where(Company.cnpj == cnpj))
    if company and not force and company.source_updated_at and \
            utcnow() - company.source_updated_at < timedelta(days=CACHE_DAYS) and not company.is_mock:
        return company, False
    try:
        record, prov = api.fetch(cnpj)
    except CnpjNotFound:
        sources_status.record_success(session, "cnpj_api")
        session.commit()
        raise
    except SourceError as exc:
        sources_status.record_failure(session, "cnpj_api", str(exc))
        session.commit()
        raise
    descriptions = record.pop("cnae_descriptions", {})
    reference = f"{api.provider} {prov.fetched_at:%Y-%m-%d}"
    company, _, _ = upsert_company(session, record, "cnpj_api", reference, Lookups(session),
                                   existing=company)
    if company.is_mock:
        company.is_mock = False
    _store_cnae_descriptions(session, {record.get("cnae_principal"): record.get("cnae_principal_desc"),
                                       **descriptions})
    session.flush()
    score_company(company, ScoringContext.load(session))
    sources_status.record_success(session, "cnpj_api", 1)
    session.commit()
    return company, True


def _store_cnae_descriptions(session: Session, descriptions: dict) -> None:
    from ..models import Cnae

    for code, desc in descriptions.items():
        if code and desc and session.get(Cnae, code) is None:
            session.add(Cnae(code=code, description=desc))


def enrich_website(session: Session, source: WebsiteSource, company: Company) -> str:
    url = normalize_url(company.website) or candidate_from_email(
        next((c.value for c in company.contacts if c.kind == "email" and c.is_company), None)
    )
    if not url:
        return "Sem site informado nem e-mail com domínio próprio para descobrir o site"
    try:
        result = source.fetch(url, company.cnpj, company.razao_social, company.nome_fantasia)
    except SourceError as exc:
        company.enriched_at = utcnow()
        sources_status.record_failure(session, "website", f"{url}: {exc}")
        return f"Falha: {exc}"
    manual = company.website_status == "manual"
    if result.verified or manual:
        company.website = result.final_url
        company.website_status = "manual" if manual else "verificado"
    else:
        company.website = result.final_url
        company.website_status = "inferido"
    company.site_title = result.title
    company.site_description = result.description
    company.logo_url = result.logo_url if (result.verified or manual) else None
    added = 0
    if result.verified or manual:
        for c in result.contacts:
            added += _add_contact(company, c.kind, c.value, "Site oficial", c.source_url,
                                  c.is_company)
    company.enriched_at = utcnow()
    company.updated_at = utcnow()
    refresh_flags(company)
    sources_status.record_success(session, "website", added)
    return (f"{result.verification_reason}. {added} contato(s) novo(s)." if (result.verified or manual)
            else f"{result.verification_reason}. Contatos não importados até confirmação do site.")


def check_icms(session: Session, sefaz: SefazIcmsSource, company: Company) -> str:
    try:
        result, prov = sefaz.consult(company.uf or "", company.cnpj)
    except SourceNotConfigured:
        raise
    except SourceError as exc:
        sources_status.record_failure(session, "sefaz_icms", str(exc))
        raise
    # Remove resultados anteriores da mesma fonte oficial (mantém manuais)
    company.fiscal_infos[:] = [f for f in company.fiscal_infos
                               if not (f.created_by == "sistema" and f.source == prov.source)]
    company.icms_status = result["status"]
    if result["status"] == "nao_contribuinte":
        company.fiscal_infos.append(FiscalInfo(
            category="icms", label="Situação no cadastro de ICMS",
            value=f"Não cadastrado como contribuinte na UF ({result['xMotivo']})",
            level="confirmado", source=prov.source, source_url=prov.url, confidence=1.0,
        ))
    for reg in result["registros"]:
        company.fiscal_infos.append(FiscalInfo(
            category="inscricao_estadual", label=f"Inscrição estadual ({reg['uf']})",
            value=f"{reg['ie']} — {'habilitada' if reg['habilitado'] else 'não habilitada'}",
            level="confirmado", source=prov.source, source_url=prov.url,
            data_date=reg["data_ultima_situacao"], confidence=1.0,
        ))
        if reg.get("regime_apuracao"):
            company.fiscal_infos.append(FiscalInfo(
                category="regime_apuracao", label="Regime de apuração do ICMS",
                value=reg["regime_apuracao"], level="confirmado", source=prov.source,
                source_url=prov.url, data_date=reg["data_ultima_situacao"], confidence=1.0,
            ))
    sources_status.record_success(session, "sefaz_icms", 1)
    return f"ICMS: {result['status']}"
