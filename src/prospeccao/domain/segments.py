"""Classificação de empresas em segmentos (estimativa explicável).

Regras:
1. O CNAE principal é comparado com os prefixos de cada segmento; vence o prefixo mais longo
   (mais específico). Quanto mais longo o prefixo, maior a confiança.
2. CNAEs secundários contam com metade do peso.
3. Palavras-chave no nome/descrição somam um bônus e podem decidir quando o CNAE é genérico.
4. Sem nenhum sinal, a empresa vai para o segmento de fallback ("Outros") com confiança baixa.

O resultado é sempre apresentado como **estimado**, exceto quando o usuário define o segmento
manualmente.
"""
from __future__ import annotations

from dataclasses import dataclass

from .text import norm

# Segmentos padrão. Os prefixos referem-se à CNAE 2.3 (subclasses de 7 dígitos). São um ponto de
# partida documentado em docs/10-documentacao-final.md §16 e podem ser editados em Configurações.
DEFAULT_SEGMENTS: list[dict] = [
    {
        "name": "Instaladores",
        "description": "Instalações elétricas e outras instalações prediais",
        "cnae_prefixes": ["4321", "4322", "4329"],
        "keywords": ["instalacoes eletricas", "instaladora", "eletricista", "instalacao eletrica"],
    },
    {
        "name": "Distribuidores",
        "description": "Comércio atacadista (material elétrico, construção, máquinas)",
        "cnae_prefixes": ["4673", "4679", "4663", "4669", "4674", "4684", "46"],
        "keywords": ["distribuidora", "distribuidor", "atacado"],
    },
    {
        "name": "Varejo",
        "description": "Comércio varejista de material elétrico, ferragens e construção",
        "cnae_prefixes": ["4742", "4744", "4743", "4789", "47"],
        "keywords": ["materiais eletricos", "material eletrico", "home center", "loja"],
    },
    {
        "name": "Energia",
        "description": "Geração, transmissão, distribuição de energia e redes elétricas",
        "cnae_prefixes": ["35", "4221902", "4221901", "4221905"],
        "keywords": ["energia", "subestacao", "eletrificacao", "transmissao"],
    },
    {
        "name": "Telecomunicações",
        "description": "Telecomunicações e redes de telecom",
        "cnae_prefixes": ["61", "4221904", "4221903"],
        "keywords": ["telecom", "telecomunicacoes", "fibra optica", "provedor", "internet"],
    },
    {
        "name": "Infraestrutura",
        "description": "Obras de infraestrutura",
        "cnae_prefixes": ["42"],
        "keywords": ["infraestrutura", "obras"],
    },
    {
        "name": "Construção Civil",
        "description": "Construção de edifícios e serviços especializados de construção",
        "cnae_prefixes": ["41", "43"],
        "keywords": ["construtora", "construcoes", "incorporadora", "engenharia civil"],
    },
    {
        "name": "Engenharia",
        "description": "Serviços de engenharia e projetos",
        "cnae_prefixes": ["7112", "7119", "711"],
        "keywords": ["engenharia", "projetos eletricos", "engenheiros"],
    },
    {
        "name": "Automação",
        "description": "Automação industrial, instrumentação e controle",
        "cnae_prefixes": ["2651", "3321", "2790", "3313"],
        "keywords": ["automacao", "instrumentacao", "controle industrial", "paineis eletricos"],
    },
    {
        "name": "Integradores",
        "description": "Integradores de sistemas (solar, segurança eletrônica, redes)",
        "cnae_prefixes": ["8020"],
        "keywords": ["integrador", "integradora", "solar", "fotovoltaica", "fotovoltaico",
                     "sistemas de seguranca", "integracao"],
    },
    {
        "name": "Fabricantes",
        "description": "Fabricação de materiais, máquinas e equipamentos elétricos/eletrônicos",
        "cnae_prefixes": ["27", "26", "28", "29", "30"],
        "keywords": ["fabricante", "fabrica", "manufatura"],
    },
    {
        "name": "Agrobusiness",
        "description": "Agropecuária, agroindústria e comércio agrícola",
        "cnae_prefixes": ["01", "02", "03", "4623", "4661", "4683", "1011", "1012", "1061",
                          "1071", "1081"],
        "keywords": ["agro", "agricola", "agropecuaria", "fazenda", "irrigacao", "cooperativa",
                     "agronegocio", "armazens", "silos"],
    },
    {
        "name": "Indústria",
        "description": "Demais atividades industriais (seções B e C da CNAE)",
        "cnae_prefixes": [str(i).zfill(2) for i in range(5, 34)],
        "keywords": ["industria", "industrial", "metalurgica"],
    },
    {
        "name": "Outros",
        "description": "Sem sinais suficientes para outro segmento",
        "cnae_prefixes": [],
        "keywords": [],
        "is_fallback": True,
    },
]

