# 01 — Requisitos (Fase 1: Descoberta)

> Documento produzido a partir do "Prompt Mestre" e do roteiro "Roteiro de Perguntas para Criação de um
> Sistema do Zero" respondido parcialmente pelo solicitante. Onde o roteiro ficou sem resposta, as
> decisões tomadas estão marcadas como **[Premissa]** e podem ser revistas com o usuário.

## 1. Problema

Paulo Alarcon (compra e venda de fios, cabos elétricos e cabos especiais) procura novos clientes
**manualmente**, em vários sites e buscadores. O processo é manual, demorado, repetitivo, sujeito a
erros e pouco escalável (respostas do roteiro, Etapa 1.2).

## 2. Objetivo

Reduzir o esforço de prospecção entregando, em um só lugar, empresas brasileiras **ainda não atendidas**
que tenham **perfil semelhante** aos clientes atuais, com dados cadastrais, fiscais e de contato
rastreáveis até a fonte. Critério de sucesso declarado no roteiro: **validação pelo próprio Paulo
após uso** (Etapa 1.3) — por isso nenhuma métrica de resultado é afirmada antes desse teste.

## 3. Usuário e perfis

| Perfil | Quem | Pode |
|---|---|---|
| Único (administrador) | Paulo Alarcon | tudo: pesquisar, importar base, gerir leads, configurar pesos/segmentos/status, disparar atualizações |

* Não haverá equipes, organizações ou hierarquia (Prompt §3).
* **[Premissa]** Uso via navegador em computador e celular, pela internet (roteiro 2.3 sem resposta).
* **[Premissa]** Sem recuperação de senha por e-mail na v1: a senha é redefinida pelo comando
  `python -m prospeccao.cli set-password` no servidor (evita depender de SMTP e reduz superfície de
  ataque para um único usuário).

## 4. Processo atual × proposto

| Etapa | Hoje (manual) | Com o sistema |
|---|---|---|
| Definir quem procurar | intuição / memória | perfil de cliente ideal calculado da base atual |
| Encontrar empresas | buscas em vários sites | base local alimentada pelos dados abertos do CNPJ (todo o Brasil) |
| Verificar cadastro | consultar CNPJ um a um | dados cadastrais já importados, com data e fonte |
| Priorizar | lista solta | ranking por compatibilidade e potencial, com explicação |
| Contato | procurar site/telefone | telefone/e-mail do CNPJ + enriquecimento do site oficial |
| Acompanhar | planilha/anotações | leads com status, observações, favoritos, descartados |
| Manter atualizado | refazer tudo | atualização periódica com detecção de mudanças |

Continua manual: o contato comercial em si e a confirmação de informações fiscais/benefícios.

## 5. Requisitos funcionais

| ID | O sistema deve… |
|---|---|
| RF01 | exigir login (usuário único) para qualquer tela ou endpoint, exceto `/login` e `/health` |
| RF02 | importar a base de clientes atuais (CSV/XLSX), detectando colunas, normalizando, validando CNPJ e eliminando duplicidades, com relatório da importação |
| RF03 | construir um perfil de cliente ideal (CNAEs, segmentos, UFs/regiões, portes, palavras-chave) a partir dos clientes importados |
| RF04 | importar empresas de todo o Brasil a partir dos Dados Abertos do CNPJ (Receita Federal), com filtros de UF, CNAE e situação para controlar volume |
| RF05 | consultar um CNPJ individual sob demanda em fonte externa (API pública), com cache |
| RF06 | classificar cada empresa em um segmento configurável, indicando método, confiança e que é **estimativa** |
| RF07 | calcular compatibilidade (0–100 %) com o perfil, explicando cada critério e quantos clientes compartilham a característica |
| RF08 | calcular potencial com metodologia publicada na própria interface |
| RF09 | pesquisar com filtros combináveis (região, UF, cidade, segmento, CNAE, porte, situação, ICMS, site, telefone, e-mail, compatibilidade, potencial, data de atualização) e pesquisa livre em linguagem natural simples |
| RF10 | ordenar por compatibilidade, potencial, localização, segmento, atualização e completude, com paginação |
| RF11 | exibir página da empresa com dados cadastrais, atividade, comerciais, fiscais (com fonte/confiança), contatos e histórico de alterações |
| RF12 | permitir salvar lead, favoritar, marcar analisado, descartar, alterar status comercial, adicionar observações |
| RF13 | permitir configurar status comerciais, segmentos (CNAEs/palavras-chave) e pesos de similaridade |
| RF14 | enriquecer contatos a partir do site oficial respeitando robots.txt e limites, distinguindo contato da empresa de contato pessoal |
| RF15 | consultar situação de ICMS em fonte oficial (SEFAZ) quando configurada; caso contrário exibir "não verificado" ou "provável (inferido)" |
| RF16 | registrar informações/benefícios fiscais manualmente com fonte, URL, datas, nível (confirmado/provável/possível) e confiança |
| RF17 | executar importações, atualizações e enriquecimentos em background com progresso e log de erros |
| RF18 | detectar mudanças cadastrais, empresas inativas/baixadas e duplicidades; registrar histórico |
| RF19 | exibir dashboard com totais, novos leads, distribuição por região/UF/segmento, top compatibilidade, atualizações recentes e status das fontes |
| RF20 | exibir painel de status das fontes (último sucesso, último erro, desatualização) |
| RF21 | disponibilizar API REST documentada (OpenAPI) |

## 6. Requisitos não funcionais

