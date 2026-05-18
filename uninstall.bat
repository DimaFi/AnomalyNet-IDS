@echo off
title AnomalyNet IDS — Uninstaller

echo.
echo  ============================================================
echo   AnomalyNet IDS ^| Uninstaller
echo  ============================================================
echo.

:: Remove from startup
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "AnomalyNet IDS" /f >nul 2>&1
echo  [1/3] Removed from startup.

:: Remove desktop shortcut
for /f "tokens=3*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop 2^>nul') do set "DESKTOP_DIR=%%a %%b"
if not defined DESKTOP_DIR set "DESKTOP_DIR=%USERPROFILE%\Desktop"
if exist "%DESKTOP_DIR%\AnomalyNet IDS.lnk" (
    del "%DESKTOP_DIR%\AnomalyNet IDS.lnk"
    echo  [2/3] Removed desktop shortcut.
) else (
    echo  [2/3] Desktop shortcut not found (already removed).
)

:: Stop running server
echo  [3/3] Stopping AnomalyNet server (if running)...
taskkill /f /im python.exe /fi "WINDOWTITLE eq anomalynet*" >nul 2>&1
curl -s -X POST http://localhost:8000/api/update/stop >nul 2>&1

echo.
echo  The application folder was NOT deleted.
echo  To fully remove, delete this folder manually.
echo.
pause
