Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\launch.bat"
If Not fso.FileExists(batPath) Then
    batPath = scriptDir & "\..\..\launch.bat"
End If
' Run launch.bat silently in background (0 = hidden window, False = don't wait for exit)
WshShell.Run "cmd /c """ & batPath & """", 0, False

