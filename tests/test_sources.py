"""Testes de integração das fontes externas com transporte HTTP simulado (sem rede real)."""
from __future__ import annotations

import httpx
import pytest

from prospeccao.sources.base import RateLimiter, SourceError, SourceNotConfigured
from prospeccao.sources.cnpj_api import CnpjApiSource, CnpjNotFound
from prospeccao.sources.receita import (
    LayoutError,
    classify_files,
    iter_rows,
    parse_date,
    parse_decimal,
    parse_empresa,
    parse_estabelecimento,
)
from prospeccao.sources.sefaz import SefazIcmsSource, build_request, parse_response
from prospeccao.sources.website import (
    WebsiteSource,
    candidate_from_email,
    parse_page,
    verify_ownership,
)

from .conftest import emp_row, est_row, make_cnpj


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


# ---------------------------------------------------------------- Receita (layout)


def test_parse_estabelecimento_layout():
    c = make_cnpj("12345678")
    row = next(iter([est_row(c, fantasia="X", sec="4742300,7112000", email="A@B.COM.BR",
                             ddd="011", tel="3333-4444").replace('"', "").split(";")]))
    rec = parse_estabelecimento(row)
    assert rec["cnpj"] == c and rec["is_matriz"] and rec["situacao_cadastral"] == "02"
    assert rec["cnaes_secundarios"] == ["4742300", "7112000"]
    assert rec["phones"] == ["1133334444"] and rec["email"] == "a@b.com.br"
    assert rec["logradouro"] == "RUA DAS FLORES" and rec["cep"] == "01001000"


def test_parse_estabelecimento_rejects_bad_rows():
    with pytest.raises(LayoutError):
        parse_estabelecimento(["1", "2"])
    row = est_row(make_cnpj("12345678")).replace('"', "").split(";")
    row[2] = "00"  # DV errado
    with pytest.raises(ValueError):
        parse_estabelecimento(row)


def test_parse_empresa_and_values():
    rec = parse_empresa(emp_row("1", "ACME LTDA", capital="1.500,50").replace('"', "").split(";"))
    assert rec["cnpj_basico"] == "00000001" and str(rec["capital_social"]) == "1500.50"
    assert parse_date("00000000") is None and parse_date("20240230") is None
    assert parse_date("20240229").isoformat() == "2024-02-29"
    assert parse_decimal("") is None


def test_iter_rows_zip_latin1_and_classify(receita_dir):
    d, _ = receita_dir
    files = classify_files(d)
    assert [p.name for p in files["estabelecimentos"]] == ["Estabelecimentos0.zip"]
    assert files["simples"] and files["cnaes"] and files["municipios"] and files["naturezas"]
    rows = list(iter_rows(files["cnaes"][0]))
    assert rows[0] == ["4321500", "Instalação e manutenção elétrica"]


def test_receita_download_validates_zip(tmp_path):
    from prospeccao.sources.receita import ReceitaOpenDataSource

    def handler(req):
        if req.url.path.endswith("/dados_abertos_cnpj/"):
            return httpx.Response(200, text='<a href="2026-08/">2026-08/</a><a href="2026-09/">x</a>')
        if req.url.path.endswith("/2026-09/"):
            return httpx.Response(200, text='<a href="Cnaes.zip">Cnaes.zip</a>')
        return httpx.Response(200, content=b"isto nao e um zip")

    src = ReceitaOpenDataSource("https://rf.test/dados_abertos_cnpj", tmp_path, "t",
                                client=_client(handler))
    # O cliente simulado é reutilizado; evita fechá-lo entre chamadas
    src._http = lambda: _NoClose(_client(handler))
    assert src.latest_month() == "2026-09"
    assert src.list_remote_files("2026-09") == ["Cnaes.zip"]
    with pytest.raises(SourceError, match="não é um ZIP"):
        src.download("2026-09", ["Cnaes.zip"])
    assert not list((tmp_path / "2026-09").glob("*.zip"))


class _NoClose:
    def __init__(self, c):
        self.c = c

    def __enter__(self):
        return self.c

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------- API de CNPJ


BRASILAPI_SAMPLE = {  # estrutura de resposta simulada (campos conforme documentação da BrasilAPI)
    "cnpj": make_cnpj("55555555"), "razao_social": "EMPRESA SIMULADA LTDA",
    "nome_fantasia": "SIMULADA", "situacao_cadastral": 2, "descricao_situacao_cadastral": "ATIVA",
    "data_inicio_atividade": "2010-05-01", "cnae_fiscal": 4321500,
    "cnae_fiscal_descricao": "Instalação e manutenção elétrica",
    "cnaes_secundarios": [{"codigo": 4742300, "descricao": "Comércio varejista de material elétrico"}],
    "codigo_natureza_juridica": 2062, "natureza_juridica": "Sociedade Empresária Limitada",
    "codigo_porte": 3, "porte": "EMPRESA DE PEQUENO PORTE", "capital_social": 50000.0,
    "descricao_tipo_de_logradouro": "RUA", "logradouro": "EXEMPLO", "numero": "1",
    "bairro": "CENTRO", "cep": "01001000", "uf": "SP", "municipio": "SAO PAULO",
    "codigo_municipio": 7107, "ddd_telefone_1": "1133334444", "ddd_telefone_2": "",
    "email": None, "opcao_pelo_simples": True, "data_opcao_pelo_simples": "2011-01-01",
    "opcao_pelo_mei": False, "identificador_matriz_filial": 1,
}


