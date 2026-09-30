"""Normalização de textos, telefones, CEP e e-mails."""
from __future__ import annotations

import re
import unicodedata

STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
    "com", "para", "por", "um", "uma", "ao", "aos", "que", "se", "sem", "sob", "sobre",
    "ltda", "me", "epp", "eireli", "sa", "s/a", "cia", "companhia", "comercio", "comercial",
    "servicos", "servico", "industria", "empresa", "empresas", "brasil", "grupo", "filial",
    "matriz", "outros", "outras", "exceto", "nao", "especificados", "anteriormente", "atividades",
    "atividade", "produtos", "geral", "varejista", "atacadista", "fabricacao", "mock",
}

FREE_EMAIL_DOMAINS = {
    "gmail.com", "hotmail.com", "outlook.com", "live.com", "yahoo.com", "yahoo.com.br",
    "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br", "icloud.com", "msn.com",
    "globo.com", "globomail.com", "r7.com", "zipmail.com.br", "oi.com.br", "hotmail.com.br",
    "outlook.com.br", "live.com.br", "protonmail.com", "gmx.com", "aol.com", "me.com",
    "email.com", "yandex.com",
}

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def norm(text: str | None) -> str:
    """minúsculas, sem acento, espaços simples."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", strip_accents(str(text)).lower()).strip()


def tokens(text: str | None, min_len: int = 4) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9]+", norm(text)) if len(t) >= min_len and t not in STOPWORDS
    ]


def clean_name(text: str | None) -> str | None:
    if text is None:
        return None
    value = re.sub(r"\s+", " ", str(text)).strip()
    return value or None


def only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_phone(ddd: str | None, number: str | None) -> str | None:
    d = only_digits(ddd)
    n = only_digits(number)
    if not n:
        return None
    if d:
        d = d.lstrip("0")[-2:]
    full = f"{d}{n}" if d else n
    if len(full) < 10 or len(full) > 11 or len(set(n)) == 1:
        return None
    return full


def format_phone(value: str | None) -> str:
    v = only_digits(value)
    if len(v) == 11:
        return f"({v[:2]}) {v[2:7]}-{v[7:]}"
    if len(v) == 10:
        return f"({v[:2]}) {v[2:6]}-{v[6:]}"
    return value or ""


def is_mobile(phone: str | None) -> bool:
    v = only_digits(phone)
    return len(v) == 11 and v[2] == "9"


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    email = value.strip().lower()
    if not _EMAIL_RE.match(email):
        return None
    return email


def email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].lower()


def is_free_email(email: str | None) -> bool:
    return (email_domain(email) or "") in FREE_EMAIL_DOMAINS


def normalize_cep(value: str | None) -> str | None:
    v = only_digits(value)
    return v if len(v) == 8 else None


def format_cnae(code: str | None) -> str:
    c = only_digits(code)
    if len(c) == 7:
        return f"{c[:4]}-{c[4]}/{c[5:]}"
    return code or ""
