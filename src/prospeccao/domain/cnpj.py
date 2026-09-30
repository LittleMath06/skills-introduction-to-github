"""Validação e formatação de CNPJ.

Suporta o CNPJ numérico tradicional e o CNPJ alfanumérico (IN RFB nº 2.229/2024, emissão a partir
de julho/2026): as 12 primeiras posições podem conter letras A–Z e os 2 dígitos verificadores
continuam numéricos. O valor de cada caractere é (código ASCII − 48), o que mantém o cálculo
idêntico para dígitos.
"""
from __future__ import annotations

import re

_WEIGHTS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_WEIGHTS_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_CLEAN_RE = re.compile(r"[^0-9A-Za-z]")
_SHAPE_RE = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")


class InvalidCNPJ(ValueError):
    pass


def clean(value: str | int | None) -> str:
    """Remove pontuação; mantém letras (maiúsculas). Completa com zeros à esquerda se numérico."""
    if value is None:
        return ""
    text = str(value).strip()
    # Planilhas costumam transformar CNPJ em número e perder zeros à esquerda (ou virar "1.23E+13")
    if re.fullmatch(r"\d+(\.0+)?", text):
        text = text.split(".")[0]
        if len(text) < 14:
            text = text.zfill(14)
    cleaned = _CLEAN_RE.sub("", text).upper()
    if cleaned.isdigit() and 8 < len(cleaned) < 14:
        cleaned = cleaned.zfill(14)
    return cleaned


def _char_value(ch: str) -> int:
    return ord(ch) - 48


def _dv(base: str, weights: list[int]) -> str:
    total = sum(_char_value(c) * w for c, w in zip(base, weights))
    rest = total % 11
    return "0" if rest < 2 else str(11 - rest)


def compute_check_digits(base12: str) -> str:
    base12 = base12.upper()
    if len(base12) != 12 or not re.fullmatch(r"[0-9A-Z]{12}", base12):
        raise InvalidCNPJ("Base do CNPJ deve ter 12 caracteres alfanuméricos")
    d1 = _dv(base12, _WEIGHTS_1)
    d2 = _dv(base12 + d1, _WEIGHTS_2)
    return d1 + d2


def is_valid(value: str | int | None) -> bool:
    cnpj = clean(value)
    if not _SHAPE_RE.match(cnpj):
        return False
    if len(set(cnpj)) == 1:  # 00000000000000, 11111111111111...
        return False
    return compute_check_digits(cnpj[:12]) == cnpj[12:]


def validate(value: str | int | None) -> str:
    """Retorna o CNPJ limpo ou lança InvalidCNPJ."""
    cnpj = clean(value)
    if not is_valid(cnpj):
        raise InvalidCNPJ(f"CNPJ inválido: {value!r}")
    return cnpj


def format_cnpj(value: str | None) -> str:
    cnpj = clean(value)
    if len(cnpj) != 14:
        return value or ""
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def basico(cnpj: str) -> str:
    return clean(cnpj)[:8]


def is_matriz(cnpj: str) -> bool:
    return clean(cnpj)[8:12] == "0001"
