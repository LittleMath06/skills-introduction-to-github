# 10 — Documentação final

Sistema de Prospecção de Clientes — fios, cabos elétricos e cabos especiais · versão 1.0.0 · 30/09/2026

Documentos de apoio: [01 Requisitos](01-requisitos.md) · [02 Fontes de dados](02-fontes-de-dados.md) ·
[03 Arquitetura](03-arquitetura.md) · [04 Banco de dados](04-database.md) ·
[05 UX/wireframes](05-ux-wireframes.md) · [06 API](06-api.md) ·
[07 Análise da base de clientes](07-analise-base-clientes.md) ·
[08 Tutorial de instalação e deploy](08-tutorial-instalacao-e-deploy.md)

---

## 1. Visão geral

Aplicação web privada, de usuário único (Paulo Alarcon), que reúne empresas de **todo o Brasil**
a partir dos dados abertos oficiais do CNPJ, compara cada uma com a base de clientes que Paulo já
atende e entrega uma lista **priorizada e explicada** de potenciais clientes, com dados cadastrais,
fiscais e de contato rastreáveis até a fonte, além de um fluxo simples de acompanhamento de leads.

## 2. Problema

A prospecção era feita **manualmente**, em vários sites e buscadores: pesquisar empresas, conferir
CNPJ um a um, descobrir atividade, localização e contato, anotar em planilhas. O processo era
demorado, repetitivo, sujeito a erros, sem critério uniforme de priorização e sem atualização —
cada nova rodada de prospecção recomeçava do zero.

## 3. Solução

| Antes | Agora |
|---|---|
| Buscar empresa por empresa em sites diferentes | Base local com empresas do Brasil inteiro importada dos arquivos oficiais da Receita |
| Intuição sobre "quem parece cliente" | Perfil de cliente ideal calculado da base real de clientes |
| Sem priorização | Compatibilidade (0–100 %) e potencial, com a explicação de cada ponto |
| Conferir CNPJ/cadastro manualmente | Situação, CNAE, porte, endereço, Simples/MEI já disponíveis, com data e fonte |
| Procurar telefone/site | Contatos do cadastro + site oficial (robots.txt respeitado), com origem de cada contato |
| Planilha solta | Leads com status, favoritos, analisados, descartados e observações |
| Refazer tudo | Atualização mensal automática com histórico de mudanças e detecção de empresas baixadas |

## 4. Público

Um único usuário: **Paulo Alarcon** (compra e venda de fios, cabos elétricos e cabos especiais).
Acesso por navegador no computador e no celular.

## 5. Objetivos

**Geral:** reduzir o esforço e o desgaste da busca manual por novos clientes, tornando-a mais rápida,
organizada e escalável.

**Específicos:** (1) localizar empresas em todo o Brasil; (2) classificar por segmento; (3) medir
semelhança com os clientes atuais; (4) priorizar por potencial; (5) apresentar dados cadastrais,
fiscais e comerciais com fonte; (6) organizar o acompanhamento dos leads; (7) manter os dados atualizados.

## 6. Requisitos

Requisitos funcionais RF01–RF21 e não funcionais RNF01–RNF11 estão em [01-requisitos.md](01-requisitos.md).
Situação na v1:

| Requisito | Situação |
|---|---|
| RF01 login / RF21 API documentada | ✅ |
| RF02 importação da base de clientes (CSV/XLSX, validação, deduplicação, relatório) | ✅ inclusive listas só com nomes (formato da planilha recebida) |
| RF03 perfil de cliente ideal | ✅ |
| RF04 importação dos dados abertos do CNPJ (filtrada) / RF18 mudanças e baixas | ✅ (layout validado com arquivos de teste; validar com o arquivo real do mês — ver §20) |
| RF05 consulta pontual de CNPJ | ✅ (BrasilAPI/OpenCNPJ, cache 30 dias) |
| RF06 segmentos / RF07 compatibilidade / RF08 potencial | ✅ explicáveis e configuráveis |
| RF09 filtros + pesquisa livre / RF10 ordenação e paginação | ✅ |
| RF11 página da empresa | ✅ |
| RF12 leads / RF13 configurações | ✅ |
| RF14 contatos pelo site | ✅ |
| RF15 ICMS oficial (SEFAZ) | ✅ implementado, **desativado até configurar certificado digital** |
| RF16 informações/benefícios fiscais com fonte | ✅ cadastro manual com fonte obrigatória |
| RF17 jobs em background com progresso | ✅ |
| RF19 dashboard / RF20 status das fontes | ✅ |

