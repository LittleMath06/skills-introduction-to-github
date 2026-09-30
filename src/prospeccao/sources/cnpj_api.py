"""Consulta pontual de um CNPJ em API pública (BrasilAPI ou OpenCNPJ).

Uso restrito a consultas individuais (volume "de pessoa real"), com intervalo mínimo entre
chamadas. Nunca usada para varredura em massa — para isso existe a importação dos arquivos oficiais.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from ..domain import cnpj as cnpj_mod
from ..domain.text import clean_name, normalize_cep, normalize_email, normalize_phone, only_digits
from .base import CNPJSource, Provenance, RateLimiter, SourceError, SourceStatus

PROVIDERS = {
    "brasilapi": "https://brasilapi.com.br/api/cnpj/v1/{cnpj}",
    "opencnpj": "https://api.opencnpj.org/{cnpj}",
}

_SITUACAO_BY_NAME = {"NULA": "01", "ATIVA": "02", "SUSPENSA": "03", "INAPTA": "04", "BAIXADA": "08"}
_PORTE_BY_NAME = {"MICRO EMPRESA": "01", "ME": "01", "EMPRESA DE PEQUENO PORTE": "03", "EPP": "03",
                  "DEMAIS": "05", "NAO INFORMADO": "00", "NÃO INFORMADO": "00"}


def _date(v) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _decimal(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) and "," in v \
            else Decimal(str(v))
    except InvalidOperation:
        return None


def _code(v, width: int) -> str | None:
    d = only_digits(str(v)) if v not in (None, "") else ""
    return d.zfill(width) if d else None


def _situacao(data: dict) -> str | None:
    code = data.get("situacao_cadastral")
    if isinstance(code, int) or (isinstance(code, str) and code.isdigit()):
        return str(code).zfill(2)
    name = str(data.get("descricao_situacao_cadastral") or code or "").upper()
    return _SITUACAO_BY_NAME.get(name)


def map_brasilapi(data: dict) -> dict:
    cnpj = cnpj_mod.validate(data.get("cnpj"))
    phones = [p for p in (normalize_phone(None, data.get("ddd_telefone_1")),
                          normalize_phone(None, data.get("ddd_telefone_2"))) if p]
    street = " ".join(p for p in [data.get("descricao_tipo_de_logradouro"),
                                  data.get("logradouro")] if p)
    return {
        "cnpj": cnpj,
        "cnpj_basico": cnpj[:8],
        "is_matriz": str(data.get("identificador_matriz_filial", "1")) == "1",
        "razao_social": clean_name(data.get("razao_social")),
        "nome_fantasia": clean_name(data.get("nome_fantasia")),
        "situacao_cadastral": _situacao(data),
        "data_situacao": _date(data.get("data_situacao_cadastral")),
        "data_abertura": _date(data.get("data_inicio_atividade")),
        "natureza_juridica_code": _code(data.get("codigo_natureza_juridica"), 4),
        "natureza_juridica": clean_name(data.get("natureza_juridica")),
        "porte": _code(data.get("codigo_porte"), 2)
        or _PORTE_BY_NAME.get(str(data.get("porte") or "").upper()),
        "capital_social": _decimal(data.get("capital_social")),
        "logradouro": clean_name(street),
        "numero": clean_name(data.get("numero")),
        "complemento": clean_name(data.get("complemento")),
        "bairro": clean_name(data.get("bairro")),
        "cep": normalize_cep(str(data.get("cep") or "")),
        "uf": (data.get("uf") or "").upper() or None,
        "municipio_code": _code(data.get("codigo_municipio"), 4),
        "municipio": clean_name(data.get("municipio")),
        "cnae_principal": _code(data.get("cnae_fiscal"), 7),
        "cnae_principal_desc": clean_name(data.get("cnae_fiscal_descricao")),
        "cnaes_secundarios": [c for c in (_code(s.get("codigo"), 7)
                                          for s in data.get("cnaes_secundarios") or [])
                              if c and c != "0000000"],
        "cnae_descriptions": {
            _code(s.get("codigo"), 7): clean_name(s.get("descricao"))
            for s in data.get("cnaes_secundarios") or [] if s.get("codigo")
        },
        "phones": phones,
        "email": normalize_email(data.get("email")),
        "simples_opcao": data.get("opcao_pelo_simples"),
        "simples_data_opcao": _date(data.get("data_opcao_pelo_simples")),
        "simples_data_exclusao": _date(data.get("data_exclusao_do_simples")),
        "mei_opcao": data.get("opcao_pelo_mei"),
    }


def map_opencnpj(data: dict) -> dict:
    cnpj = cnpj_mod.validate(data.get("cnpj"))
    phones = []
    for t in data.get("telefones") or []:
        if not t.get("is_fax"):
            p = normalize_phone(t.get("ddd"), t.get("numero"))
            if p:
                phones.append(p)
    sn = {"S": True, "N": False}
    return {
        "cnpj": cnpj,
        "cnpj_basico": cnpj[:8],
        "is_matriz": str(data.get("matriz_filial", "Matriz")).lower().startswith("matriz"),
        "razao_social": clean_name(data.get("razao_social")),
        "nome_fantasia": clean_name(data.get("nome_fantasia")),
        "situacao_cadastral": _situacao(data),
        "data_situacao": _date(data.get("data_situacao_cadastral")),
        "data_abertura": _date(data.get("data_inicio_atividade")),
        "natureza_juridica_code": None,
        "natureza_juridica": clean_name(data.get("natureza_juridica")),
        "porte": _PORTE_BY_NAME.get(str(data.get("porte_empresa") or "").upper()),
        "capital_social": _decimal(data.get("capital_social")),
        "logradouro": clean_name(data.get("logradouro")),
        "numero": clean_name(data.get("numero")),
        "complemento": clean_name(data.get("complemento")),
        "bairro": clean_name(data.get("bairro")),
        "cep": normalize_cep(str(data.get("cep") or "")),
        "uf": (data.get("uf") or "").upper() or None,
        "municipio_code": None,
        "municipio": clean_name(data.get("municipio")),
        "cnae_principal": _code(data.get("cnae_principal"), 7),
        "cnae_principal_desc": None,
        "cnaes_secundarios": [c for c in (_code(s, 7) for s in data.get("cnaes_secundarios") or [])
                              if c],
        "cnae_descriptions": {},
        "phones": list(dict.fromkeys(phones)),
        "email": normalize_email(data.get("email")),
        "simples_opcao": sn.get(str(data.get("opcao_simples") or "").upper()),
        "simples_data_opcao": _date(data.get("data_opcao_simples")),
        "simples_data_exclusao": None,
        "mei_opcao": sn.get(str(data.get("opcao_mei") or "").upper()),
    }


_MAPPERS = {"brasilapi": map_brasilapi, "opencnpj": map_opencnpj}


class CnpjNotFound(SourceError):
    pass


class CnpjApiSource(CNPJSource):
    key = "cnpj_api"

    def __init__(self, provider: str, user_agent: str, min_interval: float = 3.0,
                 client: httpx.Client | None = None, limiter: RateLimiter | None = None):
        if provider not in PROVIDERS:
            raise ValueError(f"Provedor de CNPJ desconhecido: {provider}")
        self.provider = provider
        self.name = f"API pública de CNPJ ({provider})"
        self.user_agent = user_agent
        self._client = client
        self._limiter = limiter or RateLimiter(min_interval)

    def url_for(self, cnpj: str) -> str:
        return PROVIDERS[self.provider].format(cnpj=cnpj)

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=10, headers={"User-Agent": self.user_agent})

    def check(self) -> SourceStatus:
        return SourceStatus(True, f"Consulta sob demanda via {self.provider} (sem verificação ativa "
                                  "para não consumir cota)")

    def fetch(self, cnpj: str) -> tuple[dict, Provenance]:
        cnpj = cnpj_mod.validate(cnpj)
        url = self.url_for(cnpj)
        self._limiter.wait(self.provider)
        try:
            client = self._http()
            try:
                resp = client.get(url)
            finally:
                if self._client is None:
                    client.close()
        except httpx.HTTPError as exc:
            raise SourceError(f"{self.provider} indisponível: {exc.__class__.__name__}") from exc
        if resp.status_code == 404:
            raise CnpjNotFound(f"CNPJ {cnpj} não encontrado em {self.provider}")
        if resp.status_code == 429:
            raise SourceError(f"{self.provider}: limite de requisições atingido (HTTP 429)")
        if resp.status_code != 200:
            raise SourceError(f"{self.provider} retornou HTTP {resp.status_code}")
        try:
            data = resp.json()
            record = _MAPPERS[self.provider](data)
        except (ValueError, cnpj_mod.InvalidCNPJ) as exc:
            raise SourceError(f"Resposta inválida de {self.provider}: {exc}") from exc
        return record, Provenance(source=self.name, url=url, confidence=0.9)
