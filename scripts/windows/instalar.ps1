<#
.SYNOPSIS
  Instala o sistema no Windows: ambiente virtual, dependências, arquivo .env e banco local.

.DESCRIPTION
  Pode ser executado mais de uma vez com segurança: não apaga o .env nem o banco existentes.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\instalar.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\instalar.ps1 -ComDadosFicticios
#>
param(
    # Gera 400 empresas FICTÍCIAS (marcadas MOCK) para conhecer as telas
    [switch]$ComDadosFicticios,
    # Apaga e recria a pasta .venv (use se a instalação anterior ficou corrompida)
    [switch]$RecriarAmbiente,
    # Senha do usuário (para automação). Se omitida, o script pergunta sem mostrar na tela.
    [string]$SenhaAdmin = ''
)

. (Join-Path $PSScriptRoot '_comum.ps1')

Write-Host "Instalação do Sistema de Prospecção — pasta: $script:Raiz"

# 1) Git (só avisa: não é necessário para rodar localmente)
Escrever-Etapa "Verificando o Git"
if (Get-Command git -ErrorAction SilentlyContinue) { Escrever-Ok (git --version) }
else { Escrever-Aviso "Git não encontrado. Ele só é necessário para publicar (winget install --id Git.Git -e)." }

# 2) Python 3.11–3.13
Escrever-Etapa "Procurando Python 3.11, 3.12 ou 3.13"
$python = Encontrar-Python
if (-not $python) {
    Parar-ComErro ("Python 3.11–3.13 não encontrado. Instale com:`n" +
        "    winget install --id Python.Python.3.12 -e --source winget`n" +
        "Depois FECHE e ABRA o PowerShell e execute este script de novo.")
}
Escrever-Ok ("Python {0} ({1})" -f $python.Versao, ($python.Comando -join ' '))

# 3) Ambiente virtual
Escrever-Etapa "Preparando o ambiente virtual (.venv)"
$venvDir = Join-Path $script:Raiz '.venv'
if ($RecriarAmbiente -and (Test-Path $venvDir)) {
    Remove-Item -Recurse -Force $venvDir
    Escrever-Ok "Ambiente antigo removido"
}
if (-not (Caminho-PythonVenv)) {
    $exe = $python.Comando[0]
    $argsExtra = @()
    if ($python.Comando.Count -gt 1) { $argsExtra = $python.Comando[1..($python.Comando.Count - 1)] }
    & $exe @argsExtra -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao criar o ambiente virtual." }
    Escrever-Ok "Ambiente criado em .venv"
} else {
    Escrever-Ok "Ambiente já existe (use -RecriarAmbiente para refazer)"
}
$py = Caminho-PythonVenv

# 4) Dependências
Escrever-Etapa "Instalando dependências (pode levar alguns minutos na primeira vez)"
& $py -m pip install --upgrade pip --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao atualizar o pip. Verifique a conexão com a internet." }
& $py -m pip install -r (Join-Path $script:Raiz 'requirements-dev.txt') --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao instalar as dependências (requirements-dev.txt)." }
& $py -m pip install -e $script:Raiz --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao instalar o projeto (pip install -e .)." }
Escrever-Ok "Dependências instaladas"

# 5) Arquivo .env
Escrever-Etapa "Configurando o arquivo .env"
$envPath = Join-Path $script:Raiz '.env'
if (-not (Test-Path $envPath)) {
    $modelo = [System.IO.File]::ReadAllText((Join-Path $script:Raiz '.env.example'))
    Gravar-TextoUtf8 $envPath $modelo
    Escrever-Ok ".env criado a partir do .env.example"
} else {
    Escrever-Ok ".env já existe — valores preenchidos serão mantidos"
}

$linhas = [System.Collections.Generic.List[string]]::new()
foreach ($l in [System.IO.File]::ReadAllLines($envPath)) { $linhas.Add($l) }

function Valor-Env([string]$chave) {
    foreach ($l in $linhas) { if ($l.StartsWith("$chave=")) { return $l.Substring($chave.Length + 1).Trim() } }
    return $null
}
function Definir-Env([string]$chave, [string]$valor) {
    for ($i = 0; $i -lt $linhas.Count; $i++) {
        if ($linhas[$i].StartsWith("$chave=")) { $linhas[$i] = "$chave=$valor"; return }
    }
    $linhas.Add("$chave=$valor")
}

if (-not (Valor-Env 'SECRET_KEY')) {
    $chave = (& $py -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
    Definir-Env 'SECRET_KEY' $chave
    Escrever-Ok "SECRET_KEY gerada automaticamente"
} else { Escrever-Ok "SECRET_KEY já definida" }

if (-not (Valor-Env 'ADMIN_PASSWORD')) {
    $usuario = Valor-Env 'ADMIN_USERNAME'
    if (-not $usuario) { $usuario = 'paulo'; Definir-Env 'ADMIN_USERNAME' $usuario }
    $senha = $SenhaAdmin
    while (-not $senha) {
        Write-Host "    Defina a senha do usuário '$usuario' (mínimo 10 caracteres; não aparece ao digitar)."
        $s1 = (New-Object System.Net.NetworkCredential('', (Read-Host '    Senha' -AsSecureString))).Password
        $s2 = (New-Object System.Net.NetworkCredential('', (Read-Host '    Repita a senha' -AsSecureString))).Password
        if ($s1 -ne $s2) { Escrever-Aviso "As senhas não conferem. Tente de novo."; continue }
        if ($s1.Length -lt 10) { Escrever-Aviso "A senha precisa ter pelo menos 10 caracteres."; continue }
        if ($s1 -ne $s1.Trim() -or $s1.StartsWith('"') -or $s1.StartsWith("'")) {
            Escrever-Aviso "Não comece/termine a senha com espaço ou aspas."; continue
        }
        $senha = $s1
    }
    if ($senha.Length -lt 10) { Parar-ComErro "A senha precisa ter pelo menos 10 caracteres." }
    Definir-Env 'ADMIN_PASSWORD' $senha
    Escrever-Ok "Senha registrada no .env (usada para criar o usuário na primeira execução)"
} else { Escrever-Ok "ADMIN_PASSWORD já definida" }

Gravar-TextoUtf8 $envPath (($linhas -join "`r`n") + "`r`n")

# 6) Banco de dados local
Escrever-Etapa "Criando o banco de dados local"
& $py -m prospeccao.cli init
if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao inicializar o banco. Leia a mensagem acima (geralmente um valor inválido no .env)." }

if ($ComDadosFicticios) {
    Escrever-Etapa "Gerando dados FICTÍCIOS (MOCK) para demonstração"
    & $py -m prospeccao.cli seed-mock
    if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao gerar dados fictícios." }
}

Write-Host ""
Write-Host "Instalação concluída!" -ForegroundColor Green
Write-Host "Para iniciar o sistema:  powershell -ExecutionPolicy Bypass -File .\scripts\windows\iniciar.ps1 -AbrirNavegador"
Write-Host "Ou dê dois cliques em:   iniciar-windows.bat"
Write-Host "Endereço:                http://localhost:8000   (usuário: $(Valor-Env 'ADMIN_USERNAME'))"
