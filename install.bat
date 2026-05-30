@echo off
setlocal enabledelayedexpansion
title AnomalyNet IDS — Installer
chcp 65001 >nul 2>&1

echo.
echo  ============================================================
echo   AnomalyNet IDS  ^|  Windows Installer
echo  ============================================================
echo.

set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

set "VENV_DIR=%APP_DIR%\backend\.venv"
set "LAUNCHER_VBS=%APP_DIR%\launch.vbs"
set "LAUNCHER_BAT=%APP_DIR%\launch.bat"
set "ICON_PATH=%APP_DIR%\frontend\public\AnomalyNet.ico"

:: ── Check Python ──────────────────────────────────────────────
echo  [1/5]  Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [!] Python not found.
    echo.
    echo   Download Python 3.10+ from:
    echo     https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: during installation, check
    echo   "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo         Python %PY_VER% OK

:: ── Create virtual environment ────────────────────────────────
echo  [2/5]  Setting up virtual environment...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo   [!] Failed to create virtual environment.
        echo   Try: python -m pip install --upgrade pip
        echo.
        pause
        exit /b 1
    )
)
echo         OK

:: ── Install dependencies ──────────────────────────────────────
echo  [3/5]  Installing dependencies (may take 1-2 min)...
:: Network-resilient: longer timeout + retries (default 15s times out on slow links)
set "PIP_OK="
for /l %%i in (1,1,3) do (
    if not defined PIP_OK (
        "%VENV_DIR%\Scripts\pip.exe" install -r "%APP_DIR%\backend\requirements.txt" --timeout 60 --retries 5 --disable-pip-version-check
        if not errorlevel 1 set "PIP_OK=1"
        if not defined PIP_OK (
            echo   [!] pip download failed ^(attempt %%i/3, slow network?^) - retrying in 10s...
            timeout /t 10 /nobreak >nul 2>&1
        )
    )
)
if not defined PIP_OK (
    echo.
    echo   [!] Could not install dependencies after 3 attempts.
    echo   Usually an unstable connection to pypi.org ^(read timeout^).
    echo   Check your internet and run install.bat again, or install manually:
    echo     "%VENV_DIR%\Scripts\pip.exe" install --timeout 120 --retries 10 -r "%APP_DIR%\backend\requirements.txt"
    echo.
    pause
    exit /b 1
)
echo         OK

:: ── Create desktop shortcut ───────────────────────────────────
echo  [4/5]  Creating desktop shortcut...

:: Get Desktop path from registry
for /f "tokens=3*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop 2^>nul') do set "DESKTOP_DIR=%%a %%b"
if not defined DESKTOP_DIR set "DESKTOP_DIR=%USERPROFILE%\Desktop"

set "PS_TMP=%TEMP%\anomalynet_sc_%RANDOM%.ps1"
(
    echo $lnk = '%DESKTOP_DIR%\AnomalyNet IDS.lnk'
    echo $ws = New-Object -ComObject WScript.Shell
    echo $sc = $ws.CreateShortcut($lnk^)
    echo $sc.TargetPath       = 'wscript.exe'
    echo $sc.Arguments        = '"%LAUNCHER_VBS%"'
    echo $sc.WorkingDirectory = '%APP_DIR%'
    echo $sc.Description      = 'AnomalyNet IDS - Network Intrusion Detection System'
    echo $sc.IconLocation     = '%ICON_PATH%,0'
    echo $sc.Save(^)
    echo # Mark shortcut "Run as administrator" ^(capture/firewall need elevation^)
    echo $b = [System.IO.File]::ReadAllBytes($lnk^)
    echo $b[0x15] = $b[0x15] -bor 0x20
    echo [System.IO.File]::WriteAllBytes($lnk, $b^)
) > "%PS_TMP%"

powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%PS_TMP%" >nul 2>&1
del "%PS_TMP%" >nul 2>&1
echo         Shortcut created on Desktop

:: ── Add to Windows startup (HKCU — no admin needed) ──────────
echo  [4/5]  Adding to Windows startup...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" ^
    /v "AnomalyNet IDS" ^
    /t REG_SZ ^
    /d "wscript.exe \"%LAUNCHER_VBS%\"" ^
    /f >nul 2>&1
echo         Will start automatically at Windows login

:: ── Npcap info (Live mode) ────────────────────────────────────
echo.
echo  [5/5]  Checking Npcap (required for Live traffic capture)...
reg query "HKLM\SOFTWARE\Npcap" >nul 2>&1
if errorlevel 1 (
    reg query "HKLM\SOFTWARE\WinPcap" >nul 2>&1
)
if errorlevel 1 (
    echo         Not installed.
    echo.
    echo   The app will start in Demo mode ^(simulated traffic^).
    echo   For real network monitoring, install Npcap:
    echo     https://npcap.com/#download
    echo.
    echo   Tip: check "Allow non-admin users to capture packets"
    echo   during Npcap installation to avoid needing Admin rights.
) else (
    echo         Npcap found — Live mode available
)

:: ── Launch the app ────────────────────────────────────────────
echo.
echo  Starting AnomalyNet IDS...
start "" wscript.exe "%LAUNCHER_VBS%"

echo.
echo  ============================================================
echo   Installation complete!
echo.
echo   Desktop shortcut : AnomalyNet IDS (runs as administrator)
echo   Autostart        : enabled (starts at Windows login)
echo   Open manually    : http://localhost:8000
echo   Uninstall        : run uninstall.bat
echo.
echo   NOTE: the shortcut launches AnomalyNet as administrator —
echo   live traffic capture and IP blocking require elevation (UAC).
echo  ============================================================
echo.
pause
