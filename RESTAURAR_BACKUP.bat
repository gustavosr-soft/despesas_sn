@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR.bat primeiro.
  pause
  exit /b 1
)
echo ATENCAO: restaurar SUBSTITUI os dados atuais pelos do backup escolhido.
echo O servidor precisa estar PARADO (use PARAR_SERVIDOR.bat). Os dados atuais sao guardados em dados\antes_restauracao_...
echo.
echo Backups disponiveis (pasta backups):
dir /b /o-n backups\despesas_*.db 2>nul
echo.
set "ARQ="
set /p ARQ=Digite o nome do arquivo de backup (ex.: despesas_20261024_220000.db):
if not defined ARQ exit /b 1
set "OK="
set /p OK=Confirma restaurar "%ARQ%"? Digite SIM para continuar: 
if /i not "%OK%"=="SIM" (
  echo Cancelado.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py restaurar "%ARQ%"
pause
