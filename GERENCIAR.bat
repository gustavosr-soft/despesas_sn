@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Sistema de Despesas - Gerenciador

:: GERENCIAR.bat - Script unico de administracao
:: Sistema de Despesas - Nascimento

:menu
cls
echo ========================================================
echo        SISTEMA DE DESPESAS - GERENCIADOR
echo ========================================================
echo.
echo    1.  Instalar / Atualizar dependencias
echo    2.  Iniciar servidor (visivel)
echo    3.  Iniciar servidor (oculto)
echo    4.  Parar servidor
echo    5.  Reiniciar servidor
echo    6.  Liberar firewall
echo    7.  Instalar inicio automatico
echo    8.  Remover inicio automatico
echo    9.  Criar usuario administrador
echo   10.  Fazer backup agora
echo   11.  Restaurar backup
echo   12.  Verificar sistema
echo   13.  Criar atalho na area de trabalho
echo   14.  Preparar servidor completo (1a vez)
echo.
echo    0.  Sair
echo.
echo ========================================================
echo.
set "op="
set /p op=Escolha uma opcao:
if "%op%"=="1"  goto instalar
if "%op%"=="2"  goto iniciar_visivel
if "%op%"=="3"  goto iniciar_oculto
if "%op%"=="4"  goto parar
if "%op%"=="5"  goto reiniciar
if "%op%"=="6"  goto firewall
if "%op%"=="7"  goto auto_instalar
if "%op%"=="8"  goto auto_remover
if "%op%"=="9"  goto criar_admin
if "%op%"=="10" goto backup
if "%op%"=="11" goto restaurar
if "%op%"=="12" goto verificar
if "%op%"=="13" goto atalho
if "%op%"=="14" goto preparar
if "%op%"=="0"  exit /b 0
echo Opcao invalida.
timeout /t 2 >nul
goto menu

:: ========================================================
::  1. INSTALAR / ATUALIZAR DEPENDENCIAS
:: ========================================================
:instalar
cls
echo -- Instalar / Atualizar dependencias --
echo.

:: Procura Python
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY (
    where python3 >nul 2>&1 && set "PY=python3"
)
if not defined PY (
    for %%p in (
        "%LOCALAPPDATA%\Programs\Python\Python3*\python.exe"
        "C:\Python3*\python.exe"
    ) do if exist %%p ( set "PY=%%~p" & goto :py_ok1 )
)
:py_ok1
if not defined PY (
    echo [ERRO] Python 3 nao encontrado.
    echo Baixe em https://www.python.org/downloads/
    echo Marque "Add Python to PATH" na instalacao.
    goto voltar
)
echo Python encontrado: %PY%

:: Cria/atualiza venv
if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar ambiente virtual.
        goto voltar
    )
)
echo Instalando/atualizando dependencias...
".venv\Scripts\pip.exe" install --upgrade pip >nul 2>&1
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    goto voltar
)

:: Verifica banco
echo Verificando banco de dados...
".venv\Scripts\python.exe" run.py verificar
echo.
echo [OK] Instalacao concluida com sucesso.
goto voltar

:: ========================================================
::  2. INICIAR SERVIDOR (VISIVEL)
:: ========================================================
:iniciar_visivel
cls
echo -- Iniciar servidor (visivel) --
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)
echo Iniciando... Feche esta janela para parar o servidor.
echo.
".venv\Scripts\python.exe" run.py
goto voltar

:: ========================================================
::  3. INICIAR SERVIDOR (OCULTO)
:: ========================================================
:iniciar_oculto
cls
echo -- Iniciar servidor (oculto) --
echo.
if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)
echo Iniciando servidor em segundo plano...
start "" /B ".venv\Scripts\pythonw.exe" run.py servir
echo [OK] Servidor iniciado em segundo plano.
echo Para parar, use a opcao 4.
goto voltar

:: ========================================================
::  4. PARAR SERVIDOR
:: ========================================================
:parar
cls
echo -- Parar servidor --
echo.
echo Encerrando tarefa agendada (se houver)...
schtasks /End /TN "SistemaDespesas" >nul 2>&1
schtasks /End /TN "DespesasNascimento" >nul 2>&1

echo Encerrando processo do servidor...
set "ALVO=%~dp0.venv\Scripts\python.exe"
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('%ALVO%') -and $_.CommandLine.Contains('run.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('Processo ' + $_.ProcessId + ' encerrado.') }"

:: Tambem encerra pythonw.exe
set "ALVOW=%~dp0.venv\Scripts\pythonw.exe"
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('%ALVOW%') -and $_.CommandLine.Contains('run.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('Processo ' + $_.ProcessId + ' encerrado.') }"

echo.
echo [OK] Servidor parado.
goto voltar

:: ========================================================
::  5. REINICIAR SERVIDOR
:: ========================================================
:reiniciar
cls
echo -- Reiniciar servidor --
echo.
echo Parando servidor...
call :parar_silencioso
echo Aguardando 2 segundos...
timeout /t 2 >nul
echo Iniciando servidor em segundo plano...
if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)
start "" /B ".venv\Scripts\pythonw.exe" run.py servir
echo.
echo [OK] Servidor reiniciado com sucesso.
goto voltar

:: ========================================================
::  6. LIBERAR FIREWALL
:: ========================================================
:firewall
cls
echo -- Liberar firewall --
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)

