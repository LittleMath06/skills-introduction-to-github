"""Interpretação transparente da pesquisa livre.

Exemplos:
  "Encontrar empresas de engenharia elétrica em São Paulo" → segmento=Engenharia, uf=SP, termos=[eletrica]
  "Encontrar empresas do agronegócio no Centro-Oeste"      → segmento=Agrobusiness, região=Centro-Oeste
  "Encontrar empresas semelhantes aos meus clientes atuais" → ordenar por compatibilidade, mín. 50%

A interpretação é mostrada ao usuário, que pode remover qualquer item.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .regions import REGIONS, UF_NAMES, UF_TO_REGION
from .text import norm

_FILLER = {
    "encontrar", "buscar", "procurar", "listar", "mostrar", "quero", "empresa", "empresas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "e", "o", "a", "os", "as",
    "que", "com", "para", "setor", "segmento", "area", "ramo", "estado", "regiao", "cidade",
    "todas", "todos", "atuais", "atual", "novos", "novas", "clientes", "potenciais", "potencial", "leads", "lead", "me", "meus", "minhas",
}

_SIMILAR_PATTERNS = [
    r"semelhantes?\s+a(os)?\s+(meus\s+)?clientes", r"similares?\s+a(os)?\s+(meus\s+)?clientes",
    r"parecidas?\s+com\s+(os\s+)?(meus\s+)?clientes", r"perfil\s+(dos\s+)?(meus\s+)?clientes",
]

# Sinônimos → nome do segmento
SEGMENT_SYNONYMS = {
    "agronegocio": "Agrobusiness", "agrobusiness": "Agrobusiness", "agro": "Agrobusiness",
    "agropecuaria": "Agrobusiness", "agricola": "Agrobusiness",
    "instaladores": "Instaladores", "instalador": "Instaladores", "instaladoras": "Instaladores",
    "instalacoes": "Instaladores", "eletricistas": "Instaladores",
    "varejo": "Varejo", "lojas": "Varejo", "varejistas": "Varejo",
    "construcao civil": "Construção Civil", "construcao": "Construção Civil",
    "construtoras": "Construção Civil",
    "industria": "Indústria", "industrias": "Indústria", "industrial": "Indústria",
    "distribuidores": "Distribuidores", "distribuidoras": "Distribuidores",
    "distribuicao": "Distribuidores", "atacado": "Distribuidores", "atacadistas": "Distribuidores",
    "engenharia": "Engenharia",
    "energia": "Energia", "eletricas": "Energia",
    "automacao": "Automação",
    "infraestrutura": "Infraestrutura",
    "telecomunicacoes": "Telecomunicações", "telecom": "Telecomunicações",
    "fabricantes": "Fabricantes", "fabricas": "Fabricantes",
    "integradores": "Integradores", "integradoras": "Integradores", "solar": "Integradores",
}
# "eletricas" sozinho é ambíguo; só vira segmento se nada mais for encontrado
_WEAK_SYNONYMS = {"eletricas", "solar"}


@dataclass
class ParsedQuery:
    segment: str | None = None
    uf: str | None = None
    region: str | None = None
    city: str | None = None
    similar_to_customers: bool = False
    terms: list[str] = field(default_factory=list)

    def as_filters(self) -> dict:
        out: dict = {}
        if self.segment:
            out["segment"] = self.segment
        if self.uf:
            out["uf"] = self.uf
        if self.region:
            out["region"] = self.region
        if self.city:
            out["city"] = self.city
        if self.similar_to_customers:
            out["min_similarity"] = 50
            out["sort"] = "similarity"
        if self.terms:
            out["q"] = " ".join(self.terms)
        return out


def parse(query: str, known_cities: set[str] | None = None,
          segment_names: list[str] | None = None) -> ParsedQuery:
    result = ParsedQuery()
    raw = query or ""
    text = f" {norm(raw)} "

    for pat in _SIMILAR_PATTERNS:
        if re.search(pat, text):
            result.similar_to_customers = True
            text = re.sub(pat, " ", text)

    # Estados por nome (mais longos primeiro: "mato grosso do sul" antes de "mato grosso")
    for uf, name in sorted(UF_NAMES.items(), key=lambda kv: -len(kv[1])):
        n = norm(name)
        m = re.search(rf"\b{re.escape(n)}\b", text)
        if m:
            result.uf = uf
            text = text[: m.start()] + " " + text[m.end():]
            break
    # Sigla de UF: aceita em maiúsculas no texto original ou após "em/no/na"
    if not result.uf:
        for m in re.finditer(r"\b([A-Za-z]{2})\b", raw):
            sig = m.group(1)
            before = raw[: m.start()].lower().rstrip().split(" ")[-1:] or [""]
            if sig.upper() in UF_TO_REGION and (sig.isupper() or before[0] in {"em", "no", "na"}):
                result.uf = sig.upper()
                text = re.sub(rf"\b{sig.lower()}\b", " ", text, count=1)
                break
    # Regiões (depois dos estados: "sul" faz parte de "Rio Grande do Sul")
    for region in sorted(REGIONS, key=len, reverse=True):
        key = norm(region).replace("-", "[- ]?")
        m = re.search(rf"\b{key}\b", text)
        if m:
            result.region = region
            text = text[: m.start()] + " " + text[m.end():]
            break

    if result.uf and result.region and UF_TO_REGION[result.uf] != result.region:
        result.region = None

    # Cidade conhecida (lista vinda do banco), mais longas primeiro
    for city in sorted(known_cities or set(), key=len, reverse=True):
        c = norm(city)
        if len(c) >= 4 and re.search(rf"\b{re.escape(c)}\b", text):
            result.city = city
            text = re.sub(rf"\b{re.escape(c)}\b", " ", text, count=1)
            break

    # Segmento: nome configurado ou sinônimo
    names = {norm(s): s for s in (segment_names or [])}
    candidates = {**{k: v for k, v in SEGMENT_SYNONYMS.items()}, **names}
    weak_hit = None
    for key in sorted(candidates, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", text):
            if key in _WEAK_SYNONYMS:
                weak_hit = weak_hit or key
                continue
            result.segment = candidates[key]
            text = re.sub(rf"\b{re.escape(key)}\b", " ", text, count=1)
            break
    if not result.segment and weak_hit:
        result.segment = candidates[weak_hit]
        text = re.sub(rf"\b{re.escape(weak_hit)}\b", " ", text, count=1)

    result.terms = [t for t in re.findall(r"[a-z0-9]+", text) if t not in _FILLER and len(t) > 2]
    return result
