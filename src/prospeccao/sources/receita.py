"""Dados Abertos do CNPJ — Receita Federal (fonte principal).

Layout conforme "Novo Layout para os Dados Abertos do CNPJ" (cnpj-metadados.pdf):
CSV sem cabeçalho, separador ';', aspas '"', ISO-8859-1, datas AAAAMMDD.
Os arquivos podem ser lidos diretamente dos ZIPs oficiais ou de CSVs já extraídos.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterator
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from ..domain import cnpj as cnpj_mod
from ..domain.text import clean_name, normalize_cep, normalize_email, normalize_phone
from .base import CNPJSource, SourceError, SourceStatus

csv.field_size_limit(10_000_000)

FILE_KINDS = {
    "estabelecimentos": re.compile(r"estabele", re.I),
    "empresas": re.compile(r"empresa", re.I),
    "simples": re.compile(r"simples", re.I),
    "cnaes": re.compile(r"cnae", re.I),
    "municipios": re.compile(r"munic", re.I),
    "naturezas": re.compile(r"natureza|natju", re.I),
}

EST_COLUMNS = [
    "cnpj_basico", "cnpj_ordem", "cnpj_dv", "matriz_filial", "nome_fantasia", "situacao",
    "data_situacao", "motivo_situacao", "cidade_exterior", "pais", "data_inicio", "cnae_principal",
    "cnae_secundaria", "tipo_logradouro", "logradouro", "numero", "complemento", "bairro", "cep",
    "uf", "municipio", "ddd1", "tel1", "ddd2", "tel2", "ddd_fax", "fax", "email",
    "situacao_especial", "data_situacao_especial",
]
EMP_COLUMNS = ["cnpj_basico", "razao_social", "natureza_juridica", "qualificacao_responsavel",
               "capital_social", "porte", "ente_federativo"]
SIMPLES_COLUMNS = ["cnpj_basico", "opcao_simples", "data_opcao_simples", "data_exclusao_simples",
                   "opcao_mei", "data_opcao_mei", "data_exclusao_mei"]


class LayoutError(SourceError):
    pass


def parse_date(value: str | None) -> date | None:
    v = (value or "").strip()
    if not re.fullmatch(r"\d{8}", v) or v == "00000000":
        return None
    try:
        return date(int(v[:4]), int(v[4:6]), int(v[6:]))
    except ValueError:
        return None


def parse_decimal(value: str | None) -> Decimal | None:
    v = (value or "").strip().replace(".", "").replace(",", ".")
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def _sn(value: str | None) -> bool | None:
    v = (value or "").strip().upper()
    return True if v == "S" else False if v == "N" else None


def _row_dict(row: list[str], columns: list[str], kind: str) -> dict[str, str]:
    if len(row) < len(columns):
        raise LayoutError(f"{kind}: esperado {len(columns)} colunas, recebido {len(row)}")
    return {c: (row[i] or "").strip() for i, c in enumerate(columns)}


def parse_estabelecimento(row: list[str]) -> dict:
    r = _row_dict(row, EST_COLUMNS, "Estabelecimentos")
    raw_cnpj = f"{r['cnpj_basico']}{r['cnpj_ordem']}{r['cnpj_dv']}"
    cnpj = cnpj_mod.validate(raw_cnpj)
    street = " ".join(p for p in [r["tipo_logradouro"], r["logradouro"]] if p)
    phones = [p for p in (normalize_phone(r["ddd1"], r["tel1"]),
                          normalize_phone(r["ddd2"], r["tel2"])) if p]
    return {
        "cnpj": cnpj,
        "cnpj_basico": cnpj[:8],
        "is_matriz": r["matriz_filial"] == "1",
        "nome_fantasia": clean_name(r["nome_fantasia"]),
        "situacao_cadastral": r["situacao"].zfill(2) if r["situacao"] else None,
        "data_situacao": parse_date(r["data_situacao"]),
        "data_abertura": parse_date(r["data_inicio"]),
        "cnae_principal": r["cnae_principal"].zfill(7) if r["cnae_principal"] else None,
        "cnaes_secundarios": [c.strip().zfill(7) for c in r["cnae_secundaria"].split(",")
                              if c.strip()],
        "logradouro": clean_name(street),
        "numero": clean_name(r["numero"]),
        "complemento": clean_name(r["complemento"]),
        "bairro": clean_name(r["bairro"]),
        "cep": normalize_cep(r["cep"]),
        "uf": r["uf"].upper() or None,
        "municipio_code": r["municipio"] or None,
        "phones": list(dict.fromkeys(phones)),
        "email": normalize_email(r["email"]),
    }


def parse_empresa(row: list[str]) -> dict:
    r = _row_dict(row, EMP_COLUMNS, "Empresas")
    return {
        "cnpj_basico": r["cnpj_basico"].zfill(8),
        "razao_social": clean_name(r["razao_social"]),
        "natureza_juridica_code": r["natureza_juridica"] or None,
        "capital_social": parse_decimal(r["capital_social"]),
        "porte": r["porte"].zfill(2) if r["porte"] else None,
    }


def parse_simples(row: list[str]) -> dict:
    r = _row_dict(row, SIMPLES_COLUMNS, "Simples")
    return {
        "cnpj_basico": r["cnpj_basico"].zfill(8),
        "simples_opcao": _sn(r["opcao_simples"]),
        "simples_data_opcao": parse_date(r["data_opcao_simples"]),
        "simples_data_exclusao": parse_date(r["data_exclusao_simples"]),
        "mei_opcao": _sn(r["opcao_mei"]),
    }


def parse_lookup(row: list[str]) -> tuple[str, str]:
    if len(row) < 2:
        raise LayoutError("Tabela auxiliar: esperado código;descrição")
    return row[0].strip(), clean_name(row[1]) or ""


def iter_rows(path: Path) -> Iterator[list[str]]:
    """Itera linhas de um CSV ou de todos os membros de um ZIP (streaming, sem extrair)."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                with zf.open(member) as fh:
                    text = io.TextIOWrapper(fh, encoding="latin-1", errors="replace", newline="")
                    yield from csv.reader(text, delimiter=";", quotechar='"')
    else:
        with open(path, encoding="latin-1", errors="replace", newline="") as fh:
            yield from csv.reader(fh, delimiter=";", quotechar='"')


