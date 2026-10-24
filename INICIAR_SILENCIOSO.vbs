' ============================================================
'  INICIAR_SILENCIOSO.vbs
'  Inicia o servidor de despesas sem abrir janela de console.
'  A saida vai para logs\console.txt
'  Para parar: PARAR_SERVIDOR.bat  (ou feche "python" no Gerenciador de Tarefas)
' ============================================================
Set objShell = CreateObject("WScript.Shell")
Set objFSO   = CreateObject("Scripting.FileSystemObject")

strPasta = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Garante que a pasta de logs exista
strLogs = strPasta & "\logs"
If Not objFSO.FolderExists(strLogs) Then objFSO.CreateFolder(strLogs)

' Monta o comando: usa o python do venv se existir, senao tenta py / python
strVenvPython = strPasta & "\.venv\Scripts\python.exe"
If objFSO.FileExists(strVenvPython) Then
    strPython = """" & strVenvPython & """"
Else
    strPython = "python"
End If

strCmd = "cmd /c " & strPython & " """ & strPasta & "\run.py"" servir >> """ & strLogs & "\console.txt"" 2>&1"

' 0 = janela oculta, False = nao espera terminar
objShell.Run strCmd, 0, False
