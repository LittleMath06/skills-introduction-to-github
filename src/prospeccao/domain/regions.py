"""Unidades federativas e regiões do Brasil (IBGE)."""
from __future__ import annotations

REGIONS: dict[str, list[str]] = {
    "Norte": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
    "Nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MT", "MS"],
    "Sudeste": ["ES", "MG", "RJ", "SP"],
    "Sul": ["PR", "RS", "SC"],
}

UF_TO_REGION = {uf: region for region, ufs in REGIONS.items() for uf in ufs}
ALL_UFS = sorted(UF_TO_REGION)

UF_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
    "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}


def region_of(uf: str | None) -> str | None:
    if not uf:
        return None
    return UF_TO_REGION.get(uf.upper())


def normalize_uf(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().upper()
    if v in UF_TO_REGION:
        return v
    from .text import norm

    target = norm(value)
    for uf, name in UF_NAMES.items():
        if norm(name) == target:
            return uf
    return None
