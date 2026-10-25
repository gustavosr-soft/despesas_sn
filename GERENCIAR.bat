@echo off
cd /d "%~dp0"
rem Abre o gerenciador (janela). Rode NO COMPUTADOR SERVIDOR.
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "gerenciador.pyw"
  exit /b
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "gerenciador.pyw"
  exit /b
)
where py >nul 2>nul
if %errorlevel%==0 (
  start "" py -w "gerenciador.pyw"
  exit /b
)
echo Python nao encontrado. Instale o Python 3.10+ (marque "Add to PATH").
pause
