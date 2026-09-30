# 05 — UX/UI: fluxos e wireframes (Fase 5)

Identidade própria (não copia o Apollo.io): tons de azul-marinho com acento **cobre** (referência ao
condutor dos cabos), tipografia do sistema, cartões simples, sem excesso de gráficos.

## Fluxo principal

```
Login → Dashboard → Buscar (pesquisa livre + filtros) → Resultados (lista ordenável)
      → Detalhes da empresa → Salvar lead / status / observação → Leads salvos
```

Navegação fixa: **Início · Buscar · Leads · Clientes · Configurações · Administração · Metodologia**.
No celular a navegação vira uma barra rolável horizontal e as tabelas viram cartões.

## Dashboard

```
┌───────────────────────────────────────────────────────────────────────────┐
│ [MOCK — dados fictícios de desenvolvimento]   (só aparece se houver mock) │
├──────────────┬──────────────┬──────────────┬──────────────┬───────────────┤
│ Empresas     │ Prospects    │ Novos (30d)  │ Leads salvos │ Clientes base │
├──────────────┴──────────────┴──────────────┴──────────────┴───────────────┤
│ [ Pesquisa livre: "instaladores em MG"                     ] [Buscar]     │
├─────────────────────────────────────┬─────────────────────────────────────┤
│ Maior compatibilidade (top 8)       │ Por região  ███ Sudeste 120         │
│  Empresa · Cidade/UF · 87% · Salvar │ Por segmento ██ Instaladores 80     │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ Atualizadas recentemente            │ Status das fontes ● ok ● alerta     │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

## Buscar / resultados

```
┌ Pesquisa livre ──────────────────────────────────────────────────────────┐
│ "empresas de engenharia elétrica em São Paulo"            [Pesquisar]    │
│ Interpretado como: [Segmento: Engenharia ×] [UF: SP ×] [Termo: eletrica ×]│
├ Filtros (recolhível no celular) ─────────────────────────────────────────┤
│ Região ▾ UF ▾ Cidade __ Segmento ▾ CNAE __ Porte ▾ Situação ▾ ICMS ▾     │
│ Site ▾ Telefone ▾ E-mail ▾ Compat. ≥ __ Potencial ≥ __ Atualizado desde __│
│ Leads ▾ [ ] incluir clientes atuais   Ordenar por ▾         [Aplicar]    │
├──────────────────────────────────────────────────────────────────────────┤
│ 1.234 empresas encontradas · filtros ativos: [UF: SP ×] [Compat ≥ 70 ×]   │
├──────────────────────────────────────────────────────────────────────────┤
│ ◼ NOME FANTASIA               87% compat. │ 72 potencial │ Instaladores*  │
│   Razão social · CNPJ · Cidade/UF · CNAE 4321-5/00 · Ativa · ICMS provável│
│   ☎ ✉ 🌐 · atualizado 12/09/2026                                          │
│   [Detalhes] [Salvar] [★] [Analisado] [Descartar] [Site] [Mapa]           │
└──────────────────────────────────────────────────────────────────────────┘
  * = classificação estimada               « 1 2 3 … »
```

## Detalhes da empresa

```
┌ [logo/iniciais] NOME FANTASIA  (Matriz)       [Salvar lead] [★] [Status ▾]┐
│ Razão social · CNPJ · Situação · Segmento (estimado 82%)                  │
├ Compatibilidade 87% ─────────────────────┬ Potencial 72 ──────────────────┤
│ CNAE semelhante ……… 40 pts  "mesma classe│ critérios e pesos explicados   │
│ de 12 clientes"                          │                                │
├ Dados cadastrais ────────────────────────┼ Atividade ─────────────────────┤
├ Contatos (empresa × possível pessoal) ───┼ Fiscal (Confirmado/Provável/   │
│ fonte + data de cada contato  [Copiar]   │ Possível, fonte, URL, data)    │
├ Observações / histórico do lead ─────────┼ Histórico de alterações        │
└──────────────────────────────────────────┴────────────────────────────────┘
```

## Leads salvos

Abas: Ativos · Favoritos · Analisados · Descartados; filtro por status; cada linha com status
editável, favorito, última observação.

## Clientes (base atual)

Upload CSV/XLSX → barra de progresso ("250 / 1.000") → relatório (importados, duplicados, CNPJ
inválidos com número da linha, vinculados, não encontrados) → perfil de cliente ideal (top CNAEs,
segmentos, UFs, portes, palavras-chave).

## Configurações

Pesos da compatibilidade e do potencial (sliders numéricos), afinidade por segmento, segmentos
(prefixos CNAE e palavras-chave), status comerciais.

## Administração

Status das fontes (último sucesso/erro, desatualização), ações (importar Receita, recalcular,
consultar clientes não encontrados, enriquecer sites), processos em background com log e erros,
alertas de possíveis duplicidades e dados desatualizados.

## Mensagens e feedback

* Toda ação mostra um aviso (toast) de sucesso ou erro em linguagem simples.
* Erros técnicos nunca aparecem para o usuário; o log guarda o detalhe com um código de referência.
* Campos inferidos sempre com selo **estimado**/**provável**/**possível**.
