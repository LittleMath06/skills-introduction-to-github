"""Testes funcionais e negativos da API, autenticação e segurança."""
from __future__ import annotations

from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from prospeccao.config import load_settings
from prospeccao.models import Company, FiscalInfo
from prospeccao.security import hash_password, verify_password
from prospeccao.services.mock_seed import clear_mock, seed_mock

from .conftest import PASSWORD, csrf_of, login, make_cnpj
from .test_sources import BRASILAPI_SAMPLE, RET_OK, _site_handler


@pytest.fixture
def seeded(client, db, settings):
    seed_mock(db, settings, n_companies=120, n_customers=15)
    return client


# ---------------------------------------------------------------- autenticação


def test_pages_and_api_require_login(app):
    with TestClient(app) as c:
        assert c.get("/", follow_redirects=False).headers["location"] == "/login"
        assert c.get("/buscar", follow_redirects=False).status_code == 303
        for method, url in [("GET", "/api/companies"), ("GET", "/api/dashboard"),
                            ("POST", "/api/companies/1/save"), ("PATCH", "/api/leads/1"),
                            ("GET", "/api/openapi.json"), ("GET", "/api/docs"),
                            ("POST", "/api/customers/import"), ("POST", "/api/admin/rescore")]:
            assert c.request(method, url).status_code == 401, url
        assert c.get("/health").json()["status"] == "ok"


def test_every_api_route_is_protected(app):
    """Nenhum endpoint /api pode ser acessado sem sessão (varre todas as rotas registradas)."""
    with TestClient(app) as c:
        for route in app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api"):
                continue
            url = path.replace("{company_id}", "1").replace("{lead_id}", "1") \
                .replace("{note_id}", "1").replace("{info_id}", "1").replace("{job_id}", "1") \
                .replace("{segment_id}", "1").replace("{status_id}", "1") \
                .replace("{contact_id}", "1").replace("{customer_id}", "1")
            for method in route.methods - {"HEAD", "OPTIONS"}:
                assert c.request(method, url).status_code == 401, f"{method} {path}"


def test_login_wrong_password_and_rate_limit(app):
    with TestClient(app) as c:
        assert login(c, password="errada").status_code == 401
        assert login(c, username="naoexiste").status_code == 401
        for _ in range(3):
            login(c, password="errada")
        blocked = login(c)  # mesmo com a senha certa, bloqueado após 5 falhas
        assert blocked.status_code == 429


def test_login_requires_csrf(app):
    with TestClient(app) as c:
        c.get("/login")
        r = c.post("/login", data={"username": "paulo", "password": PASSWORD, "csrf_token": "x"},
                   follow_redirects=False)
        assert r.status_code == 200 and "Sessão expirada" in r.text


def test_logout(client):
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/api/dashboard").status_code == 401


def test_csrf_required_for_mutations(client):
    token = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/admin/rescore").status_code == 403
    assert client.post("/api/admin/rescore", headers={"X-CSRF-Token": "errado"}).status_code == 403
    assert client.post("/api/admin/rescore", headers={"X-CSRF-Token": token}).status_code == 202


def test_security_headers_and_cookie(app):
    with TestClient(app) as c:
        r = login(c)
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        page = c.get("/")
        assert "default-src 'self'" in page.headers["content-security-policy"]
        assert page.headers["x-frame-options"] == "DENY"
        assert page.headers["cache-control"] == "no-store"


def test_password_hashing():
    h = hash_password("uma-senha-longa")
    assert h.startswith("scrypt$") and "uma-senha-longa" not in h
    assert verify_password("uma-senha-longa", h) and not verify_password("outra", h)
    assert hash_password("uma-senha-longa") != h  # salt aleatório
    assert not verify_password("x", "formato$invalido")
    with pytest.raises(ValueError):
        hash_password("curta")


