<#
.SYNOPSIS
  Atalho para os comandos administrativos (python -m prospeccao.cli ...) sem ativar o ambiente.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\cli.ps1 set-password paulo
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\cli.ps1 import-customers C:\Users\Paulo\Downloads\clientes.xlsx
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\cli.ps1 --help
#>
. (Join-Path $PSScriptRoot '_comum.ps1')
$py = Exigir-Venv
& $py -m prospeccao.cli @args
exit $LASTEXITCODE
