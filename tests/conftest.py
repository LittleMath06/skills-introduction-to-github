"""Fixtures compartilhadas.

Nenhum teste acessa a internet: fontes externas usam httpx.MockTransport com respostas
construídas nos próprios testes (identificadas como simuladas).
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prospeccao.config import load_settings  # noqa: E402
from prospeccao.domain.cnpj import compute_check_digits  # noqa: E402
from prospeccao.security import login_limiter  # noqa: E402
from prospeccao.services.jobs import JobRunner  # noqa: E402
from prospeccao.services.tasks import Sources  # noqa: E402
from prospeccao.sources.cnpj_api import CnpjApiSource  # noqa: E402
from prospeccao.sources.sefaz import SefazIcmsSource  # noqa: E402
from prospeccao.sources.website import WebsiteSource  # noqa: E402

PASSWORD = "senha-forte-de-teste"


def make_cnpj(base8: str, ordem: str = "0001") -> str:
    base = base8 + ordem
    return base + compute_check_digits(base)


class FakeSources(Sources):
    """Fontes com transporte HTTP simulado (sem rede)."""

    def __init__(self, settings, handler=None, sefaz_handler=None):
        super().__init__(settings)
        self.handler = handler or (lambda req: httpx.Response(404))
        self.sefaz_handler = sefaz_handler

    def _client(self, handler):
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)

    def cnpj_api(self):
        return CnpjApiSource("brasilapi", "test", 0, client=self._client(self.handler))

    def website(self):
        return WebsiteSource("test-bot", 0, client=self._client(self.handler))

    def sefaz(self):
        if not self.sefaz_handler:
            return SefazIcmsSource({}, None, None)
        return SefazIcmsSource({"SP": "https://sefaz.test/ws"}, None, None,
                               client=self._client(self.sefaz_handler), min_interval=0)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ADMIN_USERNAME", "paulo")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    import os

    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    s = load_settings()
    if url.startswith("postgresql"):
        from sqlalchemy import create_engine, text

        eng = create_engine(url)
        with eng.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        eng.dispose()
    return replace(s, website_min_interval=0, cnpj_api_min_interval=0)


@pytest.fixture
def make_app(settings):
    from prospeccao.main import create_app

    login_limiter._failures.clear()

    def _make(handler=None, sefaz_handler=None):
        return create_app(settings, runner=JobRunner(synchronous=True),
                          sources=FakeSources(settings, handler, sefaz_handler))

    return _make


@pytest.fixture
def app(make_app):
    return make_app()


def login(client, username="paulo", password=PASSWORD):
    page = client.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    return client.post("/login", data={"username": username, "password": password,
                                       "csrf_token": token}, follow_redirects=False)


def csrf_of(client) -> str:
    page = client.get("/")
    return re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text).group(1)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        assert login(c).status_code == 303
        c.headers["X-CSRF-Token"] = csrf_of(c)
        yield c


@pytest.fixture
def db(app):
    from prospeccao.db import new_session

    s = new_session()
    yield s
    s.close()


# ------------------------------------------------------------------ dados da Receita (layout oficial)

def est_row(cnpj: str, *, fantasia="", situacao="02", cnae="4321500", sec="", uf="SP",
            municipio="7107", email="", ddd="11", tel="33334444", matriz="1") -> str:
    fields = [cnpj[:8], cnpj[8:12], cnpj[12:], matriz, fantasia, situacao, "20200101", "00", "", "",
              "20150310", cnae, sec, "RUA", "DAS FLORES", "100", "", "CENTRO", "01001000", uf,
              municipio, ddd, tel, "", "", "", "", email, "", ""]
    return ";".join(f'"{f}"' for f in fields)


def emp_row(basico: str, razao: str, porte="03", capital="150000,00", natureza="2062") -> str:
    return ";".join(f'"{f}"' for f in [basico, razao, natureza, "49", capital, porte, ""])


def simples_row(basico: str, simples="S", mei="N") -> str:
    return ";".join(f'"{f}"' for f in [basico, simples, "20180101", "00000000", mei, "00000000",
                                         "00000000"])


def write_zip(path: Path, member: str, lines: list[str]) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, ("\n".join(lines) + "\n").encode("latin-1"))
    path.write_bytes(buf.getvalue())
    return path


@pytest.fixture
def receita_dir(tmp_path):
    """Arquivos no layout oficial (conteúdo de teste — empresas fictícias)."""
    d = tmp_path / "receita" / "2026-09"
    d.mkdir(parents=True)
    c1, c2, c3, c4 = (make_cnpj("11111111"), make_cnpj("22222222"), make_cnpj("33333333"),
                      make_cnpj("44444444"))
    c1_filial = make_cnpj("11111111", "0002")
    write_zip(d / "Estabelecimentos0.zip", "K3241.K03200Y0.D60913.ESTABELE", [
        est_row(c1, fantasia="ELETRICA TESTE", cnae="4321500", email="contato@eletricateste.com.br"),
        est_row(c1_filial, fantasia="ELETRICA TESTE FILIAL", cnae="4321500", uf="MG",
                municipio="4123", matriz="2"),
        est_row(c2, fantasia="DISTRIBUIDORA TESTE", cnae="4673700", uf="PR", municipio="7535"),
        est_row(c3, fantasia="RESTAURANTE TESTE", cnae="5611201"),
        est_row(c4, fantasia="BAIXADA TESTE", cnae="4321500", situacao="08"),
        '"123";"linha";"quebrada"',
    ])
    write_zip(d / "Empresas0.zip", "K3241.EMPRECSV", [
        emp_row("11111111", "ELETRICA TESTE INSTALACOES LTDA"),
        emp_row("22222222", "DISTRIBUIDORA TESTE DE MATERIAIS ELETRICOS LTDA", porte="05"),
        emp_row("33333333", "RESTAURANTE TESTE LTDA", porte="01"),
        emp_row("99999999", "OUTRA EMPRESA NAO IMPORTADA"),
    ])
    write_zip(d / "Simples.zip", "F.K03200$W.SIMPLES.CSV.D60913", [simples_row("11111111"),
                                                                     simples_row("22222222", "N")])
    write_zip(d / "Cnaes.zip", "F.K03200$Z.D60913.CNAECSV", [
        '"4321500";"Instalação e manutenção elétrica"',
        '"4673700";"Comércio atacadista de material elétrico"',
        '"5611201";"Restaurantes e similares"',
    ])
    write_zip(d / "Municipios.zip", "F.K03200$Z.D60913.MUNICCSV", [
        '"7107";"SAO PAULO"', '"4123";"BELO HORIZONTE"', '"7535";"CURITIBA"'])
    write_zip(d / "Naturezas.zip", "F.K03200$Z.D60913.NATJUCSV", ['"2062";"Sociedade Empresária Limitada"'])
    return d, {"c1": c1, "c1_filial": c1_filial, "c2": c2, "c3": c3, "c4": c4}