## 7. Regras de negócio

RN01–RN12 em [01-requisitos.md](01-requisitos.md) §7. Destaques implementados e testados:

* CNPJ validado (DV) — inclusive o novo **CNPJ alfanumérico** (IN RFB 2.229/2024, vigente desde jul/2026).
* Deduplicação por CNPJ (restrição `UNIQUE`); matriz × filial distinguidas; filiais de um cliente
  aparecem como **"Grupo já atendido"**; clientes atuais ficam fora da lista de leads.
* Empresa não ativa tem potencial 0.
* Informação fiscal "confirmada" exige fonte oficial com URL; benefícios nunca são inferidos.
* Contato com indício de pessoa física é sinalizado ("possível pessoal").
* Descartar tira a empresa das buscas (recuperável em Leads › Descartados).

## 8. Arquitetura

Monólito modular (detalhes e justificativa em [03-arquitetura.md](03-arquitetura.md)):

```
Navegador ──► web/ (páginas Jinja2) ─┐
          └─► api/ (REST JSON) ──────┤── security.py (sessão, CSRF, rate limit)
                                     ▼
                            services/ (casos de uso, jobs)
                                     ▼
            domain/ (regras puras: CNPJ, segmentos, similaridade, potencial, busca livre)
                                     ▼
       sources/ (Receita, API CNPJ, SEFAZ, site)   models.py/db.py (SQLAlchemy)
                                     ▼
                           PostgreSQL (prod) / SQLite (dev)
```

## 9. Tecnologias

Python 3.11 · FastAPI · SQLAlchemy 2 · PostgreSQL 16 / SQLite · Jinja2 + CSS/JS próprios (sem
framework front-end, sem build) · httpx · openpyxl · scrypt (hashlib) · pytest · Playwright/Chromium ·
Docker Compose · Caddy (HTTPS automático).

## 10. Banco de dados

Ver [04-database.md](04-database.md) (DER, cardinalidades, índices, rastreabilidade).

## 11. API

Ver [06-api.md](06-api.md) e a documentação interativa em `/api/docs` (após login).

## 12. Integrações

| Integração | Tipo | Estado |
|---|---|---|
| Dados abertos do CNPJ (Receita) | arquivos ZIP mensais | ativa (download ou pasta local) |
| BrasilAPI / OpenCNPJ | REST, consulta pontual | ativa, com limite de 1 req/3 s e cache |
| SEFAZ NfeConsultaCadastro 4.00 | SOAP 1.2 + certificado ICP-Brasil | pronta, desativada por padrão |
| Site oficial da empresa | HTTP (robots.txt, 1 req/5 s por domínio) | ativa |
| OpenStreetMap | apenas link | ativa |

Camada `DataSource` (sources/base.py) permite trocar ou adicionar fontes sem alterar o restante.

## 13. Fontes de dados

Pesquisa, avaliação (licença, termos, limites, confiabilidade) e decisões em
[02-fontes-de-dados.md](02-fontes-de-dados.md). **Nenhum dado é inventado**: sem fonte, o campo
aparece como "Não disponível".

## 14. Segurança

