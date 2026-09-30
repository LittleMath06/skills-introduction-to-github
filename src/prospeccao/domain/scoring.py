"""Perfil de cliente ideal, compatibilidade, potencial e completude.

Tudo aqui é **estimativa explicável**: cada pontuação vem acompanhada dos critérios que a formaram.
Os pesos são configuráveis (tabela settings) e normalizados para somar 1.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .regions import region_of
from .text import tokens

DEFAULT_SIMILARITY_WEIGHTS = {
    "cnae": 0.40,
    "segmento": 0.20,
    "palavras": 0.15,
    "localizacao": 0.15,
    "porte": 0.10,
}

DEFAULT_POTENTIAL_WEIGHTS = {
    "compatibilidade": 0.55,
    "afinidade_segmento": 0.20,
    "completude": 0.15,
    "maturidade": 0.10,
}

# Premissa comercial configurável: afinidade estimada de cada segmento com o consumo de fios e cabos.
DEFAULT_SEGMENT_AFFINITY = {
    "Instaladores": 1.0, "Distribuidores": 1.0, "Energia": 1.0, "Infraestrutura": 0.9,
    "Integradores": 0.9, "Fabricantes": 0.9, "Varejo": 0.8, "Construção Civil": 0.8,
    "Engenharia": 0.8, "Automação": 0.8, "Telecomunicações": 0.8, "Indústria": 0.6,
    "Agrobusiness": 0.6, "Outros": 0.2,
}

PORTE_LABELS = {"00": "Não informado", "01": "Micro empresa", "03": "Empresa de pequeno porte",
                "05": "Demais"}
SITUACAO_LABELS = {"01": "Nula", "02": "Ativa", "03": "Suspensa", "04": "Inapta", "08": "Baixada"}

_CNAE_LEVELS = [(7, 1.0, "subclasse"), (5, 0.85, "classe"), (4, 0.7, "classe"),
                (3, 0.5, "grupo"), (2, 0.3, "divisão")]


def normalize_weights(weights: dict[str, float], defaults: dict[str, float]) -> dict[str, float]:
    merged = {k: max(0.0, float(weights.get(k, v))) for k, v in defaults.items()}
    total = sum(merged.values())
    if total <= 0:
        return dict(defaults)
    return {k: v / total for k, v in merged.items()}


@dataclass
class CompanyFeatures:
    cnae_principal: str | None
    secondary_cnaes: list[str] = field(default_factory=list)
    segment: str | None = None
    uf: str | None = None
    porte: str | None = None
    text: str = ""


@dataclass
class Profile:
    """Perfil agregado dos clientes atuais (serializável em JSON)."""

    n: int = 0
    cnae: dict[int, Counter] = field(default_factory=lambda: {k: Counter() for k, *_ in _CNAE_LEVELS})
    segment: Counter = field(default_factory=Counter)
    uf: Counter = field(default_factory=Counter)
    region: Counter = field(default_factory=Counter)
    porte: Counter = field(default_factory=Counter)
    keywords: Counter = field(default_factory=Counter)

    @classmethod
    def build(cls, customers: list[CompanyFeatures]) -> Profile:
        p = cls()
        for c in customers:
            p.n += 1
            if c.cnae_principal:
                for level, *_ in _CNAE_LEVELS:
                    p.cnae[level][c.cnae_principal[:level]] += 1
            if c.segment:
                p.segment[c.segment] += 1
            if c.uf:
                p.uf[c.uf] += 1
                if r := region_of(c.uf):
                    p.region[r] += 1
            if c.porte:
                p.porte[c.porte] += 1
            p.keywords.update(set(tokens(c.text)))
        return p

    def top_keywords(self, n: int = 60) -> dict[str, int]:
        # Palavra precisa aparecer em pelo menos 2 clientes (ou 1 se a base for muito pequena)
        min_count = 2 if self.n >= 10 else 1
        return {k: v for k, v in self.keywords.most_common(n) if v >= min_count}

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "cnae": {str(k): dict(v) for k, v in self.cnae.items()},
            "segment": dict(self.segment),
            "uf": dict(self.uf),
            "region": dict(self.region),
            "porte": dict(self.porte),
            "keywords": dict(self.keywords.most_common(200)),
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> Profile:
        p = cls()
        if not d:
            return p
        p.n = int(d.get("n", 0))
        for k, v in (d.get("cnae") or {}).items():
            p.cnae[int(k)] = Counter(v)
        p.segment = Counter(d.get("segment") or {})
        p.uf = Counter(d.get("uf") or {})
        p.region = Counter(d.get("region") or {})
        p.porte = Counter(d.get("porte") or {})
        p.keywords = Counter(d.get("keywords") or {})
        return p


def _rel(counter: Counter, key) -> float:
    if not key or not counter:
        return 0.0
    top = max(counter.values())
    return counter.get(key, 0) / top if top else 0.0


def _pct(counter: Counter, key, n: int) -> str:
    return f"{round(100 * counter.get(key, 0) / n)}%" if n else "0%"


def _cnae_match(profile: Profile, cnae: str) -> tuple[float, int, str, str]:
    for level, factor, label in _CNAE_LEVELS:
        count = profile.cnae[level].get(cnae[:level], 0)
        if count:
            return factor, count, label, cnae[:level]
    return 0.0, 0, "", ""


def similarity(profile: Profile, c: CompanyFeatures, weights: dict[str, float]) -> dict:
    """Retorna {"score": 0-100, "criteria": [...], "similar_customers": int}."""
    w = normalize_weights(weights, DEFAULT_SIMILARITY_WEIGHTS)
    if profile.n == 0:
        return {"score": 0.0, "criteria": [], "similar_customers": 0,
                "note": "Base de clientes ainda não importada — compatibilidade indisponível."}
    criteria = []

    # CNAE
    cnae_value, cnae_text, similar = 0.0, "Nenhum CNAE em comum com clientes", 0
    if c.cnae_principal:
        f, count, label, code = _cnae_match(profile, c.cnae_principal)
        if f:
            cnae_value, similar = f, count
            cnae_text = f"CNAE principal com mesma {label} ({code}) de {count} cliente(s)"
    if cnae_value < 1.0:
        for sec in c.secondary_cnaes:
            f, count, label, code = _cnae_match(profile, sec)
            if f * 0.6 > cnae_value:
                cnae_value, similar = f * 0.6, count
                cnae_text = f"CNAE secundário com mesma {label} ({code}) de {count} cliente(s)"
    criteria.append(("cnae", "CNAE semelhante", cnae_value, cnae_text))

    # Segmento
    seg_value = _rel(profile.segment, c.segment)
    if c.segment == "Outros":
        seg_value *= 0.5
    seg_text = (f"Segmento {c.segment}: {_pct(profile.segment, c.segment, profile.n)} dos clientes"
                if c.segment else "Segmento não identificado")
    criteria.append(("segmento", "Segmento semelhante", seg_value, seg_text))

    # Palavras-chave
    top = profile.top_keywords()
    common = sorted(set(tokens(c.text)) & set(top), key=lambda k: -top[k])
    kw_value = min(1.0, len(common) / 3)
    kw_text = ("Palavras em comum: " + ", ".join(common[:5])) if common else "Sem palavras em comum"
    criteria.append(("palavras", "Atividade relacionada", kw_value, kw_text))

    # Localização
    region = region_of(c.uf)
    loc_value = _rel(profile.uf, c.uf)
    if loc_value:
        loc_text = f"UF {c.uf}: {_pct(profile.uf, c.uf, profile.n)} dos clientes"
    else:
        loc_value = 0.5 * _rel(profile.region, region)
        loc_text = (f"Região {region}: {_pct(profile.region, region, profile.n)} dos clientes"
                    if loc_value else "Região sem clientes atuais")
    criteria.append(("localizacao", "Região compatível", loc_value, loc_text))

    # Porte
    porte_value = _rel(profile.porte, c.porte) if c.porte and c.porte != "00" else 0.0
    porte_text = (f"Porte {PORTE_LABELS.get(c.porte, c.porte)}: "
                  f"{_pct(profile.porte, c.porte, profile.n)} dos clientes"
                  if porte_value else "Porte diferente ou não informado")
    criteria.append(("porte", "Porte semelhante", porte_value, porte_text))

    score = sum(w[key] * value for key, _, value, _ in criteria)
    return {
        "score": round(100 * score, 1),
        "similar_customers": similar,
        "criteria": [
            {"key": key, "label": label, "value": round(value, 3), "weight": round(w[key], 3),
             "points": round(100 * w[key] * value, 1), "explanation": text}
            for key, label, value, text in criteria
        ],
    }


def completeness(fields: dict[str, object]) -> float:
    """Fração (0-100) de campos úteis preenchidos."""
    weights = {
        "razao_social": 1, "nome_fantasia": 0.5, "cnae_principal": 1, "endereco": 1,
        "municipio": 1, "uf": 1, "telefone": 1.5, "email": 1.5, "site": 1.5, "porte": 0.5,
        "data_abertura": 0.5,
    }
    got = sum(w for k, w in weights.items() if fields.get(k))
    return round(100 * got / sum(weights.values()), 1)


def potential(
    similarity_score: float,
    segment: str | None,
    completeness_score: float,
    situacao: str | None,
    age_years: float | None,
    weights: dict[str, float] | None = None,
    affinity: dict[str, float] | None = None,
) -> dict:
    w = normalize_weights(weights or {}, DEFAULT_POTENTIAL_WEIGHTS)
    aff_table = {**DEFAULT_SEGMENT_AFFINITY, **(affinity or {})}
    if situacao and situacao != "02":
        return {
            "score": 0.0,
            "criteria": [],
            "note": f"Empresa com situação cadastral {SITUACAO_LABELS.get(situacao, situacao)} — "
                    "sem potencial comercial até regularização.",
        }
    aff = aff_table.get(segment or "Outros", 0.2)
    if age_years is None:
        maturity, maturity_text = 0.5, "Data de abertura desconhecida"
    elif age_years < 1:
        maturity, maturity_text = 0.4, "Aberta há menos de 1 ano"
    elif age_years < 3:
        maturity, maturity_text = 0.7, f"Aberta há {age_years:.0f} ano(s)"
    else:
        maturity, maturity_text = 1.0, f"Aberta há {age_years:.0f} anos"
    criteria = [
        ("compatibilidade", "Compatibilidade com perfil", similarity_score / 100,
         f"{similarity_score:.0f}% de compatibilidade"),
        ("afinidade_segmento", "Afinidade estimada do segmento com cabos", aff,
         f"Segmento {segment or 'não identificado'}: afinidade {aff:.0%} (premissa configurável)"),
        ("completude", "Dados de contato/cadastro disponíveis", completeness_score / 100,
         f"{completeness_score:.0f}% dos campos preenchidos"),
        ("maturidade", "Maturidade da empresa", maturity, maturity_text),
    ]
    score = sum(w[k] * v for k, _, v, _ in criteria)
    return {
        "score": round(100 * score, 1),
        "criteria": [
            {"key": k, "label": label, "value": round(v, 3), "weight": round(w[k], 3),
             "points": round(100 * w[k] * v, 1), "explanation": text}
            for k, label, v, text in criteria
        ],
    }
