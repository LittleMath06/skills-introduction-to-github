<#
.SYNOPSIS
  Executa os testes automatizados.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\testar.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\testar.ps1 -Interface
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\testar.ps1 -PostgreSQL
#>
param(
    # Baixa o Chromium do Playwright (uma vez) para rodar também os testes de interface
    [switch]$Interface,
    # Roda os testes num PostgreSQL 16 temporário (requer Docker Desktop aberto)
    [switch]$PostgreSQL,
    # Para no primeiro erro
    [switch]$PararNoPrimeiroErro,
    # Filtro por nome de teste (ex.: -Filtro lead)
    [string]$Filtro = ''
)

. (Join-Path $PSScriptRoot '_comum.ps1')
$py = Exigir-Venv

if ($Interface) {
    Escrever-Etapa "Instalando o navegador Chromium para os testes de interface (~150 MB, só na 1ª vez)"
    & $py -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao baixar o Chromium. Verifique a internet." }
}

$container = 'prospeccao-pg-test'
if ($PostgreSQL) {
    Escrever-Etapa "Subindo PostgreSQL 16 temporário no Docker (porta 5433)"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Parar-ComErro "Docker não encontrado. Instale e ABRA o Docker Desktop: https://www.docker.com/products/docker-desktop/"
    }
    docker rm -f $container 2>$null | Out-Null
    docker run --name $container -e POSTGRES_PASSWORD=teste -e POSTGRES_DB=prospeccao_test -p 5433:5432 -d postgres:16 | Out-Null
    if ($LASTEXITCODE -ne 0) { Parar-ComErro "Não foi possível iniciar o contêiner. O Docker Desktop está aberto?" }
    $pronto = $false
    for ($i = 0; $i -lt 30; $i++) {
        docker exec $container pg_isready -U postgres 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $pronto = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $pronto) { Parar-ComErro "O PostgreSQL de teste não ficou pronto a tempo." }
    # ATENÇÃO: os testes APAGAM o banco indicado aqui. Nunca use o banco de produção.
    $env:TEST_DATABASE_URL = 'postgresql+psycopg://postgres:teste@localhost:5433/prospeccao_test'
    Escrever-Ok "PostgreSQL pronto"
}

Escrever-Etapa "Executando os testes"
$argumentos = @('-m', 'pytest', '-q', '-rs')
if ($PararNoPrimeiroErro) { $argumentos += '-x' }
if ($Filtro) { $argumentos += @('-k', $Filtro) }
& $py @argumentos
$codigo = $LASTEXITCODE

if ($PostgreSQL) {
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
    docker rm -f $container 2>$null | Out-Null
    Escrever-Ok "PostgreSQL de teste removido"
}

Write-Host ""
if ($codigo -eq 0) { Write-Host "Todos os testes passaram." -ForegroundColor Green }
else { Write-Host "Há testes com falha (código $codigo). Veja as mensagens acima e o tutorial, etapa 5.5." -ForegroundColor Red }
exit $codigo
