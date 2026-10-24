@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR.bat primeiro.
  if /i not "%~1"=="nopause" pause
  exit /b 1
)
set "PORTA="
for /f %%p in ('.venv\Scripts\python.exe run.py porta') do set "PORTA=%%p"
if not defined PORTA (
  echo Nao foi possivel ler a porta do config.ini.
  if /i not "%~1"=="nopause" pause
  exit /b 1
)
net session >nul 2>&1
if errorlevel 1 (
  echo ATENCAO: para liberar a porta %PORTA% no Firewall do Windows, clique com o botao direito em
  echo LIBERAR_FIREWALL.bat e escolha "Executar como administrador".
  if /i not "%~1"=="nopause" pause
  exit /b 1
)
netsh advfirewall firewall delete rule name="Sistema de Despesas" >nul 2>&1
netsh advfirewall firewall add rule name="Sistema de Despesas" dir=in action=allow protocol=TCP localport=%PORTA% profile=private,domain
if errorlevel 1 (
  echo Falha ao criar a regra de firewall.
) else (
  echo Firewall: porta %PORTA% liberada para redes Privadas e de Dominio.
  echo Se a rede estiver classificada como "Publica" no Windows, mude para "Privada".
)
if /i not "%~1"=="nopause" pause
exit /b 0
