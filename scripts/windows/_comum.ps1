# Funções compartilhadas pelos scripts do Windows. Compatível com Windows PowerShell 5.1 e PowerShell 7.
# Não execute este arquivo diretamente: ele é carregado pelos outros scripts.

$ErrorActionPreference = 'Stop'
# Saída do Python em UTF-8 (acentos corretos no console e em arquivos de log)
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { $null = $_ <# console sem suporte: segue com a codificação padrão #> }

# Pasta raiz do projeto = duas pastas acima deste arquivo (scripts\windows\ -> raiz)
$script:Raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $script:Raiz

function Escrever-Etapa([string]$texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Escrever-Ok([string]$texto)    { Write-Host "    [OK] $texto" -ForegroundColor Green }
function Escrever-Aviso([string]$texto) { Write-Host "    [!] $texto" -ForegroundColor Yellow }
function Parar-ComErro([string]$texto)  { Write-Host ""; Write-Host "ERRO: $texto" -ForegroundColor Red; exit 1 }

function Testar-VersaoPython([string[]]$comando) {
    # Retorna a versão (ex.: "3.12") se o comando existir e for Python 3.11 a 3.13; senão $null
    try {
        $exe = $comando[0]
        $argsExtra = @()
        if ($comando.Count -gt 1) { $argsExtra = $comando[1..($comando.Count - 1)] }
        $saida = & $exe @argsExtra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $saida) { return $null }
        $versao = "$saida".Trim()
        $partes = $versao.Split('.')
        if ([int]$partes[0] -eq 3 -and [int]$partes[1] -ge 11 -and [int]$partes[1] -le 13) { return $versao }
    } catch { $null = $_ <# comando inexistente ou alias da Microsoft Store: tenta o próximo #> }
    return $null
}

function Encontrar-Python {
    # Ordem de preferência: lançador "py" do Windows (3.12, 3.13, 3.11), depois python/python3 do PATH
    $candidatos = @(
        @('py', '-3.12'), @('py', '-3.13'), @('py', '-3.11'),
        @('python'), @('python3')
    )
    foreach ($c in $candidatos) {
        if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
        $v = Testar-VersaoPython $c
        if ($v) { return @{ Comando = $c; Versao = $v } }
    }
    return $null
}

function Caminho-PythonVenv {
    # Windows: .venv\Scripts\python.exe   (Linux/macOS, usado nos testes do script: .venv/bin/python)
    $win = Join-Path $script:Raiz '.venv\Scripts\python.exe'
    $nix = Join-Path $script:Raiz '.venv/bin/python'
    if (Test-Path $win) { return $win }
    if (Test-Path $nix) { return $nix }
    return $null
}

function Exigir-Venv {
    $py = Caminho-PythonVenv
    if (-not $py) {
        Parar-ComErro "Ambiente virtual não encontrado. Execute primeiro: powershell -ExecutionPolicy Bypass -File .\scripts\windows\instalar.ps1"
    }
    if (-not (Test-Path (Join-Path $script:Raiz '.env'))) {
        Parar-ComErro "Arquivo .env não encontrado. Execute primeiro o instalar.ps1."
    }
    return $py
}

function Gravar-TextoUtf8([string]$caminho, [string]$texto) {
    # UTF-8 SEM BOM (o Set-Content -Encoding UTF8 do PowerShell 5.1 grava com BOM)
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($caminho, $texto, $enc)
}

function Porta-EmUso([int]$porta) {
    $ouvinte = $null
    try {
        $ouvinte = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $porta)
        $ouvinte.Start()
        return $false
    } catch {
        return $true
    } finally {
        if ($ouvinte) { try { $ouvinte.Stop() } catch { $null = $_ <# já liberada #> } }
    }
}
