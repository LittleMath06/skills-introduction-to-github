"""Processamento em background com progresso persistido no banco.

Um único worker (thread) executa os jobs em série — evita concorrência de escrita e é suficiente
para um usuário. Em testes o runner pode ser síncrono.
"""
from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..db import new_session
from ..models import Job, utcnow

log = logging.getLogger(__name__)
MAX_LOG_LINES = 200


class JobContext:
    def __init__(self, job_id: int):
        self.job_id = job_id
        self.session: Session = new_session()
        self._log: list[str] = []
        self._errors = 0

    @property
    def job(self) -> Job:
        return self.session.get(Job, self.job_id)

    def _update(self, **values) -> None:
        # Sessão separada para que o progresso seja visível mesmo se o trabalho fizer rollback.
        # Falha ao gravar progresso não pode derrubar o processo: apenas registra no log.
        try:
            with new_session() as s:
                job = s.get(Job, self.job_id)
                for k, v in values.items():
                    setattr(job, k, v)
                s.commit()
        except SQLAlchemyError as exc:
            log.warning("job %s: não foi possível gravar progresso (%s)", self.job_id,
                        exc.__class__.__name__)

    def set_total(self, total: int | None) -> None:
        self._update(total=total)

    def progress(self, processed: int, message: str | None = None) -> None:
        values = {"processed": processed}
        if message:
            values["message"] = message
        self._update(**values)

    def info(self, message: str) -> None:
        log.info("job %s: %s", self.job_id, message)
        self._log.append(message)
        self._update(log=self._log[-MAX_LOG_LINES:], message=message)

    def error(self, message: str) -> None:
        log.warning("job %s: %s", self.job_id, message)
        self._errors += 1
        self._log.append("ERRO: " + message)
        self._update(log=self._log[-MAX_LOG_LINES:], errors_count=self._errors)

    def close(self) -> None:
        self.session.close()


JobFunc = Callable[[JobContext, dict], str | None]


class JobRunner:
    def __init__(self, synchronous: bool = False):
        self.synchronous = synchronous
        self._executor = None if synchronous else ThreadPoolExecutor(max_workers=1,
                                                                     thread_name_prefix="job")

    def submit(self, session: Session, kind: str, params: dict, func: JobFunc) -> Job:
        running = session.scalar(select(Job).where(Job.kind == kind,
                                                   Job.status.in_(["queued", "running"])))
        if running is not None:
            return running
        job = Job(kind=kind, params=params, status="queued", log=[])
        session.add(job)
        session.commit()
        if self.synchronous:
            self._run(job.id, func, params)
            session.refresh(job)
        else:
            self._executor.submit(self._run, job.id, func, params)
        return job

    def _run(self, job_id: int, func: JobFunc, params: dict) -> None:
        ctx = JobContext(job_id)
        ctx._update(status="running", started_at=utcnow())
        try:
            message = func(ctx, params)
            ctx._update(status="done", finished_at=utcnow(),
                        message=message or "Concluído")
        except Exception as exc:  # registra e não derruba o worker
            log.error("job %s falhou: %s\n%s", job_id, exc, traceback.format_exc())
            ctx.session.rollback()
            ctx.error(f"{exc.__class__.__name__}: {exc}")
            ctx._update(status="failed", finished_at=utcnow(),
                        message="Falhou — veja o log do processo")
        finally:
            ctx.close()

    def shutdown(self) -> None:
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)


def recover_stale_jobs(session: Session) -> None:
    """Jobs 'running' de um processo anterior (reinício) são marcados como falhos."""
    for job in session.scalars(select(Job).where(Job.status.in_(["queued", "running"]))).all():
        job.status = "failed"
        job.message = "Interrompido por reinício da aplicação"
        job.finished_at = utcnow()
    session.commit()
