from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, Customer, DataSource, Job, Lead, Segment, utcnow
from . import settings_store
from .sources_status import health


def summary(session: Session) -> dict:
    now = utcnow()
    prospects = select(Company).where(Company.is_customer.is_(False))
    count = lambda stmt: session.scalar(select(func.count()).select_from(stmt.subquery())) or 0  # noqa: E731
    active = prospects.where(Company.situacao_cadastral == "02")

    def group(column, limit=30):
        rows = session.execute(
            select(column, func.count(Company.id)).where(Company.is_customer.is_(False),
                                                         Company.situacao_cadastral == "02")
            .group_by(column).order_by(func.count(Company.id).desc()).limit(limit)
        ).all()
        return [{"label": label or "—", "count": n} for label, n in rows]

    by_segment = [
        {"label": name or "Não classificado", "count": n}
        for name, n in session.execute(
            select(Segment.name, func.count(Company.id))
            .select_from(Company).outerjoin(Segment, Segment.id == Company.segment_id)
            .where(Company.is_customer.is_(False), Company.situacao_cadastral == "02")
            .group_by(Segment.name).order_by(func.count(Company.id).desc())
        ).all()
    ]
    top = session.scalars(
        active.outerjoin(Lead, Lead.company_id == Company.id)
        .where((Lead.id.is_(None)) | (Lead.discarded.is_(False)))
        .order_by(Company.similarity.desc(), Company.potential.desc()).limit(8)
    ).unique().all()
    recent = session.scalars(
        prospects.order_by(Company.updated_at.desc()).limit(8)
    ).unique().all()
    sources = []
    for src in session.scalars(select(DataSource).order_by(DataSource.id)).all():
        level, msg = health(src)
        sources.append({"source": src, "level": level, "message": msg})
    return {
        "total_companies": count(select(Company)),
        "active_prospects": count(active),
        "new_last_30d": count(prospects.where(Company.first_seen_at >= now - timedelta(days=30))),
        "saved_leads": count(select(Lead).where(Lead.discarded.is_(False))),
        "customers": count(select(Customer)),
        "customers_linked": count(select(Customer).where(Customer.company_id.is_not(None))),
        "mock_companies": count(select(Company).where(Company.is_mock.is_(True))),
        "by_region": group(Company.region),
        "by_uf": group(Company.uf, 27),
        "by_segment": by_segment,
        "top_similarity": top,
        "recently_updated": recent,
        "sources": sources,
        "running_jobs": session.scalars(
            select(Job).where(Job.status.in_(["queued", "running"])).order_by(Job.id.desc())
        ).all(),
        "profile": settings_store.get(session, "customer_profile"),
    }
