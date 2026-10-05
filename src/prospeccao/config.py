"""Configuração lida exclusivamente de variáveis de ambiente (ou arquivo .env local).

Nenhum segredo possui valor real no código. Em produção a aplicação recusa iniciar com a
SECRET_KEY padrão de desenvolvimento.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DEV_SECRET = "dev-insecure-secret-change-me"


def _load_dotenv(path: Path) -> None:
    """Carrega um .env simples (CHAVE=valor) sem sobrescrever variáveis já definidas."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "on"}


def _list(name: str) -> list[str]:
    value = os.environ.get(name, "")
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    env: str
    secret_key: str
    database_url: str
    data_dir: Path
    session_max_age: int
    admin_username: str
    admin_password: str | None
    allow_mock_data: bool
    rf_base_url: str
    rf_filter_ufs: list[str]
    rf_filter_cnae_prefixes: list[str]
    rf_only_active: bool
    cnpj_api_provider: str
    cnpj_api_min_interval: float
    website_enrichment_enabled: bool
    website_min_interval: float
    http_user_agent: str
    icms_cert_file: str | None
    icms_key_file: str | None
    icms_endpoints: dict[str, str] = field(default_factory=dict)
    icms_environment: str = "1"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def normalize_database_url(url: str) -> str:
    """Hospedagens (Render, Railway, Heroku…) fornecem 'postgres://' ou 'postgresql://';
    o driver instalado é o psycopg 3, que o SQLAlchemy espera como 'postgresql+psycopg://'."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def load_settings() -> Settings:
    _load_dotenv(Path(os.environ.get("ENV_FILE", ".env")))
    env = os.environ.get("APP_ENV", "development").lower()
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    # vazio no .env conta como "não definido" (usa a chave de desenvolvimento; bloqueada em produção)
    secret = os.environ.get("SECRET_KEY") or DEV_SECRET
    try:
        endpoints = json.loads(os.environ.get("ICMS_ENDPOINTS", "{}") or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("ICMS_ENDPOINTS deve ser um JSON {\"UF\": \"url\"}") from exc
    settings = Settings(
        env=env,
        secret_key=secret,
        database_url=normalize_database_url(
            os.environ.get("DATABASE_URL") or f"sqlite:///{data_dir / 'prospeccao.db'}"),
        data_dir=data_dir,
        session_max_age=int(os.environ.get("SESSION_MAX_AGE", str(8 * 3600))),
        admin_username=os.environ.get("ADMIN_USERNAME", "paulo"),
        admin_password=os.environ.get("ADMIN_PASSWORD") or None,
        allow_mock_data=_bool("ALLOW_MOCK_DATA", env != "production"),
        rf_base_url=os.environ.get(
            "RF_BASE_URL", "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/"
        ),
        rf_filter_ufs=[u.upper() for u in _list("RF_FILTER_UFS")],
        rf_filter_cnae_prefixes=_list("RF_FILTER_CNAE_PREFIXES"),
        rf_only_active=_bool("RF_ONLY_ACTIVE", True),
        cnpj_api_provider=os.environ.get("CNPJ_API_PROVIDER", "brasilapi").lower(),
        cnpj_api_min_interval=float(os.environ.get("CNPJ_API_MIN_INTERVAL", "3")),
        website_enrichment_enabled=_bool("WEBSITE_ENRICHMENT_ENABLED", True),
        website_min_interval=float(os.environ.get("WEBSITE_MIN_INTERVAL", "5")),
        http_user_agent=os.environ.get(
            "HTTP_USER_AGENT", "ProspeccaoBot/1.0 (+uso privado; contato no site do operador)"
        ),
        icms_cert_file=os.environ.get("ICMS_CERT_FILE") or None,
        icms_key_file=os.environ.get("ICMS_KEY_FILE") or None,
        icms_endpoints={k.upper(): v for k, v in endpoints.items()},
        icms_environment=os.environ.get("ICMS_ENVIRONMENT", "1"),
    )
    if settings.is_production:
        if settings.secret_key == DEV_SECRET or len(settings.secret_key) < 32:
            raise RuntimeError("SECRET_KEY forte (>= 32 caracteres) é obrigatória em produção.")
        if settings.allow_mock_data:
            raise RuntimeError("ALLOW_MOCK_DATA não pode estar ativo em produção.")
    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()