def test_cnpj_api_maps_response():
    api = CnpjApiSource("brasilapi", "t", 0,
                        client=_client(lambda r: httpx.Response(200, json=BRASILAPI_SAMPLE)))
    rec, prov = api.fetch(BRASILAPI_SAMPLE["cnpj"])
    assert rec["cnae_principal"] == "4321500" and rec["cnaes_secundarios"] == ["4742300"]
    assert rec["porte"] == "03" and rec["situacao_cadastral"] == "02"
    assert rec["phones"] == ["1133334444"] and rec["simples_opcao"] is True
    assert prov.url.endswith(BRASILAPI_SAMPLE["cnpj"])


@pytest.mark.parametrize("status,exc,msg", [(404, CnpjNotFound, "não encontrado"),
                                            (429, SourceError, "limite"),
                                            (500, SourceError, "HTTP 500")])
def test_cnpj_api_errors(status, exc, msg):
    api = CnpjApiSource("brasilapi", "t", 0, client=_client(lambda r: httpx.Response(status)))
    with pytest.raises(exc, match=msg):
        api.fetch(make_cnpj("55555555"))


def test_cnpj_api_unavailable_and_invalid_json():
    def boom(req):
        raise httpx.ConnectError("sem rede")

    with pytest.raises(SourceError, match="indisponível"):
        CnpjApiSource("brasilapi", "t", 0, client=_client(boom)).fetch(make_cnpj("55555555"))
    bad = CnpjApiSource("brasilapi", "t", 0, client=_client(lambda r: httpx.Response(200, text="<html>")))
    with pytest.raises(SourceError, match="inválida"):
        bad.fetch(make_cnpj("55555555"))


def test_cnpj_api_rejects_invalid_cnpj_before_calling():
    calls = []
    api = CnpjApiSource("brasilapi", "t", 0,
                        client=_client(lambda r: calls.append(r) or httpx.Response(200)))
    with pytest.raises(ValueError):
        api.fetch("11.111.111/1111-11")
    assert calls == []


def test_rate_limiter_waits():
    now = [0.0]
    slept = []
    rl = RateLimiter(5, clock=lambda: now[0], sleep=lambda s: slept.append(s))
    rl.wait("a")
    rl.wait("a")
    rl.wait("b")
    assert slept == [5]


# ---------------------------------------------------------------- SEFAZ