_PREFIX_CONFIDENCE = {7: 0.92, 6: 0.9, 5: 0.88, 4: 0.82, 3: 0.72, 2: 0.6}


@dataclass(frozen=True)
class SegmentRule:
    id: int | None
    name: str
    cnae_prefixes: tuple[str, ...]
    keywords: tuple[str, ...]
    is_fallback: bool = False

    @classmethod
    def from_strings(cls, id_, name, prefixes: str, keywords: str, is_fallback=False):
        return cls(
            id=id_,
            name=name,
            cnae_prefixes=tuple(p.strip() for p in (prefixes or "").split(",") if p.strip()),
            keywords=tuple(norm(k) for k in (keywords or "").split(",") if k.strip()),
            is_fallback=is_fallback,
        )


@dataclass
class Classification:
    segment_id: int | None
    segment_name: str
    confidence: float
    method: str  # "cnae" | "palavra-chave" | "fallback"
    explanation: str


def _best_prefix(cnae: str | None, prefixes: tuple[str, ...]) -> str | None:
    if not cnae:
        return None
    best = None
    for p in prefixes:
        if cnae.startswith(p) and (best is None or len(p) > len(best)):
            best = p
    return best


def classify(
    rules: list[SegmentRule],
    cnae_principal: str | None,
    secondary_cnaes: list[str] | None = None,
    text: str | None = None,
) -> Classification:
    secondary_cnaes = secondary_cnaes or []
    normalized_text = f" {norm(text)} "
    fallback = next((r for r in rules if r.is_fallback), None)
    best: tuple[float, SegmentRule, str, str] | None = None

    for rule in rules:
        if rule.is_fallback:
            continue
        score = 0.0
        reasons: list[str] = []
        method = "cnae"
        prefix = _best_prefix(cnae_principal, rule.cnae_prefixes)
        if prefix:
            score = _PREFIX_CONFIDENCE.get(len(prefix), 0.6)
            reasons.append(f"CNAE principal {cnae_principal} dentro do prefixo {prefix}")
        else:
            sec_scores = [
                (_PREFIX_CONFIDENCE.get(len(p), 0.6) * 0.5, c, p)
                for c in secondary_cnaes
                if (p := _best_prefix(c, rule.cnae_prefixes))
            ]
            if sec_scores:
                s, c, p = max(sec_scores)
                score = s
                reasons.append(f"CNAE secundário {c} dentro do prefixo {p}")
        # palavra inteira; palavras longas (>= 6) também casam como prefixo/substring
        hits = [
            k for k in rule.keywords
            if k and (f" {k} " in normalized_text or (len(k) >= 6 and k in normalized_text))
        ]
        if hits:
            bonus = 0.25 if score else 0.55
            if not score:
                method = "palavra-chave"
            score += bonus
            reasons.append("palavras-chave: " + ", ".join(sorted(set(hits))[:4]))
        if score and (best is None or score > best[0]):
            best = (score, rule, method, "; ".join(reasons))

    if best is None:
        name = fallback.name if fallback else "Outros"
        return Classification(
            fallback.id if fallback else None, name, 0.2, "fallback",
            "Nenhum CNAE ou palavra-chave corresponde aos segmentos configurados",
        )
    score, rule, method, reason = best
    return Classification(rule.id, rule.name, round(min(score, 0.95), 2), method, reason)
