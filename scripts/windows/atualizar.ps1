<#
.SYNOPSIS
  Atualiza a cópia local para a versão mais recente do repositório e reinstala as dependências.
  Feche o sistema (Ctrl+C) antes de executar.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\atualizar.ps1
#>
param(
    # Não executar os testes depois de atualizar
    [switch]$SemTestes
)

. (Join-Path $PSScriptRoot '_comum.ps1')
$py = Exigir-Venv

if (Porta-EmUso 8000) { Escrever-Aviso "Parece haver um sistema rodando na porta 8000. Feche-o (Ctrl+C) antes de atualizar." }

Escrever-Etapa "Baixando a versão mais recente (git pull)"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Parar-ComErro "Git não encontrado." }
$alteracoes = git status --porcelain --untracked-files=no
if ($alteracoes) { Parar-ComErro "Há arquivos do projeto alterados localmente. Salve-os (git stash) antes de atualizar." }
git pull
if ($LASTEXITCODE -ne 0) { Parar-ComErro "git pull falhou. Leia a mensagem acima." }

Escrever-Etapa "Atualizando dependências"
& $py -m pip install -r (Join-Path $script:Raiz 'requirements-dev.txt') --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao instalar dependências." }
& $py -m pip install -e $script:Raiz --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao reinstalar o projeto." }

Escrever-Etapa "Atualizando o banco local (novas tabelas, se houver)"
& $py -m prospeccao.cli init
if ($LASTEXITCODE -ne 0) { Parar-ComErro "Falha ao atualizar o banco." }

if (-not $SemTestes) {
    Escrever-Etapa "Executando os testes"
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { Parar-ComErro "Há testes com falha após a atualização — não publique esta versão." }
}
Write-Host ""
Write-Host "Atualização concluída." -ForegroundColor Green
