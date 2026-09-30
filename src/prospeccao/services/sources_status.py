"""Registro e monitoramento do estado das fontes de dados."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DataSource, utcnow

DEFAULT_SOURCES = [
    ("receita_open_data", "Receita Federal — Dados Abertos do CNPJ", "cnpj", 45,
     "Arquivos mensais oficiais. Fonte principal."),
    ("cnpj_api", "API pública de CNPJ (consulta pontual)", "cnpj", 3650,
     "BrasilAPI/OpenCNPJ. Usada apenas sob demanda."),
    ("sefaz_icms", "SEFAZ — NfeConsultaCadastro (ICMS)", "icms", 180,
     "Requer certificado digital e endpoints por UF."),
    ("website", "Site oficial da empresa", "website", 3650,
     "Enriquecimento de contatos respeitando robots.txt."),
    ("customer_import", "Base de clientes atuais (importação)", "interna", 3650,
     "Planilha fornecida por Paulo."),
]


def ensure_sources(session: Session) -> None:
    existing = {s.key for s in session.scalars(select(DataSource)).all()}
    for key, name, kind, stale, notes in DEFAULT_SOURCES:
        if key not in existing:
            session.add(DataSource(key=key, name=name, kind=kind, stale_after_days=stale,
                                   notes=notes))
    session.flush()


def _get(session: Session, key: str) -> DataSource:
    src = session.scalar(select(DataSource).where(DataSource.key == key))
    if src is None:
        ensure_sources(session)
        src = session.scalar(select(DataSource).where(DataSource.key == key))
    return src


def record_success(session: Session, key: str, records: int | None = None,
                   reference: str | None = None) -> None:
    src = _get(session, key)
    src.last_success_at = utcnow()
    src.consecutive_failures = 0
    if records is not None:
        src.records_last_run = records
    if reference:
        src.last_reference = reference


def record_failure(session: Session, key: str, error: str) -> None:
    src = _get(session, key)
    src.last_error_at = utcnow()
    src.last_error = error[:1000]
    src.consecutive_failures += 1


def health(src: DataSource) -> tuple[str, str]:
    """(nível, mensagem) — nível: ok | alerta | erro | inativo."""
    now = utcnow()
    if not src.enabled:
        return "inativo", "Desativada"
    if src.consecutive_failures >= 3:
        return "erro", f"{src.consecutive_failures} falhas consecutivas"
    if src.last_error_at and (not src.last_success_at or src.last_error_at > src.last_success_at):
        return "alerta", "Último uso falhou"
    if src.last_success_at is None:
        return "alerta", "Nunca executada"
    if now - src.last_success_at > timedelta(days=src.stale_after_days):
        return "alerta", f"Dados desatualizados (> {src.stale_after_days} dias)"
    return "ok", "Operacional"
