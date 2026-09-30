"""Abstração de fontes de dados.

DataSource
 ├── CNPJSource            (ReceitaOpenDataSource, CnpjApiSource)
 ├── ICMSSource            (SefazIcmsSource)
 └── CompanyWebsiteSource  (WebsiteSource)

Cada resultado carrega metadados de origem para rastreabilidade.
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone


class SourceError(Exception):
    """Falha da fonte (indisponível, resposta inválida, limite atingido...)."""


class SourceNotConfigured(SourceError):
    pass


@dataclass
class Provenance:
    source: str
    url: str | None = None
    fetched_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    reference_date: date | None = None
    confidence: float = 1.0


@dataclass
class SourceStatus:
    ok: bool
    message: str


class DataSource(ABC):
    key: str = ""
    name: str = ""
    kind: str = ""

    def is_enabled(self) -> bool:
        return True

    @abstractmethod
    def check(self) -> SourceStatus:
        """Verificação leve de disponibilidade/configuração (não consome cota significativa)."""


class CNPJSource(DataSource, ABC):
    kind = "cnpj"


class ICMSSource(DataSource, ABC):
    kind = "icms"


class CompanyWebsiteSource(DataSource, ABC):
    kind = "website"


class RateLimiter:
    """Intervalo mínimo entre chamadas por chave (ex.: domínio). Thread-safe."""

    def __init__(self, min_interval: float, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = min_interval
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self._clock = clock
        self._sleep = sleep

    def wait(self, key: str = "default") -> None:
        with self._lock:
            now = self._clock()
            last = self._last.get(key)
            delay = 0.0 if last is None else self.min_interval - (now - last)
            self._last[key] = now + max(0.0, delay)
        if delay > 0:
            self._sleep(delay)