:: Le a porta
for /f %%p in ('".venv\Scripts\python.exe" run.py porta 2^>nul') do set "PORTA=%%p"
if not defined PORTA set "PORTA=8080"

echo Criando regra de firewall para porta %PORTA%...
netsh advfirewall firewall delete rule name="SistemaDespesas" >nul 2>&1
netsh advfirewall firewall add rule name="SistemaDespesas" dir=in action=allow protocol=TCP localport=%PORTA%
if errorlevel 1 (
    echo [ERRO] Falha ao criar regra. Execute como Administrador.
) else (
    echo [OK] Firewall liberado na porta %PORTA%.
)
goto voltar

:: ========================================================
::  7. INSTALAR INICIO AUTOMATICO
:: ========================================================
:auto_instalar
cls
echo -- Instalar inicio automatico --
echo.
if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)
set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
set "RUNPY=%~dp0run.py"
echo Criando tarefa agendada "SistemaDespesas"...
schtasks /Create /TN "SistemaDespesas" /SC ONSTART /RU SYSTEM /RL HIGHEST /F /TR "\"%PYTHONW%\" \"%RUNPY%\" servir"
if errorlevel 1 (
    echo [ERRO] Falha ao criar tarefa. Execute como Administrador.
) else (
    echo [OK] Servidor sera iniciado automaticamente ao ligar o computador.
)
goto voltar

:: ========================================================
::  8. REMOVER INICIO AUTOMATICO
:: ========================================================
:auto_remover
cls
echo -- Remover inicio automatico --
echo.
echo Removendo tarefas agendadas...
schtasks /Delete /TN "SistemaDespesas" /F >nul 2>&1
schtasks /Delete /TN "DespesasNascimento" /F >nul 2>&1
echo [OK] Inicio automatico removido.
goto voltar

:: ========================================================
::  9. CRIAR USUARIO ADMINISTRADOR
:: ========================================================
:criar_admin
cls
echo -- Criar usuario administrador --
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)
".venv\Scripts\python.exe" run.py criar-admin
goto voltar

:: ========================================================
::  10. FAZER BACKUP
:: ========================================================
:backup
cls
echo -- Fazer backup agora --
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)
".venv\Scripts\python.exe" run.py backup
goto voltar

:: ========================================================
::  11. RESTAURAR BACKUP
:: ========================================================
:restaurar
cls
echo -- Restaurar backup --
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)
echo ATENCAO: restaurar SUBSTITUI os dados atuais pelos do backup escolhido.
echo O servidor precisa estar PARADO (use a opcao 4 antes).
echo Os dados atuais sao guardados em dados\antes_restauracao_...
echo.
echo Backups disponiveis (pasta backups):
dir /b /o-n backups\despesas_*.db 2>nul
echo.
set "ARQ="
set /p ARQ=Digite o nome do arquivo de backup (ex.: despesas_20261024_220000.db):
if not defined ARQ goto voltar
set "OK="
set /p OK=Confirma restaurar "%ARQ%"? Digite SIM para continuar:
if /i not "%OK%"=="SIM" (
    echo Cancelado.
    goto voltar
)
".venv\Scripts\python.exe" run.py restaurar "%ARQ%"
goto voltar

:: ========================================================
::  12. VERIFICAR SISTEMA
:: ========================================================
:verificar
cls
echo -- Verificar sistema --
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Execute a opcao 1 (Instalar) primeiro.
    goto voltar
)
".venv\Scripts\python.exe" run.py verificar
goto voltar

:: ========================================================
::  13. CRIAR ATALHO NA AREA DE TRABALHO
:: ========================================================
:atalho
cls
echo -- Criar atalho na area de trabalho --
echo.

:: Le porta do config.ini
set "PORTA=8080"
if exist config.ini (
    for /f "tokens=1,2 delims==" %%a in (config.ini) do (
        set "chave=%%a"
        set "valor=%%b"
        set "chave=!chave: =!"
        set "valor=!valor: =!"
        if "!chave!"=="porta" set "PORTA=!valor!"
    )
)

:: Detecta IP da rede local
set "IP="
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /C:"IPv4" ^| findstr /V "127.0.0"') do (
    set "IP=%%i"
    set "IP=!IP: =!"
    goto :ip_ok
)
:ip_ok
if "%IP%"=="" set "IP=localhost"
set "URL=http://%IP%:%PORTA%"
set "ICONE=%~dp0despesas.ico"

:: Detecta pasta da area de trabalho
set "DESKTOP="
for /f "usebackq tokens=2,*" %%a in (`reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop 2^>nul`) do set "DESKTOP=%%b"
if "%DESKTOP%"=="" set "DESKTOP=%USERPROFILE%\Desktop"

