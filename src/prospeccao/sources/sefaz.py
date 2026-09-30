"""Consulta oficial do cadastro de contribuintes de ICMS — web service NfeConsultaCadastro 4.00.

Requisitos (fonte: Manual de Orientação do Contribuinte NF-e / portais SEFAZ):
* conexão TLS com certificado digital ICP-Brasil (e-CNPJ) de empresa credenciada a emitir DF-e;
* endpoint da UF consultada (várias UFs usam o SVRS). O mapa UF → URL é configurado em
  ICMS_ENDPOINTS, porque os endereços variam e não devem ficar fixos no código.

Esta fonte fica DESATIVADA enquanto certificado e endpoints não forem configurados. Neste caso o
sistema exibe "ICMS não verificado" (ou "provável", quando inferido do CNAE) — nunca "confirmado".
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

import httpx

from ..domain import cnpj as cnpj_mod
from .base import ICMSSource, Provenance, RateLimiter, SourceError, SourceNotConfigured, SourceStatus

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_WSDL = "http://www.portalfiscal.inf.br/nfe/wsdl/CadConsultaCadastro4"

# cStat de sucesso: 111 = uma ocorrência, 112 = múltiplas ocorrências
_SUCCESS = {"111", "112"}
# cStat 259 = "Rejeição: CNPJ da consulta não cadastrado como contribuinte na UF"
_NOT_CONTRIBUTOR = {"259"}


def build_request(uf: str, cnpj: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Body>"
        f'<nfeDadosMsg xmlns="{NS_WSDL}">'
        f'<ConsCad xmlns="{NS_NFE}" versao="2.00">'
        f"<infCons><xServ>CONS-CAD</xServ><UF>{uf}</UF><CNPJ>{cnpj}</CNPJ></infCons>"
        "</ConsCad></nfeDadosMsg></soap12:Body></soap12:Envelope>"
    )


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el: ET.Element, name: str) -> ET.Element | None:
    for child in el.iter():
        if _local(child.tag) == name:
            return child
    return None


def _text(el: ET.Element | None, name: str) -> str | None:
    if el is None:
        return None
    found = _find(el, name)
    return found.text.strip() if found is not None and found.text else None


def _date(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v[:10]) if v else None
    except ValueError:
        return None


def parse_response(xml_text: str) -> dict:
    """Converte retConsCad em {"status": ..., "cStat", "xMotivo", "registros": [...]}."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SourceError("Resposta da SEFAZ não é XML válido") from exc
    ret = _find(root, "retConsCad")
    if ret is None:
        raise SourceError("Resposta da SEFAZ sem elemento retConsCad")
    inf_cons = _find(ret, "infCons")
    c_stat = _text(inf_cons, "cStat")
    motivo = _text(inf_cons, "xMotivo")
    if c_stat in _NOT_CONTRIBUTOR:
        return {"status": "nao_contribuinte", "cStat": c_stat, "xMotivo": motivo, "registros": []}
    if c_stat not in _SUCCESS:
        raise SourceError(f"SEFAZ retornou cStat {c_stat}: {motivo}")
    registros = []
    for inf in (el for el in ret.iter() if _local(el.tag) == "infCad"):
        registros.append({
            "ie": _text(inf, "IE"),
            "cnpj": _text(inf, "CNPJ"),
            "uf": _text(inf, "UF"),
            "habilitado": _text(inf, "cSit") == "1",
            "ind_cred_nfe": _text(inf, "indCredNFe"),
            "ind_cred_cte": _text(inf, "indCredCTe"),
            "nome": _text(inf, "xNome"),
            "regime_apuracao": _text(inf, "xRegApur"),
            "cnae": _text(inf, "CNAE"),
            "data_inicio": _date(_text(inf, "dIniAtiv")),
            "data_ultima_situacao": _date(_text(inf, "dUltSit")),
            "data_baixa": _date(_text(inf, "dBaixa")),
        })
    status = "confirmado_habilitado" if any(r["habilitado"] for r in registros) \
        else "confirmado_nao_habilitado"
    return {"status": status, "cStat": c_stat, "xMotivo": motivo, "registros": registros}


class SefazIcmsSource(ICMSSource):
    key = "sefaz_icms"
    name = "SEFAZ — NfeConsultaCadastro (ICMS)"

    def __init__(self, endpoints: dict[str, str], cert_file: str | None, key_file: str | None,
                 client: httpx.Client | None = None, min_interval: float = 2.0):
        self.endpoints = {k.upper(): v for k, v in endpoints.items()}
        self.cert_file = cert_file
        self.key_file = key_file
        self._client = client
        self._limiter = RateLimiter(min_interval)

    def is_enabled(self) -> bool:
        return bool(self.endpoints) and (self._client is not None or bool(self.cert_file))

    def check(self) -> SourceStatus:
        if not self.is_enabled():
            return SourceStatus(False, "Não configurada: requer certificado digital (ICMS_CERT_FILE/"
                                       "ICMS_KEY_FILE) e ICMS_ENDPOINTS por UF")
        return SourceStatus(True, f"Configurada para {len(self.endpoints)} UF(s): "
                                  + ", ".join(sorted(self.endpoints)))

    def _http(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        cert = (self.cert_file, self.key_file) if self.key_file else self.cert_file
        return httpx.Client(timeout=15, cert=cert)

    def consult(self, uf: str, cnpj: str) -> tuple[dict, Provenance]:
        uf = (uf or "").upper()
        if not self.is_enabled():
            raise SourceNotConfigured("Consulta SEFAZ não configurada")
        url = self.endpoints.get(uf)
        if not url:
            raise SourceNotConfigured(f"Sem endpoint SEFAZ configurado para {uf}")
        cnpj = cnpj_mod.validate(cnpj)
        self._limiter.wait(uf)
        client = self._http()
        try:
            resp = client.post(
                url, content=build_request(uf, cnpj).encode("utf-8"),
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            )
        except httpx.HTTPError as exc:
            raise SourceError(f"SEFAZ {uf} indisponível: {exc.__class__.__name__}") from exc
        finally:
            if self._client is None:
                client.close()
        if resp.status_code != 200:
            raise SourceError(f"SEFAZ {uf} retornou HTTP {resp.status_code}")
        return parse_response(resp.text), Provenance(source=f"SEFAZ-{uf} NfeConsultaCadastro",
                                                     url=url, confidence=1.0)