def test_production_refuses_insecure_config(monkeypatch, tmp_path):
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_settings()
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("ALLOW_MOCK_DATA", "true")
    with pytest.raises(RuntimeError, match="MOCK"):
        load_settings()
    monkeypatch.setenv("ALLOW_MOCK_DATA", "false")
    assert load_settings().is_production


def test_mock_seed_blocked_when_disabled(db, settings):
    with pytest.raises(PermissionError):
        seed_mock(db, replace(settings, allow_mock_data=False))


# ---------------------------------------------------------------- busca


def test_search_filters_pagination_and_sort(seeded):
    r = seeded.get("/api/companies?page_size=10&sort=similarity").json()
    assert r["total"] > 10 and len(r["items"]) == 10 and r["pages"] == -(-r["total"] // 10)
    sims = [i["compatibilidade"] for i in r["items"]]
    assert sims == sorted(sims, reverse=True)
    assert all(i["situacao"] == "Ativa" and not i["cliente_atual"] for i in r["items"])
    assert all(i["mock"] for i in r["items"])

    sp = seeded.get("/api/companies?uf=SP&page_size=100").json()["items"]
    assert sp and all(i["uf"] == "SP" for i in sp)
    reg = seeded.get("/api/companies?region=Sul&page_size=100").json()["items"]
    assert all(i["uf"] in {"PR", "SC", "RS"} for i in reg)
    hi = seeded.get("/api/companies?min_similarity=70&page_size=100").json()["items"]
    assert all(i["compatibilidade"] >= 70 for i in hi)
    inst = seeded.get("/api/companies?segment=Instaladores&cnae=4321&has_phone=true").json()["items"]
    assert all(i["segmento"] == "Instaladores" and i["tem_telefone"] for i in inst)
    allsit = seeded.get("/api/companies?situacao=&page_size=100").json()
    assert allsit["total"] >= r["total"]
    body = seeded.post("/api/companies/search", json={"uf": "MG", "page_size": 5}).json()
    assert all(i["uf"] == "MG" for i in body["items"])


def test_search_natural_language(seeded):
    r = seeded.get("/api/companies", params={"nl": "instaladores em São Paulo"}).json()
    assert r["interpretacao"] == {"segment": "Instaladores", "uf": "SP"}
    assert all(i["uf"] == "SP" and i["segmento"] == "Instaladores" for i in r["items"])
    r = seeded.get("/api/companies", params={"nl": "semelhantes aos meus clientes"}).json()
    assert all(i["compatibilidade"] >= 50 for i in r["items"])


def test_search_by_cnpj_and_text(seeded, db):
    company = db.scalar(select(Company).where(Company.is_customer.is_(False),
                                              Company.situacao_cadastral == "02"))
    r = seeded.get("/api/companies", params={"q": company.cnpj}).json()
    assert [i["id"] for i in r["items"]] == [company.id]
    word = company.razao_social.split()[1].lower()
    assert seeded.get("/api/companies", params={"q": word}).json()["total"] >= 1


@pytest.mark.parametrize("query", ["uf=XX", "region=Marte", "cnae=1", "porte=09", "situacao=99",
                                   "page=0", "page_size=500", "min_similarity=101", "icms=talvez"])
def test_search_invalid_filters(client, query):
    r = client.get("/api/companies?" + query)
    assert r.status_code == 422 and r.json()["erros"]


def test_search_page_shows_friendly_error(client):
    r = client.get("/buscar?uf=XX")
    assert r.status_code == 200 and "Filtro inválido" in r.text


# ---------------------------------------------------------------- empresa e leads


def test_company_detail_and_404(seeded, db):
    cid = db.scalar(select(Company.id))
    d = seeded.get(f"/api/companies/{cid}").json()
    assert d["compatibilidade_detalhes"]["criteria"] and d["potencial_detalhes"]
    assert seeded.get("/api/companies/999999").status_code == 404
    assert seeded.get(f"/empresas/{cid}").status_code == 200
    page404 = seeded.get("/empresas/999999")
    assert page404.status_code == 404 and "não encontrada" in page404.text.lower()


def test_lead_lifecycle(seeded, db):
    cid = db.scalar(select(Company.id).where(Company.is_customer.is_(False),
                                             Company.situacao_cadastral == "02"))
    lead = seeded.post(f"/api/companies/{cid}/save").json()
    assert lead["status"] == "Novo"
    again = seeded.post(f"/api/companies/{cid}/save").json()
    assert again["id"] == lead["id"]  # não duplica
    statuses = {s["nome"]: s["id"] for s in seeded.get("/api/lead-statuses").json()}
    r = seeded.patch(f"/api/leads/{lead['id']}", json={"status_id": statuses["Em negociação"],
                                                       "favorite": True, "analyzed": True})
    assert r.json()["status"] == "Em negociação" and r.json()["favorite"]
    assert seeded.patch(f"/api/leads/{lead['id']}", json={"status_id": 9999}).status_code == 422
    assert seeded.patch("/api/leads/9999", json={"favorite": True}).status_code == 404
    note = seeded.post(f"/api/leads/{lead['id']}/notes", json={"text": "Ligar segunda"}).json()
    assert seeded.post(f"/api/leads/{lead['id']}/notes", json={"text": ""}).status_code == 422
    assert seeded.post(f"/api/leads/{lead['id']}/notes", json={"text": "x" * 5001}).status_code == 422
    listing = seeded.get("/api/leads?favorite=true").json()
    assert listing["total"] == 1 and listing["items"][0]["observacoes"][0]["texto"] == "Ligar segunda"
    assert seeded.delete(f"/api/notes/{note['id']}").status_code == 204
    assert seeded.delete(f"/api/notes/{note['id']}").status_code == 404
    # nas buscas: aparece como salvo
    saved = seeded.get("/api/companies?lead_state=salvos").json()["items"]
    assert [i["id"] for i in saved] == [cid]
    # descartar tira da busca padrão
    seeded.patch(f"/api/leads/{lead['id']}", json={"discarded": True})
    ids = [i["id"] for i in seeded.get("/api/companies?page_size=100&situacao=").json()["items"]]
    assert cid not in ids
    assert seeded.get("/api/companies?lead_state=descartados").json()["items"][0]["id"] == cid
    for page in ("/leads", "/leads?view=descartados", "/leads?view=favoritos"):
        assert seeded.get(page).status_code == 200


def test_manual_segment_and_website(seeded, db):
    cid = db.scalar(select(Company.id))
    segs = {s["nome"]: s["id"] for s in seeded.get("/api/segments").json()}
    d = seeded.patch(f"/api/companies/{cid}", json={"segment_id": segs["Energia"]}).json()
    assert d["segmento"] == "Energia" and d["segmento_estimado"] is False
    seeded.post("/api/admin/rescore")
    assert seeded.get(f"/api/companies/{cid}").json()["segmento"] == "Energia"  # manual preservado
    assert seeded.patch(f"/api/companies/{cid}", json={"segment_id": 9999}).status_code == 422
    d = seeded.patch(f"/api/companies/{cid}", json={"website": "empresa.com.br"}).json()
    assert d["site"] == "https://empresa.com.br/" and d["site_status"] == "manual"
    assert seeded.patch(f"/api/companies/{cid}", json={"website": "invalido"}).status_code == 422


def test_fiscal_info_requires_source(seeded, db):
    cid = db.scalar(select(Company.id))
    base = {"category": "beneficio", "label": "Redução de base de cálculo", "level": "possivel",
            "source": "Hipótese do usuário", "confidence": 0.3}
    assert seeded.post(f"/api/companies/{cid}/fiscal", json={**base, "source": ""}).status_code == 422
    r = seeded.post(f"/api/companies/{cid}/fiscal", json={**base, "level": "confirmado"})
    assert r.status_code == 422 and "URL" in r.json()["detail"]
    assert seeded.post(f"/api/companies/{cid}/fiscal",
                       json={**base, "source_url": "javascript:alert(1)"}).status_code == 422
    assert seeded.post(f"/api/companies/{cid}/fiscal", json={**base, "confidence": 2}).status_code == 422
    ok = seeded.post(f"/api/companies/{cid}/fiscal", json={
        **base, "level": "confirmado", "source_url": "https://portal.sefaz.test/ato"}).json()
    assert ok["nivel"] == "confirmado" and ok["criado_por"] == "usuario"
    # registros do sistema não podem ser apagados pela API
    sys_info = FiscalInfo(company_id=cid, category="icms", label="x", level="confirmado",
                          source="SEFAZ-SP", confidence=1)
    db.add(sys_info)
    db.commit()
    assert seeded.delete(f"/api/fiscal/{sys_info.id}").status_code == 409
    assert seeded.delete(f"/api/fiscal/{ok['id']}").status_code == 204


def test_weights_segments_and_statuses_config(seeded):
    r = seeded.put("/api/settings/weights", json={"similarity": {"cnae": 1, "segmento": 1,
                                                                  "palavras": 0, "localizacao": 0,
                                                                  "porte": 0}})
    assert r.status_code == 200 and r.json()["similarity"]["cnae"] == 0.5
    assert r.json()["job"]["status"] == "done"
    assert seeded.put("/api/settings/weights", json={"similarity": {"cnae": 5}}).status_code == 422
    assert seeded.put("/api/settings/weights", json={"similarity": {"xpto": 1}}).status_code == 422
    new = seeded.post("/api/segments", json={"name": "Mineração", "cnae_prefixes": "07,08",
                                             "keywords": "mineracao"})
    assert new.status_code == 201
    assert seeded.post("/api/segments", json={"name": "Mineração"}).status_code == 409
    assert seeded.post("/api/segments", json={"name": "Z", "cnae_prefixes": "abc"}).status_code == 422
    st = seeded.post("/api/lead-statuses", json={"name": "Proposta enviada", "position": 3})
    assert st.status_code == 201
    assert seeded.post("/api/lead-statuses", json={"name": "Proposta enviada"}).status_code == 409


def test_dashboard_and_pages(seeded):
    d = seeded.get("/api/dashboard").json()
    assert d["total_empresas"] == 120 and d["empresas_mock"] == 120 and d["clientes"] == 15
    assert d["por_regiao"] and d["maior_compatibilidade"]
    for page in ("/", "/buscar", "/clientes", "/configuracoes", "/administracao", "/metodologia",
                 "/buscar?nl=agro+no+centro-oeste", "/buscar?page=2&sort=location"):
        r = seeded.get(page)
        assert r.status_code == 200, page
    assert "MOCK" in seeded.get("/").text


def test_clear_mock_removes_everything(seeded, db):
    assert clear_mock(db) == 120
    d = seeded.get("/api/dashboard").json()
    assert d["total_empresas"] == 0 and d["clientes"] == 0
    assert "mock-banner" not in seeded.get("/").text


# ---------------------------------------------------------------- integrações via API (simuladas)


def test_cnpj_lookup_uses_source_and_cache(make_app):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=BRASILAPI_SAMPLE)

    with TestClient(make_app(handler)) as c:
        login(c)
        c.headers["X-CSRF-Token"] = csrf_of(c)
        r = c.post("/api/companies/lookup", json={"cnpj": BRASILAPI_SAMPLE["cnpj"]}).json()
        assert r["consultou_fonte"] and r["empresa"]["razao_social"] == "EMPRESA SIMULADA LTDA"
        assert r["empresa"]["segmento"] == "Instaladores"
        r2 = c.post("/api/companies/lookup", json={"cnpj": BRASILAPI_SAMPLE["cnpj"]}).json()
        assert not r2["consultou_fonte"] and len(calls) == 1  # cache de 30 dias
        c.post("/api/companies/lookup", json={"cnpj": BRASILAPI_SAMPLE["cnpj"], "force": True})
        assert len(calls) == 2
        assert c.post("/api/companies/lookup", json={"cnpj": "123"}).status_code == 422
        src = {s["chave"]: s for s in c.get("/api/sources").json()}["cnpj_api"]
        assert src["nivel"] == "ok"


