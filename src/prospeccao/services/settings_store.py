"""Configurações editáveis persistidas na tabela settings."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..domain.scoring import (
    DEFAULT_POTENTIAL_WEIGHTS,
    DEFAULT_SEGMENT_AFFINITY,
    DEFAULT_SIMILARITY_WEIGHTS,
    normalize_weights,
)
from ..models import Setting


def get(session: Session, key: str, default=None):
    row = session.get(Setting, key)
    return default if row is None or row.value is None else row.value


def put(session: Session, key: str, value) -> None:
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value


def similarity_weights(session: Session) -> dict[str, float]:
    return normalize_weights(get(session, "similarity_weights", {}), DEFAULT_SIMILARITY_WEIGHTS)


def potential_weights(session: Session) -> dict[str, float]:
    return normalize_weights(get(session, "potential_weights", {}), DEFAULT_POTENTIAL_WEIGHTS)


def segment_affinity(session: Session) -> dict[str, float]:
    return {**DEFAULT_SEGMENT_AFFINITY, **get(session, "segment_affinity", {})}
