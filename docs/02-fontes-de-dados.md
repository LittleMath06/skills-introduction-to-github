# 02 — Fontes de dados (Fase 2: Pesquisa técnica)

## Como esta pesquisa foi feita (transparência)

A pesquisa foi feita em 30/09/2026 via mecanismo de busca. O ambiente de desenvolvimento **não tinha
acesso de rede** aos domínios `gov.br`, `receitafederal.gov.br`, `brasilapi.com.br` e `ibge.gov.br`
(bloqueio do proxy do ambiente), portanto:

* a **existência** de cada fonte foi confirmada por resultados de busca que apontam para as páginas oficiais;
* o **layout** dos arquivos do CNPJ foi implementado conforme o documento oficial de metadados
  (`cnpj-metadados.pdf`, "Novo Layout para os Dados Abertos do CNPJ"), que é estável desde 2021, e
  o parser é tolerante (colunas extras são ignoradas, linhas inválidas são registradas como erro);
* **nenhuma chamada real** às fontes foi executada durante o desenvolvimento. Os testes usam arquivos
  de exemplo com o mesmo layout e transportes HTTP simulados, identificados como tal.

**Ação obrigatória na implantação:** executar `python -m prospeccao.cli check-sources` e a primeira
importação com um arquivo pequeno (ex.: `Simples.zip` ou uma parte de `Estabelecimentos`) para validar
o layout contra o arquivo do mês. Registrar o resultado em `docs/10-documentacao-final.md` §18.

## Critérios de avaliação

API/arquivo oficial · licença · termos de uso · robots.txt · limites · estabilidade · legalidade ·
confiabilidade · custo · alternativa em caso de indisponibilidade.

## 1. Dados cadastrais (CNPJ)

### 1.1 Dados Abertos do CNPJ — Receita Federal ✅ **fonte principal**

| Item | Avaliação |
|---|---|
| Onde | <https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/> (pastas `AAAA-MM`); catálogo em <https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj> |
| Layout | <https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf> |
| Formato | ZIP com CSV sem cabeçalho, separador `;`, aspas `"`, codificação ISO-8859-1 (latin-1), datas `AAAAMMDD`, capital com vírgula decimal |
| Arquivos usados | `Estabelecimentos0..9`, `Empresas0..9`, `Simples`, `Cnaes`, `Municipios`, `Naturezas`, `Motivos` |
| Arquivos **não** usados | `Socios` (dados de pessoas físicas — minimização LGPD), `Paises`, `Qualificacoes` |
| Licença / legalidade | Dados abertos publicados pelo governo federal (Lei de Acesso à Informação, Decreto 8.777/2016). Uso permitido. |
| Atualização | Mensal |
| Volume | ~60 milhões de estabelecimentos; ~25 GB compactado (fonte: projeto `rictom/cnpj-sqlite`). **Por isso a importação é filtrada** |
| Limites | Download de arquivos estáticos; baixar uma vez por mês, sequencialmente |
| Riscos | URL/estrutura do servidor já mudou várias vezes → URL base configurável (`RF_BASE_URL`) e importação a partir de pasta local |
| Conteúdo útil | CNPJ, matriz/filial, razão social, fantasia, situação, datas, natureza jurídica, porte, capital, CNAE principal/secundários, endereço, telefones, e-mail, **opção pelo Simples/MEI** |

Colunas utilizadas (ordem oficial):

* **Estabelecimentos:** CNPJ_BASICO, CNPJ_ORDEM, CNPJ_DV, IDENTIFICADOR_MATRIZ_FILIAL (1 matriz, 2 filial),
  NOME_FANTASIA, SITUACAO_CADASTRAL (01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada),
  DATA_SITUACAO_CADASTRAL, MOTIVO_SITUACAO_CADASTRAL, NOME_CIDADE_EXTERIOR, PAIS, DATA_INICIO_ATIVIDADE,
  CNAE_FISCAL_PRINCIPAL, CNAE_FISCAL_SECUNDARIA (lista separada por vírgula), TIPO_LOGRADOURO,
  LOGRADOURO, NUMERO, COMPLEMENTO, BAIRRO, CEP, UF, MUNICIPIO (código RF), DDD_1, TELEFONE_1, DDD_2,
  TELEFONE_2, DDD_FAX, FAX, CORREIO_ELETRONICO, SITUACAO_ESPECIAL, DATA_SITUACAO_ESPECIAL.