| ID | Requisito |
|---|---|
| RNF01 | Senha com hash forte (scrypt), sessão em cookie assinado `HttpOnly`/`SameSite`, `Secure` em produção |
| RNF02 | Segredos apenas em variáveis de ambiente; `.env` fora do Git |
| RNF03 | Consultas parametrizadas (ORM), validação de entrada em todos os endpoints |
| RNF04 | Rate limiting no login e nas fontes externas |
| RNF05 | Paginação obrigatória; índices em CNPJ, UF, município, CNAE, segmento, scores |
| RNF06 | Busca paginada < 1 s para centenas de milhares de empresas em PostgreSQL (meta, a validar com dados reais) |
| RNF07 | Responsivo (desktop e celular), navegadores modernos |
| RNF08 | Rastreabilidade: toda informação externa guarda fonte e data |
| RNF09 | Nenhum dado inventado; dados de desenvolvimento marcados `MOCK` e bloqueados em produção |
| RNF10 | Logs sem segredos; erros tratados sem expor detalhes técnicos ao usuário |
| RNF11 | Troca de fonte sem reescrever o sistema (camada `DataSource`) |

## 7. Regras de negócio

| ID | Regra |
|---|---|
| RN01 | O CNPJ (14 dígitos, DV válido) é o identificador principal de estabelecimento; `cnpj_basico` (8) agrupa matriz e filiais |
| RN02 | Uma empresa encontrada em várias fontes é **um** registro (upsert por CNPJ); fontes ficam registradas |
| RN03 | Empresas que já são clientes não aparecem como "novo lead" (filtro padrão), nem as filiais/matriz de um cliente (mesmo `cnpj_basico`) — sinalizadas como "grupo já atendido" |
| RN04 | CNPJ inválido na importação é rejeitado e reportado; linhas sem CNPJ são aceitas somente para o perfil se tiverem CNAE/UF |
| RN05 | Classificação de segmento e compatibilidade são **estimativas**; a interface usa "perfil compatível", "potencial cliente", nunca "compra" |
| RN06 | Informação fiscal só é "confirmada" se vier de fonte oficial com data; inferências são "provável"; hipóteses são "possível" |
| RN07 | Benefício fiscal nunca é gerado automaticamente; só entra com fonte informada |
| RN08 | Contato pessoal (ex.: e-mail com nome de pessoa em provedor gratuito) é marcado como tal; nenhum contato é criado sem fonte |
| RN09 | Scraping apenas do site da própria empresa, uma página inicial (+ página de contato), respeitando robots.txt e intervalo mínimo |
| RN10 | Status comerciais são configuráveis; padrão: Novo → Analisar → Contato realizado → Em negociação → Cliente (+ Descartado) |
| RN11 | Mudanças cadastrais (situação, endereço, CNAE, contato) geram registro de histórico |
| RN12 | Pesos da similaridade são configuráveis e normalizados para somar 1 |

## 8. Entidades identificadas

User, Company (estabelecimento), CompanyContact, FiscalInfo (inclui benefícios), CompanyChange,
Segment, Customer (linha da base do Paulo), Lead, LeadStatus, LeadNote, DataSource, Job, Setting,
Cnae, Municipio. Descartadas por não agregarem na v1: `Search`/`SearchFilter` (a busca é
representada pela URL, que pode ser salva como favorito do navegador), `CompanyAddress` separado
(endereço é 1:1 com estabelecimento), `CompanyActivity` separado (CNAEs secundários em campo
indexável). Detalhes em `04-database.md`.

## 9. Dependências e riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Base do CNPJ completa tem ~60 milhões de estabelecimentos (~30 GB) | disco/tempo | importação filtrada por CNAE/UF/situação; PostgreSQL em produção |
| Servidor de arquivos da Receita muda de URL/estrutura com frequência | atualização quebra | URL configurável; importação aceita arquivos baixados manualmente; painel de status |
| APIs públicas de CNPJ sem SLA / termos em beta | indisponibilidade | uso apenas pontual, cache, fonte alternativa configurável |
| ICMS por UF exige certificado digital (SEFAZ) ou tem CAPTCHA (Sintegra) | sem confirmação de ICMS | integração SEFAZ opcional com certificado de Paulo; senão, "não verificado"/"provável" explícitos |
| Benefícios fiscais não têm fonte estruturada nacional | não automatizável | cadastro manual com fonte obrigatória |
| Sites de empresas: termos/robots, instabilidade | dados incompletos | robots.txt, limite, timeout, registro de erro, sem insistência |
| LGPD — telefone/e-mail do CNPJ podem ser de pessoa física (MEI, empresário) | privacidade | minimização, marcação "possível dado pessoal", finalidade comercial B2B documentada, exclusão sob demanda |

## 10. Informações faltantes (a confirmar com Paulo)

1. **Arquivo da base de clientes** — ainda não fornecido. O importador detecta colunas por sinônimos;
   quando o arquivo chegar, validar o relatório de importação (Fase 6.4).
2. Regiões/UFs prioritárias e CNAEs de interesse (para limitar a importação inicial).
3. Hospedagem desejada (VPS própria, nuvem) e domínio.
4. Se possui certificado digital A1 (necessário para a consulta oficial de cadastro ICMS na SEFAZ).
5. Status comerciais além dos padrão.

## 11. Escopo

* **v1 (este entregável):** RF01–RF21.
* **Fora do escopo:** envio de e-mails/campanhas, CRM completo, multiusuário, app nativo, compra de
  bases comerciais, dados de sócios (evitados por minimização LGPD).
* **Futuro:** ver `docs/10-documentacao-final.md` §21.
