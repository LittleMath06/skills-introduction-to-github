from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(database_url: str) -> Engine:
    """Cria (ou recria) o engine global. Chamado na inicialização da app e nos testes."""
    global _engine, _SessionLocal
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Banco não inicializado")
    return _engine


def create_all() -> None:
    from . import models  # noqa: F401  (registra mapeamentos)

    engine = get_engine()
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        _postgres_search_index(engine)


def _postgres_search_index(engine: Engine) -> None:
    """Índice trigram para a busca por termos (LIKE '%termo%') em bases grandes.

    Requer a extensão pg_trgm; sem permissão para criá-la, a busca continua funcionando
    (apenas sem o índice) e um aviso é registrado.
    """
    import logging

    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_companies_search_trgm "
                "ON companies USING gin (search_text gin_trgm_ops)"
            ))
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).warning("Índice trigram não criado: %s", exc.__class__.__name__)


def new_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Banco não inicializado")
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """Dependência FastAPI."""
    session = new_session()
    try:
        yield session
    finally:
        session.close()