* **Empresas:** CNPJ_BASICO, RAZAO_SOCIAL, NATUREZA_JURIDICA, QUALIFICACAO_RESPONSAVEL, CAPITAL_SOCIAL,
  PORTE_EMPRESA (00 não informado, 01 micro empresa, 03 empresa de pequeno porte, 05 demais),
  ENTE_FEDERATIVO_RESPONSAVEL.
* **Simples:** CNPJ_BASICO, OPCAO_PELO_SIMPLES (S/N), DATA_OPCAO_SIMPLES, DATA_EXCLUSAO_SIMPLES,
  OPCAO_MEI (S/N), DATA_OPCAO_MEI, DATA_EXCLUSAO_MEI.
* **Cnaes / Municipios / Naturezas:** CODIGO, DESCRICAO.

### 1.2 APIs públicas de consulta por CNPJ (uso pontual) ⚠️ **fonte secundária**

| Fonte | Avaliação | Uso no sistema |
|---|---|---|
| BrasilAPI `GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}` | Gratuita, open source, sem chave. Termos em elaboração; pede para **não** fazer varredura em loop — volume "de pessoa real". Sem SLA. | Consulta sob demanda de **um** CNPJ (botão "Consultar CNPJ" e checagem de clientes da base sem correspondência local). Limite interno: 1 requisição/3 s, cache 30 dias |
| OpenCNPJ (`opencnpj.org`) | Gratuita, open source, limite publicado ~50 req/s por IP; também oferece dataset | Alternativa configurável (`CNPJ_API_PROVIDER=opencnpj`) — mesmo contrato interno |
| Minha Receita (`minhareceita.org`) | Open source (base do BrasilAPI), pode ser auto-hospedada | Alternativa futura / auto-hospedagem |
| ReceitaWS | Plano gratuito muito limitado (poucas req/min) | Não utilizada |
| Conecta gov.br "Consulta CNPJ" | API oficial, porém restrita a órgãos públicos | Não aplicável |

Todas são **derivadas** dos mesmos dados abertos da Receita; por isso a fonte principal é o arquivo
oficial e as APIs são apenas conveniência — nenhuma dependência crítica de terceiros.

## 2. Classificações (CNAE, municípios)

| Fonte | Avaliação | Uso |
|---|---|---|
| Arquivos `Cnaes`/`Municipios` da própria Receita | oficiais, vêm junto com a base | tabelas de descrição (padrão) |
| IBGE CONCLA API `https://servicodados.ibge.gov.br/api/v2/cnae/subclasses` (doc: `/api/docs/CNAE?versao=2`) | oficial, sem autenticação, JSON | alternativa documentada; não necessária na v1 |

## 3. ICMS / Inscrição Estadual

| Fonte | Avaliação | Uso |
|---|---|---|
| **Web service `NfeConsultaCadastro` / `CadConsultaCadastro4` das SEFAZ** | Oficial. Retorna IE, situação (`cSit` 0 não habilitado / 1 habilitado), indicadores de credenciamento NF-e/CT-e, regime de apuração (`xRegApur`), CNAE, datas. **Exige conexão TLS com certificado digital ICP-Brasil (e-CNPJ A1) de empresa credenciada a emitir DF-e.** Cada UF tem seu endpoint; várias usam o SVRS. Exemplos confirmados: MS `https://nfe.sefaz.ms.gov.br/ws/CadConsultaCadastro4`, SVRS `https://cad.svrs.rs.gov.br/ws/cadconsultacadastro/cadconsultacadastro4.asmx` | Implementado como `SefazIcmsSource`, **desativado por padrão**. Ativa-se com `ICMS_CERT_FILE`/`ICMS_KEY_FILE` e o mapa de endpoints por UF em `ICMS_ENDPOINTS` (JSON). Resultado = **confirmado** |
| Sintegra (portais estaduais) | Consulta pública, porém com CAPTCHA na maioria das UFs e sem API | **Não automatizado** (contornar CAPTCHA violaria os termos). Link de consulta manual exibido na página da empresa |
| CCC — Cadastro Centralizado de Contribuintes | consulta web com CAPTCHA | Link manual |
| Inferência pelo CNAE | não oficial | Exibida apenas como **"provável contribuinte (inferido pelo CNAE — requer confirmação)"** para atividades de indústria/comércio |