def classify_files(directory: Path) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {k: [] for k in FILE_KINDS}
    if not directory.is_dir():
        return out
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.suffix.lower() == ".part":
            continue
        for kind, pattern in FILE_KINDS.items():
            if pattern.search(path.name):
                out[kind].append(path)
                break
    return out


class ReceitaOpenDataSource(CNPJSource):
    key = "receita_open_data"
    name = "Receita Federal — Dados Abertos do CNPJ"

    def __init__(self, base_url: str, files_dir: Path, user_agent: str,
                 client: httpx.Client | None = None):
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.files_dir = files_dir
        self.user_agent = user_agent
        self._client = client

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(
            timeout=httpx.Timeout(30, read=120), headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )

    def check(self) -> SourceStatus:
        files = classify_files(self.files_dir)
        local = sum(len(v) for v in files.values())
        try:
            with self._http() as client:
                resp = client.get(self.base_url)
            remote = f"servidor respondeu HTTP {resp.status_code}"
            ok = resp.status_code == 200
        except httpx.HTTPError as exc:
            remote, ok = f"servidor indisponível ({exc.__class__.__name__})", False
        return SourceStatus(ok or local > 0, f"{remote}; {local} arquivo(s) local(is) em {self.files_dir}")

    def latest_month(self) -> str:
        """Descobre a pasta AAAA-MM mais recente no servidor da Receita."""
        with self._http() as client:
            resp = client.get(self.base_url)
        if resp.status_code != 200:
            raise SourceError(f"Listagem da Receita retornou HTTP {resp.status_code}")
        months = sorted(set(re.findall(r"(\d{4}-\d{2})/", resp.text)))
        if not months:
            raise SourceError("Nenhuma pasta AAAA-MM encontrada na listagem da Receita")
        return months[-1]

    def list_remote_files(self, month: str) -> list[str]:
        with self._http() as client:
            resp = client.get(f"{self.base_url}{month}/")
        if resp.status_code != 200:
            raise SourceError(f"Listagem de {month} retornou HTTP {resp.status_code}")
        return sorted(set(re.findall(r'href="([^"/]+\.zip)"', resp.text, re.I)))

    def download(self, month: str, names: list[str], progress=None) -> list[Path]:
        """Baixa sequencialmente (sem paralelismo) os ZIPs indicados para files_dir/month."""
        dest_dir = self.files_dir / month
        dest_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        with self._http() as client:
            for i, name in enumerate(names, 1):
                target = dest_dir / name
                if target.exists() and zipfile.is_zipfile(target):
                    saved.append(target)
                    continue
                tmp = target.with_suffix(".part")
                with client.stream("GET", f"{self.base_url}{month}/{name}") as resp:
                    if resp.status_code != 200:
                        raise SourceError(f"Download de {name} retornou HTTP {resp.status_code}")
                    with open(tmp, "wb") as fh:
                        for chunk in resp.iter_bytes(1 << 20):
                            fh.write(chunk)
                if not zipfile.is_zipfile(tmp):
                    tmp.unlink(missing_ok=True)
                    raise SourceError(f"{name} baixado não é um ZIP válido")
                tmp.rename(target)
                saved.append(target)
                if progress:
                    progress(i, len(names), name)
        return saved