| Controle | Implementação |
|---|---|
| Autenticação | formulário + sessão em cookie assinado (`HttpOnly`, `SameSite=Lax`, `Secure` em produção, expiração 8 h) |
| Senha | scrypt (N=2¹⁵, r=8, p=1, salt aleatório); mínimo 10 caracteres; tempo constante para usuário inexistente |
| Força bruta | 5 falhas/15 min por IP → HTTP 429 |
| CSRF | token por sessão exigido em toda alteração (header `X-CSRF-Token` ou campo de formulário), inclusive no login |
| Autorização | todas as rotas exigem sessão, exceto `/login`, `/health`, `/static`; teste automatizado varre todas as rotas `/api` |
| Entrada | Pydantic em todos os endpoints (tamanhos, faixas, enums, URLs `http(s)`), upload limitado a 20 MB e extensões permitidas |
| SQL injection | somente consultas parametrizadas do ORM |
| XSS | autoescape do Jinja2; CSP `script-src 'self'` sem scripts inline; nenhum `innerHTML` com dados |
| Cabeçalhos | CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, HSTS em produção, `Cache-Control: no-store` |
| Segredos | apenas variáveis de ambiente; `.env`, certificados e chaves no `.gitignore`; produção recusa `SECRET_KEY` fraca e dados MOCK |
| Erros | mensagem genérica + código de referência; detalhe apenas no log; filtro de log omite mensagens com possíveis segredos |
| HTTPS | Caddy com Let's Encrypt (docker-compose) |
| Arquivos enviados | a planilha de clientes é apagada do disco após a importação |

## 15. LGPD

* **Finalidade:** prospecção comercial B2B (legítimo interesse), uso exclusivo de Paulo.
* **Necessidade/minimização:** o arquivo de **sócios** da Receita (dados de pessoas físicas) **não é
  importado**; somente contatos institucionais publicados pela própria empresa (cadastro CNPJ e site).
* **Transparência:** cada contato mostra origem e data; contatos com indício de pessoa física
  (e-mail pessoal em provedor gratuito, e-mail nominal, telefone de MEI) são marcados "possível pessoal".
* **Segurança/controle de acesso:** ver §14.
* **Qualidade:** datas de coleta, histórico de alterações, atualização mensal.
* **Exclusão:** botão "Excluir" por contato e `python -m prospeccao.cli forget <CNPJ>` (remove contatos,
  lead e histórico). Estrutura pronta para políticas de retenção (datas `fetched_at`/`updated_at` em
  todos os registros).
* **Base de clientes de Paulo:** privada; não exposta em rotas públicas; arquivo enviado é apagado.

## 16. Metodologia de classificação dos leads (segmentos)

1. O CNAE principal é comparado aos **prefixos de CNAE** de cada segmento; vence o prefixo **mais
   longo** (mais específico). Confiança: 2 dígitos 60 %, 3 → 72 %, 4 → 82 %, 5 → 88 %, 7 → 92 %.
2. CNAEs secundários valem metade.
3. **Palavras-chave** no nome/atividade/site somam bônus (+0,25) ou, sozinhas, classificam (0,55).
4. Sem sinais → "Outros" (20 %).
5. Resultado sempre marcado **estimado** (com a explicação) — exceto quando Paulo define manualmente,
   o que é preservado nos recálculos.

Segmentos padrão (editáveis em Configurações): Instaladores (4321, 4322, 4329), Distribuidores (4673,
4679, 4663, 4669, 4674, 4684, 46), Varejo (4742, 4744, 4743, 4789, 47), Energia (35, 4221901/902/905),
Telecomunicações (61, 4221903/904), Infraestrutura (42), Construção Civil (41, 43), Engenharia (7112,
7119), Automação (2651, 3321, 2790, 3313), Integradores (8020 + palavras "solar", "integrador"…),
Fabricantes (26–30), Agrobusiness (01–03, 4623, 4661, 4683, agroindústria), Indústria (05–33), Outros.

## 17. Metodologia de similaridade e de potencial

**Perfil de cliente ideal:** contagens, na base de clientes, de CNAE (subclasse, classe, grupo,
divisão), segmento, UF, região, porte e palavras-chave (presentes em ≥ 2 clientes).

**Compatibilidade** = Σ peso × valor (0–1) × 100, pesos padrão:

| Critério | Peso | Valor |
|---|---|---|
| CNAE | 40 % | mesma subclasse 1 · classe 0,85/0,7 · grupo 0,5 · divisão 0,3 · secundário ×0,6 |
| Segmento | 20 % | frequência do segmento ÷ segmento mais comum ("Outros" ×0,5) |
| Atividade (palavras) | 15 % | palavras em comum com as mais frequentes (3+ = 1) |
| Localização | 15 % | frequência da UF ÷ UF mais comum; senão 0,5 × região |
| Porte | 10 % | frequência do porte ÷ porte mais comum |

