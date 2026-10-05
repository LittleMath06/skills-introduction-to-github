<#
.SYNOPSIS
  Inicia o sistema localmente (http://localhost:8000). Para parar: Ctrl+C nesta janela.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\iniciar.ps1 -AbrirNavegador
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\iniciar.ps1 -Porta 8001
#>
param(
    # Porta local (padrão 8000)
    [int]$Porta = 8000,
    # Abre o navegador automaticamente quando o sistema estiver pronto
    [switch]$AbrirNavegador,
    # Permite acesso de outros dispositivos da mesma rede (ex.: celular no Wi-Fi)
    [switch]$RedeLocal,
    # Desliga o recarregamento automático ao editar o código
    [switch]$SemRecarregar
)

. (Join-Path $PSScriptRoot '_comum.ps1')
$py = Exigir-Venv

if (Porta-EmUso $Porta) {
    Parar-ComErro ("A porta $Porta já está em uso (o sistema já está aberto em outra janela?).`n" +
        "Use outra porta:  powershell -ExecutionPolicy Bypass -File .\scripts\windows\iniciar.ps1 -Porta 8001`n" +
        "Ou descubra o processo:  netstat -ano | findstr :$Porta")
}

$hostLigacao = '127.0.0.1'
if ($RedeLocal) { $hostLigacao = '0.0.0.0' }
$url = "http://localhost:$Porta"

if ($AbrirNavegador) {
    # Espera o /health responder e então abre o navegador (em segundo plano)
    Start-Job -ArgumentList $url -ScriptBlock {
        param($u)
        for ($i = 0; $i -lt 60; $i++) {
            try {
                $r = Invoke-WebRequest -Uri "$u/health" -UseBasicParsing -TimeoutSec 2
                if ($r.StatusCode -eq 200) { Start-Process $u; break }
            } catch { Start-Sleep -Seconds 1 }
        }
    } | Out-Null
}

Write-Host ""
Write-Host "Sistema de Prospecção iniciando em $url" -ForegroundColor Green
if ($RedeLocal) { Write-Host "Acesso pela rede local liberado: use http://IP-DESTE-COMPUTADOR:$Porta (veja o IP com: ipconfig)" }
Write-Host "Para PARAR: pressione Ctrl+C nesta janela." -ForegroundColor Yellow
Write-Host ""

$argumentos = @('-m', 'uvicorn', 'prospeccao.main:app_factory', '--factory', '--host', $hostLigacao, '--port', "$Porta")
if (-not $SemRecarregar) { $argumentos += @('--reload', '--reload-dir', (Join-Path $script:Raiz 'src')) }
& $py @argumentos