def test_cnpj_lookup_errors(make_app):
    with TestClient(make_app(lambda r: httpx.Response(503))) as c:
        login(c)
        c.headers["X-CSRF-Token"] = csrf_of(c)
        r = c.post("/api/companies/lookup", json={"cnpj": make_cnpj("55555555")})
        assert r.status_code == 502 and "indisponível" in r.json()["detail"]
        src = {s["chave"]: s for s in c.get("/api/sources").json()}["cnpj_api"]
        assert src["falhas_consecutivas"] == 1 and src["nivel"] == "alerta"
    with TestClient(make_app(lambda r: httpx.Response(404))) as c:
        login(c)
        c.headers["X-CSRF-Token"] = csrf_of(c)
        assert c.post("/api/companies/lookup",
                      json={"cnpj": make_cnpj("55555555")}).status_code == 404


def test_website_enrichment_job(make_app):
    cnpj = BRASILAPI_SAMPLE["cnpj"]
    sample = {**BRASILAPI_SAMPLE, "email": "contato@eletricateste.com.br"}
    site = _site_handler(cnpj)

    def handler(req):
        if req.url.host == "brasilapi.com.br":
            return httpx.Response(200, json=sample)
        return site(req)

    with TestClient(make_app(handler)) as c:
        login(c)
        c.headers["X-CSRF-Token"] = csrf_of(c)
        cid = c.post("/api/companies/lookup", json={"cnpj": cnpj}).json()["empresa"]["id"]
        job = c.post(f"/api/companies/{cid}/enrich").json()
        assert job["status"] == "done", job["log"]
        d = c.get(f"/api/companies/{cid}").json()
        assert d["site"] == "https://eletricateste.com.br/" and d["site_status"] == "verificado"
        kinds = {(x["tipo"], x["valor"]) for x in d["contatos"]}
        assert ("whatsapp", "5511988887777") in kinds
        assert all(x["fonte"] in ("Site oficial", "cnpj_api") for x in d["contatos"])
        assert all(x["url_fonte"] for x in d["contatos"] if x["fonte"] == "Site oficial")
        assert d["tem_telefone"] and d["logo_url"].endswith("/logo.png")


