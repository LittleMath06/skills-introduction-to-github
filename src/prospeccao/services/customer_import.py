"""Importação, validação e normalização da base de clientes atuais (CSV ou XLSX)."""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import cnpj as cnpj_mod
from ..domain.names import NameIndex, name_key, resolve_candidates
from ..domain.regions import normalize_uf
from ..domain.text import clean_name, norm, only_digits, tokens
from ..models import Company, Customer

MAX_ROWS = 50_000
MAX_BYTES = 20 * 1024 * 1024

# Sinônimos de cabeçalho (normalizados: minúsculo, sem acento, sem pontuação)
HEADER_SYNONYMS = {
    "cnpj": ["cnpj", "cnpj cpf", "cpf cnpj", "documento", "cnpj do cliente", "cnpj cliente", "doc"],
    "razao_social": ["razao social", "razao", "nome empresarial", "cliente", "empresa", "nome",
                     "nome do cliente"],
    "nome_fantasia": ["nome fantasia", "fantasia"],
    "municipio": ["cidade", "municipio", "localidade"],
    "uf": ["uf", "estado", "sigla uf"],
    "cnae": ["cnae", "cnae principal", "codigo cnae", "cnae fiscal"],
    "segmento": ["segmento", "ramo", "setor", "categoria", "tipo de cliente", "atividade"],
    "porte": ["porte"],
}
_PORTE_TEXT = {"me": "01", "micro": "01", "micro empresa": "01", "microempresa": "01",
               "epp": "03", "pequeno porte": "03", "empresa de pequeno porte": "03",
               "demais": "05", "grande": "05", "media": "05"}


@dataclass
class ImportReport:
    batch: str
    total_rows: int = 0
    imported: int = 0
    updated: int = 0
    duplicates_in_file: int = 0
    invalid_cnpj: list[dict] = field(default_factory=list)
    without_cnpj: int = 0
    linked: int = 0
    not_found: int = 0
    ignored_empty: int = 0
    columns: dict[str, str] = field(default_factory=dict)
    unmapped_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {**self.__dict__, "invalid_cnpj": self.invalid_cnpj[:200],
                "invalid_cnpj_count": len(self.invalid_cnpj)}


class ImportError_(ValueError):
    pass


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", norm(h)).strip()


def map_headers(headers: list[str]) -> tuple[dict[str, int], list[str]]:
    normalized = [re.sub(r"\s+", " ", _norm_header(h or "")) for h in headers]
    mapping: dict[str, int] = {}
    for fieldname, synonyms in HEADER_SYNONYMS.items():
        for syn in synonyms:  # ordem de preferência
            if syn in normalized and normalized.index(syn) not in mapping.values():
                mapping[fieldname] = normalized.index(syn)
                break
    unmapped = [headers[i] for i in range(len(headers)) if i not in mapping.values() and headers[i]]
    return mapping, unmapped


