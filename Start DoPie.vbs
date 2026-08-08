Option Explicit
Dim shell, files, root, powershell, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
powershell = shell.ExpandEnvironmentStrings("%ProgramFiles%") & "\PowerShell\7\pwsh.exe"
If Not files.FileExists(powershell) Then
    powershell = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
End If
command = Chr(34) & powershell & Chr(34) & " -NoProfile -File " & Chr(34) & files.BuildPath(root, "Start DoPie.ps1") & Chr(34)
shell.Run command, 1, False
