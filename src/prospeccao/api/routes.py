"""API REST (JSON). Documentação interativa em /api/docs (requer login)."""
from __future__ import annotations

import uuid
from datetime import date
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain import cnpj as cnpj_mod
from ..domain.scoring import DEFAULT_POTENTIAL_WEIGHTS, DEFAULT_SIMILARITY_WEIGHTS
from ..domain.segments import SegmentRule
from ..models import Company, CompanyContact, Customer, FiscalInfo, Job, LeadStatus, Segment
from ..security import current_user, require_csrf
from ..services import leads as leads_svc
from ..services import settings_store
from ..services.companies import ScoringContext, refresh_flags, score_company
from ..services.customer_import import MAX_BYTES
from ..services.dashboard import summary
from ..services.enrichment import lookup_cnpj
from ..services.search import SearchFilters, search
from ..services.sources_status import health
from ..services.tasks import (
    task_enrich_websites,
    task_icms,
    task_import_customers,
    task_import_receita,
    task_lookup_customers,
    task_rescore,
)
from ..sources.base import SourceError
from ..sources.cnpj_api import CnpjNotFound
from ..sources.website import normalize_url
from . import serializers as ser

router = APIRouter(prefix="/api", dependencies=[Depends(current_user), Depends(require_csrf)])


def _runner(request: Request):
    return request.app.state.runner


def _sources(request: Request):
    return request.app.state.sources


