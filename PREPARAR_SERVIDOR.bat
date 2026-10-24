@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title Preparar Servidor - Sistema de Despesas

REM ============================================================
REM  PREPARAR_SERVIDOR.bat
REM  Faz TUDO de uma vez: instala dependencias, cria admin,
REM  libera firewall e configura inicio automatico.
REM  Execute como Administrador.
REM ============================================================

echo.
echo ============================================================
echo  PREPARAR SERVIDOR - Sistema de Despesas
echo ============================================================
echo.

REM --- Verifica se esta rodando como administrador ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Este script precisa ser executado como Administrador.
    echo Clique com o botao direito e escolha "Executar como administrador".
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0"

REM === ETAPA 1: Encontrar Python ===
echo [1/5] Procurando Python...
set PYTHON=
where py >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%i in ('py -3 -c "import sys; print(sys.executable)"') do set PYTHON=%%i
)
if not defined PYTHON (
    where python >nul 2>&1
    if %errorlevel%==0 (
        for /f "tokens=*" %%i in ('python -c "import sys; print(sys.executable)"') do set PYTHON=%%i
    )
)
if not defined PYTHON (
    echo ERRO: Python nao encontrado. Instale o Python 3.9 ou mais novo.
    echo Baixe em https://www.python.org/downloads/
    echo Marque "Add python.exe to PATH" durante a instalacao.
    pause
    exit /b 1
)
echo       Python encontrado: !PYTHON!

REM Verificar versao minima (3.9)
for /f "tokens=*" %%v in ('"!PYTHON!" -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")"') do set PYVER=%%v
echo       Versao: !PYVER!

REM === ETAPA 2: Criar venv e instalar dependencias ===
echo.
echo [2/5] Criando ambiente virtual e instalando dependencias...
if not exist .venv (
    "!PYTHON!" -m venv .venv
    if %errorlevel% neq 0 (
        echo ERRO: Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat

REM Instalar dependencias (tenta offline primeiro se houver pasta pacotes)
if exist pacotes (
    echo       Instalando a partir da pasta pacotes (offline)...
    pip install --no-index --find-links=pacotes -r requirements.txt -q
) else (
    echo       Instalando da internet...
    pip install -r requirements.txt -q
)
if %errorlevel% neq 0 (
    echo ERRO: Falha ao instalar as dependencias.
    pause
    exit /b 1
)
echo       Dependencias instaladas.

REM === ETAPA 3: Verificar banco e criar admin ===
echo.
echo [3/5] Verificando banco de dados...
python run.py verificar
if %errorlevel% neq 0 (
    echo       Criando banco de dados...
)

REM Verificar se ja existe admin
python -c "from despesas.config import carregar; from despesas import db; cfg=carregar(); db.iniciar(cfg.db_path); c=db.conectar(cfg.db_path); n=c.execute('SELECT COUNT(*) FROM usuarios WHERE perfil=\"admin\" AND ativo=1').fetchone()[0]; c.close(); exit(0 if n>0 else 1)" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo       Nenhum administrador encontrado. Vamos criar um:
    echo.
    python run.py criar-admin
    if %errorlevel% neq 0 (
        echo ERRO: Falha ao criar o administrador.
        pause
        exit /b 1
    )
) else (
    echo       Administrador ja cadastrado.
)

REM === ETAPA 4: Liberar firewall ===
echo.
echo [4/5] Liberando porta no firewall...
for /f "tokens=*" %%p in ('python run.py porta') do set PORTA=%%p
netsh advfirewall firewall show rule name="Sistema de Despesas" >nul 2>&1
if %errorlevel%==0 (
    netsh advfirewall firewall delete rule name="Sistema de Despesas" >nul 2>&1
)
netsh advfirewall firewall add rule name="Sistema de Despesas" dir=in action=allow protocol=TCP localport=!PORTA! profile=private,domain >nul
if %errorlevel%==0 (
    echo       Porta !PORTA! liberada no firewall (perfis privado e dominio).
) else (
    echo       AVISO: Nao foi possivel liberar a porta. Verifique manualmente.
)

REM === ETAPA 5: Inicio automatico ===
echo.
echo [5/5] Configurando inicio automatico com o Windows...
set VBSPATH=%~dp0INICIAR_SILENCIOSO.vbs
schtasks /query /tn "SistemaDespesas" >nul 2>&1
if %errorlevel%==0 (
    schtasks /delete /tn "SistemaDespesas" /f >nul 2>&1
)
schtasks /create /tn "SistemaDespesas" /tr "wscript.exe \"!VBSPATH!\"" /sc onstart /ru SYSTEM /rl HIGHEST /f >nul 2>&1
if %errorlevel%==0 (
    echo       Tarefa agendada criada: o servidor inicia com o Windows.
) else (
    echo       AVISO: Nao foi possivel criar a tarefa agendada.
    echo       O servidor pode ser iniciado manualmente com INICIAR.bat
    echo       ou INICIAR_SILENCIOSO.vbs
)

echo.
echo ============================================================
echo  PREPARACAO CONCLUIDA
echo ============================================================
echo.
echo  O servidor pode ser iniciado de tres formas:
echo.
echo    INICIAR.bat              - com janela visivel (para ver mensagens)
echo    INICIAR_SILENCIOSO.vbs   - sem janela (saida em logs\console.txt)
echo    Reiniciar o Windows      - inicia automaticamente
echo.
echo  Para parar o servidor:     PARAR_SERVIDOR.bat
echo  Acesso neste computador:   http://localhost:!PORTA!
echo.
for /f "tokens=*" %%i in ('python -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect((chr(49)+chr(48)+'.255.255.255',1)); print(s.getsockname()[0]); s.close()" 2^>nul') do set IP=%%i
if defined IP (
    echo  Outros computadores:      http://!IP!:!PORTA!
)
echo.
echo  Deseja iniciar o servidor agora?
echo.
set /p INICIAR="  Iniciar agora? (S/N): "
if /i "!INICIAR!"=="S" (
    echo.
    echo  Iniciando...
    start "" wscript.exe "!VBSPATH!"
    echo  Servidor iniciado em segundo plano.
    echo  Aguarde alguns segundos e acesse pelo navegador.
)
echo.
pause
