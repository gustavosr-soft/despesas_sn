@echo off
rem Abre o gerenciador. Funciona no servidor (C:\despesas\sistema) e pela rede (\\servidor\C\despesas\sistema).
rem Precisa de Python com tkinter no computador onde for aberto (o normal do instalador python.org).
rem Nao usa cd/pushd: cmd nao entra em pasta de rede; o Python abre o script direto pelo caminho.
set "GER=%~dp0gerenciador.pyw"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" /d "%TEMP%" pythonw "%GER%"
  exit /b
)
where py >nul 2>nul
if %errorlevel%==0 (
  start "" /d "%TEMP%" py -w "%GER%"
  exit /b
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" /d "%TEMP%" "%~dp0.venv\Scripts\pythonw.exe" "%GER%"
  exit /b
)
echo Python nao encontrado neste computador. Instale o Python 3.10+ (marque "Add to PATH").
pause
