Set WshShell = CreateObject("WScript.Shell")
' Run launch.bat silently in background (0 = hidden window, False = don't wait for exit)
WshShell.Run "cmd /c launch.bat", 0, False
