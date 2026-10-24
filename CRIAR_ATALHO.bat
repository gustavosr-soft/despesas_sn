@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Criar Atalho na Area de Trabalho - Sistema de Despesas
echo ============================================================
echo.

REM Detecta IP e porta do config.ini
set "PORTA=8080"
set "IP="
if exist config.ini (
    for /f "tokens=1,2 delims==" %%a in (config.ini) do (
        set "chave=%%a"
        set "valor=%%b"
        set "chave=!chave: =!"
        set "valor=!valor: =!"
        if "!chave!"=="porta" set "PORTA=!valor!"
    )
)

REM Detecta IP da rede local
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /C:"IPv4" ^| findstr /V "127.0.0"') do (
    set "IP=%%i"
    set "IP=!IP: =!"
    goto :ip_ok
)
:ip_ok
if "%IP%"=="" set "IP=localhost"

set "URL=http://%IP%:%PORTA%"
set "ICONE=%~dp0despesas.ico"
set "PASTA_SISTEMA=%~dp0"

REM Detecta pasta da area de trabalho
set "DESKTOP="
for /f "usebackq tokens=2,*" %%a in (`reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop 2^>nul`) do set "DESKTOP=%%b"
if "%DESKTOP%"=="" set "DESKTOP=%USERPROFILE%\Desktop"

set "ATALHO=%DESKTOP%\Sistema de Despesas.lnk"

echo Endereco: %URL%
echo Icone:    %ICONE%
echo Atalho:   %ATALHO%
echo.

REM Cria o atalho usando PowerShell
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%ATALHO%'); ^
   $s.TargetPath = '%URL%'; ^
   $s.IconLocation = '%ICONE%'; ^
   $s.Description = 'Acessar o Sistema de Despesas pela rede local'; ^
   $s.Save(); ^
   Write-Host 'Atalho criado com sucesso!'"

if errorlevel 1 (
    echo.
    echo Falha ao criar o atalho. Tente executar como administrador.
    pause
    exit /b 1
)

echo.
echo Pronto! O atalho "Sistema de Despesas" foi criado na area de trabalho.
echo Clique duas vezes nele para abrir o sistema no navegador.
echo.
pause