def read_table(filename: str, content: bytes) -> list[list[str]]:
    if len(content) > MAX_BYTES:
        raise ImportError_("Arquivo maior que 20 MB")
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # arquivo corrompido ou não-XLSX
            raise ImportError_("Não foi possível ler a planilha XLSX") from exc
        ws = wb.worksheets[0]
        rows = [["" if v is None else str(v) for v in row]
                for row in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    if name.endswith((".csv", ".txt")):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sample = text[:5000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    raise ImportError_("Formato não suportado. Envie .csv ou .xlsx")


_NAME_WORDS = ("cliente", "empresa", "razao", "nome", "fornecedor")


def _name_only_header(row: list[str]) -> int | None:
    """Planilha com uma única coluna de nomes (ex.: "Clientes que já tiveram cotação")."""
    filled = [i for i, h in enumerate(row) if (h or "").strip()]
    if len(filled) == 1:
        header = _norm_header(row[filled[0]])
        if any(w in header for w in _NAME_WORDS) and not re.search(r"\d{8,}", header):
            return filled[0]
    return None


def _find_header_row(rows: list[list[str]]) -> tuple[int, dict[str, int] | None]:
    for i, row in enumerate(rows[:20]):
        mapping, _ = map_headers(row)
        if "cnpj" in mapping or "razao_social" in mapping:
            return i, None
    # nenhuma linha com cabeçalho reconhecido: planilha de uma coluna só com nomes
    for i, row in enumerate(rows[:20]):
        col = _name_only_header(row)
        if col is not None:
            return i, {"razao_social": col}
    raise ImportError_("Cabeçalho não reconhecido: é necessária a coluna CNPJ ou uma coluna "
                       "com o nome/razão social das empresas")


def import_customers(session: Session, filename: str, content: bytes) -> ImportReport:
    rows = read_table(filename, content)
    header_idx, forced = _find_header_row(rows)
    headers = rows[header_idx]
    mapping, unmapped = map_headers(headers)
    if forced:
        mapping = forced
        unmapped = [h for i, h in enumerate(headers) if h and i not in forced.values()]
    report = ImportReport(batch=uuid.uuid4().hex[:12])
    report.columns = {k: headers[v] for k, v in mapping.items()}
    report.unmapped_columns = unmapped
    data_rows = rows[header_idx + 1:]
    if len(data_rows) > MAX_ROWS:
        raise ImportError_(f"Máximo de {MAX_ROWS} linhas por importação")

    def cell(row: list[str], fieldname: str) -> str | None:
        idx = mapping.get(fieldname)
        if idx is None or idx >= len(row):
            return None
        v = (row[idx] or "").strip()
        return v or None

    seen: set[str] = set()
    seen_names: set[str] = set()
    for line_no, row in enumerate(data_rows, start=header_idx + 2):
        if not any((c or "").strip() for c in row):
            report.ignored_empty += 1
            continue
        report.total_rows += 1
        raw_cnpj = cell(row, "cnpj")
        cnpj = None
        if raw_cnpj:
            cleaned = cnpj_mod.clean(raw_cnpj)
            if not cnpj_mod.is_valid(cleaned):
                # 11 dígitos que não formam CNPJ válido: provavelmente CPF (pessoa física)
                is_cpf = len(only_digits(raw_cnpj)) == 11
                report.invalid_cnpj.append({
                    "linha": line_no,
                    "valor": f"{raw_cnpj} (CPF/pessoa física — ignorado)" if is_cpf else raw_cnpj,
                })
                continue
            cnpj = cleaned
            if cnpj in seen:
                report.duplicates_in_file += 1
                continue
            seen.add(cnpj)
        cnae = only_digits(cell(row, "cnae") or "")
        cnae = cnae.zfill(7) if 5 <= len(cnae) <= 7 else None
        porte_raw = norm(cell(row, "porte"))
        values = {
            "razao_social": clean_name(cell(row, "razao_social")),
            "nome_fantasia": clean_name(cell(row, "nome_fantasia")),
            "municipio": clean_name(cell(row, "municipio")),
            "uf": normalize_uf(cell(row, "uf")),
            "cnae": cnae,
            "segmento_informado": clean_name(cell(row, "segmento")),
            "porte": porte_raw if porte_raw in {"00", "01", "03", "05"} else _PORTE_TEXT.get(porte_raw),
            "raw": {headers[i]: (row[i] if i < len(row) else None)
                    for i in range(len(headers)) if headers[i]},
        }
        if not cnpj and not (values["cnae"] or values["uf"] or values["razao_social"]):
            report.ignored_empty += 1
            continue
        key = name_key(values["razao_social"]) or None
        values["name_key"] = key[:255] if key else None
        if cnpj:
            customer = session.scalar(select(Customer).where(Customer.cnpj == cnpj))
            if customer is None and key:
                # cliente importado antes só pelo nome, agora com CNPJ: completa o mesmo registro
                customer = session.scalar(select(Customer).where(
                    Customer.cnpj.is_(None), Customer.name_key == key))
                if customer is not None:
                    customer.cnpj = cnpj
        else:
            # sem CNPJ: o nome normalizado é a chave de deduplicação
            if key and key in seen_names:
                report.duplicates_in_file += 1
                continue
            if key:
                seen_names.add(key)
            customer = session.scalar(select(Customer).where(
                Customer.cnpj.is_(None), Customer.name_key == key)) if key else None
        if customer is None:
            customer = Customer(cnpj=cnpj, import_batch=report.batch, **values)
            session.add(customer)
            report.imported += 1
        else:
            for k, v in values.items():
                if v is not None:
                    setattr(customer, k, v)
            customer.import_batch = report.batch
            report.updated += 1
        if not cnpj:
            report.without_cnpj += 1
            if customer.company_id is None:  # mantém vínculo já feito (por nome ou manual)
                customer.status = "sem_cnpj"
            continue
        company = session.scalar(select(Company).where(Company.cnpj == cnpj))
        customer.company_id = company.id if company else None
        customer.status = "ok" if company else "nao_encontrado"
        customer.match_method = "cnpj"
        if company:
            report.linked += 1
        else:
            report.not_found += 1
    session.flush()
    return report


def link_customer(customer: Customer, company: Company, method: str, note: str | None = None) -> None:
    customer.company_id = company.id
    customer.cnpj = customer.cnpj or company.cnpj
    customer.status = "ok"
    customer.match_method = method
    customer.match_note = note


def relink_customers(session: Session) -> int:
    """Liga clientes a empresas da base local: pelo CNPJ ('nao_encontrado') e, para clientes
    informados só pelo nome ('sem_cnpj'/'ambiguo'), pela razão social (regras em domain.names)."""
    linked = 0
    for customer in session.scalars(
        select(Customer).where(Customer.status == "nao_encontrado")
    ).all():
        company = session.scalar(select(Company).where(Company.cnpj == customer.cnpj))
        if company:
            link_customer(customer, company, "cnpj")
            linked += 1

    pending = {c.id: c for c in session.scalars(select(Customer).where(
        Customer.cnpj.is_(None), Customer.status.in_(["sem_cnpj", "ambiguo"]))).all()
        if c.razao_social}
    if not pending:
        return linked
    index = NameIndex({cid: c.razao_social for cid, c in pending.items()})
    candidates: dict[int, dict[str, tuple[Company, str]]] = {}
    for cid, customer in pending.items():
        # pré-filtro no banco pelas 2 palavras mais longas do nome; comparação final em Python
        words = sorted((w for w in tokens(customer.razao_social, min_len=3)), key=len,
                       reverse=True)[:2]
        if not words:
            continue
        stmt = select(Company).where(*[Company.search_text.like(f"%{w}%") for w in words]).limit(200)
        for company in session.scalars(stmt).unique():
            hit = index.match(company.razao_social)
            if hit and hit[0] == cid:
                candidates.setdefault(cid, {})[company.cnpj_basico] = (company, hit[1])
    unique, ambiguous = resolve_candidates({cid: set(v) for cid, v in candidates.items()})
    for cid, basico in unique.items():
        company, method = candidates[cid][basico]
        if not company.is_matriz:  # prefere a matriz do grupo
            company = session.scalar(select(Company).where(
                Company.cnpj_basico == basico, Company.is_matriz.is_(True))) or company
        link_customer(pending[cid], company, method,
                      "Vinculado pela razão social — confira se é a empresa correta")
        linked += 1
    for cid in ambiguous:
        pending[cid].status = "ambiguo"
        pending[cid].match_note = (f"{len(candidates[cid])} empresas com o mesmo nome — "
                                   "informe o CNPJ manualmente")
    return linked