A tela mostra os pontos de cada critério e "perfil semelhante a **N** clientes existentes".

**Potencial** = 55 % compatibilidade + 20 % afinidade estimada do segmento com cabos (premissa
configurável: Instaladores/Distribuidores/Energia 100 % … Outros 20 %) + 15 % completude dos dados +
10 % maturidade (idade). Empresas não ativas: 0.

Todos os pesos são configuráveis (normalizados para somar 100 %). As notas são **estimativas**;
a interface usa "perfil compatível", "potencial cliente", "indício de aderência" — nunca "compra".

**ICMS "provável":** atividade típica de contribuinte (indústria, comércio, energia, comunicação,
transporte) → "Provável contribuinte (inferido)", confiança 60 %/40 %, com aviso de que precisa de
confirmação. "Confirmado" somente via SEFAZ.

## 18. Testes realizados

Executados em 30/09/2026 nesta versão — **138 testes, todos aprovados em SQLite e em PostgreSQL 16** (e em Python 3.11, 3.12 e 3.13):

| Arquivo | Tipo | Qtde | Cobre |
|---|---|---|---|
| `test_domain.py` | unitários | 53 | CNPJ (incl. alfanumérico, zeros perdidos em planilha, inválidos), telefones/e-mails, regiões, classificação por CNAE/palavra-chave/fallback, similaridade, pesos, potencial, completude, inferência de ICMS, pesquisa livre, chaves de nome e abreviações de ERP, redistribuição de pesos sem dados |
| `test_sources.py` | integração (HTTP simulado) | 23 | layout Receita, ZIP latin-1, download inválido, API de CNPJ (200/404/429/500/sem rede/JSON inválido), rate limiter, SEFAZ (111/259/erro/XML inválido/não configurada), site (contatos, pessoal × empresa, robots.txt, robots indisponível, não-HTML, verificação de propriedade) |
| `test_imports.py` | integração (banco) | 16 | importação filtrada, reimportação idempotente, mudanças e baixas, filtros por UF, falha de fonte registrada, pontuação após importação, CSV/XLSX de clientes com CNPJ inválido/CPF/duplicado/sem CNPJ/linhas vazias/cabeçalho deslocado, arquivos inválidos, vínculo com empresas e perfil, CNPJ duplicado no mesmo lote, truncamento de campos longos, lista só com nomes (formato da planilha real, com nomes fictícios), identificação pela razão social nos arquivos da Receita (exato, nome cortado, homônimos → ambíguo), vínculo pelo nome na base local, reenvio com CNPJ sem duplicar |
| `test_api.py` | funcionais e negativos | 44 | login/logout, senha errada, rate limit, CSRF, todas as rotas protegidas, cabeçalhos, hash de senha, configuração insegura em produção, MOCK bloqueado, filtros/ordenação/paginação, pesquisa livre, filtros inválidos (422), 404, ciclo do lead, segmento manual, informações fiscais com fonte, pesos/segmentos/status, dashboard, consulta de CNPJ com cache e falhas, enriquecimento por site, ICMS confirmado, job com falha, upload inválido, exclusão de contato (LGPD), CNPJ manual de cliente |
| `test_ui.py` | interface (Chromium) | 2 | fluxo completo em desktop e celular: login (inclusive senha errada), pesquisa livre, remoção de filtro, detalhes, salvar lead, status, observação, lista de leads, sem rolagem horizontal, sem erros de JavaScript |

Como rodar: `pytest` (SQLite) · `TEST_DATABASE_URL=postgresql+psycopg://... pytest` (PostgreSQL).
A CI do GitHub (`.github/workflows/ci.yml`) executa os dois.

**Defeitos encontrados pelos testes e corrigidos durante o desenvolvimento:** telefone "00000000"
aceito; "Mato Grosso do Sul" interpretado como região Sul; telefone `tel:+55…` com código do país;
CPF de 11 dígitos não identificado; filtros inválidos retornando 500 em vez de 422; bloqueio de
escrita do SQLite durante jobs; relacionamentos desatualizados após alterar status/segmento; campo
de referência maior que a coluna no PostgreSQL; CNPJ repetido no mesmo lote de importação; linha de
título ("Relatório de clientes") confundida com cabeçalho de lista de nomes.

