@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR.bat primeiro.
  pause
  exit /b 1
)
echo Cria um administrador. Se o usuario ja existir, a SENHA DELE e redefinida (use para recuperar acesso).
".venv\Scripts\python.exe" run.py criar-admin
pause
