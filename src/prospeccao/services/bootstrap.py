"""Dados iniciais obrigatórios (segmentos, status, fontes) e usuário administrador."""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..domain.segments import DEFAULT_SEGMENTS
from ..models import Segment, User
from ..security import hash_password
from .leads import ensure_statuses
from .sources_status import ensure_sources

log = logging.getLogger(__name__)


def ensure_segments(session: Session) -> None:
    if session.scalar(select(func.count(Segment.id))):
        return
    for s in DEFAULT_SEGMENTS:
        session.add(Segment(
            name=s["name"], description=s["description"],
            cnae_prefixes=",".join(s["cnae_prefixes"]), keywords=",".join(s["keywords"]),
            is_fallback=s.get("is_fallback", False),
        ))
    session.flush()


def ensure_admin(session: Session, settings: Settings) -> None:
    if session.scalar(select(func.count(User.id))):
        return
    if not settings.admin_password:
        log.warning("Nenhum usuário cadastrado. Defina ADMIN_PASSWORD ou rode "
                    "`python -m prospeccao.cli set-password`.")
        return
    session.add(User(username=settings.admin_username.lower(),
                     password_hash=hash_password(settings.admin_password)))
    log.info("Usuário %s criado a partir de ADMIN_PASSWORD", settings.admin_username)


def set_password(session: Session, username: str, password: str) -> User:
    user = session.scalar(select(User).where(User.username == username.lower()))
    if user is None:
        user = User(username=username.lower(), password_hash=hash_password(password))
        session.add(user)
    else:
        user.password_hash = hash_password(password)
    return user


def bootstrap(session: Session, settings: Settings) -> None:
    ensure_segments(session)
    ensure_statuses(session)
    ensure_sources(session)
    ensure_admin(session, settings)
    session.commit()
