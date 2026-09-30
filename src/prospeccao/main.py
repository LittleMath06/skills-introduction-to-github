"""Fábrica da aplicação FastAPI."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .config import Settings, get_settings
from .db import create_all, get_engine, init_engine, new_session
from .security import NotAuthenticated, current_user
from .services.bootstrap import bootstrap
from .services.jobs import JobRunner, recover_stale_jobs
from .services.tasks import Sources

log = logging.getLogger("prospeccao")

CSP = ("default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class _RedactFilter(logging.Filter):
    """Evita que senhas/tokens apareçam nos logs."""

    KEYS = ("password", "senha", "secret", "token", "csrf")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        if any(k in msg.lower() for k in self.KEYS) and "=" in msg:
            record.msg = "[mensagem com possível segredo omitida]"
            record.args = ()
        return True


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(_RedactFilter())


def create_app(settings: Settings | None = None, runner: JobRunner | None = None,
               sources: Sources | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_engine(settings.database_url)
    create_all()
    with new_session() as s:
        bootstrap(s, settings)
        recover_stale_jobs(s)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.runner.shutdown()
        get_engine().dispose()

    app = FastAPI(title="Prospecção de Clientes — API", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.runner = runner or JobRunner()
    app.state.sources = sources or Sources(settings)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if not request.url.path.startswith("/static"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.add_middleware(
        SessionMiddleware, secret_key=settings.secret_key, session_cookie="prospeccao_session",
        max_age=settings.session_max_age, same_site="lax", https_only=settings.is_production,
    )

    # OpenAPI protegido por login
    @app.get("/api/openapi.json", include_in_schema=False, dependencies=[Depends(current_user)])
    def openapi_json():
        return app.openapi()

    @app.get("/api/docs", include_in_schema=False, dependencies=[Depends(current_user)])
    def api_docs():
        resp = get_swagger_ui_html(openapi_url="/api/openapi.json", title="API — Prospecção")
        # O Swagger UI é servido pelo CDN jsDelivr e usa script inline: CSP própria só nesta página
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' https://cdn.jsdelivr.net; img-src 'self' data: https:; "
            "frame-ancestors 'none'")
        return resp

    @app.get("/health", include_in_schema=False)
    def health():
        from sqlalchemy import text

        try:
            with new_session() as s:
                s.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            return JSONResponse({"status": "erro", "db": False}, status_code=503)
        return {"status": "ok", "db": True, "version": __version__}

    @app.exception_handler(NotAuthenticated)
    async def not_authenticated(request: Request, exc: NotAuthenticated):
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": "Não autenticado"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api") or request.method != "GET":
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                                headers=getattr(exc, "headers", None))
        from .web.routes import render

        resp = render(request, "error.html", message=exc.detail, code=exc.status_code)
        resp.status_code = exc.status_code
        return resp

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [{"campo": ".".join(str(x) for x in e.get("loc", [])[1:]),
                   "erro": e.get("msg", "").replace("Value error, ", "")} for e in exc.errors()]
        return JSONResponse({"detail": "Dados inválidos", "erros": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        ref = uuid.uuid4().hex[:8]
        log.exception("Erro não tratado [%s] em %s %s", ref, request.method, request.url.path)
        msg = f"Erro interno. Referência: {ref}"
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": msg}, status_code=500)
        return HTMLResponse(f"<h1>Erro</h1><p>{msg}</p>", status_code=500)

    from .api.routes import router as api_router
    from .web.routes import protected, router as web_router

    app.include_router(api_router)
    app.include_router(web_router)
    app.include_router(protected)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")),
              name="static")
    return app


def app_factory() -> FastAPI:  # usado por: uvicorn prospeccao.main:app_factory --factory
    return create_app()
