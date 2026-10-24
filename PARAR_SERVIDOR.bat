@echo off
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  echo Clique com o botao direito neste arquivo e escolha "Executar como administrador".
  pause
  exit /b 1
)
schtasks /End /TN "Sistema de Despesas" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0PARAR_SERVIDOR.ps1"
echo Servidor parado (se estava em execucao).
pause
