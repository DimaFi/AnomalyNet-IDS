@echo off
title AnomalyNet IDS — Uninstaller

echo.
echo  ============================================================
echo   AnomalyNet IDS ^| Uninstaller
echo  ============================================================
echo.

:: Remove from startup (panel + tray app)
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "AnomalyNet IDS" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "AnomalyNet Tray" /f >nul 2>&1
echo  [1/3] Removed panel + tray from startup.

:: Resolve Desktop and Start Menu Programs folders from registry (fallback to defaults)
for /f "tokens=3*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop 2^>nul') do set "DESKTOP_DIR=%%a %%b"
if not defined DESKTOP_DIR set "DESKTOP_DIR=%USERPROFILE%\Desktop"
for /f "tokens=3*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Programs 2^>nul') do set "PROGRAMS_DIR=%%a %%b"
if not defined PROGRAMS_DIR set "PROGRAMS_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

:: Remove shortcuts (desktop + Start Menu, both .lnk and .url — safe if missing)
set "REMOVED=0"
for %%S in (
    "%DESKTOP_DIR%\AnomalyNet IDS.lnk"
    "%DESKTOP_DIR%\AnomalyNet IDS.url"
    "%DESKTOP_DIR%\AnomalyNet.lnk"
    "%PROGRAMS_DIR%\AnomalyNet\AnomalyNet IDS.lnk"
    "%PROGRAMS_DIR%\AnomalyNet\AnomalyNet IDS.url"
) do (
    if exist "%%~S" (
        del "%%~S" >nul 2>&1
        echo  [2/3] Removed shortcut: %%~S
        set "REMOVED=1"
    )
)
:: Remove the Start Menu \AnomalyNet folder only if empty
if exist "%PROGRAMS_DIR%\AnomalyNet" (
    rmdir "%PROGRAMS_DIR%\AnomalyNet" >nul 2>&1
)
if "%REMOVED%"=="0" echo  [2/3] No shortcuts found (already removed).

:: Stop running server + tray app
echo  [3/3] Stopping AnomalyNet server and tray app (if running)...
curl -s -X POST http://localhost:8000/api/update/stop >nul 2>&1
taskkill /f /im python.exe /fi "WINDOWTITLE eq anomalynet*" >nul 2>&1
:: Tray runs under pythonw.exe -m app.tray.main — stop only that process
for /f "tokens=2" %%p in ('wmic process where "name='pythonw.exe' and commandline like '%%app.tray.main%%'" get processid 2^>nul ^| findstr [0-9]') do taskkill /f /pid %%p >nul 2>&1

echo.
echo  The application folder was NOT deleted.
echo  To fully remove, delete this folder manually.
echo.
pause
