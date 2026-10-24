@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  echo Clique com o botao direito neste arquivo e escolha "Executar como administrador".
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR.bat primeiro.
  pause
  exit /b 1
)
REM Usa o VBS para iniciar sem janela de console
schtasks /Create /TN "SistemaDespesas" /SC ONSTART /RU SYSTEM /RL HIGHEST /F /TR "wscript.exe \"%~dp0INICIAR_SILENCIOSO.vbs\""
if errorlevel 1 (
  echo Falha ao criar a tarefa agendada.
  pause
  exit /b 1
)
schtasks /Run /TN "SistemaDespesas"
echo.
echo Pronto: o sistema vai iniciar sozinho sempre que o Windows ligar (mesmo sem ninguem logado).
echo Ele foi iniciado agora em segundo plano (sem janela).
echo Aguarde cerca de 10 segundos e acesse http://localhost:8080
echo (se mudou a porta no config.ini, use a nova).
echo Registro de funcionamento: pasta logs\console.txt e logs\despesas.log
echo.
echo ATENCAO: a tarefa roda como usuario SYSTEM; se o backup for para uma pasta de rede, ela precisa
echo aceitar acesso do computador. Prefira um segundo disco ou pasta local no servidor.
pause
