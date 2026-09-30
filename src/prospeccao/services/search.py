"""Busca de empresas com filtros combináveis, ordenação e paginação."""
from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from ..domain import query_parser
from ..domain.regions import REGIONS, UF_TO_REGION
from ..domain.text import norm, only_digits
from ..models import Company, Lead, Municipio, Segment

SORTS = {
    "similarity": "Maior compatibilidade",
    "potential": "Maior potencial",
    "location": "Localização (UF/cidade)",
    "segment": "Segmento",
    "updated": "Atualização mais recente",
    "completeness": "Qualidade/completude dos dados",
    "name": "Nome",
}
ICMS_FILTERS = {"confirmado_habilitado", "confirmado_nao_habilitado", "nao_contribuinte",
                "provavel", "nao_verificado", "contribuinte"}
LEAD_STATES = {"todos", "novos", "salvos", "favoritos", "analisados", "descartados"}


class SearchFilters(BaseModel):
    nl: str | None = Field(None, max_length=300, description="Pesquisa em linguagem natural")
    q: str | None = Field(None, max_length=200, description="Termos (nome, atividade, cidade) ou CNPJ")
    region: str | None = None
    uf: str | None = None
    city: str | None = Field(None, max_length=120)
    segment: str | None = Field(None, max_length=80)
    cnae: str | None = Field(None, max_length=9, description="Prefixo de CNAE (2 a 7 dígitos)")
    porte: str | None = None
    situacao: str | None = Field("02", description="Código de situação; vazio = todas")
    icms: str | None = None
    has_site: bool | None = None
    has_phone: bool | None = None
    has_email: bool | None = None
    min_similarity: float | None = Field(None, ge=0, le=100)
    min_potential: float | None = Field(None, ge=0, le=100)
    updated_since: date | None = None
    include_customers: bool = False
    lead_state: str = "todos"
    sort: str = "potential"
    page: int = Field(1, ge=1, le=10_000)
    page_size: int = Field(25, ge=1, le=100)

    @field_validator("region")
    @classmethod
    def _region(cls, v):
        if v and v not in REGIONS:
            raise ValueError(f"Região inválida. Use: {', '.join(REGIONS)}")
        return v or None

    @field_validator("uf")
    @classmethod
    def _uf(cls, v):
        if v:
            v = v.upper()
            if v not in UF_TO_REGION:
                raise ValueError("UF inválida")
        return v or None

    @field_validator("cnae")
    @classmethod
    def _cnae(cls, v):
        if v:
            v = only_digits(v)
            if not 2 <= len(v) <= 7:
                raise ValueError("CNAE deve ter de 2 a 7 dígitos")
        return v or None

    @field_validator("porte")
    @classmethod
    def _porte(cls, v):
        if v and v not in {"00", "01", "03", "05"}:
            raise ValueError("Porte inválido (00, 01, 03, 05)")
        return v or None

    @field_validator("situacao")
    @classmethod
    def _situacao(cls, v):
        if v and v not in {"01", "02", "03", "04", "08"}:
            raise ValueError("Situação inválida (01, 02, 03, 04, 08)")
        return v or None

    @field_validator("icms")
    @classmethod
    def _icms(cls, v):
        if v and v not in ICMS_FILTERS:
            raise ValueError("Filtro de ICMS inválido")
        return v or None

    @field_validator("sort")
    @classmethod
    def _sort(cls, v):
        return v if v in SORTS else "potential"

    @field_validator("lead_state")
    @classmethod
    def _lead_state(cls, v):
        return v if v in LEAD_STATES else "todos"


def apply_natural_language(session: Session, filters: SearchFilters) -> tuple[SearchFilters, dict]:
    """Interpreta `nl` e devolve filtros resultantes + a interpretação (para exibição)."""
    if not filters.nl:
        return filters, {}
    segment_names = list(session.scalars(select(Segment.name)).all())
    # Nomes oficiais de municípios (tabela da Receita); sem ela, os presentes na base
    cities = set(session.scalars(select(Municipio.name)).all()) or set(session.scalars(
        select(Company.municipio).where(Company.municipio.is_not(None)).distinct().limit(6000)
    ).all())
    parsed = query_parser.parse(filters.nl, known_cities=cities, segment_names=segment_names)
    interpreted = parsed.as_filters()
    data = filters.model_dump()
    for key, value in interpreted.items():
        if key == "sort" or not data.get(key):
            data[key] = value
    data["nl"] = None
    return SearchFilters(**data), interpreted