RET_OK = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body>
<nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/CadConsultaCadastro4">
<retConsCad xmlns="http://www.portalfiscal.inf.br/nfe" versao="2.00"><infCons>
<verAplic>SIMULADO</verAplic><cStat>111</cStat><xMotivo>Consulta cadastro com uma ocorrência</xMotivo>
<UF>SP</UF><CNPJ>{cnpj}</CNPJ><dhCons>2026-09-30T10:00:00-03:00</dhCons><cUF>35</cUF>
<infCad><IE>123456789012</IE><CNPJ>{cnpj}</CNPJ><UF>SP</UF><cSit>1</cSit><indCredNFe>1</indCredNFe>
<indCredCTe>4</indCredCTe><xNome>EMPRESA SIMULADA</xNome><xRegApur>NORMAL - REGIME PERIÓDICO DE APURAÇÃO</xRegApur>
<CNAE>4321500</CNAE><dIniAtiv>2010-05-01</dIniAtiv><dUltSit>2015-01-01</dUltSit></infCad>
</infCons></retConsCad></nfeResultMsg></soap:Body></soap:Envelope>"""


def test_sefaz_request_and_parse_ok():
    c = make_cnpj("55555555")
    req = build_request("SP", c)
    assert "<xServ>CONS-CAD</xServ><UF>SP</UF>" in req and f"<CNPJ>{c}</CNPJ>" in req
    res = parse_response(RET_OK.format(cnpj=c))
    assert res["status"] == "confirmado_habilitado"
    assert res["registros"][0]["ie"] == "123456789012"
    assert res["registros"][0]["regime_apuracao"].startswith("NORMAL")


def test_sefaz_not_contributor_and_errors():
    ret = RET_OK.replace("<cStat>111</cStat>", "<cStat>259</cStat>")
    assert parse_response(ret.format(cnpj="x"))["status"] == "nao_contribuinte"
    with pytest.raises(SourceError, match="cStat 999"):
        parse_response(RET_OK.replace("<cStat>111</cStat>", "<cStat>999</cStat>").format(cnpj="x"))
    with pytest.raises(SourceError, match="XML"):
        parse_response("não é xml")
    with pytest.raises(SourceError, match="retConsCad"):
        parse_response("<a/>")


def test_sefaz_not_configured():
    src = SefazIcmsSource({}, None, None)
    assert not src.is_enabled() and not src.check().ok
    with pytest.raises(SourceNotConfigured):
        src.consult("SP", make_cnpj("55555555"))
    configured = SefazIcmsSource({"SP": "https://x"}, None, None,
                                 client=_client(lambda r: httpx.Response(200)))
    with pytest.raises(SourceNotConfigured, match="MG"):
        configured.consult("MG", make_cnpj("55555555"))


def test_sefaz_consult_posts_soap():
    c = make_cnpj("55555555")
    seen = {}

    def handler(req):
        seen["ct"] = req.headers["content-type"]
        seen["body"] = req.content.decode()
        return httpx.Response(200, text=RET_OK.format(cnpj=c))

    src = SefazIcmsSource({"SP": "https://sefaz.test/ws"}, None, None, client=_client(handler),
                          min_interval=0)
    res, prov = src.consult("sp", c)
    assert res["status"] == "confirmado_habilitado" and prov.source == "SEFAZ-SP NfeConsultaCadastro"
    assert seen["ct"].startswith("application/soap+xml") and "ConsCad" in seen["body"]


# ---------------------------------------------------------------- Site oficial

HOME = """<html><head><title>Elétrica Teste</title>
<meta name="description" content="Instalações elétricas industriais">
<meta property="og:image" content="/logo.png"><link rel="icon" href="/fav.ico"></head>
<body>Elétrica Teste Instalações — CNPJ {cnpj}
<a href="tel:+55 11 3333-4444">ligue</a><a href="mailto:vendas@eletricateste.com.br">e-mail</a>
<a href="mailto:joao.silva@eletricateste.com.br">João</a><a href="mailto:fulano@gmail.com">x</a>
<a href="https://wa.me/5511988887777">WhatsApp</a>
<a href="https://www.instagram.com/eletricateste/">insta</a>
<a href="https://www.linkedin.com/company/eletrica-teste">in</a>
<a href="/contato">Fale conosco</a><a href="https://outro-site.com/contato">externo</a></body></html>"""


def test_parse_page_contacts_and_personal_flags():
    page, contacts = parse_page(HOME.format(cnpj="x"), "https://eletricateste.com.br/",
                                "eletricateste.com.br")
    got = {(c.kind, c.value): c.is_company for c in contacts}
    assert got[("telefone", "1133334444")] is True
    assert got[("email", "vendas@eletricateste.com.br")] is True
    assert got[("email", "joao.silva@eletricateste.com.br")] is False  # possível pessoal
    assert got[("email", "fulano@gmail.com")] is False
    assert got[("whatsapp", "5511988887777")] is True
    assert ("instagram", "https://www.instagram.com/eletricateste") in got
    assert ("linkedin", "https://www.linkedin.com/company/eletrica-teste") in got
    assert page.description == "Instalações elétricas industriais"


def test_verify_ownership():
    assert verify_ownership("CNPJ 11.222.333/0001-81", "11222333000181", None, None)[0]
    assert verify_ownership("Bem-vindo à Elétrica Teste", "x", "ELETRICA TESTE LTDA", None)[0]
    assert not verify_ownership("Outra empresa", "11222333000181", "ACME LTDA", None)[0]


def test_candidate_from_email():
    assert candidate_from_email("contato@eletricateste.com.br") == "https://eletricateste.com.br/"
    assert candidate_from_email("fulano@hotmail.com") is None
    assert candidate_from_email(None) is None


def _site_handler(cnpj, robots="User-agent: *\nAllow: /", counter=None):
    def handler(req):
        if counter is not None:
            counter.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if req.url.path == "/contato":
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  text='<a href="tel:1144445555">x</a>')
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                              text=HOME.format(cnpj=cnpj))
    return handler


def test_website_fetch_full_flow():
    c = make_cnpj("11111111")
    calls = []
    src = WebsiteSource("bot", 0, client=_client(_site_handler(c, counter=calls)))
    res = src.fetch("eletricateste.com.br", c, "ELETRICA TESTE LTDA", None)
    assert res.verified and res.verification_reason == "CNPJ encontrado na página"
    assert res.logo_url == "https://eletricateste.com.br/logo.png"
    assert ("telefone", "1144445555") in {(x.kind, x.value) for x in res.contacts}  # página contato
    assert not any("outro-site" in u for u in calls)  # não segue links externos
    assert len(calls) == 3  # robots + home + contato


def test_website_respects_robots():
    c = make_cnpj("11111111")
    src = WebsiteSource("bot", 0, client=_client(_site_handler(c, robots="User-agent: *\nDisallow: /")))
    with pytest.raises(SourceError, match="robots"):
        src.fetch("https://eletricateste.com.br", c, None, None)


def test_website_robots_unreachable_means_no_fetch():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(503)
        raise AssertionError("não deveria buscar a página")

    with pytest.raises(SourceError):
        WebsiteSource("bot", 0, client=_client(handler)).fetch("https://x.com.br", "1", None, None)


def test_website_non_html_and_invalid_url():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    src = WebsiteSource("bot", 0, client=_client(handler))
    with pytest.raises(SourceError):
        src.fetch("https://x.com.br", "1", None, None)
    with pytest.raises(SourceError, match="URL"):
        src.fetch("semponto", "1", None, None)
