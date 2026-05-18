@echo off
setlocal enabledelayedexpansion
title AnomalyNet IDS — Installer

echo.
echo  ============================================================
echo   AnomalyNet IDS ^| Windows Installer
echo  ============================================================
echo.

set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

set "VENV_DIR=%APP_DIR%\backend\.venv"
set "LAUNCHER_VBS=%APP_DIR%\launch.vbs"
set "LAUNCHER_BAT=%APP_DIR%\launch.bat"
set "ICON_PATH=%APP_DIR%\frontend\public\AnomalyNet.ico"

:: ── Check Python ──────────────────────────────────────────────
echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python not found.
    echo  Download Python 3.10+ from https://python.org and re-run this installer.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo         Python %PY_VER% found.

:: ── Create virtual environment ────────────────────────────────
echo [2/6] Setting up virtual environment...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)
echo         OK

:: ── Install dependencies ──────────────────────────────────────
echo [3/6] Installing dependencies (may take a minute)...
"%VENV_DIR%\Scripts\pip.exe" install -r "%APP_DIR%\backend\requirements.txt" --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [WARNING] Some packages may have failed. Check backend\requirements.txt.
)
echo         OK

:: ── Create desktop shortcut ───────────────────────────────────
echo [4/6] Creating desktop shortcut...

:: Get real Desktop path from registry
for /f "tokens=3*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop 2^>nul') do set "DESKTOP_DIR=%%a %%b"
if not defined DESKTOP_DIR set "DESKTOP_DIR=%USERPROFILE%\Desktop"

:: Use PowerShell to create .lnk with icon — write script to temp file to avoid encoding issues
set "PS_SCRIPT=%TEMP%\anomalynet_shortcut.ps1"
(
    echo $ws = New-Object -ComObject WScript.Shell
    echo $sc = $ws.CreateShortcut('%DESKTOP_DIR%\AnomalyNet IDS.lnk'^)
    echo $sc.TargetPath = 'wscript.exe'
    echo $sc.Arguments = '"%LAUNCHER_VBS%"'
    echo $sc.WorkingDirectory = '%APP_DIR%'
    echo $sc.Description = 'AnomalyNet IDS — Network Intrusion Detection System'
    echo $sc.IconLocation = '%ICON_PATH%,0'
    echo $sc.Save(^)
) > "%PS_SCRIPT%"

powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%PS_SCRIPT%" >nul 2>&1
del "%PS_SCRIPT%" >nul 2>&1
echo         Shortcut created on Desktop.

:: ── Add to Windows startup (HKCU — no admin needed) ──────────
echo [5/6] Adding to Windows startup...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" ^
    /v "AnomalyNet IDS" ^
    /t REG_SZ ^
    /d "wscript.exe \"%LAUNCHER_VBS%\"" ^
    /f >nul 2>&1
echo         Added to startup (HKCU, no admin required).

:: ── Launch the app ────────────────────────────────────────────
echo [6/6] Starting AnomalyNet IDS...
start "" wscript.exe "%LAUNCHER_VBS%"

echo.
echo  ============================================================
echo   Installation complete!
echo.
echo   Desktop shortcut:  AnomalyNet IDS.lnk
echo   Autostart:         Enabled (runs at Windows login)
echo   To uninstall:      run uninstall.bat
echo  ============================================================
echo.
pause
