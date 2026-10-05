@echo off
REM Duplo clique: inicia o sistema e abre o navegador em http://localhost:8000
REM Para parar: Ctrl+C nesta janela (ou feche a janela).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\iniciar.ps1" -AbrirNavegador %*
echo.
pause
