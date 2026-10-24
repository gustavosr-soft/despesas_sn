@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title Instalacao - Sistema de Despesas
echo ============================================================
echo  Sistema de Despesas - INSTALACAO (executar uma vez no servidor)
echo ============================================================
echo.

rem --- 1) procurar o Python 3
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY goto :sem_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 goto :sem_python

rem --- 2) ambiente virtual (pasta .venv)
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente Python...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo ERRO ao criar o ambiente Python.
    pause
    exit /b 1
  )
)

rem --- 3) bibliotecas (precisa de internet, ou da pasta "pacotes" para instalar sem internet)
echo Instalando bibliotecas...
if exist "pacotes" (
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links pacotes -r requirements.txt
) else (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if errorlevel 1 (
  echo.
  echo ERRO ao instalar as bibliotecas. Confira a internet do servidor e rode de novo.
  pause
  exit /b 1
)

rem --- 4) conferir configuracao e criar o banco
".venv\Scripts\python.exe" run.py verificar
if errorlevel 1 (
  echo.
  echo ERRO na configuracao ou no banco. Veja a mensagem acima.
  pause
  exit /b 1
)

rem --- 5) primeiro administrador (so se ainda nao existir nenhum)
echo.
echo Agora crie o usuario ADMINISTRADOR (voce vai definir a senha).
".venv\Scripts\python.exe" run.py criar-admin
if errorlevel 1 (
  echo.
  echo O administrador nao foi criado. Rode CRIAR_ADMIN.bat para tentar de novo.
  pause
  exit /b 1
)

rem --- 6) firewall (so funciona se este script foi aberto "Como administrador")
echo.
call "%~dp0LIBERAR_FIREWALL.bat" nopause

echo.
echo ============================================================
echo  INSTALACAO CONCLUIDA.
echo  - Para iniciar agora:                   INICIAR.bat
echo  - Para iniciar sozinho com o Windows:   INSTALAR_INICIO_AUTOMATICO.bat
echo  Veja o LEIA-ME.txt para o restante.
echo ============================================================
pause
exit /b 0

:sem_python
echo Python 3.9 ou mais novo nao foi encontrado neste computador.
echo.
echo 1. Baixe o instalador em https://www.python.org/downloads/windows/
echo 2. Na primeira tela do instalador MARQUE "Add python.exe to PATH".
echo 3. Depois execute INSTALAR.bat novamente.
echo.
pause
exit /b 1
