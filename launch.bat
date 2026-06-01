@echo off
:: AnomalyNet IDS — Windows Launcher
:: Double-click to start the server and open the browser.
:: Live capture (Npcap) and IP blocking (Windows Firewall) need administrator
:: rights, so the launcher self-elevates via UAC.
setlocal

cd /d "%~dp0"

:: ── Self-elevate to administrator (capture + firewall need it) ──
:: If already running, skip elevation and just open the browser.
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/health 2>nul | findstr "200" >nul
if %errorlevel%==0 (
    start "" "http://localhost:8000"
    exit /b 0
)
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WindowStyle Hidden"
    exit /b
)

:: Find Python: prefer venv, then system
set "PYTHON="
if exist "backend\.venv\Scripts\pythonw.exe" set "PYTHON=backend\.venv\Scripts\pythonw.exe"
if exist "backend\.venv\Scripts\python.exe"  set "PYTHON=backend\.venv\Scripts\python.exe"
if "%PYTHON%"=="" where python >nul 2>&1 && set "PYTHON=python"
if "%PYTHON%"=="" (
    echo Python not found. Please install Python 3.10+ or run install-windows.bat
    pause
    exit /b 1
)

:: Check if server is already running
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/health 2>nul | findstr "200" >nul
if %errorlevel%==0 (
    echo AnomalyNet already running — opening browser...
    start "" "http://localhost:8000"
    exit /b 0
)

:: Choose bind host from the allow_remote_access setting:
::   0.0.0.0   = reachable from phones / other devices on the LAN
::   127.0.0.1 = this PC only (default)
set "BIND_HOST=127.0.0.1"
"%PYTHON%" "%~dp0backend\bindhost.py" > "%TEMP%\anet_host.txt" 2>nul
set /p BIND_HOST=<"%TEMP%\anet_host.txt"
if "%BIND_HOST%"=="" set "BIND_HOST=127.0.0.1"
del "%TEMP%\anet_host.txt" >nul 2>&1

:: Start server in background (no console window)
echo Starting AnomalyNet IDS... (host %BIND_HOST%)
start /B "" "%PYTHON%" -m uvicorn app.main:app --host %BIND_HOST% --port 8000 --app-dir backend

:: Wait for server to become ready (up to 15 seconds)
set /a attempts=0
:wait_loop
if %attempts% geq 15 goto timeout
timeout /t 1 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/health 2>nul | findstr "200" >nul
if %errorlevel%==0 goto ready
set /a attempts=%attempts%+1
goto wait_loop

:ready
start "" "http://localhost:8000"
exit /b 0

:timeout
echo Server did not start in time. Check logs.
start "" "http://localhost:8000"
exit /b 1
