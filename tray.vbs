' AnomalyNet Control — Silent tray launcher (Windows)
' Runs tray.bat without showing a console window.
' Double-click this file (or autostart points here) to start the tray app.
Option Explicit

Dim fso, shell, scriptDir, trayBat
Set fso       = CreateObject("Scripting.FileSystemObject")
Set shell     = CreateObject("WScript.Shell")
scriptDir     = fso.GetParentFolderName(WScript.ScriptFullName)
trayBat       = scriptDir & "\tray.bat"

If Not fso.FileExists(trayBat) Then
    MsgBox "tray.bat not found in: " & vbNewLine & scriptDir, 16, "AnomalyNet Control"
    WScript.Quit
End If

' Run the batch hidden (window style 0 = no window)
shell.Run "cmd /c """ & trayBat & """", 0, False
