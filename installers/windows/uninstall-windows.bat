@echo off
setlocal

title AnomalyNet IDS - Windows Uninstaller

:: ── Require admin rights (UAC prompt) ───────────────────────
:: Uninstall removes the Task Scheduler task, firewall rules and env vars —
:: all of which need elevation. Pass-through args (e.g. -Purge) are preserved.
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrator rights...
    powershell -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c \"%~f0\" %*' -Verb RunAs"
    exit /b
)

:: ── Check uninstaller script exists ──────────────────────────
if not exist "%~dp0uninstall-windows.ps1" (
    echo ERROR: uninstall-windows.ps1 not found.
    echo Make sure you are running this from the installers\windows folder.
    echo.
    pause
    exit /b 1
)

:: ── Run PowerShell uninstaller ───────────────────────────────
cd /d "%~dp0"
echo Starting AnomalyNet uninstaller (PowerShell loading, please wait...)
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "uninstall-windows.ps1" %*

echo.
echo  Tip: to also delete the install folder, run with -Purge:
echo       uninstall-windows.bat -Purge
echo.
pause