**Validação com a planilha real (30/09/2026, banco local de teste, fora do repositório):** 207 linhas →
205 clientes, 2 duplicados unificados, 0 erros; perfil calculado; reenvio da planilha de apoio
atualizou os 205 sem duplicar. Detalhes agregados em [07-analise-base-clientes.md](07-analise-base-clientes.md).

**Desempenho (PostgreSQL 16, 300 mil empresas sintéticas MOCK, `scripts/benchmark_search.py`):**
busca padrão 49 ms · UF + compatibilidade ≥ 70: 40 ms · região + CNAE + telefone: 72 ms · termo livre
(índice trigram): 50 ms · página 200: 66 ms. (Ambiente de desenvolvimento; repetir no servidor final.)

**Não testado contra os serviços reais** (ambiente de desenvolvimento sem acesso a `gov.br` e às
APIs): download da Receita, BrasilAPI, SEFAZ e sites reais — ver §20.

## 19. Resultados

| Aspecto | Processo anterior (manual) | Processo proposto |
|---|---|---|
| Tempo para montar uma lista de prospects | vários acessos a sites por empresa | uma pesquisa com filtros; resultado paginado em < 0,1 s no benchmark — **tempo real: métrica a ser validada após utilização pelo usuário** |
| Quantidade de informações | dependia do que se encontrava | cadastro completo, CNAEs, porte, Simples/MEI, contatos, site, notas explicadas — **cobertura real: métrica a ser validada após a primeira importação** |
| Facilidade de pesquisa | buscadores genéricos | filtros combináveis + pesquisa em linguagem natural |
| Organização | planilhas/anotações | leads com status, favoritos, descartes e observações |
| Atualização | manual, esporádica | mensal automática, com histórico de mudanças e detecção de baixas |
| Identificação de potenciais clientes | intuição | ranking por semelhança com os clientes reais, explicado |
| Esforço operacional | alto e repetitivo | concentrado na análise e no contato — **redução real: métrica a ser validada após utilização pelo usuário** |

Critério de sucesso definido no roteiro: **avaliação do próprio Paulo após uso**. Sugestão de
métricas a coletar nas primeiras semanas: tempo médio para chegar a 20 leads qualificados; % de
leads salvos que viram "Contato realizado"; % de descartados (indica ajuste de pesos/segmentos).

## 20. Limitações

1. **A base de clientes recebida tem só razões sociais** (205 únicas, sem CNPJ/UF/CNAE). Até os CNPJs
   serem identificados (automaticamente pela razão social na importação da Receita, ou informados por
   Paulo), a compatibilidade usa apenas segmento estimado pelo nome e palavras; CNAE, localização e
   porte ficam "não avaliados". 58 nomes não têm palavra de atividade e só serão classificados pelo
   CNAE. O título da planilha indica clientes **cotados**, não necessariamente compradores.
   Vínculos pela razão social podem errar em nomes muito parecidos — ficam marcados para conferência;
   homônimos ficam "ambíguos" e não são vinculados.
2. **Fontes reais não exercitadas neste ambiente** (sem rede para `gov.br`/APIs). Layout e contratos
   foram implementados pela documentação oficial e testados com dados simulados. Na implantação:
   `python -m prospeccao.cli check-sources` e primeira importação de um mês real, conferindo o log.
3. **ICMS:** confirmação oficial depende de certificado digital e-CNPJ A1 e dos endpoints por UF;
   Sintegra tem CAPTCHA e não é automatizado. Sem isso, apenas "provável (inferido)" ou "não verificado".
4. **Regime Lucro Presumido/Real e benefícios fiscais:** não há fonte aberta — somente cadastro manual.
5. **Contatos:** telefone/e-mail do cadastro CNPJ podem estar desatualizados; sites só são lidos quando
   o domínio é conhecido (e-mail corporativo ou informado por Paulo). Sem LinkedIn/Instagram por coleta
   direta (termos de uso) — apenas links publicados no próprio site.
