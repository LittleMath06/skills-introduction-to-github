# Prospecção de Clientes — fios, cabos elétricos e cabos especiais

Sistema web **privado, de usuário único** (Paulo Alarcon) para encontrar, analisar e priorizar
potenciais clientes em todo o Brasil, usando como referência a base de empresas que Paulo já atende.

> Pergunta que o sistema responde: *"Quais empresas ainda não atendo, mas têm características
> semelhantes às que já compram nossos produtos?"*

## O que faz

* Importa empresas dos **dados abertos oficiais do CNPJ** (Receita Federal), filtradas por CNAE/UF.
* Importa a **base de clientes atuais** (CSV/XLSX), valida CNPJs, remove duplicidades e calcula o
  **perfil de cliente ideal**.
* Classifica cada empresa em **segmentos** (Instaladores, Distribuidores, Energia, Agro…) e calcula
  **compatibilidade** e **potencial** — sempre como estimativas, com a explicação de cada ponto.
* Busca com **filtros combináveis** e **pesquisa livre** ("instaladores em Minas Gerais",
  "semelhantes aos meus clientes").
* **Cartão da empresa** com cadastro, atividade, contatos (com origem), informações fiscais
  classificadas em *confirmado / provável / possível* com fonte e data, histórico de alterações.
* **Leads**: salvar, status comercial configurável, favoritos, analisados, descartados, observações.
* **Atualização periódica**, jobs em segundo plano com progresso, painel de status das fontes.

## Início rápido (desenvolvimento)

> **Passo a passo completo, do zero até a produção (Windows, macOS e Linux):**
> [docs/08-tutorial-instalacao-e-deploy.md](docs/08-tutorial-instalacao-e-deploy.md)

```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install -e .
cp .env.example .env          # preencha SECRET_KEY e ADMIN_PASSWORD (≥ 10 caracteres)
python -m prospeccao.cli init
python -m prospeccao.cli seed-mock      # opcional: dados FICTÍCIOS (marcados MOCK)
uvicorn prospeccao.main:app_factory --factory --reload
```

Acesse <http://localhost:8000>. Testes: `python -m pytest` (135 testes; Python 3.11–3.13; também
em PostgreSQL com `TEST_DATABASE_URL`).

## Produção

**Não use Netlify** (só executa sites estáticos e funções JS/Go curtas; este sistema precisa de
servidor Python, PostgreSQL e disco). Opção recomendada: **Render** com o `render.yaml` incluso
(New → Blueprint). Alternativa: VPS com `docker compose up -d --build` (app + PostgreSQL + Caddy com
HTTPS automático). Detalhes de
configuração, backup, atualização mensal e monitoramento em
[docs/10-documentacao-final.md](docs/10-documentacao-final.md#24-deploy).

## Documentação

| Documento | Conteúdo |
|---|---|
| [01 — Requisitos](docs/01-requisitos.md) | problema, requisitos, regras, riscos, informações faltantes |
| [02 — Fontes de dados](docs/02-fontes-de-dados.md) | pesquisa e decisão sobre cada fonte (licença, limites, termos) |
| [03 — Arquitetura](docs/03-arquitetura.md) | camadas, tecnologias, fluxo de dados, segurança |
| [04 — Banco de dados](docs/04-database.md) | DER, índices, rastreabilidade |
| [05 — UX/wireframes](docs/05-ux-wireframes.md) | fluxos e telas |
| [06 — API](docs/06-api.md) | endpoints, filtros, códigos de erro |
| [07 — Análise da base de clientes](docs/07-analise-base-clientes.md) | estrutura e padrões da planilha recebida (agregado) |
| [08 — Tutorial: instalação, execução e deploy](docs/08-tutorial-instalacao-e-deploy.md) | passo a passo do zero até a produção, troubleshooting e checklist |
| [10 — Documentação final](docs/10-documentacao-final.md) | visão completa, metodologias, testes, resultados, limitações, instalação, deploy |

## Estrutura

```
src/prospeccao/
  domain/     regras puras (CNPJ, segmentos, similaridade, potencial, pesquisa livre, fiscal)
  services/   casos de uso (busca, importações, enriquecimento, leads, jobs, dashboard)
  sources/    integrações (Receita, API de CNPJ, SEFAZ, site oficial) — camada DataSource
  api/        REST JSON          web/  páginas        templates/ static/  interface
  models.py   banco (SQLAlchemy) security.py  autenticação, CSRF, rate limit    cli.py  administração
tests/        unitários, integração, funcionais, negativos e interface (Playwright)
scripts/      backup, restauração, atualização via cron, benchmark
deploy/       Caddyfile (HTTPS)
```

## Princípios

Nenhum dado inventado · toda informação externa com fonte e data · estimativas sempre rotuladas ·
nenhum segredo no Git · scraping somente do site da própria empresa, respeitando robots.txt ·
LGPD: sem dados de sócios, contatos pessoais sinalizados, exclusão sob demanda.
