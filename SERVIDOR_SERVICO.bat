@echo off
rem Usado pela tarefa agendada (inicio automatico). Reinicia o servidor se ele cair.
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist "logs" mkdir "logs"
:laco
".venv\Scripts\python.exe" run.py >> "logs\console.txt" 2>&1
rem codigo 2 = erro de configuracao ou sem administrador: nao adianta repetir
if errorlevel 2 exit /b %errorlevel%
timeout /t 10 /nobreak >nul
goto laco