set "ATALHO=%DESKTOP%\Sistema de Despesas.lnk"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%ATALHO%'); ^
   $s.TargetPath = '%URL%'; ^
   $s.IconLocation = '%ICONE%'; ^
   $s.Description = 'Acessar o Sistema de Despesas pela rede local'; ^
   $s.Save(); ^
   Write-Host '[OK] Atalho criado: %ATALHO%'"
goto voltar

:: ========================================================
::  14. PREPARAR SERVIDOR COMPLETO (1a VEZ)
:: ========================================================
:preparar
cls
echo ========================================================
echo        PREPARACAO COMPLETA DO SERVIDOR
echo        (execute como Administrador)
echo ========================================================
echo.
echo   Este assistente executara:
echo    Passo 1: Instalar dependencias
echo    Passo 2: Criar usuario administrador
echo    Passo 3: Liberar firewall
echo    Passo 4: Instalar inicio automatico
echo    Passo 5: Iniciar o servidor
echo.
set "CONT="
set /p CONT=Deseja continuar? (S/N):
if /i not "%CONT%"=="S" goto menu

echo.
echo ========================================================
echo  PASSO 1/5 - Instalando dependencias...
echo ========================================================

:: Procura Python
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY (
    where python3 >nul 2>&1 && set "PY=python3"
)
if not defined PY (
    for %%p in (
        "%LOCALAPPDATA%\Programs\Python\Python3*\python.exe"
        "C:\Python3*\python.exe"
    ) do if exist %%p ( set "PY=%%~p" & goto :py_ok2 )
)
:py_ok2
if not defined PY (
    echo [ERRO] Python 3 nao encontrado.
    echo Baixe em https://www.python.org/downloads/
    goto voltar
)
echo Python: %PY%

if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar ambiente virtual.
        goto voltar
    )
)
".venv\Scripts\pip.exe" install --upgrade pip >nul 2>&1
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    goto voltar
)
".venv\Scripts\python.exe" run.py verificar
echo [OK] Passo 1 concluido.
echo.

echo ========================================================
echo  PASSO 2/5 - Criar usuario administrador
echo ========================================================
".venv\Scripts\python.exe" run.py criar-admin
echo [OK] Passo 2 concluido.
echo.

echo ========================================================
echo  PASSO 3/5 - Liberar firewall
echo ========================================================
for /f %%p in ('".venv\Scripts\python.exe" run.py porta 2^>nul') do set "PORTA=%%p"
if not defined PORTA set "PORTA=8080"
netsh advfirewall firewall delete rule name="SistemaDespesas" >nul 2>&1
netsh advfirewall firewall add rule name="SistemaDespesas" dir=in action=allow protocol=TCP localport=%PORTA%
if errorlevel 1 (
    echo [AVISO] Nao foi possivel liberar firewall. Execute como Administrador.
) else (
    echo [OK] Passo 3 concluido - porta %PORTA% liberada.
)
echo.

echo ========================================================
echo  PASSO 4/5 - Instalar inicio automatico
echo ========================================================
set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
set "RUNPY=%~dp0run.py"
schtasks /Create /TN "SistemaDespesas" /SC ONSTART /RU SYSTEM /RL HIGHEST /F /TR "\"%PYTHONW%\" \"%RUNPY%\" servir"
if errorlevel 1 (
    echo [AVISO] Nao foi possivel criar tarefa. Execute como Administrador.
) else (
    echo [OK] Passo 4 concluido.
)
echo.

echo ========================================================
echo  PASSO 5/5 - Iniciando servidor
echo ========================================================
start "" /B ".venv\Scripts\pythonw.exe" run.py servir
echo [OK] Servidor iniciado em segundo plano.
echo.

:: Mostra IP para acesso
set "IP="
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /C:"IPv4" ^| findstr /V "127.0.0"') do (
    set "IP=%%i"
    set "IP=!IP: =!"
    goto :ip_ok3
)
:ip_ok3
if "%IP%"=="" set "IP=localhost"
echo ========================================================
echo  PREPARACAO CONCLUIDA!
echo.
echo  Acesse o sistema em: http://%IP%:%PORTA%
echo ========================================================
goto voltar

:: ========================================================
::  Sub-rotina: parar servidor silenciosamente
:: ========================================================
:parar_silencioso
schtasks /End /TN "SistemaDespesas" >nul 2>&1
schtasks /End /TN "DespesasNascimento" >nul 2>&1
set "ALVO=%~dp0.venv\Scripts\python.exe"
set "ALVOW=%~dp0.venv\Scripts\pythonw.exe"
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine.Contains('%ALVO%') -or $_.CommandLine.Contains('%ALVOW%')) -and $_.CommandLine.Contains('run.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
goto :eof

:: ========================================================
::  Voltar ao menu
:: ========================================================
:voltar
echo.
echo --------------------------------------------------------
pause
goto menu
