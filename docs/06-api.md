# 06 — API REST

* Base: `/api` · formato JSON · documentação interativa (OpenAPI/Swagger) em **`/api/docs`** (exige login).
* **Autenticação:** sessão por cookie (`prospeccao_session`, `HttpOnly`, `SameSite=Lax`, `Secure` em produção), obtida em `POST /login`.
* **CSRF:** toda requisição `POST/PUT/PATCH/DELETE` deve enviar o header `X-CSRF-Token` com o token da sessão (disponível na meta tag `csrf-token` das páginas).
* **Paginação:** `page` (≥ 1) e `page_size` (1–100). Respostas paginadas: `{items, total, page, page_size, pages}`.
* **Erros:** `{"detail": "..."}`; validação: `422 {"detail": "Dados inválidos", "erros": [{"campo", "erro"}]}`. Erros internos retornam 500 com um código de referência (o detalhe fica apenas no log).

| Código | Uso |
|---|---|
| 200 / 201 / 202 / 204 | ok / criado / processo iniciado (background) / removido |
| 401 | sem sessão válida |
| 403 | token CSRF ausente ou inválido |
| 404 | recurso inexistente |
| 409 | conflito (duplicado, ação não permitida — ex.: excluir registro fiscal do sistema, consultar SEFAZ sem configuração, enriquecer empresa MOCK) |
| 413 / 415 | arquivo grande demais / formato não suportado |
| 422 | dados inválidos |
| 429 | muitas tentativas de login |
| 502 | fonte externa indisponível |

## Empresas e busca

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/companies` | Busca com filtros na query string |
| POST | `/api/companies/search` | Mesma busca com filtros no corpo JSON |
| GET | `/api/companies/{id}` | Cartão completo (cadastro, atividade, contatos, fiscal, detalhes das notas) |
| PATCH | `/api/companies/{id}` | Correções manuais: `website`, `segment_id`, `clear_manual_segment` |
| POST | `/api/companies/lookup` | `{cnpj, force}` — consulta pontual na API pública (cache de 30 dias) |
| POST | `/api/companies/{id}/save` | Salva como lead (idempotente) |
| POST | `/api/companies/{id}/enrich` | Busca contatos no site oficial (job) |
| POST | `/api/companies/{id}/icms` | Consulta ICMS na SEFAZ (job; 409 se não configurada) |
| POST | `/api/companies/{id}/fiscal` | Registra informação/benefício fiscal **com fonte** |
| DELETE | `/api/fiscal/{id}` | Remove registro fiscal manual |
| DELETE | `/api/contacts/{id}` | Remove contato (ex.: pedido do titular — LGPD) |

Filtros de busca (`SearchFilters`):

| Parâmetro | Exemplo | Observação |
|---|---|---|
| `nl` | `instaladores em São Paulo` | pesquisa livre; a interpretação volta em `interpretacao` |
| `q` | `eletrica` ou `11222333000181` | termos (nome, atividade, cidade) ou CNPJ |
| `region` | `Sudeste` | Norte, Nordeste, Centro-Oeste, Sudeste, Sul |
| `uf`, `city` | `SP`, `Campinas` | |
| `segment` | `Instaladores` | nome do segmento |
| `cnae` | `4321` | prefixo de 2 a 7 dígitos (7 dígitos também busca CNAEs secundários) |
| `porte` | `01`, `03`, `05`, `00` | micro, pequeno porte, demais, não informado |
| `situacao` | `02` (padrão) | vazio = todas; 01 nula, 03 suspensa, 04 inapta, 08 baixada |
| `icms` | `contribuinte`, `provavel`, `confirmado_habilitado`… | |
| `has_site`, `has_phone`, `has_email` | `true`/`false` | |
| `min_similarity`, `min_potential` | `70` | 0–100 |
| `updated_since` | `2026-09-01` | |
| `include_customers` | `false` (padrão) | clientes atuais ficam ocultos |
| `lead_state` | `todos`, `novos`, `salvos`, `favoritos`, `analisados`, `descartados` | padrão oculta descartados |
| `sort` | `potential` (padrão), `similarity`, `location`, `segment`, `updated`, `completeness`, `name` | |

Exemplo:

```http
GET /api/companies?region=Sudeste&segment=Instaladores&has_phone=true&min_similarity=70&sort=similarity&page=1&page_size=25
```

```json
{
  "items": [{
    "id": 42, "cnpj": "…", "cnpj_formatado": "…", "razao_social": "…", "nome_fantasia": "…",
    "municipio": "CAMPINAS", "uf": "SP", "regiao": "Sudeste",
    "segmento": "Instaladores", "segmento_estimado": true, "cnae_principal": "4321-5/00",
    "compatibilidade": 87.5, "potencial": 81.2, "completude": 72.7, "situacao": "Ativa",
    "icms": "ICMS não verificado", "site": null, "tem_telefone": true, "tem_email": true,
    "cliente_atual": false, "grupo_ja_atendido": false, "atualizado_em": "2026-09-30T15:00:00",
    "mock": false, "lead": null
  }],
  "total": 1, "page": 1, "page_size": 25, "pages": 1, "interpretacao": {}
}
```

## Leads

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/leads` | `status_id`, `favorite`, `analyzed`, `discarded`, paginação |
| PATCH | `/api/leads/{id}` | `status_id`, `favorite`, `analyzed`, `discarded` |
| POST | `/api/leads/{id}/notes` | `{text}` (1–5000 caracteres) |
| DELETE | `/api/notes/{id}` | |
| GET/POST | `/api/lead-statuses` | listar / criar status |
| PATCH | `/api/lead-statuses/{id}` | renomear, reordenar, marcar final |

## Clientes e perfil

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/customers/import` | `multipart/form-data` campo `file` (.csv/.xlsx, ≤ 20 MB) → job com relatório |
| GET | `/api/customers` | lista paginada (`status` = ok, sem_cnpj, nao_encontrado) |
| GET | `/api/profile` | perfil de cliente ideal |

## Configuração, monitoramento e processos

| Método | Rota | Descrição |
|---|---|---|
| GET/PUT | `/api/settings/weights` | pesos da compatibilidade/potencial e afinidade por segmento (PUT dispara recálculo) |
| GET/POST | `/api/segments`, PATCH `/api/segments/{id}` | segmentos (prefixos CNAE e palavras-chave) |
| GET | `/api/dashboard` | indicadores do painel |
| GET | `/api/sources` | estado das fontes (último sucesso/erro, falhas consecutivas) |
| GET | `/api/jobs`, `/api/jobs/{id}` | processos em background (status, total, processados, erros, log) |
| POST | `/api/admin/receita-import` | `{download, month}` importa dados abertos |
| POST | `/api/admin/rescore` | recalcula segmentos e notas |
| POST | `/api/admin/lookup-customers` | consulta clientes não encontrados na API pública |
| POST | `/api/admin/enrich` | `{limit}` enriquece os leads de maior potencial |

Rotas públicas (sem login): `GET /login`, `POST /login`, `GET /health`, `/static/*`.
Um teste automatizado percorre **todas** as rotas `/api` e verifica que retornam 401 sem sessão.
