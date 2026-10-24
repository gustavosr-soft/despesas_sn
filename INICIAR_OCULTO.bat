@echo off
cd /d "%~dp0"

REM Verifica se o servidor ja esta rodando
tasklist /FI "WINDOWTITLE eq Sistema de Despesas*" 2>nul | find "python" >nul 2>&1
if %errorlevel%==0 (
    echo O servidor ja esta rodando.
    pause
    exit /b 0
)

if not exist ".venv\Scripts\pythonw.exe" (
    echo Execute INSTALAR.bat primeiro.
    pause
    exit /b 1
)

REM Garante pasta de logs
if not exist logs mkdir logs

REM Inicia com pythonw (sem janela nenhuma)
start "" /b .venv\Scripts\pythonw.exe run.py servir
echo Servidor iniciado em segundo plano.
echo Para verificar: abra http://localhost:8080 no navegador.
echo Para parar: PARAR_SERVIDOR.bat
echo Logs em: logs\despesas.log
timeout /t 5
