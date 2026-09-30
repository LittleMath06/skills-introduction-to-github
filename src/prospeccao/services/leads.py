"""Leads: salvar, status comercial, favoritos, análise, descarte e observações."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, Lead, LeadNote, LeadStatus, utcnow

DEFAULT_STATUSES = [
    ("Novo", False), ("Analisar", False), ("Contato realizado", False), ("Em negociação", False),
    ("Cliente", True), ("Descartado", True),
]


class NotFound(LookupError):
    pass


def ensure_statuses(session: Session) -> None:
    if session.scalar(select(func.count(LeadStatus.id))):
        return
    for i, (name, final) in enumerate(DEFAULT_STATUSES):
        session.add(LeadStatus(name=name, position=i, is_final=final))
    session.flush()


def statuses(session: Session) -> list[LeadStatus]:
    return list(session.scalars(select(LeadStatus).order_by(LeadStatus.position)).all())


def get_or_create(session: Session, company_id: int) -> Lead:
    company = session.get(Company, company_id)
    if company is None:
        raise NotFound("Empresa não encontrada")
    if company.lead is not None:
        return company.lead
    first = statuses(session)[0]
    lead = Lead(company_id=company.id, status_id=first.id)
    session.add(lead)
    session.flush()
    session.refresh(company)
    return lead


def update(session: Session, lead_id: int, *, status_id: int | None = None,
           favorite: bool | None = None, analyzed: bool | None = None,
           discarded: bool | None = None) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFound("Lead não encontrado")
    if status_id is not None:
        if session.get(LeadStatus, status_id) is None:
            raise ValueError("Status inexistente")
        lead.status_id = status_id
        status = session.get(LeadStatus, status_id)
        if status.name == "Descartado":
            lead.discarded = True
    if favorite is not None:
        lead.favorite = favorite
    if analyzed is not None:
        lead.analyzed = analyzed
    if discarded is not None:
        lead.discarded = discarded
    lead.updated_at = utcnow()
    session.flush()
    return lead


def add_note(session: Session, lead_id: int, text: str) -> LeadNote:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFound("Lead não encontrado")
    text = (text or "").strip()
    if not text:
        raise ValueError("Observação vazia")
    if len(text) > 5000:
        raise ValueError("Observação muito longa (máx. 5000 caracteres)")
    note = LeadNote(lead_id=lead.id, text=text)
    session.add(note)
    lead.updated_at = utcnow()
    session.flush()
    return note


def delete_note(session: Session, note_id: int) -> None:
    note = session.get(LeadNote, note_id)
    if note is None:
        raise NotFound("Observação não encontrada")
    session.delete(note)


def list_leads(session: Session, *, status_id: int | None = None, favorite: bool | None = None,
               analyzed: bool | None = None, discarded: bool = False, page: int = 1,
               page_size: int = 25) -> dict:
    stmt = select(Lead).join(Company)
    if status_id:
        stmt = stmt.where(Lead.status_id == status_id)
    if favorite is not None:
        stmt = stmt.where(Lead.favorite.is_(favorite))
    if analyzed is not None:
        stmt = stmt.where(Lead.analyzed.is_(analyzed))
    stmt = stmt.where(Lead.discarded.is_(discarded))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = session.scalars(
        stmt.order_by(Lead.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).unique().all()
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": max(1, -(-total // page_size))}