def test_enrich_refuses_mock_and_icms_not_configured(seeded, db):
    cid = db.scalar(select(Company.id))
    assert seeded.post(f"/api/companies/{cid}/enrich").status_code == 409
    r = seeded.post(f"/api/companies/{cid}/icms")
    assert r.status_code == 409 and "certificado" in r.json()["detail"]


def test_icms_check_confirmed(make_app):
    cnpj = BRASILAPI_SAMPLE["cnpj"]
    app = make_app(lambda r: httpx.Response(200, json=BRASILAPI_SAMPLE),
                   sefaz_handler=lambda r: httpx.Response(200, text=RET_OK.format(cnpj=cnpj)))
    with TestClient(app) as c:
        login(c)
        c.headers["X-CSRF-Token"] = csrf_of(c)
        cid = c.post("/api/companies/lookup", json={"cnpj": cnpj}).json()["empresa"]["id"]
        job = c.post(f"/api/companies/{cid}/icms").json()
        assert job["status"] == "done", job["log"]
        d = c.get(f"/api/companies/{cid}").json()
        assert d["icms"] == "Contribuinte ICMS (confirmado)"
        ie = [f for f in d["fiscal"] if f["categoria"] == "inscricao_estadual"][0]
        assert ie["nivel"] == "confirmado" and ie["fonte"] == "SEFAZ-SP NfeConsultaCadastro"
        assert ie["url_fonte"] and ie["consultado_em"]
        # nova consulta substitui (não duplica) o registro da mesma fonte
        c.post(f"/api/companies/{cid}/icms")
        d = c.get(f"/api/companies/{cid}").json()
        assert len([f for f in d["fiscal"] if f["categoria"] == "inscricao_estadual"]) == 1