6. **Volume:** a importação completa (~60 mi de estabelecimentos) exige muito disco/tempo; por isso é
   filtrada. A importação mantém em memória o conjunto de CNPJs já existentes (≈ 100 MB por milhão).
7. **Pesquisa livre** é baseada em regras (sinônimos, UFs, regiões, cidades) — não é IA; a interpretação
   é sempre exibida e pode ser corrigida pelos filtros.
8. **Jobs** rodam em uma thread do processo web (1 worker); reiniciar a aplicação interrompe o job
   (marcado como "interrompido"). Um job do mesmo tipo em andamento não é duplicado.
9. **Esquema do banco** criado com `create_all`; mudanças futuras de colunas exigirão migração (Alembic).
10. Recuperação de senha por e-mail não implementada (decisão de segurança para usuário único): usar a CLI.

## 21. Melhorias futuras

1. Validar com a base real de clientes e ajustar pesos/segmentos com Paulo (maior ganho imediato).
2. Configurar certificado digital para confirmação de ICMS nas UFs prioritárias.
3. Alembic para migrações; fila dedicada (ex.: RQ/Redis) se o volume de jobs crescer.
4. Aprender pesos a partir do histórico de leads convertidos em "Cliente" (mantendo explicabilidade).
5. Exportação CSV/Excel de listas de leads; lembretes de retorno por lead.
6. Busca por raio geográfico (geocodificação do CEP com fonte aberta).
7. Autenticação em dois fatores (TOTP).
8. Política de retenção automática para contatos não atualizados há X meses.

## 22. Instalação (desenvolvimento)

```bash
git clone <repositório> && cd <repositório>
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # defina SECRET_KEY e ADMIN_PASSWORD (≥ 10 caracteres)
export PYTHONPATH=src
python -m prospeccao.cli init
python -m prospeccao.cli seed-mock   # opcional: dados FICTÍCIOS para explorar a interface
uvicorn prospeccao.main:app_factory --factory --reload
# http://localhost:8000  (usuário: ADMIN_USERNAME, senha: ADMIN_PASSWORD)
pytest                            # testes
```

## 23. Configuração

Todas as opções estão comentadas em [`.env.example`](../.env.example). Principais:

| Variável | Para quê |
|---|---|
| `APP_ENV` | `production` ativa cookie `Secure`, HSTS e as travas de segurança |
| `SECRET_KEY` | assinatura da sessão (≥ 32 caracteres em produção) |
| `DATABASE_URL` | PostgreSQL em produção |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | cria o usuário na primeira execução |
| `RF_FILTER_UFS`, `RF_FILTER_CNAE_PREFIXES`, `RF_ONLY_ACTIVE` | escopo da importação da Receita |
| `CNPJ_API_PROVIDER` | `brasilapi` ou `opencnpj` |
| `WEBSITE_ENRICHMENT_ENABLED` | liga/desliga leitura de sites |
| `ICMS_CERT_FILE`, `ICMS_KEY_FILE`, `ICMS_ENDPOINTS` | consulta oficial de ICMS |

Fluxo inicial recomendado: 1) importar a base de clientes (a planilha só com nomes é aceita);
2) importar os dados da Receita — o filtro automático usa os CNAEs dos clientes e segmentos, e a
importação procura os CNPJs dos clientes pela razão social; 3) conferir em *Clientes* os vínculos por
nome, os ambíguos e completar CNPJs; 4) revisar segmentos e pesos; 5) enriquecer os melhores leads.

## 24. Deploy

### 24.1 Onde hospedar (e por que não no Netlify)

O Netlify hospeda sites estáticos e funções serverless curtas em JavaScript/TypeScript/Go. Este
sistema precisa de **servidor Python contínuo, PostgreSQL, disco persistente e processos longos**
(a importação mensal da Receita leva horas). Por isso **não roda no Netlify** — publicar só os
arquivos HTML/CSS geraria páginas sem login, sem banco e sem busca.

