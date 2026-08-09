Option Explicit
Dim shell, files, root, powershell, script, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
powershell = shell.ExpandEnvironmentStrings("%ProgramFiles%") & "\PowerShell\7\pwsh.exe"
If Not files.FileExists(powershell) Then
    powershell = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
End If
script = files.BuildPath(files.BuildPath(root, "bootstrap"), "Start DoPie.ps1")
command = Chr(34) & powershell & Chr(34) & " -NoLogo -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & script & Chr(34)
shell.Run command, 0, False
