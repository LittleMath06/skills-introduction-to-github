"""Conversão de modelos em JSON (somente campos necessários)."""
from __future__ import annotations

from ..domain.cnpj import format_cnpj
from ..domain.fiscal import ICMS_STATUS_LABELS
from ..domain.scoring import PORTE_LABELS, SITUACAO_LABELS
from ..domain.text import format_cnae
from ..models import Company, CompanyContact, FiscalInfo, Job, Lead, LeadNote


def _dt(v):
    return v.isoformat() if v else None


def lead_brief(lead: Lead | None) -> dict | None:
    if lead is None:
        return None
    return {"id": lead.id, "status_id": lead.status_id, "status": lead.status.name,
            "favorite": lead.favorite, "analyzed": lead.analyzed, "discarded": lead.discarded,
            "updated_at": _dt(lead.updated_at)}


def company_brief(c: Company) -> dict:
    return {
        "id": c.id,
        "cnpj": c.cnpj,
        "cnpj_formatado": format_cnpj(c.cnpj),
        "matriz": c.is_matriz,
        "razao_social": c.razao_social,
        "nome_fantasia": c.nome_fantasia,
        "municipio": c.municipio,
        "uf": c.uf,
        "regiao": c.region,
        "segmento": c.segment.name if c.segment else None,
        "segmento_estimado": c.segment_method != "manual",
        "cnae_principal": format_cnae(c.cnae_principal),
        "cnae_descricao": c.cnae_principal_desc,
        "compatibilidade": c.similarity,
        "potencial": c.potential,
        "completude": c.completeness,
        "situacao": SITUACAO_LABELS.get(c.situacao_cadastral or "", c.situacao_cadastral),
        "icms": ICMS_STATUS_LABELS.get(c.icms_status, c.icms_status),
        "site": c.website,
        "site_status": c.website_status,
        "tem_telefone": c.has_phone,
        "tem_email": c.has_email,
        "cliente_atual": c.is_customer,
        "grupo_ja_atendido": c.customer_group and not c.is_customer,
        "atualizado_em": _dt(c.updated_at),
        "mock": c.is_mock,
        "lead": lead_brief(c.lead),
    }


def contact(ct: CompanyContact) -> dict:
    return {"id": ct.id, "tipo": ct.kind, "valor": ct.value,
            "contato_empresa": ct.is_company, "fonte": ct.source, "url_fonte": ct.source_url,
            "coletado_em": _dt(ct.fetched_at)}


def fiscal(f: FiscalInfo) -> dict:
    return {"id": f.id, "categoria": f.category, "rotulo": f.label, "valor": f.value,
            "nivel": f.level, "fonte": f.source, "url_fonte": f.source_url,
            "consultado_em": _dt(f.consulted_at), "data_do_dado": _dt(f.data_date),
            "confianca": f.confidence, "observacoes": f.notes, "criado_por": f.created_by}


def company_full(c: Company) -> dict:
    return {
        **company_brief(c),
        "situacao_codigo": c.situacao_cadastral,
        "data_situacao": _dt(c.data_situacao),
        "data_abertura": _dt(c.data_abertura),
        "natureza_juridica": c.natureza_juridica,
        "porte": PORTE_LABELS.get(c.porte or "", c.porte),
        "capital_social": float(c.capital_social) if c.capital_social is not None else None,
        "endereco": {"logradouro": c.logradouro, "numero": c.numero, "complemento": c.complemento,
                     "bairro": c.bairro, "cep": c.cep, "municipio": c.municipio, "uf": c.uf},
        "cnaes_secundarios": [format_cnae(x) for x in c.secondary_cnaes],
        "segmento_confianca": c.segment_confidence,
        "segmento_explicacao": c.segment_explanation,
        "compatibilidade_detalhes": c.similarity_details,
        "potencial_detalhes": c.potential_details,
        "simples_nacional": c.simples_opcao,
        "mei": c.mei_opcao,
        "contatos": [contact(x) for x in c.contacts],
        "fiscal": [fiscal(x) for x in c.fiscal_infos],
        "logo_url": c.logo_url,
        "site_titulo": c.site_title,
        "site_descricao": c.site_description,
        "fonte": c.source,
        "referencia_fonte": c.source_reference,
        "dados_da_fonte_em": _dt(c.source_updated_at),
        "primeira_vez_visto_em": _dt(c.first_seen_at),
    }


def note(n: LeadNote) -> dict:
    return {"id": n.id, "texto": n.text, "criado_em": _dt(n.created_at)}


def lead_full(lead: Lead) -> dict:
    return {**lead_brief(lead), "empresa": company_brief(lead.company),
            "observacoes": [note(n) for n in lead.notes]}


def job(j: Job) -> dict:
    return {"id": j.id, "tipo": j.kind, "status": j.status, "total": j.total,
            "processados": j.processed, "erros": j.errors_count, "mensagem": j.message,
            "log": (j.log or [])[-50:], "criado_em": _dt(j.created_at),
            "iniciado_em": _dt(j.started_at), "finalizado_em": _dt(j.finished_at),
            "relatorio": (j.params or {}).get("report")}
