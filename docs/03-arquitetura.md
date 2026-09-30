# 03 — Arquitetura (Fase 3)

## 1. Decisão: monólito modular em Python

| Alternativa | Prós | Contras | Decisão |
|---|---|---|---|
| SPA (React) + API + fila (Redis/Celery) + microsserviços | escalável, "moderno" | 3–4 processos, build JS, mais pontos de falha para **1 usuário** | ❌ overengineering |
| **Monólito FastAPI** + páginas server-side (Jinja2) + JS leve + API REST + jobs em thread | 1 processo, 1 banco, deploy simples, API documentada automática (OpenAPI), Python forte em ETL de CSV | escala vertical | ✅ |
| Django | admin pronto | ORM/estrutura mais pesados que o necessário | ❌ |

A ordem de prioridades do projeto (Confiabilidade > Segurança > Qualidade > Usabilidade > Performance >
Complexidade) favorece poucos componentes. A separação em camadas permite extrair API/SPA no futuro.

## 2. Tecnologias

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Linguagem | Python 3.11+ | ETL de arquivos grandes, bibliotecas maduras |
| Web/API | FastAPI + Starlette | validação com Pydantic, OpenAPI em `/api/docs` |
| Templates | Jinja2 + CSS próprio + JS vanilla | sem build, rápido, responsivo |
| ORM | SQLAlchemy 2 | consultas parametrizadas (anti SQL injection), portável SQLite/PostgreSQL |
| Banco | PostgreSQL 16 (produção) / SQLite (dev e testes) | PostgreSQL para milhões de linhas e concorrência; SQLite zero-config |
| HTTP client | httpx | timeouts, cliente com certificado (SEFAZ), `MockTransport` para testes |
| Planilhas | openpyxl + csv | importação XLSX/CSV |
| Senha | `hashlib.scrypt` (stdlib) | KDF memory-hard recomendada pela OWASP, sem dependência extra |
| Sessão | cookie assinado (`itsdangerous` via `SessionMiddleware`) | simples para usuário único |
| Jobs | tabela `jobs` + `ThreadPoolExecutor` no processo; CLI para cron | sem Redis; progresso persistido no banco |
| Testes | pytest, TestClient, Playwright (Chromium) | unitário, integração, funcional, UI |
| Deploy | Docker + docker-compose (app, PostgreSQL, Caddy com HTTPS automático) | reprodutível; HTTPS Let's Encrypt |

## 3. Camadas e pastas

```
Navegador (páginas Jinja2 + fetch JSON)
      ↓
src/prospeccao/web/        rotas de páginas (HTML)
src/prospeccao/api/        rotas REST (JSON)  ── autenticação/CSRF: security.py
      ↓
src/prospeccao/services/   casos de uso (application): busca, leads, importação, dashboard, jobs, fiscal
      ↓
src/prospeccao/domain/     regras puras, sem I/O: CNPJ, regiões, segmentos, similaridade, potencial,
                           completude, interpretação da busca livre
      ↓
src/prospeccao/sources/    integrações (infrastructure): DataSource e implementações
src/prospeccao/models.py   mapeamento ORM (infrastructure) ── db.py (engine/sessão)
      ↓
PostgreSQL / SQLite
```

Regras de negócio **não** acessam banco nem rede (`domain/` é 100 % testável isoladamente).

## 4. Camada de fontes

```
DataSource (base.py)             name, kind, is_enabled(), check() -> SourceStatus
 ├── CNPJSource
 │    ├── ReceitaOpenDataSource  importação em lote dos arquivos oficiais (streaming, filtrada)
 │    └── CnpjApiSource          consulta pontual (BrasilAPI | OpenCNPJ), rate limit + cache
 ├── ICMSSource
 │    └── SefazIcmsSource        NfeConsultaCadastro 4.00 (SOAP + certificado)
 └── CompanyWebsiteSource        site oficial (robots.txt, rate limit por domínio)
```

Toda fonte devolve **dados + metadados de origem** (`source`, `url`, `fetched_at`, `reference_date`,
`confidence`). Falhas atualizam a tabela `data_sources` (último erro, contagem de falhas) exibida no
painel de status.

## 5. Fluxo de dados (pipeline de atualização)

```
Fonte (arquivos RF do mês)  → Coleta (download/stream do ZIP)
  → Validação (DV do CNPJ, colunas, datas)
  → Normalização (maiúsculas/acentos, telefone, CEP, UF, região)
  → Deduplicação (upsert por CNPJ; matriz/filial por cnpj_basico)
  → Detecção de mudanças (hash de campos → company_changes)
  → Enriquecimento (Simples/MEI, descrições CNAE/município/natureza; site sob demanda/lote)
  → Classificação (segmento) → Similaridade → Potencial → Completude
  → Banco → Interface/API
```

Jobs: `import_customers`, `import_receita`, `enrich_websites`, `rescore`, `icms_check`,
`cnpj_lookup`. Cada job grava `total`, `processed`, `errors`, `log` e `status`
(`queued/running/done/failed`). A interface faz polling de `/api/jobs/{id}`.

Agendamento: `python -m prospeccao.cli update` (cron mensal para a Receita, semanal para rescore e
enriquecimento). Não há agendador interno para evitar execução duplicada em múltiplos workers.

## 6. Segurança (resumo; detalhes em `10-documentacao-final.md`)

* Autenticação por formulário → cookie de sessão assinado (`HttpOnly`, `SameSite=Lax`, `Secure` em produção, expiração).
* Todas as rotas exigem sessão, exceto `/login`, `/health`, `/static`.
* CSRF: toda requisição que altera estado precisa do header `X-CSRF-Token` (JSON) ou campo `csrf_token` (form) igual ao token da sessão.
* Rate limiting de login (5 tentativas/15 min por IP) com atraso constante.
* Cabeçalhos: CSP restritiva, `X-Frame-Options: DENY`, `X-Content-Type-Options`, `Referrer-Policy`.
* Segredos em variáveis de ambiente (`.env` ignorado pelo Git); em produção a aplicação **recusa**
  iniciar com `SECRET_KEY` padrão.
* Erros: handler global devolve mensagem genérica + id de correlação; detalhe só no log.
* Logs mascaram tokens/senhas.

## 7. Integrações externas e resiliência

* Timeouts em todas as chamadas (10 s), sem retries agressivos (máx. 2 com backoff).
* Rate limiter por fonte/domínio.
* Cache: consultas de CNPJ por 30 dias; site por 30 dias (reconsulta manual possível).
* Falha de fonte **nunca** apaga dado existente; o dado fica com a data da última atualização válida.