def _company_or_404(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")
    return company


def _page(result: dict, items: list) -> dict:
    return {"items": items, "total": result["total"], "page": result["page"],
            "page_size": result["page_size"], "pages": result["pages"]}


# ---------------------------------------------------------------- empresas / busca


@router.get("/companies", summary="Lista empresas com filtros (query string)")
def list_companies(filters: Annotated[SearchFilters, Query()], db: Session = Depends(get_db)):
    result = search(db, filters)
    return {**_page(result, [ser.company_brief(c) for c in result["items"]]),
            "interpretacao": result["interpreted"]}


@router.post("/companies/search", summary="Pesquisa com filtros no corpo (JSON)")
def search_companies(filters: SearchFilters, db: Session = Depends(get_db)):
    return list_companies(filters, db)


@router.get("/companies/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db)):
    return ser.company_full(_company_or_404(db, company_id))


class LookupIn(BaseModel):
    cnpj: str = Field(..., max_length=20)
    force: bool = False


@router.post("/companies/lookup", summary="Consulta um CNPJ na fonte pública (com cache de 30 dias)")
def lookup(body: LookupIn, request: Request, db: Session = Depends(get_db)):
    if not cnpj_mod.is_valid(body.cnpj):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "CNPJ inválido")
    try:
        company, fetched = lookup_cnpj(db, _sources(request).cnpj_api(), body.cnpj, body.force)
    except CnpjNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CNPJ não encontrado na fonte consultada")
    except SourceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Fonte indisponível: {exc}")
    return {"consultou_fonte": fetched, "empresa": ser.company_full(company)}


class CompanyPatch(BaseModel):
    website: str | None = Field(None, max_length=255)
    segment_id: int | None = None
    clear_manual_segment: bool = False


@router.patch("/companies/{company_id}", summary="Correções manuais (site, segmento)")
def patch_company(company_id: int, body: CompanyPatch, db: Session = Depends(get_db)):
    company = _company_or_404(db, company_id)
    if body.website is not None:
        if body.website == "":
            company.website, company.website_status = None, None
        else:
            url = normalize_url(body.website)
            if not url:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "URL inválida")
            company.website, company.website_status = url, "manual"
    if body.segment_id is not None:
        if db.get(Segment, body.segment_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Segmento inexistente")
        company.segment_id = body.segment_id
        company.segment_method = "manual"
        company.segment_confidence = 1.0
        company.segment_explanation = "Definido manualmente pelo usuário"
    if body.clear_manual_segment:
        company.segment_method = None
    score_company(company, ScoringContext.load(db))
    db.commit()
    db.refresh(company)
    return ser.company_full(company)


@router.post("/companies/{company_id}/save", status_code=status.HTTP_201_CREATED,
             summary="Salva a empresa como lead")
def save_lead(company_id: int, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    lead = leads_svc.get_or_create(db, company_id)
    db.commit()
    return ser.lead_full(lead)


@router.post("/companies/{company_id}/enrich", status_code=status.HTTP_202_ACCEPTED,
             summary="Enriquecimento pelo site oficial (background)")
def enrich(company_id: int, request: Request, db: Session = Depends(get_db)):
    company = _company_or_404(db, company_id)
    if company.is_mock:
        raise HTTPException(status.HTTP_409_CONFLICT, "Empresa MOCK não é enriquecida em fontes reais")
    job = _runner(request).submit(db, "enrich_websites", {"company_ids": [company_id]},
                                  partial(task_enrich_websites, sources=_sources(request)))
    return ser.job(job)


@router.post("/companies/{company_id}/icms", status_code=status.HTTP_202_ACCEPTED,
             summary="Consulta oficial de ICMS na SEFAZ (background)")
def icms(company_id: int, request: Request, db: Session = Depends(get_db)):
    _company_or_404(db, company_id)
    if not _sources(request).sefaz().is_enabled():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Consulta SEFAZ não configurada (requer certificado digital e endpoints)")
    job = _runner(request).submit(db, "icms", {"company_ids": [company_id]},
                                  partial(task_icms, sources=_sources(request)))
    return ser.job(job)


class FiscalIn(BaseModel):
    category: Literal["beneficio", "regime_especial", "inscricao_estadual", "icms",
                      "regime_apuracao", "outro"]
    label: str = Field(..., min_length=2, max_length=200)
    value: str | None = Field(None, max_length=2000)
    level: Literal["confirmado", "provavel", "possivel"]
    source: str = Field(..., min_length=2, max_length=120, description="Fonte obrigatória")
    source_url: str | None = Field(None, max_length=500)
    data_date: date | None = None
    confidence: float = Field(..., ge=0, le=1)
    notes: str | None = Field(None, max_length=2000)

    @field_validator("source_url")
    @classmethod
    def _url(cls, v):
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("URL deve começar com http:// ou https://")
        return v or None


@router.post("/companies/{company_id}/fiscal", status_code=status.HTTP_201_CREATED,
             summary="Registra informação/benefício fiscal com fonte")
def add_fiscal(company_id: int, body: FiscalIn, db: Session = Depends(get_db)):
    company = _company_or_404(db, company_id)
    if body.level == "confirmado" and not body.source_url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Informação 'confirmada' exige URL ou referência da fonte oficial")
    info = FiscalInfo(company_id=company.id, created_by="usuario", **body.model_dump())
    db.add(info)
    db.commit()
    return ser.fiscal(info)


@router.delete("/fiscal/{info_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fiscal(info_id: int, db: Session = Depends(get_db)):
    info = db.get(FiscalInfo, info_id)
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro não encontrado")
    if info.created_by != "usuario":
        raise HTTPException(status.HTTP_409_CONFLICT, "Somente registros manuais podem ser excluídos")
    db.delete(info)
    db.commit()


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Exclui um contato (ex.: solicitação de titular — LGPD)")
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.get(CompanyContact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contato não encontrado")
    company = contact.company
    company.contacts.remove(contact)
    refresh_flags(company)
    db.commit()


# ---------------------------------------------------------------- leads


@router.get("/leads")
def get_leads(status_id: int | None = None, favorite: bool | None = None,
              analyzed: bool | None = None, discarded: bool = False,
              page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
              db: Session = Depends(get_db)):
    result = leads_svc.list_leads(db, status_id=status_id, favorite=favorite, analyzed=analyzed,
                                  discarded=discarded, page=page, page_size=page_size)
    return _page(result, [ser.lead_full(x) for x in result["items"]])


class LeadPatch(BaseModel):
    status_id: int | None = None
    favorite: bool | None = None
    analyzed: bool | None = None
    discarded: bool | None = None


@router.patch("/leads/{lead_id}")
def patch_lead(lead_id: int, body: LeadPatch, db: Session = Depends(get_db)):
    try:
        lead = leads_svc.update(db, lead_id, **body.model_dump())
    except leads_svc.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    db.commit()
    db.refresh(lead)
    return ser.lead_full(lead)


class NoteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


@router.post("/leads/{lead_id}/notes", status_code=status.HTTP_201_CREATED)
def add_note(lead_id: int, body: NoteIn, db: Session = Depends(get_db)):
    try:
        note = leads_svc.add_note(db, lead_id, body.text)
    except leads_svc.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    db.commit()
    return ser.note(note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    try:
        leads_svc.delete_note(db, note_id)
    except leads_svc.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    db.commit()


@router.get("/lead-statuses")
def get_statuses(db: Session = Depends(get_db)):
    return [{"id": s.id, "nome": s.name, "posicao": s.position, "final": s.is_final}
            for s in leads_svc.statuses(db)]


class StatusIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    position: int = Field(0, ge=0, le=1000)
    is_final: bool = False


@router.post("/lead-statuses", status_code=status.HTTP_201_CREATED)
def create_status(body: StatusIn, db: Session = Depends(get_db)):
    if db.scalar(select(LeadStatus).where(LeadStatus.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Status já existe")
    s = LeadStatus(name=body.name, position=body.position, is_final=body.is_final)
    db.add(s)
    db.commit()
    return {"id": s.id, "nome": s.name, "posicao": s.position, "final": s.is_final}


@router.patch("/lead-statuses/{status_id}")
def update_status(status_id: int, body: StatusIn, db: Session = Depends(get_db)):
    s = db.get(LeadStatus, status_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Status não encontrado")
    s.name, s.position, s.is_final = body.name, body.position, body.is_final
    db.commit()
    return {"id": s.id, "nome": s.name, "posicao": s.position, "final": s.is_final}


# ---------------------------------------------------------------- clientes / perfil


@router.post("/customers/import", status_code=status.HTTP_202_ACCEPTED,
             summary="Importa a base de clientes (CSV/XLSX) em background")
async def import_customers(request: Request, file: UploadFile = File(...),
                           db: Session = Depends(get_db)):
    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".txt", ".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Envie um arquivo .csv ou .xlsx")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Arquivo maior que 20 MB")
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Arquivo vazio")
    upload_dir = request.app.state.settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid.uuid4().hex}{'.xlsx' if name.endswith(('.xlsx', '.xlsm')) else '.csv'}"
    path.write_bytes(content)
    job = _runner(request).submit(db, "import_customers",
                                  {"path": str(path), "filename": file.filename},
                                  task_import_customers)
    return ser.job(job)


@router.get("/customers")
def list_customers(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                   status_filter: str | None = Query(None, alias="status"),
                   db: Session = Depends(get_db)):
    stmt = select(Customer)
    if status_filter:
        stmt = stmt.where(Customer.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Customer.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": c.id, "cnpj": c.cnpj, "razao_social": c.razao_social, "uf": c.uf,
                       "municipio": c.municipio, "cnae": c.cnae, "segmento_informado":
                       c.segmento_informado, "status": c.status, "company_id": c.company_id,
                       "vinculo": c.match_method, "observacao": c.match_note}
                      for c in rows],
            "total": total, "page": page, "page_size": page_size,
            "pages": max(1, -(-total // page_size))}


class CustomerPatch(BaseModel):
    cnpj: str = Field(..., max_length=20)


@router.patch("/customers/{customer_id}", summary="Informa/corrige o CNPJ de um cliente")
def patch_customer(customer_id: int, body: CustomerPatch, request: Request,
                   db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado")
    if not cnpj_mod.is_valid(body.cnpj):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "CNPJ inválido")
    cnpj = cnpj_mod.clean(body.cnpj)
    other = db.scalar(select(Customer).where(Customer.cnpj == cnpj, Customer.id != customer.id))
    if other is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Este CNPJ já pertence ao cliente '{other.razao_social or other.id}'")
    customer.cnpj = cnpj
    company = db.scalar(select(Company).where(Company.cnpj == cnpj))
    customer.company_id = company.id if company else None
    customer.status = "ok" if company else "nao_encontrado"
    customer.match_method = "manual"
    customer.match_note = None if company else "CNPJ informado; empresa ainda não está na base local"
    db.commit()
    job = _runner(request).submit(db, "rescore", {}, task_rescore)
    return {"id": customer.id, "cnpj": customer.cnpj, "status": customer.status,
            "company_id": customer.company_id, "job": ser.job(job)}


@router.get("/profile", summary="Perfil de cliente ideal calculado")
def get_profile(db: Session = Depends(get_db)):
    return {"perfil": settings_store.get(db, "customer_profile"),
            "calculado_em": settings_store.get(db, "customer_profile_built_at")}


# ---------------------------------------------------------------- configuração


class WeightsIn(BaseModel):
    similarity: dict[str, float] = Field(default_factory=dict)
    potential: dict[str, float] = Field(default_factory=dict)
    segment_affinity: dict[str, float] = Field(default_factory=dict)

    @field_validator("similarity", "potential", "segment_affinity")
    @classmethod
    def _range(cls, v):
        for k, x in v.items():
            if not 0 <= x <= 1:
                raise ValueError(f"Valor de {k} deve estar entre 0 e 1")
        return v


@router.get("/settings/weights")
def get_weights(db: Session = Depends(get_db)):
    return {"similarity": settings_store.similarity_weights(db),
            "potential": settings_store.potential_weights(db),
            "segment_affinity": settings_store.segment_affinity(db)}


@router.put("/settings/weights")
def put_weights(body: WeightsIn, request: Request, db: Session = Depends(get_db)):
    unknown = (set(body.similarity) - set(DEFAULT_SIMILARITY_WEIGHTS)) | \
        (set(body.potential) - set(DEFAULT_POTENTIAL_WEIGHTS))
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Critérios desconhecidos: {', '.join(sorted(unknown))}")
    if body.similarity:
        settings_store.put(db, "similarity_weights", body.similarity)
    if body.potential:
        settings_store.put(db, "potential_weights", body.potential)
    if body.segment_affinity:
        settings_store.put(db, "segment_affinity", body.segment_affinity)
    db.commit()
    job = _runner(request).submit(db, "rescore", {}, task_rescore)
    return {**get_weights(db), "job": ser.job(job)}


class SegmentIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    description: str | None = Field(None, max_length=500)
    cnae_prefixes: str = Field("", max_length=2000)
    keywords: str = Field("", max_length=2000)
    active: bool = True

    @field_validator("cnae_prefixes")
    @classmethod
    def _prefixes(cls, v):
        parts = [p.strip() for p in v.split(",") if p.strip()]
        for p in parts:
            if not p.isdigit() or not 2 <= len(p) <= 7:
                raise ValueError(f"Prefixo CNAE inválido: {p}")
        return ",".join(parts)


def _segment_out(s: Segment) -> dict:
    return {"id": s.id, "nome": s.name, "descricao": s.description,
            "cnae_prefixes": s.cnae_prefixes, "palavras_chave": s.keywords, "ativo": s.active,
            "fallback": s.is_fallback}


@router.get("/segments")
def get_segments(db: Session = Depends(get_db)):
    return [_segment_out(s) for s in db.scalars(select(Segment).order_by(Segment.name)).all()]


@router.post("/segments", status_code=status.HTTP_201_CREATED)
def create_segment(body: SegmentIn, request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(Segment).where(Segment.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Segmento já existe")
    seg = Segment(**body.model_dump())
    db.add(seg)
    db.commit()
    _runner(request).submit(db, "rescore", {}, task_rescore)
    return _segment_out(seg)


@router.patch("/segments/{segment_id}")
def update_segment(segment_id: int, body: SegmentIn, request: Request, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if seg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Segmento não encontrado")
    SegmentRule.from_strings(seg.id, body.name, body.cnae_prefixes, body.keywords)  # valida
    for k, v in body.model_dump().items():
        setattr(seg, k, v)
    db.commit()
    _runner(request).submit(db, "rescore", {}, task_rescore)
    return _segment_out(seg)


# ---------------------------------------------------------------- dashboard / admin


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    d = summary(db)
    return {
        "total_empresas": d["total_companies"], "prospects_ativos": d["active_prospects"],
        "novos_30_dias": d["new_last_30d"], "leads_salvos": d["saved_leads"],
        "clientes": d["customers"], "clientes_vinculados": d["customers_linked"],
        "empresas_mock": d["mock_companies"],
        "por_regiao": d["by_region"], "por_uf": d["by_uf"], "por_segmento": d["by_segment"],
        "maior_compatibilidade": [ser.company_brief(c) for c in d["top_similarity"]],
        "atualizadas_recentemente": [ser.company_brief(c) for c in d["recently_updated"]],
        "fontes": [{"chave": s["source"].key, "nome": s["source"].name, "nivel": s["level"],
                    "mensagem": s["message"]} for s in d["sources"]],
    }


@router.get("/sources")
def get_sources(request: Request, db: Session = Depends(get_db)):
    from ..models import DataSource

    out = []
    for src in db.scalars(select(DataSource).order_by(DataSource.id)).all():
        level, msg = health(src)
        out.append({"chave": src.key, "nome": src.name, "tipo": src.kind, "ativa": src.enabled,
                    "nivel": level, "mensagem": msg, "ultimo_sucesso": ser._dt(src.last_success_at),
                    "ultimo_erro_em": ser._dt(src.last_error_at), "ultimo_erro": src.last_error,
                    "falhas_consecutivas": src.consecutive_failures,
                    "referencia": src.last_reference, "registros_ultima_execucao":
                    src.records_last_run})
    return out


@router.get("/jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return [ser.job(j) for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(limit)).all()]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Processo não encontrado")
    db.refresh(job)
    return ser.job(job)


class ReceitaIn(BaseModel):
    download: bool = False
    month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")


@router.post("/admin/rescore", status_code=status.HTTP_202_ACCEPTED)
def admin_rescore(request: Request, db: Session = Depends(get_db)):
    return ser.job(_runner(request).submit(db, "rescore", {}, task_rescore))


@router.post("/admin/receita-import", status_code=status.HTTP_202_ACCEPTED,
             summary="Importa arquivos da Receita (pasta local ou download do mês)")
def admin_receita(body: ReceitaIn, request: Request, db: Session = Depends(get_db)):
    params = body.model_dump()
    return ser.job(_runner(request).submit(db, "import_receita", params,
                                           partial(task_import_receita, sources=_sources(request))))


@router.post("/admin/lookup-customers", status_code=status.HTTP_202_ACCEPTED,
             summary="Consulta na API pública clientes sem correspondência local")
def admin_lookup_customers(request: Request, db: Session = Depends(get_db)):
    return ser.job(_runner(request).submit(db, "lookup_customers", {"limit": 200},
                                           partial(task_lookup_customers, sources=_sources(request))))


class EnrichIn(BaseModel):
    limit: int = Field(50, ge=1, le=500)


@router.post("/admin/enrich", status_code=status.HTTP_202_ACCEPTED,
             summary="Enriquece pelo site os leads de maior potencial ainda não enriquecidos")
def admin_enrich(body: EnrichIn, request: Request, db: Session = Depends(get_db)):
    return ser.job(_runner(request).submit(db, "enrich_websites", {"limit": body.limit},
                                           partial(task_enrich_websites, sources=_sources(request))))