def test_failed_job_is_recorded(client, db):
    r = client.post("/api/admin/receita-import", json={"download": False})
    job = r.json()
    assert job["status"] == "failed" and job["erros"] == 1
    assert "Estabelecimentos" in job["log"][-1]
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "failed"
    assert client.get("/api/jobs/99999").status_code == 404
    assert client.post("/api/admin/receita-import", json={"month": "2026/9"}).status_code == 422


def test_customer_upload_validation(client):
    r = client.post("/api/customers/import", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415
    r = client.post("/api/customers/import", files={"file": ("x.csv", b"", "text/csv")})
    assert r.status_code == 422
    r = client.post("/api/customers/import", files={"file": ("x.csv", b"a;b\n1;2", "text/csv")})
    assert r.json()["status"] == "failed"  # cabeçalho não reconhecido → registrado no job


def test_delete_contact_lgpd(make_app):
    with TestClient(make_app(lambda r: httpx.Response(200, json=BRASILAPI_SAMPLE))) as c:
        login(c)
        c.headers["X-CSRF-Token"] = csrf_of(c)
        d = c.post("/api/companies/lookup", json={"cnpj": BRASILAPI_SAMPLE["cnpj"]}).json()["empresa"]
        tel = next(x for x in d["contatos"] if x["tipo"] == "telefone")
        assert c.delete(f"/api/contacts/{tel['id']}").status_code == 204
        after = c.get(f"/api/companies/{d['id']}").json()
        assert not after["contatos"] and after["tem_telefone"] is False
        assert c.delete(f"/api/contacts/{tel['id']}").status_code == 404


def test_customer_manual_cnpj(client, db):
    from prospeccao.models import Customer

    r = client.post("/api/customers/import", files={"file": (
        "c.csv", "Cliente que já tiveram cotação\nALFA LTDA\nBETA LTDA\n".encode(), "text/csv")})
    assert r.json()["status"] == "done", r.json()["log"]
    alfa, beta = db.scalars(select(Customer).order_by(Customer.id)).all()
    cnpj = make_cnpj("13131313")
    assert client.patch(f"/api/customers/{alfa.id}", json={"cnpj": "123"}).status_code == 422
    ok = client.patch(f"/api/customers/{alfa.id}", json={"cnpj": cnpj}).json()
    assert ok["status"] == "nao_encontrado" and ok["cnpj"] == cnpj  # fora da base local ainda
    assert client.patch(f"/api/customers/{beta.id}", json={"cnpj": cnpj}).status_code == 409
    assert client.patch("/api/customers/999", json={"cnpj": cnpj}).status_code == 404
    page = client.get("/clientes?status=sem_cnpj")
    assert page.status_code == 200 and "BETA LTDA" in page.text and "ALFA LTDA" not in page.text


def test_hosting_database_url_is_normalized():
    from prospeccao.config import normalize_database_url

    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgresql+psycopg://x") == "postgresql+psycopg://x"
    assert normalize_database_url("sqlite:///a.db") == "sqlite:///a.db"


def test_empty_secret_key_in_env_file(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=\nADMIN_PASSWORD=\nDATABASE_URL=\n", encoding="utf-8")
    for k in ("SECRET_KEY", "ADMIN_PASSWORD", "DATABASE_URL", "APP_ENV"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ENV_FILE", str(env))
    s = load_settings()
    assert s.secret_key and s.database_url.startswith("sqlite") and s.admin_password is None
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_MOCK_DATA", "false")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_settings()
