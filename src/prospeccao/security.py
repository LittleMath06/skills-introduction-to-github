"""Autenticação (usuário único), hash de senha, CSRF e rate limiting."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

# scrypt: N=2^15, r=8, p=1 (~32 MB) — parâmetros recomendados pela OWASP
_N, _R, _P, _DKLEN = 2**15, 8, 1, 64
_MAXMEM = 128 * 1024 * 1024
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha deve ter ao menos {MIN_PASSWORD_LENGTH} caracteres")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = encoded.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r),
                            p=int(p), dklen=len(expected), maxmem=_MAXMEM)
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# Hash fixo usado para gastar o mesmo tempo quando o usuário não existe (evita enumeração)
_DUMMY_HASH: str | None = None


def authenticate(session: Session, username: str, password: str) -> User | None:
    global _DUMMY_HASH
    user = session.scalar(select(User).where(User.username == (username or "").strip().lower()))
    if user is None:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
        verify_password(password or "", _DUMMY_HASH)
        return None
    return user if verify_password(password or "", user.password_hash) else None


class LoginRateLimiter:
    """No máximo `limit` falhas por IP em `window` segundos."""

    def __init__(self, limit: int = 5, window: int = 900):
        self.limit = limit
        self.window = window
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.limit

    def fail(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = LoginRateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def login_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session["uid"] = user.id
    request.session["csrf"] = secrets.token_urlsafe(32)
    request.session["iat"] = int(time.time())


class NotAuthenticated(Exception):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    max_age = request.app.state.settings.session_max_age
    if not uid or int(time.time()) - int(request.session.get("iat", 0)) > max_age:
        request.session.clear()
        raise NotAuthenticated()
    user = db.get(User, uid)
    if user is None:
        request.session.clear()
        raise NotAuthenticated()
    return user


async def require_csrf(request: Request) -> None:
    """Exige token CSRF em métodos que alteram estado (header ou campo de formulário)."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = request.session.get("csrf")
    sent = request.headers.get("x-csrf-token")
    if not sent and request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        form = await request.form()
        sent = form.get("csrf_token")
    if not expected or not sent or not hmac.compare_digest(str(sent), str(expected)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token CSRF inválido ou ausente")
