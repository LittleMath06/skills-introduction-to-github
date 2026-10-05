@echo off
REM Duplo clique: instala o sistema (ambiente, dependencias, .env e banco local).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\instalar.ps1" %*
echo.
pause
