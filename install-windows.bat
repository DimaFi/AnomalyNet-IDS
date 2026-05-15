@echo off
setlocal

title AnomalyNet IDS - Windows Installer

:: ── Require admin rights (UAC prompt) ───────────────────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrator rights...
    powershell -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

:: ── Check installer script exists ───────────────────────────
if not exist "%~dp0scripts\install-windows.ps1" (
    echo ERROR: scripts\install-windows.ps1 not found.
    echo Make sure you extracted the full AnomalyNet archive.
    echo.
    pause
    exit /b 1
)

:: ── Run PowerShell installer ─────────────────────────────────
cd /d "%~dp0"
echo Starting AnomalyNet installer (PowerShell loading, please wait...)
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "scripts\install-windows.ps1" %*

echo.
pause
