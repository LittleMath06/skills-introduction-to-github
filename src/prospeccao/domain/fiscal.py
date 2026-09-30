"""Regras fiscais auxiliares. Nunca produzem informação 'confirmada' — apenas 'provável'."""
from __future__ import annotations

# Divisões CNAE cujas atividades típicas são fatos geradores de ICMS
# (circulação de mercadorias, energia elétrica, comunicação, transporte intermunicipal).
_ICMS_DIVISIONS = {f"{i:02d}" for i in range(5, 34)} | {"35", "45", "46", "47", "49", "50", "61"}

LEVELS = {
    "confirmado": "Informação confirmada — obtida em fonte oficial",
    "provavel": "Informação provável — inferida a partir de dados disponíveis",
    "possivel": "Possível — hipótese que precisa de confirmação",
}

ICMS_STATUS_LABELS = {
    "confirmado_habilitado": "Contribuinte ICMS (confirmado)",
    "confirmado_nao_habilitado": "IE não habilitada (confirmado)",
    "nao_contribuinte": "Não consta como contribuinte (SEFAZ)",
    "provavel": "Provável contribuinte (inferido)",
    "nao_verificado": "ICMS não verificado",
}


def infer_icms(cnae_principal: str | None, secondary: list[str] | None = None) -> dict | None:
    """Retorna uma inferência 'provável' ou None se não houver indício."""
    codes = [c for c in [cnae_principal, *(secondary or [])] if c]
    matched = [c for c in codes if c[:2] in _ICMS_DIVISIONS]
    if not matched:
        return None
    return {
        "category": "icms",
        "label": "Provável contribuinte de ICMS",
        "value": "Atividade econômica típica de contribuinte (indústria/comércio/energia/"
                 "comunicação/transporte)",
        "level": "provavel",
        "source": "Inferência pelo CNAE (regra do sistema)",
        "confidence": 0.6 if matched[0] == cnae_principal else 0.4,
        "notes": f"Baseado no(s) CNAE(s) {', '.join(matched[:3])}. Requer confirmação na SEFAZ/"
                 "Sintegra da UF. Não constitui aconselhamento tributário.",
    }


SINTEGRA_URL = "http://www.sintegra.gov.br/"
