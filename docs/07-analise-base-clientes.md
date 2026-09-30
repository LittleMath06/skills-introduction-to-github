# 07 — Análise da base de clientes recebida

> Este documento contém **apenas dados agregados**. A planilha original e a lista de nomes são
> dados privados de Paulo e **não são versionadas** no repositório (prompt §4).

Arquivo recebido em 30/09/2026: `clientes_do_paulo.xlsx`.

## 1. Estrutura encontrada

| Item | Resultado |
|---|---|
| Abas | 1 (`Planilha1`) |
| Colunas | **1** — título: *"Cliente que já tiveram cotação"* |
| Conteúdo | razão social (texto livre, maiúsculas, como no ERP) |
| Linhas de dados | 207 (nenhuma vazia) |
| CNPJ, cidade, UF, CNAE, segmento, porte | **ausentes** |

**Observação de negócio:** o título indica empresas que **receberam cotação**, não necessariamente
que compraram. O perfil de cliente ideal passa a representar "empresas que demandaram cotação".
Se houver distinção entre cotados e compradores, vale separar as listas (ou incluir uma coluna
"comprou: sim/não") para, no futuro, dar mais peso a quem efetivamente comprou.

## 2. Validação e normalização

| Verificação | Resultado |
|---|---|
| Nomes distintos após normalização (sem acento/pontuação/natureza societária, abreviações de ERP expandidas) | **205** |
| Duplicados unificados | 2 |
| CNPJ válidos / inválidos | não se aplica (sem coluna CNPJ) |
| Nomes aparentemente cortados pelo sistema de origem (≥ 35 caracteres e sem LTDA/S.A./EIRELI…) | 7 |
| Nomes com abreviações de ERP (IND, COM, MAT, ELET, REFR…) | presentes; tratadas na comparação e na classificação |

## 3. Características comuns (estimadas pelo nome)

Segmento estimado por palavras-chave do nome (sem CNAE, a estimativa é mais fraca que a por CNAE):

| Segmento | Clientes |
|---|---|
| Indústria | 36 |
| Instaladores | 27 |
| Construção Civil | 17 |
| Engenharia | 16 |
| Fabricantes | 16 |
| Varejo | 10 |
| Energia | 7 |
| Agrobusiness | 5 |
| Automação | 5 |
| Distribuidores | 5 |
| Infraestrutura | 2 |
| Telecomunicações | 1 |
| **Sem palavra de atividade no nome** | **58** (classificados só após identificar o CNPJ) |

Palavras mais frequentes nos nomes: engenharia (19), elétricos (18), elétrica (14), materiais (12),
energia (6), soluções (6), iluminação (5), eletrônicos (5), componentes (5), automação (5),
peças (5), imobiliário (5), refrigeração (4), máquinas (4), projetos (4), painéis (4),
equipamentos (4), solar (3).

Leitura: a base concentra **engenharia/instalações elétricas, indústria e fabricantes de
componentes elétricos/eletrônicos, construção/incorporação e materiais elétricos** — coerente com
o mercado de fios e cabos.

## 4. Consequências e o que o sistema passou a fazer

| Situação | Tratamento implementado |
|---|---|
| Planilha de 1 coluna só com nomes | reconhecida automaticamente como lista de razões sociais |
| Sem CNPJ | clientes ficam com status **"só nome"**; deduplicação pelo nome normalizado |
| Perfil sem CNAE/UF/porte | compatibilidade usa **segmento + palavras**; critérios sem dados aparecem como "não avaliado" e seus pesos são redistribuídos (explicado na tela) |
| Identificar o CNPJ | (1) pela razão social na base local; (2) **na importação dos dados da Receita**, a razão social é procurada no arquivo Empresas — correspondência exata ou, para nomes cortados, pelo início do nome; vincula à **matriz**; nome com mais de um CNPJ possível fica **"ambíguo"** (não vincula); (3) CNPJ informado manualmente na tela Clientes |
| Reenvio da planilha com CNPJ/UF preenchidos | atualiza o mesmo cliente (não duplica) |
| Filtro da importação da Receita | empresas identificadas como clientes entram mesmo fora do filtro de CNAE |

Todos os vínculos por nome ficam marcados ("vinculado pelo nome — confira") para revisão.

## 5. Próximos passos recomendados

1. Paulo completar o **CNPJ** (e, se possível, cidade/UF) na planilha de apoio gerada pelo sistema
   (`clientes_do_paulo_para_completar.xlsx`, entregue fora do repositório) e reimportar.
   Cada CNPJ informado permite usar CNAE, localização e porte no perfil.
2. Rodar a primeira importação dos dados abertos da Receita: além de trazer os prospects, ela tenta
   identificar automaticamente os CNPJs dos clientes pelo nome.
3. Revisar na tela Clientes os vínculos por nome e os "ambíguos".
