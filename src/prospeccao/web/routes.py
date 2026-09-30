"""Páginas HTML (renderizadas no servidor). Ações usam a API JSON via fetch()."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain.cnpj import format_cnpj
from ..domain.fiscal import ICMS_STATUS_LABELS, LEVELS, SINTEGRA_URL, infer_icms
from ..domain.regions import ALL_UFS, REGIONS, UF_NAMES
from ..domain.scoring import (
    DEFAULT_POTENTIAL_WEIGHTS,
    DEFAULT_SIMILARITY_WEIGHTS,
    PORTE_LABELS,
    SITUACAO_LABELS,
)
from ..domain.text import format_cnae, format_phone
from ..models import Cnae, Company, Customer, DataSource, Job, Segment, User, utcnow
from ..security import (
    authenticate,
    client_ip,
    csrf_token,
    current_user,
    login_limiter,
    login_session,
    require_csrf,
)
from ..services import leads as leads_svc
from ..services import settings_store
from ..services.companies import age_label, last_changes
from ..services.dashboard import summary
from ..services.search import ICMS_FILTERS, LEAD_STATES, SORTS, SearchFilters, search
from ..services.sources_status import health

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
templates.env.filters.update(cnpj=format_cnpj, cnae=format_cnae, phone=format_phone)
templates.env.globals.update(
    PORTE_LABELS=PORTE_LABELS, SITUACAO_LABELS=SITUACAO_LABELS, ICMS_LABELS=ICMS_STATUS_LABELS,
    REGIONS=list(REGIONS), UFS=ALL_UFS, UF_NAMES=UF_NAMES, SORTS=SORTS, LEVELS=LEVELS,
)

router = APIRouter(include_in_schema=False)
protected = APIRouter(include_in_schema=False,
                      dependencies=[Depends(current_user), Depends(require_csrf)])


def render(request: Request, name: str, db: Session | None = None, **ctx) -> HTMLResponse:
    mock = False
    if db is not None:
        mock = bool(db.scalar(select(func.count(Company.id)).where(Company.is_mock.is_(True))))
    return templates.TemplateResponse(request, name, {
        "csrf": csrf_token(request), "mock_active": mock,
        "env": request.app.state.settings.env, "path": request.url.path, **ctx,
    })


@router.get("/login")
def login_page(request: Request):
    if request.session.get("uid"):
        return RedirectResponse("/", status.HTTP_303_SEE_OTHER)
    return render(request, "login.html", error=None)


@router.post("/login")
def login(request: Request, username: str = Form(..., max_length=60),
          password: str = Form(..., max_length=200), csrf_token_: str = Form("", alias="csrf_token"),
          db: Session = Depends(get_db)):
    ip = client_ip(request)
    if not request.session.get("csrf") or csrf_token_ != request.session.get("csrf"):
        return render(request, "login.html", error="Sessão expirada. Tente novamente.")
    if login_limiter.blocked(ip):
        resp = render(request, "login.html",
                      error="Muitas tentativas. Aguarde 15 minutos e tente novamente.")
        resp.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        return resp
    user = authenticate(db, username, password)
    if user is None:
        login_limiter.fail(ip)
        resp = render(request, "login.html", error="Usuário ou senha inválidos.")
        resp.status_code = status.HTTP_401_UNAUTHORIZED
        return resp
    login_limiter.reset(ip)
    user.last_login_at = utcnow()
    db.commit()
    login_session(request, user)
    return RedirectResponse("/", status.HTTP_303_SEE_OTHER)


@protected.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status.HTTP_303_SEE_OTHER)


@protected.get("/")
def dashboard_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    return render(request, "dashboard.html", db, d=summary(db), user=user)


@protected.get("/buscar")
def search_page(request: Request, db: Session = Depends(get_db)):
    params = {k: v for k, v in request.query_params.items() if v != ""}
    for flag in ("has_site", "has_phone", "has_email"):
        if params.get(flag) not in (None, "true", "false"):
            params.pop(flag)
    if "situacao" not in request.query_params:
        params["situacao"] = "02"
    error, result = None, None
    try:
        filters = SearchFilters(**params)
        result = search(db, filters)
    except ValidationError as exc:
        error = "; ".join(e["msg"].replace("Value error, ", "") for e in exc.errors())
        filters = SearchFilters()
    segments = db.scalars(select(Segment).where(Segment.active.is_(True))
                          .order_by(Segment.name)).all()
    return render(request, "search.html", db, r=result, f=result["filters"] if result else filters,
                  error=error, segments=segments, statuses=leads_svc.statuses(db),
                  icms_filters=sorted(ICMS_FILTERS), lead_states=sorted(LEAD_STATES),
                  query=dict(request.query_params))


@protected.get("/empresas/{company_id}")
def company_page(company_id: int, request: Request, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada")
    cnae_codes = [company.cnae_principal, *company.secondary_cnaes]
    cnae_desc = dict(db.execute(select(Cnae.code, Cnae.description)
                                .where(Cnae.code.in_([c for c in cnae_codes if c]))).all())
    siblings = db.scalars(select(Company).where(Company.cnpj_basico == company.cnpj_basico,
                                                Company.id != company.id).limit(20)).all()
    icms_inference = None
    if company.icms_status in ("provavel", "nao_verificado"):
        icms_inference = infer_icms(company.cnae_principal, company.secondary_cnaes)
    return render(
        request, "company.html", db, c=company, cnae_desc=cnae_desc, siblings=siblings,
        changes=last_changes(db, company.id), statuses=leads_svc.statuses(db),
        segments=db.scalars(select(Segment).order_by(Segment.name)).all(),
        icms_inference=icms_inference, sintegra_url=SINTEGRA_URL, age=age_label(company.data_abertura),
        sefaz_enabled=request.app.state.sources.sefaz().is_enabled(),
    )


@protected.get("/leads")
def leads_page(request: Request, db: Session = Depends(get_db), status_id: int | None = None,
               view: str = "ativos", page: int = 1):
    page = max(1, min(page, 10_000))
    kwargs = {"status_id": status_id, "page": page, "page_size": 25}
    if view == "favoritos":
        kwargs["favorite"] = True
    elif view == "analisados":
        kwargs["analyzed"] = True
    elif view == "descartados":
        kwargs["discarded"] = True
    result = leads_svc.list_leads(db, **kwargs)
    return render(request, "leads.html", db, r=result, statuses=leads_svc.statuses(db),
                  view=view, status_id=status_id)


CUSTOMER_STATUS_LABELS = {"ok": "vinculado", "sem_cnpj": "só nome (sem CNPJ)",
                          "ambiguo": "nome ambíguo", "nao_encontrado": "CNPJ fora da base"}
CUSTOMER_METHOD_LABELS = {"nome_exato": "vinculado pelo nome (base local)",
                          "nome_prefixo": "vinculado pelo início do nome (base local)",
                          "nome_receita": "vinculado pelo nome (dados da Receita)",
                          "manual": "CNPJ informado por você"}


@protected.get("/clientes")
def customers_page(request: Request, db: Session = Depends(get_db), page: int = 1,
                   status_filter: str | None = Query(None, alias="status")):
    page = max(1, min(page, 10_000))
    base = select(Customer)
    if status_filter in CUSTOMER_STATUS_LABELS:
        base = base.where(Customer.status == status_filter)
    else:
        status_filter = None
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Customer.id).offset((page - 1) * 50).limit(50)).all()
    by_status = dict(db.execute(select(Customer.status, func.count(Customer.id))
                                .group_by(Customer.status)).all())
    last_import = db.scalar(select(Job).where(Job.kind == "import_customers")
                            .order_by(Job.id.desc()).limit(1))
    return render(request, "customers.html", db, customers=rows, total=total, page=page,
                  pages=max(1, -(-total // 50)), by_status=by_status,
                  profile=settings_store.get(db, "customer_profile"),
                  profile_at=settings_store.get(db, "customer_profile_built_at"),
                  last_import=last_import, status_filter=status_filter,
                  STATUS_LABELS=CUSTOMER_STATUS_LABELS, METHOD_LABELS=CUSTOMER_METHOD_LABELS)


@protected.get("/configuracoes")
def settings_page(request: Request, db: Session = Depends(get_db)):
    return render(request, "settings.html", db,
                  sim=settings_store.similarity_weights(db),
                  pot=settings_store.potential_weights(db),
                  affinity=settings_store.segment_affinity(db),
                  sim_keys=list(DEFAULT_SIMILARITY_WEIGHTS), pot_keys=list(DEFAULT_POTENTIAL_WEIGHTS),
                  segments=db.scalars(select(Segment).order_by(Segment.name)).all(),
                  statuses=leads_svc.statuses(db))


@protected.get("/administracao")
def admin_page(request: Request, db: Session = Depends(get_db)):
    sources = []
    for src in db.scalars(select(DataSource).order_by(DataSource.id)).all():
        level, msg = health(src)
        sources.append((src, level, msg))
    s = request.app.state.sources
    checks = {"sefaz_icms": s.sefaz().check().message, "website": s.website().check().message}
    jobs = db.scalars(select(Job).order_by(Job.id.desc()).limit(20)).all()
    dup = db.execute(
        select(Company.cnpj_basico, func.count(Company.id)).where(Company.is_matriz.is_(True))
        .group_by(Company.cnpj_basico).having(func.count(Company.id) > 1).limit(20)
    ).all()
    stale = db.scalar(select(func.count(Company.id)).where(
        Company.source_updated_at < utcnow().replace(year=utcnow().year - 1))) or 0
    return render(request, "admin.html", db, sources=sources, checks=checks, jobs=jobs,
                  duplicates=dup, stale=stale, settings=request.app.state.settings)


@protected.get("/metodologia")
def methodology_page(request: Request, db: Session = Depends(get_db)):
    return render(request, "methodology.html", db,
                  sim=settings_store.similarity_weights(db),
                  pot=settings_store.potential_weights(db),
                  affinity=settings_store.segment_affinity(db),
                  segments=db.scalars(select(Segment).order_by(Segment.name)).all())
