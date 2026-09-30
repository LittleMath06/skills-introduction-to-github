"""Dados FICTÍCIOS para desenvolvimento e demonstração.

* Todas as empresas geradas têm is_mock=True, source="MOCK" e nome iniciado por "[MOCK]".
* A interface exibe uma faixa "MOCK" enquanto houver dados fictícios.
* Bloqueado em produção (ALLOW_MOCK_DATA=false é obrigatório em APP_ENV=production).
* Os CNPJs têm dígitos verificadores válidos, mas são gerados aleatoriamente e NÃO correspondem
  intencionalmente a nenhuma empresa real.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..domain.cnpj import compute_check_digits
from ..models import Company, CompanyChange, Customer, Lead
from .companies import mark_customers, rebuild_profile, rescore_all, upsert_company

_ACTIVITIES = [
    ("4321500", "Instalação e manutenção elétrica", "INSTALACOES ELETRICAS"),
    ("4673700", "Comércio atacadista de material elétrico", "DISTRIBUIDORA DE MATERIAIS ELETRICOS"),
    ("4742300", "Comércio varejista de material elétrico", "MATERIAIS ELETRICOS"),
    ("7112000", "Serviços de engenharia", "ENGENHARIA ELETRICA"),
    ("4221902", "Construção de estações e redes de distribuição de energia elétrica",
     "ENERGIA E REDES"),
    ("4120400", "Construção de edifícios", "CONSTRUTORA"),
    ("2733300", "Fabricação de fios, cabos e condutores elétricos isolados", "CONDUTORES"),
    ("0115600", "Cultivo de soja", "AGROPECUARIA"),
    ("4661300", "Comércio atacadista de máquinas agrícolas", "AGRO MAQUINAS"),
    ("3321000", "Instalação de máquinas e equipamentos industriais", "AUTOMACAO INDUSTRIAL"),
    ("6110801", "Serviços de telefonia fixa comutada", "TELECOM"),
    ("2512800", "Fabricação de esquadrias de metal", "METALURGICA"),
    ("5611201", "Restaurantes e similares", "RESTAURANTE"),
]
_CITIES = [
    ("SP", "SAO PAULO"), ("SP", "CAMPINAS"), ("SP", "RIBEIRAO PRETO"), ("MG", "BELO HORIZONTE"),
    ("MG", "UBERLANDIA"), ("RJ", "RIO DE JANEIRO"), ("PR", "CURITIBA"), ("PR", "LONDRINA"),
    ("SC", "JOINVILLE"), ("RS", "PORTO ALEGRE"), ("GO", "GOIANIA"), ("MT", "CUIABA"),
    ("MT", "RONDONOPOLIS"), ("MS", "CAMPO GRANDE"), ("BA", "SALVADOR"), ("PE", "RECIFE"),
    ("CE", "FORTALEZA"), ("PA", "BELEM"), ("AM", "MANAUS"), ("DF", "BRASILIA"),
]
_WORDS = ["ALFA", "BETA", "DELTA", "OMEGA", "NOVA", "PRIME", "TOTAL", "CENTRAL", "UNIAO", "FORTE",
          "LUZ", "VOLT", "CONEXAO", "PADRAO", "MODELO", "EXEMPLO"]


def _cnpj(rng: random.Random) -> str:
    base = f"{rng.randint(0, 99_999_999):08d}0001"
    return base + compute_check_digits(base)


def clear_mock(session: Session) -> int:
    ids = select(Company.id).where(Company.is_mock.is_(True))
    session.execute(delete(Lead).where(Lead.company_id.in_(ids)))
    session.execute(delete(CompanyChange).where(CompanyChange.company_id.in_(ids)))
    session.execute(delete(Customer).where(Customer.import_batch == "MOCK"))
    n = 0
    for company in session.scalars(select(Company).where(Company.is_mock.is_(True))).all():
        session.delete(company)
        n += 1
    session.commit()
    return n


def seed_mock(session: Session, settings: Settings, n_companies: int = 400,
              n_customers: int = 30, seed: int = 42) -> dict:
    if not settings.allow_mock_data:
        raise PermissionError("Dados MOCK desabilitados neste ambiente")
    rng = random.Random(seed)
    today = date.today()
    created = []
    for i in range(n_companies):
        cnae, desc, label = rng.choices(_ACTIVITIES, weights=[5, 4, 4, 3, 2, 3, 1, 2, 2, 2, 1, 2, 3])[0]
        uf, city = rng.choice(_CITIES)
        name = f"[MOCK] {label} {rng.choice(_WORDS)} {rng.choice(_WORDS)} LTDA"
        record = {
            "cnpj": _cnpj(rng),
            "is_matriz": True,
            "razao_social": name,
            "nome_fantasia": f"[MOCK] {rng.choice(_WORDS)} {label.split()[0]}",
            "situacao_cadastral": rng.choices(["02", "08", "04"], weights=[90, 7, 3])[0],
            "data_abertura": today - timedelta(days=rng.randint(100, 9000)),
            "natureza_juridica_code": "2062",
            "natureza_juridica": "Sociedade Empresária Limitada",
            "porte": rng.choice(["01", "03", "05"]),
            "logradouro": f"RUA FICTICIA {rng.randint(1, 999)}",
            "numero": str(rng.randint(1, 3000)),
            "bairro": "CENTRO",
            "cep": f"{rng.randint(1000000, 99999999):08d}",
            "municipio": city,
            "uf": uf,
            "cnae_principal": cnae,
            "cnae_principal_desc": desc,
            "cnaes_secundarios": rng.sample([a[0] for a in _ACTIVITIES if a[0] != cnae], 2),
            # Telefones com DDD 00 (inexistente) e e-mails em domínio .invalid (RFC 2606):
            # impossível corresponderem a contatos reais
            "phones": [f"00{rng.randint(20000000, 39999999)}"]
            if rng.random() < 0.8 else [],
            "email": f"contato{i}@exemplo.invalid" if rng.random() < 0.6 else None,
            "simples_opcao": rng.random() < 0.5,
            "mei_opcao": False,
        }
        company, _, _ = upsert_company(session, record, "MOCK", "MOCK", is_mock=True)
        created.append(company)
    session.flush()
    customers = [c for c in created if c.situacao_cadastral == "02"
                 and c.cnae_principal in {"4321500", "4673700", "4742300", "7112000", "4221902"}]
    for company in rng.sample(customers, min(n_customers, len(customers))):
        session.add(Customer(cnpj=company.cnpj, razao_social=company.razao_social,
                             uf=company.uf, municipio=company.municipio,
                             cnae=company.cnae_principal, company_id=company.id,
                             import_batch="MOCK", status="ok"))
    session.flush()
    mark_customers(session)
    rebuild_profile(session)
    session.commit()
    rescore_all(session)
    return {"companies": len(created), "customers": min(n_customers, len(customers))}