## 4. Regime tributário e benefícios

* **Simples Nacional / MEI:** arquivo `Simples` da Receita → **confirmado** (fonte + mês de referência).
* **Lucro Presumido / Real:** não há fonte aberta; exibido como "não disponível". O `xRegApur` da SEFAZ,
  quando consultado, é registrado com a fonte.
* **Benefícios fiscais / regimes especiais:** não existe fonte pública estruturada nacional. Na v1 o
  sistema **não infere benefícios**. Paulo pode registrá-los manualmente com: tipo, descrição, nível
  (confirmado/provável/possível), fonte, URL, data da consulta, data do dado, confiança e observações.

## 5. Informações comerciais / contato / imagem

| Fonte | Avaliação | Uso |
|---|---|---|
| Telefones e e-mail do cadastro CNPJ | oficiais, declarados pela empresa, podem estar desatualizados | Contatos com fonte "Receita Federal" |
| Site oficial da empresa | descoberto pelo domínio do e-mail cadastral (se não for provedor gratuito) ou informado manualmente | `WebsiteSource`: `robots.txt` respeitado, User-Agent identificado, 1 requisição por domínio a cada 5 s, timeout 10 s, somente página inicial + página "contato" |
| Do site extraímos | título, meta description, `og:image`/favicon (logo), links `tel:`/`mailto:`, `wa.me`/`api.whatsapp.com`, LinkedIn, Instagram, Facebook | cada item com URL de origem e data |
| Google Maps / OpenStreetMap | apenas **link** de busca pelo endereço (sem API, sem custo, sem coleta) | botão "Abrir mapa" |
| LinkedIn/Instagram direto, buscadores | termos proíbem coleta automatizada | **não** utilizados; só links que o próprio site da empresa publica |
| Bases comerciais (Apollo, Econodata, Speedio…) | pagas, termos próprios | não utilizadas; a camada `DataSource` permite adicionar no futuro |

## 6. Resumo da decisão

```
CNPJSource        → ReceitaOpenDataSource (principal, arquivos oficiais)
                  → CnpjApiSource (BrasilAPI | OpenCNPJ, pontual, cache)
ICMSSource        → SefazIcmsSource (oficial, requer certificado; desativado por padrão)
                  → inferência por CNAE (rotulada "provável")
WebsiteSource     → site da própria empresa (robots.txt, rate limit)
Manual            → benefícios fiscais e correções do usuário (com fonte)
```

Referências consultadas:
[Dados abertos CNPJ — Receita](https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/) ·
[Metadados CNPJ](https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf) ·
[Portal Dados Abertos](https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj) ·
[BrasilAPI docs](https://brasilapi.com.br/docs) ·
[OpenCNPJ](https://opencnpj.org/) ·
[Comparativo APIs CNPJ](https://blog.hubdodesenvolvedor.com.br/api-de-consulta-de-cnpj/) ·
[IBGE CNAE API](https://servicodados.ibge.gov.br/api/docs/CNAE?versao=2) ·
[NFeConsultaCadastro (SEFAZ-PR)](http://moc.sped.fazenda.pr.gov.br/NFeConsultaCadastro.html) ·
[Consulta Cadastro SEFAZ-RS](https://atendimento.receita.rs.gov.br/qual-web-service-e-utilizado-na-verificacao-da-habilitacao-de-um-contribuinte-para-emitente-ou-destinatario-de-df-e) ·
[SEFAZ-MS NF-e](https://www.sefaz.ms.gov.br/documentos-fiscais-eletronicos/nf-e/) ·
[cnpj-sqlite (volume)](https://github.com/rictom/cnpj-sqlite)
