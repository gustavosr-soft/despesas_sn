@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
title Sistema de Despesas - SERVIDOR (nao feche esta janela)
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
echo.
echo O servidor foi encerrado (codigo %errorlevel%). Veja a mensagem acima ou a pasta logs.
pause