def build_query(filters: SearchFilters) -> Select:
    stmt = select(Company).outerjoin(Lead, Lead.company_id == Company.id)
    conds = []
    if filters.q:
        digits = only_digits(filters.q)
        if len(digits) >= 8 and len(digits) == len(filters.q.replace(".", "").replace("/", "")
                                                    .replace("-", "").strip()):
            conds.append(Company.cnpj.like(f"{digits}%"))
        else:
            for term in norm(filters.q).split():
                if len(term) >= 2:
                    conds.append(Company.search_text.like(f"%{term}%"))
    if filters.region:
        conds.append(Company.region == filters.region)
    if filters.uf:
        conds.append(Company.uf == filters.uf)
    if filters.city:
        conds.append(func.lower(Company.municipio) == filters.city.lower())
    if filters.segment:
        seg = select(Segment.id).where(Segment.name == filters.segment).scalar_subquery()
        conds.append(Company.segment_id == seg)
    if filters.cnae:
        cnae_cond = Company.cnae_principal.like(f"{filters.cnae}%")
        sec_cond = Company.cnaes_secundarios.like(f"%{filters.cnae}%")
        conds.append(or_(cnae_cond, sec_cond) if len(filters.cnae) == 7 else cnae_cond)
    if filters.porte:
        conds.append(Company.porte == filters.porte)
    if filters.situacao:
        conds.append(Company.situacao_cadastral == filters.situacao)
    if filters.icms == "contribuinte":
        conds.append(Company.icms_status.in_(["confirmado_habilitado", "provavel"]))
    elif filters.icms:
        conds.append(Company.icms_status == filters.icms)
    for flag, column in ((filters.has_site, Company.has_website),
                         (filters.has_phone, Company.has_phone),
                         (filters.has_email, Company.has_email)):
        if flag is not None:
            conds.append(column.is_(flag))
    if filters.min_similarity is not None:
        conds.append(Company.similarity >= filters.min_similarity)
    if filters.min_potential is not None:
        conds.append(Company.potential >= filters.min_potential)
    if filters.updated_since:
        conds.append(Company.updated_at >= datetime.combine(filters.updated_since, time.min))
    if not filters.include_customers:
        conds.append(Company.is_customer.is_(False))
    state = filters.lead_state
    if state == "novos":
        conds.append(Lead.id.is_(None))
    elif state == "salvos":
        conds.append(and_(Lead.id.is_not(None), Lead.discarded.is_(False)))
    elif state == "favoritos":
        conds.append(Lead.favorite.is_(True))
    elif state == "analisados":
        conds.append(Lead.analyzed.is_(True))
    elif state == "descartados":
        conds.append(Lead.discarded.is_(True))
    else:
        conds.append(or_(Lead.id.is_(None), Lead.discarded.is_(False)))
    if conds:
        stmt = stmt.where(and_(*conds))
    return stmt


def _order(stmt: Select, sort: str) -> Select:
    if sort == "similarity":
        return stmt.order_by(Company.similarity.desc(), Company.potential.desc(), Company.id)
    if sort == "location":
        return stmt.order_by(Company.uf, Company.municipio, Company.potential.desc(), Company.id)
    if sort == "segment":
        return stmt.outerjoin(Segment, Segment.id == Company.segment_id).order_by(
            Segment.name, Company.potential.desc(), Company.id)
    if sort == "updated":
        return stmt.order_by(Company.updated_at.desc(), Company.id)
    if sort == "completeness":
        return stmt.order_by(Company.completeness.desc(), Company.potential.desc(), Company.id)
    if sort == "name":
        return stmt.order_by(Company.razao_social, Company.id)
    return stmt.order_by(Company.potential.desc(), Company.similarity.desc(), Company.id)


def search(session: Session, filters: SearchFilters) -> dict:
    filters, interpreted = apply_natural_language(session, filters)
    base = build_query(filters)
    total = session.scalar(select(func.count()).select_from(base.with_only_columns(Company.id)
                                                             .subquery()))
    stmt = _order(base, filters.sort).offset((filters.page - 1) * filters.page_size) \
        .limit(filters.page_size)
    items = session.scalars(stmt).unique().all()
    return {
        "items": items,
        "total": total or 0,
        "page": filters.page,
        "page_size": filters.page_size,
        "pages": max(1, -(-(total or 0) // filters.page_size)),
        "filters": filters,
        "interpreted": interpreted,
    }
