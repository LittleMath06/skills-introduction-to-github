"""Correspondência de empresas pelo nome (razão social) quando não há CNPJ.

Regras conservadoras — preferimos não vincular a vincular errado:
* chave = nome sem acento/pontuação, sem natureza societária (LTDA, S.A., EIRELI, ME, EPP…) e
  com abreviações comuns expandidas (IND → INDUSTRIA, COM → COMERCIO, MAT → MATERIAIS…);
* vínculo por chave **exata**; se o nome da planilha parece truncado (sistemas de ERP costumam
  cortar em ~40 caracteres), aceita-se o nome oficial que **começa** com a chave;
* mais de uma empresa candidata → "ambíguo" (não vincula; o usuário decide).
"""
from __future__ import annotations

import re

from .text import norm

_LEGAL_SUFFIXES = {
    "ltda", "limitada", "me", "epp", "eireli", "sa", "s a", "s/a", "cia", "mei", "ss", "sociedade",
    "simples", "unipessoal", "em recuperacao judicial", "em liquidacao",
}
# Abreviações comuns em cadastros de ERP (expandidas também na classificação de segmento)
ABBREVIATIONS = {
    "ind": "industria", "inds": "industria",
    "com": "comercio", "coml": "comercial", "mat": "materiais", "mats": "materiais",
    "elet": "eletricos", "eletr": "eletricos", "equip": "equipamentos", "equips": "equipamentos",
    "serv": "servicos", "servs": "servicos", "eng": "engenharia", "const": "construcoes",
    "distrib": "distribuidora", "dist": "distribuidora", "imp": "importacao",
    "exp": "exportacao", "refr": "refrigeracao", "tec": "tecnologia", "tecn": "tecnologia",
    "adm": "administracao", "part": "participacoes", "parts": "participacoes",
    "emp": "empreendimentos", "empreend": "empreendimentos", "bras": "brasileira",
    "bra": "brasil", "nac": "nacional", "intl": "internacional", "prods": "produtos",
    "prod": "produtos", "sist": "sistemas", "agroind": "agroindustrial",
}
# Unificação de flexões (somente para comparar nomes)
_CANONICAL = {"industrias": "industria", "eletricas": "eletricos", "eletrico": "eletricos",
              "eletrica": "eletricos"}
_ABBREVIATIONS = {**ABBREVIATIONS, **_CANONICAL}


def expand_abbreviations(text: str | None) -> str:
    """'COM DE MAT ELET' → 'comercio de materiais eletricos' (sem acento, minúsculo)."""
    words = re.sub(r"[^a-z0-9 ]", " ", norm(text)).split()
    return " ".join(ABBREVIATIONS.get(w, w) for w in words)
_TRUNCATION_MIN_LEN = 35


def name_key(name: str | None) -> str:
    """Chave canônica do nome para comparação."""
    text = norm(name)
    text = text.replace("s/a", " sa ").replace("s.a.", " sa ").replace("s.a", " sa ")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    tokens = [_ABBREVIATIONS.get(t, t) for t in text.split()]
    # remove natureza societária no fim (pode haver várias: "EIRELI - EPP", "LTDA ME")
    joined = " ".join(tokens)
    changed = True
    while changed and joined:
        changed = False
        for suffix in sorted(_LEGAL_SUFFIXES, key=len, reverse=True):
            if joined == suffix:
                break
            if joined.endswith(" " + suffix):
                joined = joined[: -len(suffix) - 1].strip()
                changed = True
    return re.sub(r"\s+", " ", joined).strip()


def looks_truncated(raw_name: str | None) -> bool:
    """Nome sem natureza societária e longo o bastante para ter sido cortado por um sistema."""
    if not raw_name:
        return False
    raw = raw_name.strip()
    has_suffix = re.search(r"(LTDA|LIMITADA|S\.?\s?/?A\.?|EIRELI|EPP|\bME)\W*$", raw.upper())
    return len(raw) >= _TRUNCATION_MIN_LEN and not has_suffix


def prefix_key(raw_name: str | None) -> str | None:
    """Para nomes truncados: chave sem a última palavra (possivelmente cortada)."""
    if not looks_truncated(raw_name):
        return None
    parts = name_key(raw_name).split()
    if len(parts) < 3:
        return None
    return " ".join(parts[:-1])


class NameIndex:
    """Índice em memória dos nomes a procurar (clientes sem CNPJ)."""

    def __init__(self, names: dict[int, str]):
        self.exact: dict[str, int] = {}
        self.prefixes: dict[str, int] = {}
        for cid, raw in names.items():
            key = name_key(raw)
            if len(key) < 4:
                continue
            self.exact.setdefault(key, cid)
            pk = prefix_key(raw)
            if pk and len(pk) >= 12:
                self.prefixes.setdefault(pk, cid)
        self._prefix_lengths = sorted({len(p) for p in self.prefixes})

    def __bool__(self) -> bool:
        return bool(self.exact or self.prefixes)

    def match(self, official_name: str | None) -> tuple[int, str] | None:
        """Retorna (id do cliente, método) se o nome oficial corresponde a algum cliente."""
        key = name_key(official_name)
        if not key:
            return None
        if key in self.exact:
            return self.exact[key], "nome_exato"
        if key in self.prefixes:  # a palavra cortada era apenas a natureza societária
            return self.prefixes[key], "nome_prefixo"
        for length in self._prefix_lengths:
            if length < len(key) and key[length] == " " and key[:length] in self.prefixes:
                return self.prefixes[key[:length]], "nome_prefixo"
        return None


def resolve_candidates(candidates: dict[int, set[str]]) -> tuple[dict[int, str], set[int]]:
    """{cliente: {cnpj_basico,...}} → (vínculos únicos, clientes ambíguos)."""
    unique = {cid: next(iter(b)) for cid, b in candidates.items() if len(b) == 1}
    ambiguous = {cid for cid, b in candidates.items() if len(b) > 1}
    return unique, ambiguous
