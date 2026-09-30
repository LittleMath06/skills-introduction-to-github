"""Benchmark da busca em PostgreSQL com volume sintético (dados MOCK).

Uso (NUNCA em produção — cria dados fictícios):
  DATABASE_URL=postgresql+psycopg://... python scripts/benchmark_search.py 300000

Insere N empresas fictícias (is_mock = true) via generate_series, executa as consultas mais comuns
da tela de busca e imprime o tempo médio. Remove os dados ao final.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import text  # noqa: E402

from prospeccao.db import create_all, init_engine, new_session  # noqa: E402
from prospeccao.services.search import SearchFilters, search  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200_000
url = os.environ["DATABASE_URL"]
if not url.startswith("postgresql"):
    sys.exit("Somente PostgreSQL")
engine = init_engine(url)
create_all()

INSERT = """
INSERT INTO companies (cnpj, cnpj_basico, is_matriz, razao_social, nome_fantasia, situacao_cadastral,
  uf, region, municipio, cnae_principal, search_text, has_phone, has_email, has_website, icms_status,
  similarity, potential, completeness, is_customer, customer_group, source, is_mock, first_seen_at,
  updated_at)
SELECT lpad(g::text, 14, '9'), lpad(g::text, 8, '9'), true,
  'EMPRESA BENCH ' || g, 'BENCH ' || g, CASE WHEN (g * 31 + 7) % 11 = 0 THEN '08' ELSE '02' END,
  (ARRAY['SP','MG','RJ','PR','SC','RS','GO','MT','BA','PE'])[1 + g % 10],
  (ARRAY['Sudeste','Sudeste','Sudeste','Sul','Sul','Sul','Centro-Oeste','Centro-Oeste','Nordeste','Nordeste'])[1 + g % 10],
  'CIDADE ' || (g % 500),
  (ARRAY['4321500','4673700','4742300','7112000','4120400','0115600'])[1 + (g / 10) % 6],
  'empresa bench ' || g || (ARRAY[' instalacoes eletricas',' material eletrico',' engenharia',' construtora',' agro soja'])[1 + g % 5],
  (g / 7) % 3 <> 0, (g / 3) % 2 = 0, (g / 13) % 5 = 0, 'nao_verificado',
  ((g * 7919) % 1000) / 10.0, (g * 104729 % 1000) / 10.0, (g % 100), false, false, 'MOCK', true,
  now(), now()
FROM generate_series(1::bigint, :n) g
ON CONFLICT (cnpj) DO NOTHING
"""

with engine.begin() as conn:
    t = time.perf_counter()
    conn.execute(text(INSERT), {"n": N})
    conn.execute(text("ANALYZE companies"))
    print(f"{N} empresas fictícias inseridas em {time.perf_counter() - t:.1f}s")

cases = {
    "padrão (potencial)": SearchFilters(),
    "UF + compat ≥ 70": SearchFilters(uf="SP", min_similarity=70, sort="similarity"),
    "região + CNAE + contato": SearchFilters(region="Sul", cnae="4321", has_phone=True),
    "termo livre": SearchFilters(q="eletric"),
    "página 200": SearchFilters(page=200),
    "linguagem natural": SearchFilters(nl="engenharia em São Paulo"),
}
try:
    with new_session() as s:
        for label, f in cases.items():
            search(s, f)  # aquecimento
            t = time.perf_counter()
            for _ in range(5):
                r = search(s, f)
            print(f"{label:28s} {(time.perf_counter() - t) / 5 * 1000:7.1f} ms  ({r['total']} resultados)")
finally:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM companies WHERE is_mock AND source = 'MOCK' AND razao_social LIKE 'EMPRESA BENCH %'"))
    print("Dados de benchmark removidos")
