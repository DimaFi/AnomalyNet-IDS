' AnomalyNet IDS — Silent Launcher
' Runs launch.bat without showing a console window, then opens the browser.
' Double-click this file (or create a shortcut to it) to start AnomalyNet.
Option Explicit

Dim fso, shell, scriptDir, launchBat
Set fso       = CreateObject("Scripting.FileSystemObject")
Set shell     = CreateObject("WScript.Shell")
scriptDir     = fso.GetParentFolderName(WScript.ScriptFullName)
launchBat     = scriptDir & "\launch.bat"

If Not fso.FileExists(launchBat) Then
    MsgBox "launch.bat not found in: " & vbNewLine & scriptDir, 16, "AnomalyNet IDS"
    WScript.Quit
End If

' Run the batch hidden (window style 0 = no window)
shell.Run "cmd /c """ & launchBat & """", 0, False
