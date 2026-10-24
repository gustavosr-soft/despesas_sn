@echo off
net session >nul 2>&1
if errorlevel 1 (
  echo Clique com o botao direito neste arquivo e escolha "Executar como administrador".
  pause
  exit /b 1
)
REM Remove ambos os nomes possiveis da tarefa (versao antiga e nova)
schtasks /End /TN "SistemaDespesas" >nul 2>&1
schtasks /Delete /TN "SistemaDespesas" /F >nul 2>&1
schtasks /End /TN "Sistema de Despesas" >nul 2>&1
schtasks /Delete /TN "Sistema de Despesas" /F >nul 2>&1
echo Inicio automatico removido. (Se o servidor ainda estiver rodando, use PARAR_SERVIDOR.bat.)
pause
