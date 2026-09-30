"""Upsert de empresas (deduplicação por CNPJ), histórico de mudanças e pontuação."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..domain import scoring
from ..domain.fiscal import infer_icms
from ..domain.regions import region_of
from ..domain.segments import SegmentRule, classify
from ..domain.text import is_free_email, norm
from ..models import (
    Cnae,
    Company,
    CompanyChange,
    CompanyContact,
    Customer,
    Municipio,
    NaturezaJuridica,
    Segment,
    utcnow,
)
from . import settings_store

TRACKED_FIELDS = [
    "razao_social", "nome_fantasia", "situacao_cadastral", "cnae_principal", "cnaes_secundarios",
    "logradouro", "numero", "cep", "municipio", "uf", "porte", "natureza_juridica_code",
    "simples_opcao", "mei_opcao",
]

COMPANY_FIELDS = [
    "cnpj_basico", "is_matriz", "razao_social", "nome_fantasia", "situacao_cadastral",
    "data_situacao", "data_abertura", "natureza_juridica_code", "natureza_juridica", "porte",
    "capital_social", "logradouro", "numero", "complemento", "bairro", "cep", "municipio_code",
    "municipio", "uf", "cnae_principal", "cnae_principal_desc", "simples_opcao", "mei_opcao",
    "simples_data_opcao", "simples_data_exclusao",
]


class Lookups:
    """Cache em memória das tabelas auxiliares (CNAE, município, natureza jurídica)."""

    def __init__(self, session: Session):
        self.cnae = dict(session.execute(select(Cnae.code, Cnae.description)).all())
        self.municipio = dict(session.execute(select(Municipio.code, Municipio.name)).all())
        self.natureza = dict(
            session.execute(select(NaturezaJuridica.code, NaturezaJuridica.description)).all()
        )


def _stringify(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ",".join(value)
    if isinstance(value, bool):
        return "sim" if value else "não"
    return str(value)


_MAX_LEN = {c.name: c.type.length for c in Company.__table__.columns
            if getattr(c.type, "length", None)}


def _fit(field: str, value):
    """Trunca textos ao tamanho da coluna (dados de fontes externas podem exceder o esperado)."""
    limit = _MAX_LEN.get(field)
    if limit and isinstance(value, str) and len(value) > limit:
        return value[:limit]
    return value


def build_search_text(c: Company) -> str:
    return norm(" ".join(filter(None, [
        c.razao_social, c.nome_fantasia, c.cnae_principal_desc, c.municipio, c.site_title,
    ])))


def _add_contact(company: Company, kind: str, value: str, source: str,
                 source_url: str | None = None, is_company: bool = True) -> bool:
    for existing in company.contacts:
        if existing.kind == kind and existing.value == value:
            existing.fetched_at = utcnow()
            return False
    company.contacts.append(CompanyContact(
        kind=kind, value=value, source=source, source_url=source_url, is_company=is_company,
    ))
    return True


def refresh_flags(company: Company) -> None:
    kinds = {c.kind for c in company.contacts}
    company.has_phone = bool(kinds & {"telefone", "whatsapp"})
    company.has_email = "email" in kinds
    company.has_website = bool(company.website)


def upsert_company(
    session: Session,
    record: dict,
    source: str,
    reference: str | None,
    lookups: Lookups | None = None,
    is_mock: bool = False,
    existing: Company | None = None,
    known_absent: bool = False,
) -> tuple[Company, bool, int]:
    """Cria ou atualiza pelo CNPJ. Retorna (empresa, criada?, nº de mudanças registradas).

    `known_absent=True` indica que o chamador já verificou que o CNPJ não existe (lote)."""
    company = existing
    if company is None and not known_absent:
        company = session.scalar(select(Company).where(Company.cnpj == record["cnpj"]))
    created = company is None
    if not created and company.id is None:
        session.flush()  # criada neste mesmo lote: precisa de id para o histórico
    if created:
        company = Company(cnpj=record["cnpj"], cnpj_basico=record["cnpj"][:8],
                          is_matriz=record["cnpj"][8:12] == "0001", source=source,
                          is_mock=is_mock, contacts=[], fiscal_infos=[])
        session.add(company)

    values = dict(record)
    if lookups:
        if not values.get("municipio") and values.get("municipio_code"):
            values["municipio"] = lookups.municipio.get(values["municipio_code"])
        if not values.get("cnae_principal_desc") and values.get("cnae_principal"):
            values["cnae_principal_desc"] = lookups.cnae.get(values["cnae_principal"])
        if not values.get("natureza_juridica") and values.get("natureza_juridica_code"):
            values["natureza_juridica"] = lookups.natureza.get(values["natureza_juridica_code"])
    if "cnaes_secundarios" in values:
        values["cnaes_secundarios"] = ",".join(values["cnaes_secundarios"] or [])

    changes = 0
    for field in COMPANY_FIELDS + ["cnaes_secundarios"]:
        if field not in values:
            continue
        new = _fit(field, values[field])
        # Nunca apaga um dado existente com vazio vindo de fonte parcial
        if new is None and field not in {"simples_data_exclusao"}:
            continue
        old = getattr(company, field)
        if old != new:
            if not created and field in TRACKED_FIELDS and old is not None:
                session.add(CompanyChange(
                    company_id=company.id, field=field,
                    old_value=_stringify(old), new_value=_stringify(new), source=source,
                ))
                changes += 1
            setattr(company, field, new)

    company.region = region_of(company.uf)
    company.source_reference = reference or company.source_reference
    company.source_updated_at = utcnow()
    company.updated_at = utcnow()
    company.is_mock = company.is_mock or is_mock

    src_label = "MOCK" if is_mock else (
        "Receita Federal (cadastro CNPJ)" if source == "receita_open_data" else source)
    mei = bool(company.mei_opcao)
    for phone in record.get("phones") or []:
        _add_contact(company, "telefone", phone, src_label, is_company=not mei)
    if record.get("email"):
        email = record["email"]
        _add_contact(company, "email", email, src_label,
                     is_company=not (mei or is_free_email(email)))
    refresh_flags(company)
    company.search_text = build_search_text(company)
    return company, created, changes


# ----------------------------------------------------------------------------------------------
# Pontuação
# ----------------------------------------------------------------------------------------------


@dataclass
class ScoringContext:
    rules: list[SegmentRule]
    segment_ids: dict[str, int]
    segment_names: dict[int, str]
    profile: scoring.Profile
    sim_weights: dict[str, float]
    pot_weights: dict[str, float]
    affinity: dict[str, float]
    customer_cnpjs: set[str]
    customer_basicos: set[str]
    today: date

    @classmethod
    def load(cls, session: Session) -> ScoringContext:
        segs = session.scalars(select(Segment).where(Segment.active.is_(True))).all()
        customer_cnpjs = set(session.scalars(
            select(Customer.cnpj).where(Customer.cnpj.is_not(None))
        ).all())
        return cls(
            rules=[SegmentRule.from_strings(s.id, s.name, s.cnae_prefixes, s.keywords, s.is_fallback)
                   for s in segs],
            segment_ids={s.name: s.id for s in segs},
            segment_names={s.id: s.name for s in segs},
            profile=scoring.Profile.from_dict(settings_store.get(session, "customer_profile")),
            sim_weights=settings_store.similarity_weights(session),
            pot_weights=settings_store.potential_weights(session),
            affinity=settings_store.segment_affinity(session),
            customer_cnpjs=customer_cnpjs,
            customer_basicos={c[:8] for c in customer_cnpjs},
            today=date.today(),
        )


def features_of(company: Company, segment_name: str | None) -> scoring.CompanyFeatures:
    return scoring.CompanyFeatures(
        cnae_principal=company.cnae_principal,
        secondary_cnaes=company.secondary_cnaes,
        segment=segment_name,
        uf=company.uf,
        porte=company.porte,
        text=" ".join(filter(None, [company.razao_social, company.nome_fantasia,
                                    company.cnae_principal_desc, company.site_description])),
    )


def classify_company(company: Company, ctx: ScoringContext) -> None:
    if company.segment_method == "manual" and company.segment_id in ctx.segment_names:
        return
    result = classify(
        ctx.rules, company.cnae_principal, company.secondary_cnaes,
        " ".join(filter(None, [company.razao_social, company.nome_fantasia,
                               company.cnae_principal_desc, company.site_title])),
    )
    company.segment_id = result.segment_id
    company.segment_method = result.method
    company.segment_confidence = result.confidence
    company.segment_explanation = result.explanation


def score_company(company: Company, ctx: ScoringContext) -> None:
    classify_company(company, ctx)
    seg_name = ctx.segment_names.get(company.segment_id) if company.segment_id else None
    company.is_customer = company.cnpj in ctx.customer_cnpjs
    company.customer_group = company.cnpj_basico in ctx.customer_basicos
    sim = scoring.similarity(ctx.profile, features_of(company, seg_name), ctx.sim_weights)
    company.similarity = sim["score"]
    company.similarity_details = sim
    company.completeness = scoring.completeness({
        "razao_social": company.razao_social, "nome_fantasia": company.nome_fantasia,
        "cnae_principal": company.cnae_principal, "endereco": company.logradouro,
        "municipio": company.municipio, "uf": company.uf, "telefone": company.has_phone,
        "email": company.has_email, "site": company.has_website,
        "porte": company.porte not in (None, "00"), "data_abertura": company.data_abertura,
    })
    age = ((ctx.today - company.data_abertura).days / 365.25) if company.data_abertura else None
    pot = scoring.potential(sim["score"], seg_name, company.completeness,
                            company.situacao_cadastral, age, ctx.pot_weights, ctx.affinity)
    company.potential = pot["score"]
    company.potential_details = pot
    if company.icms_status in ("nao_verificado", "provavel"):
        company.icms_status = "provavel" if infer_icms(
            company.cnae_principal, company.secondary_cnaes) else "nao_verificado"


def rebuild_profile(session: Session, ctx: ScoringContext | None = None) -> scoring.Profile:
    """Recalcula o perfil de cliente ideal a partir da base de clientes."""
    ctx = ctx or ScoringContext.load(session)
    features = []
    for customer in session.scalars(select(Customer)).all():
        company = customer.company
        if company is not None:
            classify_company(company, ctx)
            features.append(features_of(company, ctx.segment_names.get(company.segment_id)))
        elif customer.cnae or customer.uf or customer.razao_social:
            seg = classify(ctx.rules, customer.cnae, [], customer.razao_social)
            informed = customer.segmento_informado
            if informed:
                seg_name = next((n for n in ctx.segment_ids if norm(n) == norm(informed)),
                                seg.segment_name)
            else:
                # só o nome e nenhuma palavra-chave reconhecida: não "inventa" o segmento
                seg_name = None if seg.method == "fallback" else seg.segment_name
            features.append(scoring.CompanyFeatures(
                cnae_principal=customer.cnae, segment=seg_name, uf=customer.uf,
                porte=customer.porte, text=" ".join(filter(None, [customer.razao_social,
                                                                  customer.nome_fantasia])),
            ))
    profile = scoring.Profile.build(features)
    settings_store.put(session, "customer_profile", profile.to_dict())
    settings_store.put(session, "customer_profile_built_at", utcnow().isoformat())
    return profile


def rescore_all(session: Session, progress=None, batch: int = 500) -> int:
    ctx = ScoringContext.load(session)
    total = 0
    last_id = 0
    while True:
        rows = session.scalars(
            select(Company).where(Company.id > last_id).order_by(Company.id).limit(batch)
        ).all()
        if not rows:
            break
        for company in rows:
            score_company(company, ctx)
        last_id = rows[-1].id
        total += len(rows)
        session.commit()
        if progress:
            progress(total)
    return total


def mark_customers(session: Session) -> None:
    cnpjs = set(session.scalars(select(Customer.cnpj).where(Customer.cnpj.is_not(None))).all())
    session.execute(update(Company).values(is_customer=False, customer_group=False))
    if cnpjs:
        basicos = {c[:8] for c in cnpjs}
        session.execute(update(Company).where(Company.cnpj.in_(cnpjs)).values(is_customer=True))
        for chunk in _chunks(sorted(basicos), 500):
            session.execute(update(Company).where(Company.cnpj_basico.in_(chunk))
                            .values(customer_group=True))


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i: i + size]


def age_label(d: date | None) -> str:
    if not d:
        return "—"
    years = (date.today() - d).days // 365
    return f"{years} ano(s)"


def last_changes(session: Session, company_id: int, limit: int = 30) -> list[CompanyChange]:
    return session.scalars(
        select(CompanyChange).where(CompanyChange.company_id == company_id)
        .order_by(CompanyChange.changed_at.desc()).limit(limit)
    ).all()
