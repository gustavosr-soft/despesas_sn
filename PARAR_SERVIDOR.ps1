# Encerra apenas o servidor DESTA pasta (nao mexe em outros programas Python).
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$alvo = Join-Path $dir '.venv\Scripts\python.exe'
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -and $_.CommandLine.Contains($alvo) -and $_.CommandLine.Contains('run.py') } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