| Opção | Adequação | Observação |
|---|---|---|
| **Render (Blueprint `render.yaml`)** | ✅ recomendada | Docker + PostgreSQL gerenciado + disco + HTTPS automático, configurado em poucos cliques |
| Railway / Fly.io | ✅ | usam o mesmo `Dockerfile` (porta via `PORT`); criar PostgreSQL e volume no painel |
| VPS própria (docker-compose) | ✅ | mais barata em volume grande; exige administrar o servidor (§24.3) |
| Netlify / GitHub Pages / Vercel estático | ❌ | não executam o backend Python nem mantêm banco |

### 24.2 Render (passo a passo)

1. Suba este repositório para o GitHub (privado).
2. No Render: **New → Blueprint**, escolha o repositório. O `render.yaml` cria o serviço web
   (Docker), o PostgreSQL 16 e um disco de 40 GB em `/data`.
3. Informe `ADMIN_PASSWORD` quando o painel pedir (≥ 10 caracteres). `SECRET_KEY` é gerada
   automaticamente; `DATABASE_URL` vem do banco criado (o sistema converte o formato `postgres://`).
4. Após o deploy, acesse a URL `https://….onrender.com` (HTTPS automático) e faça login.
5. Em *Clientes*, importe a planilha; em *Administração*, rode a importação da Receita
   ("Baixar mês mais recente e importar"). Repita mensalmente (ou agende um Cron Job no Render com
   `python -m prospeccao.cli update` — atenção: cron jobs do Render não compartilham o disco do
   serviço web, então prefira disparar pela página *Administração*).
6. Domínio próprio: *Settings → Custom Domains* no serviço web.
7. Backup: o PostgreSQL gerenciado tem backups conforme o plano; exporte periodicamente com
   `pg_dump` usando a *External Database URL*.

Confira planos e preços no painel antes de confirmar (os nomes de plano no `render.yaml` podem
precisar de ajuste). Planos gratuitos "dormem" e não têm disco persistente — não recomendados.

### 24.3 VPS própria (docker-compose)

Servidor Linux com Docker (VPS de 2 vCPU/4 GB RAM é suficiente para a base filtrada; reserve disco
para os ZIPs da Receita, ~25 GB se baixar o mês inteiro):

```bash
cp .env.example .env    # APP_ENV=production, SECRET_KEY, ADMIN_PASSWORD, POSTGRES_PASSWORD, DOMAIN
docker compose up -d --build
# DNS do DOMAIN apontando para o servidor → Caddy emite o certificado HTTPS automaticamente
docker compose exec app python -m prospeccao.cli check-sources
```

* **Backup:** `scripts/backup.sh` diário no cron (mantém 14 cópias; copie para fora do servidor).
  Restauração: `scripts/restore.sh arquivo.sql.gz` — testar periodicamente.
* **Atualização de dados:** `scripts/cron-update.sh` mensal (baixa o mês mais recente, importa,
  recalcula e enriquece 100 leads).
* **Atualização da aplicação:** `git pull && docker compose up -d --build`.
* **Logs:** `docker compose logs -f app` (sem segredos). **Monitoramento:** `/health` (usado pelo
  healthcheck do contêiner) e a página *Administração* (fontes, jobs, erros, desatualização, duplicidades).
* O Dockerfile foi escrito mas **não pôde ser construído neste ambiente** (sem daemon Docker); o modo
  produção foi validado executando o mesmo comando do contêiner com PostgreSQL (HSTS, CSP, bloqueio
  de MOCK e de chave fraca verificados).

---

## Checklist de aceitação (prompt §35)

| Critério | Status |
|---|---|
| Pesquisar empresas em todo o Brasil, filtrar, por segmento e por semelhança | ✅ |
| Página de detalhes; CNPJ, dados cadastrais, região e segmento | ✅ |
| ICMS quando disponível; benefícios com fonte; estimativas identificadas | ✅ (confirmação oficial depende do certificado) |
| Site e contatos quando disponíveis; salvar lead; observações e status | ✅ |
| Mecanismo de atualização; duplicidades tratadas; data da última atualização | ✅ |
| Responsivo, navegação simples, desktop e celular | ✅ (teste de UI em 1366 px e 390 px) |
| Código organizado, testes, documentação, GitHub, instruções de instalação | ✅ |
