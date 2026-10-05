# Tutorial — do zero até a produção

**Sistema de Prospecção de Clientes** · Python 3 + FastAPI + PostgreSQL

Este tutorial parte de um computador sem nada instalado. Ele leva você a rodar o sistema na sua
máquina, testá-lo e publicá-lo na internet com HTTPS. Siga as etapas **na ordem**. Cada comando
vem acompanhado de uma explicação do que ele faz.

> 🪟 **Usa Windows?** Comece pelo [Caminho rápido no Windows](#caminho-rápido-no-windows-scripts-automáticos):
> dois scripts fazem a instalação e a execução por você. As etapas 1 a 10 explicam cada passo em
> detalhe e servem de referência quando algo der errado.

> **Validação:** os comandos deste tutorial foram executados em 05/10/2026 num clone limpo do
> projeto, com Python 3.11, 3.12 e 3.13 (138 testes aprovados). Os scripts do Windows
> (`scripts/windows/*.ps1`) foram executados de ponta a ponta com o PowerShell 7.4 e verificados
> pelo analisador oficial da Microsoft (PSScriptAnalyzer) quanto à compatibilidade com o
> **Windows PowerShell 5.1**, que vem no Windows: 0 problemas. Não houve um teste num computador
> Windows físico. Se algo divergir, veja a [Etapa 9 — Troubleshooting](#9-troubleshooting),
> em especial a [9.6](#96-problemas-específicos-do-windows).

---

## Sumário

* 🪟 [Caminho rápido no Windows (scripts automáticos)](#caminho-rápido-no-windows-scripts-automáticos)
0. [Antes de começar: decisões e informações necessárias](#0-antes-de-começar-decisões-e-informações-necessárias)
1. [Pré-requisitos](#1-pré-requisitos)
2. [Configuração do ambiente](#2-configuração-do-ambiente)
3. [Instalação do projeto](#3-instalação-do-projeto)
4. [Execução local](#4-execução-local)
5. [Testes](#5-testes)
6. [Preparação para produção](#6-preparação-para-produção)
7. [Hospedagem](#7-hospedagem)
8. [Pós-deploy](#8-pós-deploy)
9. [Troubleshooting](#9-troubleshooting)
10. [Checklist final](#10-checklist-final)

### Como ler os blocos de comando

* Os blocos marcados **Linux/macOS** usam o terminal *bash/zsh*.
* Os blocos marcados **Windows** usam o **PowerShell**. Abra-o pelo menu Iniciar e digite
  "PowerShell". Não use o "Prompt de Comando" (cmd), a menos que o bloco indique.
* Quando não há marcação, o comando é igual em todos os sistemas.
* Linhas que começam com `#` são comentários: não precisam ser digitadas.

---

## Caminho rápido no Windows (scripts automáticos)

O projeto traz scripts que executam, sozinhos, as etapas 2 a 5 deste tutorial no Windows. Você
precisa apenas do **Python** e do **Git** instalados (etapa 1).

### Passo 1 — Instalar Python e Git (uma única vez)

Abra o **PowerShell** (menu Iniciar → digite "PowerShell" → Enter) e execute:

```powershell
# Instala o Python 3.12 e o Git pelo gerenciador oficial do Windows (winget)
winget install --id Python.Python.3.12 -e --source winget
winget install --id Git.Git -e --source winget
```

**Feche o PowerShell e abra de novo**, para que os comandos novos sejam reconhecidos. Depois
confira:

```powershell
py --list          # deve listar -V:3.12
git --version      # deve mostrar "git version 2.x"
```

### Passo 2 — Baixar o projeto

```powershell
# Cria a pasta de projetos e entra nela (fora do OneDrive, para evitar travamentos)
New-Item -ItemType Directory -Force -Path C:\projetos | Out-Null
Set-Location C:\projetos
# Baixa o código e entra na pasta
git clone https://github.com/LittleMath06/skills-introduction-to-github.git prospeccao
Set-Location C:\projetos\prospeccao
# Branch com o sistema (pule se o código já estiver no main)
git checkout claude/happy-hamilton-lnok0r
```

> Recebeu o **`prospeccao-sistema.zip`**? Clique com o botão direito → *Extrair tudo…* →
> `C:\projetos`. Depois, no PowerShell: `Set-Location C:\projetos\prospeccao` e libere os
> arquivos baixados da internet com `Get-ChildItem -Recurse | Unblock-File`.

### Passo 3 — Instalar (uma única vez)

Escolha uma das formas:

* **Duplo clique** em `instalar-windows.bat`, na pasta do projeto; **ou**
* no PowerShell, dentro da pasta do projeto:

```powershell
# -ComDadosFicticios: cria 400 empresas FICTÍCIAS (MOCK) para você conhecer as telas
powershell -ExecutionPolicy Bypass -File .\scripts\windows\instalar.ps1 -ComDadosFicticios
```

O que o script faz:

1. Encontra o Python 3.11–3.13 (usando o lançador `py`).
2. Cria o ambiente virtual `.venv`.
3. Instala todas as dependências e o projeto.
4. Cria o `.env` a partir do `.env.example` e **gera a `SECRET_KEY` sozinho**.
5. **Pede a senha** do usuário `paulo`. Ela não aparece enquanto você digita e precisa ter no
   mínimo 10 caracteres.
6. Cria o banco de dados local (`data\prospeccao.db`).

O script pode ser executado de novo com segurança: ele **não** apaga o `.env` nem o banco.

> `-ExecutionPolicy Bypass` libera a execução **apenas deste script, nesta vez**, sem alterar a
> configuração de segurança do Windows.

### Passo 4 — Usar o sistema

* **Duplo clique** em `iniciar-windows.bat`: o navegador abre sozinho em <http://localhost:8000>; **ou**
* no PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\iniciar.ps1 -AbrirNavegador
```

Entre com o usuário **`paulo`** e a senha definida no passo 3. **Para parar:** `Ctrl + C` na
janela do PowerShell (ou feche a janela). **Para reiniciar:** rode o comando, ou dê o duplo
clique, de novo.

Opções do `iniciar.ps1`:

| Opção | Efeito |
|---|---|
| `-Porta 8001` | usa outra porta (se a 8000 estiver ocupada) |
| `-RedeLocal` | permite abrir pelo celular na mesma rede Wi-Fi (o Windows pode pedir para liberar o Python no firewall: aceite apenas para **redes privadas**) |
| `-SemRecarregar` | não reinicia sozinho ao editar o código |

### Passo 5 — Testar

```powershell
# Todos os testes automatizados (resultado esperado: "Todos os testes passaram.")
powershell -ExecutionPolicy Bypass -File .\scripts\windows\testar.ps1
# Inclui os testes de interface (baixa o Chromium, ~150 MB, só na 1ª vez)
powershell -ExecutionPolicy Bypass -File .\scripts\windows\testar.ps1 -Interface
# Repete os testes num PostgreSQL 16 temporário (requer o Docker Desktop aberto)
powershell -ExecutionPolicy Bypass -File .\scripts\windows\testar.ps1 -PostgreSQL
```

### Comandos administrativos e atualização

```powershell
# Trocar a senha
powershell -ExecutionPolicy Bypass -File .\scripts\windows\cli.ps1 set-password paulo
# Importar a planilha de clientes pela linha de comando (também dá pela tela Clientes)
powershell -ExecutionPolicy Bypass -File .\scripts\windows\cli.ps1 import-customers "C:\Users\SEU-USUARIO\Downloads\clientes.xlsx"
# Remover os dados fictícios antes de usar dados reais
powershell -ExecutionPolicy Bypass -File .\scripts\windows\cli.ps1 clear-mock
# Listar todos os comandos
powershell -ExecutionPolicy Bypass -File .\scripts\windows\cli.ps1 --help
# Baixar a versão mais recente do código, reinstalar e testar (feche o sistema antes)
powershell -ExecutionPolicy Bypass -File .\scripts\windows\atualizar.ps1
```

Com isso, o sistema já roda localmente. Para **publicar na internet**, vá direto para a
[etapa 6](#6-preparação-para-produção) e a [etapa 7](#7-hospedagem). Os dois caminhos funcionam
a partir do Windows:

* o **Render** é configurado pelo navegador; o código é enviado com `git push`;
* para a **VPS**, o Windows já traz o cliente SSH: `ssh root@IP-DO-SERVIDOR`.

---

## 0. Antes de começar: decisões e informações necessárias

Algumas informações **não estão no projeto** e só você (ou o Paulo) pode fornecê-las. Elas não
são necessárias para rodar localmente, apenas para a produção:

| Informação | Para que serve | Onde será usada |
|---|---|---|
| **Senha do Paulo** (mínimo 10 caracteres) | login no sistema | `ADMIN_PASSWORD` (etapas 2 e 7) |
| **Conta na hospedagem** (Render, recomendado) e forma de pagamento | o plano gratuito não serve (ver etapa 7) | etapa 7 |
| **Domínio próprio** (ex.: `prospeccao.suaempresa.com.br`) | endereço amigável; **opcional** no Render | etapas 7.1.7 e 7.2 |
| **Acesso ao painel DNS do domínio** (Registro.br, GoDaddy, Cloudflare…) | apontar o domínio para a hospedagem | etapa 7 |
| **Conta no GitHub** com acesso ao repositório | o Render publica a partir do GitHub | etapas 1 e 7 |
| Certificado digital **e-CNPJ A1** (opcional) | consulta oficial de ICMS na SEFAZ | etapa 6.6 |
| UFs/CNAEs prioritários (opcional) | reduzir o volume da importação da Receita | etapa 6.5 |

> ⚠️ **O repositório atual é PÚBLICO** (`github.com/LittleMath06/skills-introduction-to-github`).
> O código não tem senhas nem dados de clientes, mas o sistema é privado. Antes da produção,
> deixe o repositório **privado**: no GitHub, abra *Settings → General → Danger Zone →
> Change visibility → Make private*. Outra opção é criar um repositório privado novo (etapa 7.1.1).

> ℹ️ **Onde está o código:** ele está no branch `claude/happy-hamilton-lnok0r`. Se esse branch já
> tiver sido mesclado (*merge*) no `main`, use `main` nos comandos. Se não tiver, use o nome do
> branch, como mostrado na etapa 3.1.

---

## 1. Pré-requisitos

### 1.1 O que é necessário

| Ferramenta | Versão | Obrigatória para | Para que serve |
|---|---|---|---|
| **Python** | **3.12** (recomendada); 3.11 e 3.13 também testadas | rodar localmente | linguagem do sistema |
| **pip** | o que acompanha o Python | rodar localmente | instala as bibliotecas |
| **Git** | 2.40+ | baixar e publicar o código | controle de versão |
| Editor de texto | qualquer um (recomendado: **VS Code**) | editar o `.env` | — |
| Navegador | Chrome, Edge, Firefox ou Safari atual | usar o sistema | — |
| **Docker Desktop / Docker Engine** | 24+ com Compose v2 | **opcional**: PostgreSQL local e hospedagem em servidor próprio (VPS) | contêineres |
| PostgreSQL | 16 | **não precisa instalar**: em produção vem da hospedagem; localmente o sistema usa SQLite | banco de dados |

As bibliotecas Python (FastAPI, SQLAlchemy etc.) **não** precisam ser instaladas à mão. A etapa 3
instala tudo de uma vez, com as versões definidas em `requirements.txt`.

### 1.2 Verificar e instalar o Git

**Verificar** (todos os sistemas):

```bash
git --version
```

Se aparecer algo como `git version 2.4x.x`, o Git está instalado. Se aparecer "comando não
encontrado" ou "não é reconhecido", instale conforme o seu sistema:

**Windows** (PowerShell):

```powershell
# winget já vem no Windows 10/11 atualizado. "-e" exige o nome exato do pacote.
winget install --id Git.Git -e --source winget
```

Feche e abra o PowerShell de novo para que o comando `git` passe a ser reconhecido.

**macOS:**

```bash
# Instala as ferramentas de linha de comando da Apple, que incluem o Git
xcode-select --install
```

**Linux (Ubuntu/Debian):**

```bash
# Atualiza a lista de pacotes e instala o Git
sudo apt update && sudo apt install -y git
```

Configure seu nome e e-mail uma única vez. Eles aparecem nos *commits*:

```bash
git config --global user.name "Seu Nome"
git config --global user.email "seu-email@exemplo.com"
```

### 1.3 Verificar e instalar o Python

**Verificar:**

**Windows:**

```powershell
# O "py" é o lançador oficial do Python no Windows. Mostra as versões instaladas.
py --list
python --version
```

**Linux/macOS:**

```bash
python3 --version
```

Você precisa de **3.11, 3.12 ou 3.13**. Se a versão for 3.10 ou menor, ou se o comando não
existir, instale:

**Windows:**

```powershell
winget install --id Python.Python.3.12 -e --source winget
```

Se preferir o instalador gráfico de <https://www.python.org/downloads/>, **marque a opção
"Add python.exe to PATH"** na primeira tela. Depois feche e reabra o PowerShell e confira com
`py -3.12 --version`.

**macOS** (usando o [Homebrew](https://brew.sh)):

```bash
# 1) Se ainda não tiver o Homebrew, instale-o (comando oficial do site brew.sh):
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# 2) Instale o Python 3.12:
brew install python@3.12
# 3) Confira:
python3.12 --version
```

Outra opção é usar o instalador `.pkg` de <https://www.python.org/downloads/macos/>.

**Linux:**

```bash
# Ubuntu 24.04 já traz o Python 3.12. Basta instalar o módulo de ambientes virtuais:
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
python3 --version
```

> No Ubuntu 22.04, o Python padrão é o 3.10, que é antigo demais para o projeto. Instale o 3.11:
> `sudo apt install -y python3.11 python3.11-venv` e use `python3.11` no lugar de `python3` nos
> comandos seguintes.

### 1.4 (Opcional) Instalar o VS Code

Baixe em <https://code.visualstudio.com/>. No Windows também funciona
`winget install --id Microsoft.VisualStudioCode -e`. Ele serve para editar o `.env` com
segurança: editores como o TextEdit do macOS podem salvar o arquivo em formato "rich text" e
corrompê-lo.

### 1.5 (Opcional) Verificar e instalar o Docker

Você só precisa do Docker se quiser **(a)** testar com PostgreSQL na sua máquina ou
**(b)** hospedar num servidor próprio (etapa 7.2). Para o Render (etapa 7.1), ele **não** é necessário.

```bash
docker --version
docker compose version
```

* **Windows/macOS:** instale o **Docker Desktop** em <https://www.docker.com/products/docker-desktop/>.
  No Windows ele usa o WSL 2, e o próprio instalador conduz essa configuração.
* **Linux:** veja a etapa 7.2.2, que traz o script oficial de instalação.

### 1.6 Contas online (para a hospedagem)

* **GitHub:** <https://github.com/signup> (gratuita).
* **Render:** <https://render.com>. Crie a conta entrando com o GitHub, o que facilita a conexão
  com o repositório.

---

## 2. Configuração do ambiente

### 2.1 Escolher uma pasta de trabalho

Crie uma pasta para seus projetos e entre nela:

**Linux/macOS:**

```bash
mkdir -p ~/projetos && cd ~/projetos
```

**Windows:**

```powershell
New-Item -ItemType Directory -Force -Path $HOME\projetos | Out-Null
Set-Location $HOME\projetos
```

> ⚠️ **Windows:** evite pastas sincronizadas pelo OneDrive (como "Documentos" ou "Área de
> Trabalho"). A sincronização pode travar o banco local (SQLite) e os arquivos temporários.

### 2.2 Baixar o código (clonar o repositório)

```bash
# Copia o repositório do GitHub para a pasta "prospeccao"
git clone https://github.com/LittleMath06/skills-introduction-to-github.git prospeccao

# Entra na pasta do projeto. TODOS os comandos a partir daqui são executados nela.
cd prospeccao

# Muda para o branch que contém o sistema (pule este comando se o código já estiver no main)
git checkout claude/happy-hamilton-lnok0r
```

> Se você recebeu o arquivo **`prospeccao-sistema.zip`**, pode extraí-lo e entrar na pasta
> `prospeccao` em vez de clonar. Para publicar no Render, porém, o código precisa estar num
> repositório do GitHub (etapa 7.1.1).

Confira se você está na pasta certa: a listagem deve mostrar `README.md`, `src`, `tests`,
`docs`, `.env.example` e outros arquivos.

**Linux/macOS:** `ls -a`  ·  **Windows:** `Get-ChildItem -Force`

### 2.3 Criar o ambiente virtual do Python

O *ambiente virtual* (`.venv`) é uma pasta isolada onde ficam as bibliotecas **deste** projeto,
sem interferir em outros projetos nem no Python do sistema.

**Linux/macOS:**

```bash
# Cria o ambiente virtual na pasta .venv (use python3.12 ou python3.11 se for o seu caso)
python3 -m venv .venv
# Ativa o ambiente: o prompt passa a mostrar "(.venv)"
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
# Cria o ambiente virtual com o Python 3.12
py -3.12 -m venv .venv
# Ativa o ambiente
.\.venv\Scripts\Activate.ps1
```

> **Windows — erro "a execução de scripts foi desabilitada neste sistema":** execute uma única
> vez `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, confirme com `S` e
> ative de novo.
> **Windows (cmd):** se estiver usando o Prompt de Comando, a ativação é `.venv\Scripts\activate.bat`.

> 🔁 **Sempre que abrir um terminal novo** para trabalhar no projeto, entre na pasta e **ative o
> ambiente de novo** (`source .venv/bin/activate` ou `.\.venv\Scripts\Activate.ps1`). Com ele
> ativo, use simplesmente `python` em qualquer sistema. Para sair do ambiente: `deactivate`.

### 2.4 Criar o arquivo `.env` (configurações e segredos)

O sistema lê as configurações de **variáveis de ambiente**. Em desenvolvimento, elas ficam no
arquivo `.env`, na raiz do projeto. O projeto traz um modelo chamado `.env.example`. Copie-o:

**Linux/macOS:** `cp .env.example .env`  ·  **Windows:** `Copy-Item .env.example .env`

> 🔒 O `.env` contém segredos e **nunca deve ir para o GitHub**. Ele já está listado no
> `.gitignore`, então o Git o ignora automaticamente.

#### 2.4.1 Gerar a chave secreta (`SECRET_KEY`)

A `SECRET_KEY` assina o cookie de login. Gere uma chave aleatória com este comando (funciona em
todos os sistemas com o ambiente ativo):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

O comando imprime algo como `q3J…xYz` (64 caracteres). Copie esse valor.

#### 2.4.2 Editar o `.env`

Abra o arquivo: **VS Code:** `code .env` · **Windows:** `notepad .env` · **Linux:** `nano .env`
(no nano, `Ctrl+O` salva e `Ctrl+X` sai).

Para **desenvolvimento local**, altere **somente** estas linhas e deixe o restante como está:

```dotenv
APP_ENV=development
SECRET_KEY=<cole aqui a chave gerada no passo anterior>
ADMIN_USERNAME=paulo
ADMIN_PASSWORD=<uma senha com no mínimo 10 caracteres>
ALLOW_MOCK_DATA=true
```

Regras do arquivo:

* Escreva `CHAVE=valor`, sem espaços em volta do `=` e sem aspas.
* Linhas com `#` são comentários.
* Valor vazio (`DATABASE_URL=`) significa "usar o padrão". Para `DATABASE_URL` vazio, o padrão é
  um banco SQLite em `data/prospeccao.db`, criado automaticamente.

#### 2.4.3 Referência de todas as variáveis

| Variável | Valor em desenvolvimento | Valor em produção | O que faz / onde obter |
|---|---|---|---|
| `APP_ENV` | `development` | `production` | Em produção, liga cookie seguro (só HTTPS), HSTS e travas de segurança |
| `SECRET_KEY` | gerada (2.4.1) | gerada, **diferente** da de desenvolvimento, ≥ 32 caracteres | assina a sessão. O Render gera sozinho |
| `DATABASE_URL` | vazio (SQLite) | URL do PostgreSQL | O Render e o docker-compose preenchem sozinhos. Formato: `postgresql+psycopg://usuario:senha@host:5432/banco` (`postgres://…` também é aceito) |
| `DATA_DIR` | `./data` | `/data` | pasta dos arquivos da Receita, uploads temporários e SQLite |
| `SESSION_MAX_AGE` | `28800` | `28800` | duração do login em segundos (8 h) |
| `ADMIN_USERNAME` | `paulo` | `paulo` | nome de usuário |
| `ADMIN_PASSWORD` | sua senha (≥ 10) | senha forte do Paulo | **só é usada para criar o usuário na primeira execução**. Depois, troque a senha com `set-password` (etapa 4.5) |
| `ALLOW_MOCK_DATA` | `true` | **`false`** (obrigatório) | permite gerar dados fictícios de teste |
| `RF_BASE_URL` | padrão | padrão | endereço dos dados abertos do CNPJ. Mude apenas se a Receita trocar o endereço |
| `RF_FILTER_UFS` | vazio | ex.: `SP,MG,PR` (opcional) | limita a importação a algumas UFs. Vazio = Brasil todo |
| `RF_FILTER_CNAE_PREFIXES` | vazio | opcional, ex.: `4321,4673,4742` | limita por CNAE. Vazio = automático (CNAEs dos clientes + segmentos) |
| `RF_ONLY_ACTIVE` | `true` | `true` | importa só empresas ativas (as que já estão na base são sempre atualizadas) |
| `CNPJ_API_PROVIDER` | `brasilapi` | `brasilapi` ou `opencnpj` | API pública para consultar um CNPJ por vez |
| `CNPJ_API_MIN_INTERVAL` | `3` | `3` | intervalo mínimo, em segundos, entre consultas à API |
| `WEBSITE_ENRICHMENT_ENABLED` | `true` | `true` | busca contatos no site oficial das empresas |
| `WEBSITE_MIN_INTERVAL` | `5` | `5` | segundos entre acessos ao mesmo site |
| `HTTP_USER_AGENT` | padrão | padrão (ou com um contato seu) | identificação do robô ao acessar sites |
| `ICMS_CERT_FILE`, `ICMS_KEY_FILE`, `ICMS_ENDPOINTS` | vazios | só se houver e-CNPJ (etapa 6.6) | consulta oficial de ICMS |
| `POSTGRES_PASSWORD`, `DOMAIN` | vazios | **só para o docker-compose** (etapa 7.2) | senha do banco e domínio do Caddy |

---

## 3. Instalação do projeto

Com o terminal **na pasta do projeto** e o **ambiente virtual ativo** (o prompt mostra `(.venv)`):

```bash
# 1) Atualiza o pip, o instalador de pacotes do Python
python -m pip install --upgrade pip

# 2) Instala as dependências do sistema e dos testes (FastAPI, SQLAlchemy, pytest, Playwright...)
python -m pip install -r requirements-dev.txt

# 3) Instala o próprio projeto em modo "editável" (-e). O comando "prospeccao" passa a ser
#    encontrado de qualquer lugar e mudanças no código valem na hora, sem reinstalar.
python -m pip install -e .
```

Confira se a instalação funcionou:

```bash
# Deve imprimir "ok" e o caminho da pasta src/prospeccao
python -c "import prospeccao; print('ok', prospeccao.__file__)"
```

### 3.1 Criar o banco de dados e o usuário

```bash
# Cria as tabelas, os dados iniciais (segmentos, status, fontes) e o usuário do .env
python -m prospeccao.cli init
```

A saída esperada é `Banco inicializado em sqlite:///…/data/prospeccao.db`.

* Se aparecer `Erro de configuração: ADMIN_PASSWORD inválida…`, a senha no `.env` tem menos de
  10 caracteres. Corrija e rode de novo.

### 3.2 (Opcional, recomendado na primeira vez) Gerar dados fictícios para explorar

```bash
# Gera 400 empresas e 30 clientes FICTÍCIOS, todos marcados "MOCK"
python -m prospeccao.cli seed-mock
```

Esses dados existem só para você conhecer as telas. Uma faixa amarela "MOCK" aparece no topo
enquanto eles existirem. Para removê-los:

```bash
python -m prospeccao.cli clear-mock
```

> ⚠️ **Remova os dados MOCK antes de importar dados reais.**

### 3.3 Outros comandos da linha de comando (CLI)

| Comando | O que faz |
|---|---|
| `python -m prospeccao.cli --help` | lista todos os comandos |
| `python -m prospeccao.cli check-sources` | testa as fontes externas (Receita, API de CNPJ, SEFAZ, sites) |
| `python -m prospeccao.cli set-password paulo` | cria ou troca a senha (pede a senha duas vezes, sem mostrá-la) |
| `python -m prospeccao.cli import-customers caminho/planilha.xlsx` | importa a base de clientes |
| `python -m prospeccao.cli import-receita --dir data/receita/2026-09` | importa os ZIPs da Receita de uma pasta |
| `python -m prospeccao.cli import-receita --download` | baixa o mês mais recente da Receita e importa |
| `python -m prospeccao.cli rescore` | recalcula segmentos, compatibilidade e potencial |
| `python -m prospeccao.cli enrich --limit 50` | busca contatos nos sites das 50 empresas de maior potencial |
| `python -m prospeccao.cli lookup-customers` | consulta na API pública os clientes com CNPJ que ainda não estão na base |
| `python -m prospeccao.cli forget <CNPJ>` | LGPD: apaga contatos, lead e histórico de um CNPJ |

---

## 4. Execução local

### 4.1 Iniciar

Na pasta do projeto, com o ambiente ativo:

```bash
uvicorn prospeccao.main:app_factory --factory --reload
```

* `uvicorn` é o servidor web.
* `prospeccao.main:app_factory --factory` diz a ele onde está a aplicação.
* `--reload` reinicia o servidor sozinho quando você altera o código. Use só em desenvolvimento.

O terminal mostra `Uvicorn running on http://127.0.0.1:8000`. **Deixe esse terminal aberto**:
fechá-lo desliga o sistema.

### 4.2 Acessar

Abra no navegador: **<http://localhost:8000>**

1. A página de login aparece.
2. Entre com o `ADMIN_USERNAME` (`paulo`) e o `ADMIN_PASSWORD` definidos no `.env`.
3. O painel inicial ("Olá, Paulo") é exibido.

| Endereço | O que é |
|---|---|
| <http://localhost:8000/> | painel inicial (exige login) |
| <http://localhost:8000/buscar> | busca de empresas |
| <http://localhost:8000/clientes> | importação da base de clientes e perfil |
| <http://localhost:8000/administracao> | fontes de dados, importações e processos |
| <http://localhost:8000/api/docs> | documentação interativa da API (exige login) |
| <http://localhost:8000/health> | verificação de saúde (não exige login) |

### 4.3 Verificar se está tudo funcionando

Abra **outro** terminal (o primeiro está ocupado com o servidor):

**Linux/macOS:**

```bash
curl http://localhost:8000/health
```

**Windows:**

```powershell
Invoke-RestMethod http://localhost:8000/health
```

A resposta esperada é `{"status":"ok","db":true,"version":"1.0.0"}`.

Depois, no navegador, confira:

1. **Login** funciona; uma senha errada mostra "Usuário ou senha inválidos".
2. **Buscar:** digite `instaladores em São Paulo` e clique em *Pesquisar*. Com os dados MOCK, a
   lista aparece com os filtros interpretados.
3. **Abrir uma empresa** → *Salvar como lead* → mudar o status → adicionar uma observação.
4. **Leads:** o lead aparece com o status e a observação.
5. **Administração:** as fontes aparecem com o estado de cada uma.

### 4.4 Parar e reiniciar

* **Parar:** no terminal do servidor, pressione **`Ctrl + C`** (em todos os sistemas).
* **Reiniciar:** pare com `Ctrl + C` e rode de novo o comando da etapa 4.1. Com `--reload`,
  alterações no código já reiniciam sozinhas. Alterações no **`.env` exigem reiniciar** manualmente.
* **Usar outra porta** (se a 8000 estiver ocupada):

  ```bash
  uvicorn prospeccao.main:app_factory --factory --reload --port 8001
  ```

  Nesse caso, acesse <http://localhost:8001>.

* **Liberar o acesso de outro dispositivo da rede local** (ex.: celular na mesma rede Wi-Fi):

  ```bash
  uvicorn prospeccao.main:app_factory --factory --host 0.0.0.0 --port 8000
  ```

  Acesse `http://IP-DO-COMPUTADOR:8000`. O IP aparece com `ipconfig` (Windows) ou
  `ip addr` (Linux) / `ipconfig getifaddr en0` (macOS). Talvez seja preciso liberar a porta no
  firewall.

### 4.5 Trocar a senha

```bash
python -m prospeccao.cli set-password paulo
```

Mudar `ADMIN_PASSWORD` no `.env` **não** altera a senha de um usuário que já existe. Use sempre
este comando.

### 4.6 Usar com dados reais localmente (opcional)

1. `python -m prospeccao.cli clear-mock` (remove os dados fictícios).
2. Em **Clientes → Importar**, envie a planilha de clientes (`.xlsx` ou `.csv`).
3. **Dados da Receita:** a base completa tem cerca de 25 GB compactados. Para testar, defina um
   filtro no `.env` (ex.: `RF_FILTER_UFS=SP`), reinicie e use **Administração → "Baixar mês mais
   recente e importar"**. O download pode levar horas. Outra opção é baixar manualmente alguns
   ZIPs de <https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/> (pasta do
   mês mais recente: `Estabelecimentos0.zip`, `Empresas0.zip`, `Simples.zip`, `Cnaes.zip`,
   `Municipios.zip`, `Naturezas.zip`), colocá-los numa pasta e importar:

   ```bash
   python -m prospeccao.cli import-receita --dir data/receita/2026-09
   ```

   (troque `2026-09` pela pasta onde você salvou os arquivos.)

---

## 5. Testes

### 5.1 Rodar todos os testes automatizados

Na pasta do projeto, com o ambiente ativo:

```bash
python -m pytest
```

O resultado esperado é `138 passed` (o número pode crescer em versões futuras). Os testes **não
usam a internet nem os seus dados**: cada teste cria um banco temporário próprio e simula as
fontes externas.

| Comando | Para quê |
|---|---|
| `python -m pytest -v` | mostra o nome de cada teste |
| `python -m pytest tests/test_domain.py` | só as regras de negócio (CNPJ, segmentos, similaridade) |
| `python -m pytest tests/test_imports.py` | importações (Receita, planilha de clientes) com banco |
| `python -m pytest tests/test_api.py` | API, login, segurança, leads, consultas externas simuladas |
| `python -m pytest tests/test_sources.py` | integrações (Receita, BrasilAPI, SEFAZ, sites) simuladas |
| `python -m pytest tests/test_ui.py` | navegador real: login → busca → empresa → lead |
| `python -m pytest -k lead` | só os testes cujo nome contém "lead" |
| `python -m pytest -x` | para no primeiro erro |
| `python -m pytest -rs` | mostra o motivo dos testes pulados (*skipped*) |

### 5.2 Teste de interface (navegador)

O `tests/test_ui.py` abre um Chromium invisível. Na primeira vez, baixe o navegador (~150 MB):

```bash
python -m playwright install chromium
```

**Linux:** se aparecer erro de bibliotecas faltando, use
`python -m playwright install --with-deps chromium` (pede a senha do `sudo`).

Se o Chromium não estiver instalado, esses 2 testes ficam como **skipped**, e isso não é falha.

### 5.3 Testes com PostgreSQL (opcional; reproduz a produção)

Os testes normalmente usam SQLite. Para rodá-los no PostgreSQL 16, igual à produção:

```bash
# Sobe um PostgreSQL 16 temporário no Docker, na porta 5433
docker run --name prospeccao-pg-test -e POSTGRES_PASSWORD=teste -e POSTGRES_DB=prospeccao_test -p 5433:5432 -d postgres:16
```

**Linux/macOS:**

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:teste@localhost:5433/prospeccao_test python -m pytest
```

**Windows:**

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:teste@localhost:5433/prospeccao_test"
python -m pytest
Remove-Item Env:TEST_DATABASE_URL
```

> ⚠️ **Nunca** aponte `TEST_DATABASE_URL` para o banco de produção: os testes **apagam todo o
> conteúdo** do banco indicado antes de rodar.

Ao terminar: `docker rm -f prospeccao-pg-test`.

### 5.4 Testes manuais das funcionalidades principais

| # | Teste | Como | Resultado esperado |
|---|---|---|---|
| 1 | Saúde | abrir `/health` | `{"status":"ok","db":true,…}` |
| 2 | Proteção | aba anônima → `/buscar` | redireciona para `/login` |
| 3 | Bloqueio de força bruta | errar a senha 5 vezes | 6ª tentativa: "Muitas tentativas" (por 15 min) |
| 4 | Busca e filtros | Buscar → filtros UF, segmento, compatibilidade ≥ 70 | lista filtrada; cada filtro aparece como "chip" removível |
| 5 | Pesquisa livre | "agronegócio no Centro-Oeste" | interpretado como Segmento=Agrobusiness, Região=Centro-Oeste |
| 6 | Página da empresa | abrir qualquer resultado | compatibilidade e potencial com explicação; fiscal com "Confirmado/Provável/Possível" |
| 7 | Lead | salvar, mudar status, observação, favorito, descartar | aparece em Leads; descartado some da busca |
| 8 | Importar clientes | Clientes → importar uma planilha com coluna "CNPJ" ou só com nomes | relatório (importados, duplicados, inválidos) e perfil calculado |
| 9 | Configurações | mudar um peso e salvar | recalcula em segundo plano; notas mudam |
| 10 | API | `/api/docs` logado → `GET /api/dashboard` → *Try it out* | JSON com totais |
| 11 | Celular | DevTools (F12) → modo dispositivo, ou o próprio celular (4.4) | layout se adapta, sem rolagem lateral |

> Na `/api/docs`, as consultas (**GET**) funcionam direto. As operações que **alteram dados**
> (POST/PATCH/DELETE) exigem o cabeçalho `X-CSRF-Token`, que a interface envia sozinha. Por
> isso, teste alterações pelas telas do sistema.

### 5.5 Erros comuns nos testes

| Sintoma | Causa | Solução |
|---|---|---|
| `ModuleNotFoundError: No module named 'prospeccao'` | ambiente virtual desativado ou projeto não instalado | ative o `.venv` e rode `python -m pip install -e .` |
| `ModuleNotFoundError: fastapi` (ou outro) | dependências não instaladas | `python -m pip install -r requirements-dev.txt` |
| `pytest: command not found` | ambiente desativado | use `python -m pytest` com o `.venv` ativo |
| `2 skipped` | Chromium do Playwright ausente | etapa 5.2 (opcional) |
| `connection refused` com `TEST_DATABASE_URL` | PostgreSQL de teste não está rodando | `docker start prospeccao-pg-test` |
| testes lentos (~40 s) | normal: hash de senha forte e navegador real | — |

---

## 6. Preparação para produção

### 6.1 O que muda em relação ao desenvolvimento

| Item | Desenvolvimento | **Produção** |
|---|---|---|
| `APP_ENV` | `development` | **`production`** |
| `SECRET_KEY` | qualquer chave gerada | **nova** chave forte (≥ 32 caracteres), nunca reutilizada |
| Banco | SQLite (arquivo) | **PostgreSQL 16** gerenciado ou em contêiner |
| `ALLOW_MOCK_DATA` | `true` | **`false`** (o sistema se recusa a iniciar em produção com `true`) |
| HTTPS | não | **obrigatório**: em produção o cookie de login só trafega por HTTPS |
| `--reload` | sim | **não** (o Dockerfile já roda sem ele) |
| Dados MOCK | podem existir | **nunca** |
| Repositório | — | **privado** |

> Em produção, o sistema **recusa iniciar** se a `SECRET_KEY` for fraca ou se
> `ALLOW_MOCK_DATA=true`. Isso é proposital.

### 6.2 Boas práticas de segurança

1. **Segredos só nas variáveis de ambiente da hospedagem**, nunca no código nem no Git.
2. **Senha do Paulo** com 12 ou mais caracteres, sem reaproveitar senhas de outros sistemas.
3. **Repositório privado** (veja o aviso da etapa 0).
4. **HTTPS sempre.** O Render e o Caddy (VPS) emitem o certificado automaticamente.
5. **Backups do banco** ativos e testados (etapas 7.1.8 e 7.2.6).
6. **Não rode `seed-mock` em produção** (ele fica bloqueado de qualquer forma).
7. **Atualizações:** aplique novas versões pelo fluxo da etapa 8.3, sempre depois de rodar os
   testes localmente.
8. A planilha de clientes é **dado privado**: não a coloque no repositório. O `.gitignore` já
   bloqueia `.xlsx` e `.csv`.

### 6.3 Banco de dados

* Você **não** precisa criar tabelas manualmente. Na primeira inicialização, o sistema cria as
  tabelas, os índices e a extensão `pg_trgm`, que acelera a busca por texto.
* O PostgreSQL precisa ser **versão 16** (a testada).
* Estimativa de espaço: a base filtrada costuma ter de centenas de milhares a poucos milhões de
  empresas. Reserve de 10 a 20 GB e acompanhe o uso.

### 6.4 Build

Não existe "build" de front-end: as telas são renderizadas pelo servidor. O "build" de produção é
a **imagem Docker** definida no `Dockerfile`, que a hospedagem constrói sozinha. Ela:

* usa Python 3.11 *slim*;
* instala o `requirements.txt`;
* roda como usuário sem privilégios;
* tem *healthcheck* em `/health`;
* escuta na porta indicada pela variável `PORT` (padrão 8000).

### 6.5 Volume da importação da Receita

A importação usa um disco persistente (`/data`) para os ZIPs (~25 GB por mês). Para importar menos:

* `RF_FILTER_UFS=SP,MG,PR,SC,RS` (exemplo), para limitar por estado;
* `RF_FILTER_CNAE_PREFIXES=…`, para limitar por atividade.

**Informação pendente:** quais UFs e CNAEs o Paulo considera prioritários. Sem filtro, o sistema
usa os CNAEs dos clientes e dos segmentos configurados.

### 6.6 (Opcional) Certificado digital para ICMS

A consulta oficial de ICMS na SEFAZ exige o **e-CNPJ A1 da empresa do Paulo**, convertido para PEM.
Sem ele, o sistema mostra "ICMS não verificado" ou "provável (inferido)", e funciona normalmente.
Informações pendentes:

* se existe certificado A1;
* a senha do certificado;
* as UFs a consultar e os endereços (*endpoints*) vigentes de cada SEFAZ.

A conversão do `.pfx` usa o OpenSSL (`openssl pkcs12 -in certificado.pfx -out cert.pem -clcerts -nokeys`
e `openssl pkcs12 -in certificado.pfx -out key.pem -nocerts -nodes`). **Nunca** envie esses
arquivos ao Git. Em produção, use o recurso de *Secret Files* da hospedagem.

---

## 7. Hospedagem

> ❌ **Netlify, Vercel (estático) e GitHub Pages não servem.** Eles não executam um servidor
> Python contínuo nem mantêm banco de dados e disco.

| Opção | Indicada para | Dificuldade |
|---|---|---|
| **7.1 Render (recomendada)** | quem quer o caminho mais simples, sem administrar servidor | ⭐ baixa |
| 7.2 Servidor próprio (VPS) com Docker Compose | quem prefere custo fixo e controle total | ⭐⭐⭐ média |

### 7.1 Render (recomendado)

O Render lê o arquivo `render.yaml` do projeto (*Blueprint*) e cria automaticamente:

* **serviço web** `prospeccao`: Docker, plano *starter*, disco de 40 GB em `/data`, healthcheck `/health`;
* **banco** `prospeccao-db`: PostgreSQL 16, plano *basic-1gb*, 15 GB;
* **variáveis**:
  * `SECRET_KEY` é gerada automaticamente;
  * `DATABASE_URL` vem do banco;
  * `ADMIN_PASSWORD` é pedida a você.

> 💰 O Render cobra pelo serviço web com disco e pelo banco. O plano **gratuito não serve**: ele
> "dorme" sem uso, não tem disco e o banco gratuito expira. Confira os valores atuais em
> <https://render.com/pricing> antes de confirmar. Se os nomes de plano do `render.yaml` não
> existirem mais, o próprio painel indicará os novos.

#### 7.1.1 Colocar o código num repositório privado seu

**Caminho A — usar o repositório existente:**

1. Torne-o privado (veja o aviso da etapa 0).
2. Mescle o branch do sistema no `main`. No GitHub, abra *Pull requests → New pull request*,
   escolha `base: main` e `compare: claude/happy-hamilton-lnok0r`, depois clique em
   *Create pull request → Merge*. Assim o Render publica a partir do `main`.

**Caminho B — repositório novo e privado:**

1. No GitHub, clique em **New repository**, dê um nome (ex.: `prospeccao`), marque
   **Private** e **não** marque a opção de criar README.
2. Na pasta do projeto, envie o código:

```bash
# Aponta o projeto local para o repositório novo (troque SEU-USUARIO e o nome se necessário)
git remote set-url origin https://github.com/SEU-USUARIO/prospeccao.git
# Envia o branch atual como "main" do repositório novo
git push -u origin HEAD:main
```

O `git push` pede login. Siga a janela do navegador ou use um *Personal Access Token* do
GitHub no lugar da senha.

Confira no site do GitHub se os arquivos `render.yaml`, `Dockerfile` e `src/` estão no
repositório e se **não** há `.env`, planilhas nem a pasta `data/`.

#### 7.1.2 Criar o Blueprint no Render

1. Entre em <https://dashboard.render.com> e conecte sua conta do GitHub, se ainda não estiver
   conectada. Autorize o acesso ao repositório.
2. Clique em **New +** → **Blueprint**.
3. Escolha o repositório e o branch (`main`).
4. O Render mostra os recursos do `render.yaml` (serviço `prospeccao` e banco `prospeccao-db`).
5. Ele pede o valor de **`ADMIN_PASSWORD`**: digite a senha do Paulo (≥ 10 caracteres).
6. Revise os planos e custos e clique em **Apply** (ou **Deploy Blueprint**).

#### 7.1.3 Acompanhar o primeiro deploy

1. Abra o serviço **prospeccao** → aba **Events**/**Logs**.
2. O Render constrói a imagem Docker (alguns minutos) e inicia o sistema.
3. Quando aparecer `Uvicorn running on http://0.0.0.0:…` e o status ficar **Live**, o deploy terminou.

#### 7.1.4 Verificar

O endereço aparece no topo da página do serviço, algo como `https://prospeccao-xxxx.onrender.com`.

**Linux/macOS:** `curl https://prospeccao-xxxx.onrender.com/health`
**Windows:** `Invoke-RestMethod https://prospeccao-xxxx.onrender.com/health`

> No Windows PowerShell 5.1, `curl` é um apelido de `Invoke-WebRequest`. Para usar o curl de
> verdade, que já vem no Windows 10/11, digite `curl.exe`.

A resposta esperada é `{"status":"ok","db":true,…}`. Depois, abra o endereço no navegador e faça
login com `paulo` e a senha informada.

#### 7.1.5 Variáveis de ambiente (ajustes posteriores)

No serviço **prospeccao** → **Environment**, você pode adicionar ou editar variáveis (ex.:
`RF_FILTER_UFS`). Ao salvar, o Render reinicia o serviço.

* **Não** altere `DATABASE_URL` nem `SECRET_KEY`. Trocar a `SECRET_KEY` desconecta todos os
  logins, o que só é útil se ela tiver vazado.
* Para o certificado da SEFAZ (6.6), use **Secret Files** (ex.: `/etc/secrets/cert.pem`) e aponte
  `ICMS_CERT_FILE`/`ICMS_KEY_FILE` para esses caminhos.

#### 7.1.6 Primeiro uso em produção

1. **Clientes → Importar**: envie a planilha de clientes.
2. **Administração → "Baixar mês mais recente e importar"**: confirme e acompanhe o progresso na
   mesma página. Pode levar várias horas. Durante a importação, o sistema também tenta encontrar
   os CNPJs dos clientes pela razão social.
3. **Clientes**: confira os vínculos feitos por nome e os casos "ambíguos".
4. Repita a importação **todo mês**. A Receita publica os dados mensalmente.

#### 7.1.7 Domínio próprio e HTTPS

1. No serviço → **Settings → Custom Domains → Add Custom Domain**. Informe, por exemplo,
   `prospeccao.suaempresa.com.br`.
2. O Render mostra o registro DNS a criar. Para um **subdomínio**, normalmente é um **CNAME**
   apontando para `prospeccao-xxxx.onrender.com`.
3. No painel DNS do domínio (Registro.br, Cloudflare…), crie o registro exatamente como o Render
   indicou.
4. Aguarde a propagação (minutos a algumas horas) e clique em **Verify**. O Render emite o
   certificado **HTTPS** automaticamente.

> **Informação pendente:** o domínio a usar e quem tem acesso ao DNS. Sem domínio, o sistema
> funciona normalmente no endereço `…onrender.com`, que já tem HTTPS.

#### 7.1.8 Backup do banco

* Os bancos pagos do Render têm backups automáticos. Confira o período de retenção do seu plano
  na aba do banco (*Recovery*/*Backups*).
* Para manter **uma cópia sua** fora do Render, pegue a *External Database URL* (banco
  `prospeccao-db` → *Connect*) e, num computador com PostgreSQL 16 ou Docker, rode:

```bash
# Gera um arquivo de backup compactado (troque a URL pela External Database URL do Render)
docker run --rm -v "$PWD":/backup postgres:16 pg_dump "COLE_A_EXTERNAL_DATABASE_URL" -Fc -f /backup/prospeccao-$(date +%Y%m%d).dump
```

No **Windows (PowerShell)**, troque `"$PWD"` por `"${PWD}"` e `$(date +%Y%m%d)` por
`$(Get-Date -Format yyyyMMdd)`.

### 7.2 Alternativa: servidor próprio (VPS) com Docker Compose

Use esta opção se preferir um servidor Linux (Hetzner, DigitalOcean, AWS Lightsail, Contabo, Locaweb…).

> 🪟 **Do Windows:** os comandos desta seção rodam **no servidor Linux**, não no seu computador.
> Conecte-se pelo PowerShell com o cliente SSH que já vem no Windows 10/11:
> `ssh root@IP-DO-SERVIDOR`. Na primeira conexão, digite `yes` para confiar no servidor e depois
> a senha enviada pelo provedor. Para sair: `exit`.

#### 7.2.1 Requisitos do servidor

* **Sistema:** Ubuntu 24.04 LTS.
* **Recursos:** 2 vCPU, 4 GB de RAM, 80 GB de disco (base filtrada + ZIPs da Receita).
* **Acesso:** IP público e acesso SSH (`ssh root@IP-DO-SERVIDOR`).
* **Domínio:** um domínio apontado para o IP. No DNS, crie um registro **A**, por exemplo
  `prospeccao.suaempresa.com.br → IP-DO-SERVIDOR`. Ele é **obrigatório** para o HTTPS automático.

#### 7.2.2 Preparar o servidor

```bash
# Atualiza o sistema
sudo apt update && sudo apt upgrade -y
# Instala o Docker Engine + Compose pelo script oficial da Docker
curl -fsSL https://get.docker.com | sudo sh
# Confere a instalação
docker --version && docker compose version
# Firewall: libera SSH, HTTP e HTTPS e bloqueia o resto
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw --force enable
sudo apt install -y git
```

#### 7.2.3 Baixar o projeto e configurar

```bash
# Repositório privado: o git pedirá usuário + Personal Access Token do GitHub
sudo git clone https://github.com/SEU-USUARIO/prospeccao.git /opt/prospeccao
cd /opt/prospeccao
sudo cp .env.example .env
# Gere DUAS chaves: uma para SECRET_KEY, outra (só letras e números) para POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
python3 -c "import secrets; print(secrets.token_hex(24))"
sudo nano .env
```

No `.env` do servidor, preencha:

```dotenv
APP_ENV=production
SECRET_KEY=<primeira chave gerada>
ADMIN_USERNAME=paulo
ADMIN_PASSWORD=<senha do Paulo>
ALLOW_MOCK_DATA=false
POSTGRES_PASSWORD=<segunda chave gerada (só letras e números)>
DOMAIN=prospeccao.suaempresa.com.br
```

Deixe `DATABASE_URL` e `DATA_DIR` como estão: o `docker-compose.yml` preenche os dois.

> A `POSTGRES_PASSWORD` deve ter **só letras e números**. Caracteres como `@ : / #` quebram a URL
> de conexão.

#### 7.2.4 Subir

```bash
# Constrói a imagem e sobe banco, aplicação e Caddy (HTTPS) em segundo plano
sudo docker compose up -d --build
# Mostra o estado dos 3 contêineres (devem ficar "running"/"healthy")
sudo docker compose ps
# Acompanha os logs (Ctrl+C sai dos logs sem parar nada)
sudo docker compose logs -f
```

Em 1 a 2 minutos, o Caddy obtém o certificado. Acesse `https://prospeccao.suaempresa.com.br`.

#### 7.2.5 Comandos do dia a dia na VPS

| Ação | Comando (dentro de `/opt/prospeccao`) |
|---|---|
| Ver estado | `sudo docker compose ps` |
| Logs da aplicação | `sudo docker compose logs -f app` |
| Reiniciar a aplicação | `sudo docker compose restart app` |
| Parar tudo | `sudo docker compose down` (os dados ficam nos volumes) |
| Iniciar tudo | `sudo docker compose up -d` |
| Trocar a senha | `sudo docker compose exec app python -m prospeccao.cli set-password paulo` |
| Testar fontes | `sudo docker compose exec app python -m prospeccao.cli check-sources` |

#### 7.2.6 Backups e atualização mensal (cron)

```bash
sudo crontab -e
```

Adicione as linhas abaixo e salve:

```cron
# Backup diário às 03:15 (mantém os 14 mais recentes em deploy/backups/)
15 3 * * * /opt/prospeccao/scripts/backup.sh >> /var/log/prospeccao-backup.log 2>&1
# Atualização dos dados da Receita no dia 20 de cada mês, às 04:30
30 4 20 * * /opt/prospeccao/scripts/cron-update.sh >> /var/log/prospeccao-update.log 2>&1
```

Copie os backups para **fora** do servidor periodicamente (outro computador ou armazenamento em
nuvem). Para restaurar, use `sudo ./scripts/restore.sh deploy/backups/<arquivo>.sql.gz`. Esse
comando **substitui** o banco atual.

---

## 8. Pós-deploy

### 8.1 Verificar se está funcionando

1. `https://SEU-ENDERECO/health` retorna `{"status":"ok","db":true,…}`.
2. O login funciona. No navegador, o cadeado aparece e o endereço começa com `https://`.
3. **Não** aparece a faixa amarela "MOCK".
4. **Administração → Status das fontes:**
   * "Receita" fica "Nunca executada" até a primeira importação. Isso é normal.
   * "SEFAZ" aparece desativada, a menos que o certificado esteja configurado.
5. Na **Busca**, os resultados aparecem depois da primeira importação.

### 8.2 Logs e diagnóstico

| Onde | Render | VPS |
|---|---|---|
| Logs da aplicação | serviço → **Logs** (filtros e busca) | `sudo docker compose logs -f app` |
| Histórico de deploys | serviço → **Events** | `git log --oneline` |
| Comandos dentro do sistema | serviço → **Shell**: `python -m prospeccao.cli check-sources` | `sudo docker compose exec app …` |
| Processos em segundo plano | página **Administração → Processos** (status, progresso, log de erros) | idem |
| Saúde | `/health` | `/health` e `sudo docker compose ps` |

Quando a tela mostrar **"Erro interno. Referência: abc12345"**, procure `abc12345` nos logs: a
linha correspondente traz o detalhe técnico do erro.

### 8.3 Atualizar para uma nova versão

**Fluxo recomendado (vale para os dois tipos de hospedagem):**

1. No seu computador: `git pull`, depois `python -m pytest`. Todos os testes devem passar.
2. Envie a nova versão: `git push origin main`.

**Render:** com `autoDeploy: true`, o Render publica sozinho a cada `push` no `main`. Acompanhe em
**Events**.

> Serviços **com disco** no Render ficam fora do ar **por alguns segundos/minutos** durante cada
> deploy, porque o Render para a instância antiga antes de subir a nova. Prefira atualizar fora do
> horário de uso.

**VPS:**

```bash
cd /opt/prospeccao
sudo ./scripts/backup.sh              # backup antes de atualizar
sudo git pull                         # baixa a nova versão
sudo docker compose up -d --build     # reconstrói e reinicia só o que mudou
sudo docker compose logs -f app       # confere a inicialização
```

> ⚠️ **Mudanças no banco:** o sistema cria tabelas novas automaticamente, mas **não altera
> colunas de tabelas que já existem**, porque ainda não há ferramenta de migração (Alembic).
> Se uma versão futura alterar colunas, ela precisa vir acompanhada de instruções de migração.
> Faça **sempre** backup antes de atualizar.

### 8.4 Reiniciar ou reverter

| Situação | Render | VPS |
|---|---|---|
| Reiniciar | serviço → **Manual Deploy → Restart service** (ou *Deploy latest commit*) | `sudo docker compose restart app` |
| Voltar para a versão anterior | serviço → **Events** → no deploy anterior que funcionava, **Rollback** | `sudo git log --oneline` → `sudo git checkout <hash-anterior>` → `sudo docker compose up -d --build`. Para voltar ao normal depois: `sudo git checkout main` |
| Restaurar os dados | banco → **Recovery** (conforme o plano) ou `pg_restore` do seu backup | `sudo ./scripts/restore.sh deploy/backups/<arquivo>.sql.gz` |

> No Render, o *Rollback* volta **o código**, não o banco. Se uma versão nova tiver alterado
> dados, restaure também o backup do banco.

---

## 9. Troubleshooting

### 9.1 Instalação e ambiente

| Erro | Causa | Solução |
|---|---|---|
| `python`/`git` "não é reconhecido" (Windows) | não está no PATH ou o terminal foi aberto antes da instalação | feche e reabra o PowerShell; no instalador do Python, marque "Add to PATH" |
| `python3: command not found` (macOS) | Python não instalado | `brew install python@3.12` |
| `The virtual environment was not created successfully because ensurepip is not available` (Ubuntu) | falta o pacote venv | `sudo apt install -y python3-venv` (ou `python3.11-venv`) |
| "execução de scripts foi desabilitada" (Windows) | política do PowerShell | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `ERROR: Package 'prospeccao' requires a different Python` | Python < 3.11 | instale o 3.12 e recrie o `.venv` (apague a pasta `.venv` e repita a etapa 2.3) |
| `pip install` falha compilando `psycopg` | versão de Python sem pacote pronto | use Python 3.11–3.13 e `python -m pip install --upgrade pip` |

### 9.2 Configuração e execução local

| Erro | Causa | Solução |
|---|---|---|
| `Erro de configuração: ADMIN_PASSWORD inválida…` | senha com menos de 10 caracteres | corrija o `.env` |
| Login sempre "Usuário ou senha inválidos" | o usuário foi criado com outra senha (`ADMIN_PASSWORD` só vale na 1ª vez) | `python -m prospeccao.cli set-password paulo` |
| Log: "Nenhum usuário cadastrado" | `ADMIN_PASSWORD` vazio | preencha o `.env` e rode `init`, ou use `set-password` |
| "Muitas tentativas. Aguarde 15 minutos" | proteção contra força bruta | aguarde ou reinicie o servidor (o contador fica em memória) |
| Login não "segura" localmente (volta para /login) | `APP_ENV=production` em `http://localhost` (cookie só por HTTPS) | localmente, use `APP_ENV=development` |
| `[Errno 98] Address already in use` / `10048` | porta 8000 ocupada | use `--port 8001` ou encontre o processo: `lsof -i :8000` (Linux/macOS) · `netstat -ano \| findstr :8000` (Windows) |
| `RuntimeError: SECRET_KEY forte… é obrigatória em produção` | produção sem chave forte | gere uma chave (2.4.1) |
| `RuntimeError: ALLOW_MOCK_DATA não pode estar ativo em produção` | `.env` de produção com `true` | `ALLOW_MOCK_DATA=false` |
| `database is locked` (SQLite) | dois servidores usando o mesmo arquivo, ou pasta no OneDrive | rode um único servidor; tire o projeto de pastas sincronizadas |
| Alterei o `.env` e nada mudou | o `.env` só é lido na inicialização | pare (`Ctrl+C`) e inicie de novo |
| `.env` ignorado | comando executado fora da pasta do projeto | entre na pasta (`cd prospeccao`) antes de iniciar |
| Página sem estilo (CSS) | servidor iniciado fora da pasta, ou instalação incompleta | `python -m pip install -e .` e inicie na pasta do projeto |

### 9.3 Importações

| Erro | Causa | Solução |
|---|---|---|
| "Cabeçalho não reconhecido" (planilha) | nenhuma coluna parecida com CNPJ ou nome | a 1ª linha deve ter "CNPJ" e/ou "Razão social"/"Cliente"/"Empresa" |
| "Formato não suportado" | arquivo `.xls` antigo ou `.pdf` | salve como `.xlsx` ou `.csv` |
| Importação da Receita "Falhou — Nenhum arquivo de Estabelecimentos" | pasta sem os ZIPs | baixe pela tela (com internet) ou coloque os ZIPs em `data/receita/` |
| `Receita … servidor indisponível` | site da Receita fora do ar ou endereço mudou | tente mais tarde; confira o endereço em <https://dados.gov.br> e ajuste `RF_BASE_URL` |
| `… retornou HTTP 429` (API de CNPJ) | limite de consultas da API pública | aguarde; aumente `CNPJ_API_MIN_INTERVAL`; ou troque `CNPJ_API_PROVIDER=opencnpj` |
| Processo "Interrompido por reinício da aplicação" | o servidor reiniciou (deploy, falta de memória) no meio do processo | dispare de novo; no Render, se reiniciar sempre, mude o plano para *standard* |
| Disco cheio (`No space left on device`) | ZIPs da Receita acumulados | apague meses antigos em `/data/receita/AAAA-MM` ou aumente o disco |

### 9.4 Hospedagem

| Erro | Causa | Solução |
|---|---|---|
| Render: deploy falha em `pip install` | indisponibilidade momentânea | **Manual Deploy → Clear build cache & deploy** |
| Render: "Exited with status 1" logo ao iniciar | variável faltando (ex.: `ADMIN_PASSWORD` curta) ou `SECRET_KEY` fraca | leia as últimas linhas dos **Logs**: a mensagem diz o que corrigir em **Environment** |
| Render: healthcheck falhando | aplicação não subiu, ou banco ainda criando | aguarde o banco ficar *Available* e veja os Logs |
| `could not translate host name` / `connection refused` (banco) | `DATABASE_URL` errada ou banco parado | no Render, não edite `DATABASE_URL`; na VPS, `sudo docker compose ps` (o `db` deve estar *healthy*) |
| Domínio sem HTTPS / "certificate" | DNS ainda não propagou ou registro errado | confira com `nslookup prospeccao.suaempresa.com.br`; aguarde e clique *Verify* (Render) ou veja `sudo docker compose logs caddy` (VPS) |
| VPS: Caddy não emite certificado | portas 80/443 fechadas ou `DOMAIN` errado | `sudo ufw status`; revise `DOMAIN` no `.env` e rode `sudo docker compose up -d` |
| VPS: `password authentication failed` | `POSTGRES_PASSWORD` mudou depois que o banco foi criado | volte à senha original no `.env` (o volume guarda a senha da criação) |

### 9.5 Comandos úteis de diagnóstico

```bash
# Saúde do sistema (troque o endereço pelo seu)
curl -i https://SEU-ENDERECO/health

# Estado das fontes externas (local)
python -m prospeccao.cli check-sources

# Versões instaladas (local)
python --version
python -m pip list

# Testes completos (local)
python -m pytest -x -q

# VPS: estado, uso de disco e logs recentes
sudo docker compose ps
df -h
sudo docker compose logs --tail=200 app
```

**Windows (PowerShell), equivalentes:**

```powershell
# Saúde do sistema
Invoke-RestMethod https://SEU-ENDERECO/health
# Fontes externas, versões e testes (na pasta do projeto)
powershell -ExecutionPolicy Bypass -File .\scripts\windows\cli.ps1 check-sources
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip list
powershell -ExecutionPolicy Bypass -File .\scripts\windows\testar.ps1 -PararNoPrimeiroErro
# Quem está usando a porta 8000 (o último número é o PID; encerre com: Stop-Process -Id PID)
netstat -ano | findstr :8000
# Espaço livre em disco
Get-PSDrive C
```

### 9.6 Problemas específicos do Windows

| Erro | Causa | Solução |
|---|---|---|
| Digitar `python` abre a **Microsoft Store** | "alias de execução" do Windows | use `py` no lugar de `python`, ou desative em *Configurações → Aplicativos → Configurações avançadas de aplicativos → Aliases de execução de aplicativo* (desligue "python.exe" e "python3.exe") |
| `py` não é reconhecido | Python instalado sem o lançador, ou terminal antigo | feche e reabra o PowerShell; reinstale com `winget install --id Python.Python.3.12 -e` |
| "…não pode ser carregado porque a execução de scripts foi desabilitada" | política de execução do PowerShell | execute os scripts com `powershell -ExecutionPolicy Bypass -File …` (como neste tutorial) ou use os `.bat` |
| "O arquivo … não está assinado digitalmente" / aviso ao abrir o `.bat` | arquivos vindos de um `.zip` baixado da internet | na pasta do projeto: `Get-ChildItem -Recurse \| Unblock-File` |
| "O Windows protegeu o computador" (SmartScreen) ao abrir o `.bat` | arquivo baixado da internet | *Mais informações → Executar assim mesmo* (confira antes que o arquivo veio do seu repositório) |
| `pip install` muito lento ou "Access is denied" | antivírus verificando milhares de arquivos, ou pasta protegida | aguarde; mantenha o projeto em `C:\projetos` (fora de *Arquivos de Programas* e do OneDrive) |
| `database is locked` | pasta sincronizada pelo OneDrive, ou duas janelas do sistema abertas | mova para `C:\projetos`; feche a outra janela |
| Acentos estranhos no console (`ImportaÃ§Ã£o`) | console antigo sem UTF-8 | os scripts já configuram UTF-8; se persistir, use o **Windows Terminal** (`winget install --id Microsoft.WindowsTerminal -e`) |
| `.env` "ignorado" depois de editar no Bloco de Notas | — | o sistema aceita UTF-8, UTF-8 com BOM, UTF-16 e ANSI. Confira se o nome é exatamente `.env`, e não `.env.txt` (*Exibir → Extensões de nomes de arquivos*) |
| `docker` não reconhecido / "error during connect" | Docker Desktop não instalado ou fechado | instale (requer WSL 2: `wsl --install` como administrador e reinicie) e **abra** o Docker Desktop antes de usar `-PostgreSQL` |
| Caminho muito longo (`Filename too long`) no `git clone` | limite de 260 caracteres do Windows | use uma pasta curta (`C:\projetos`); se precisar: `git config --global core.longpaths true` |
| `git` converte quebras de linha e scripts `.sh` falham na VPS | conversão CRLF | o `.gitattributes` do projeto já força LF nos arquivos de Linux; clone de novo se o problema vier de uma cópia antiga |

---

## 10. Checklist final

### Ambiente local

> 🪟 **Windows:** os itens abaixo são cobertos por `instalar-windows.bat` (ou `instalar.ps1`),
> `iniciar-windows.bat` e `testar.ps1`. Confira apenas o resultado de cada um.

- [ ] Git instalado (`git --version`)
- [ ] Python 3.11–3.13 instalado (`python --version`)
- [ ] Projeto clonado e no branch/código correto
- [ ] Ambiente virtual criado e **ativo** (`(.venv)` no prompt)
- [ ] `.env` criado a partir do `.env.example`, com `SECRET_KEY` gerada e `ADMIN_PASSWORD` ≥ 10
- [ ] Dependências instaladas (`pip install -r requirements-dev.txt` e `pip install -e .`)
- [ ] `python -m prospeccao.cli init` executado sem erro
- [ ] `uvicorn prospeccao.main:app_factory --factory --reload` rodando
- [ ] <http://localhost:8000/health> retorna `"status":"ok"`
- [ ] Login, busca, página da empresa e lead funcionando
- [ ] `python -m pytest` (Windows: `testar.ps1`) com todos os testes aprovados

### Preparação para produção

- [ ] Repositório **privado**, sem `.env`, planilhas ou pasta `data/`
- [ ] Senha forte do Paulo definida
- [ ] Hospedagem escolhida e conta criada (Render recomendado)
- [ ] (Opcional) Domínio e acesso ao DNS
- [ ] (Opcional) Filtros de UF/CNAE definidos
- [ ] (Opcional) Certificado e-CNPJ A1 para ICMS

### Produção

- [ ] Blueprint aplicado (Render) **ou** `docker compose up -d --build` (VPS)
- [ ] `APP_ENV=production`, `ALLOW_MOCK_DATA=false`, `SECRET_KEY` forte
- [ ] `https://…/health` retorna `"status":"ok","db":true`
- [ ] Login por HTTPS funcionando; sem faixa "MOCK"
- [ ] Planilha de clientes importada
- [ ] Primeira importação da Receita concluída (Administração → Processos = *done*)
- [ ] Vínculos de clientes por nome conferidos
- [ ] Backups automáticos ativos e **uma restauração testada**
- [ ] (Opcional) Domínio próprio com cadeado HTTPS
- [ ] Rotina mensal de atualização definida (Render: botão na Administração; VPS: cron)

---

**Documentos relacionados:**

* [README](../README.md)
* [Documentação final](10-documentacao-final.md): arquitetura, metodologias, limitações
* [API](06-api.md)
* [Análise da base de clientes](07-analise-base-clientes.md)
