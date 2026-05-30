@echo off
:: AnomalyNet Control — tray app launcher (Windows)
:: Starts the system-tray controller using the venv pythonw (no console window).
setlocal
set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

set "PYW=%APP_DIR%\backend\.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%APP_DIR%\backend\.venv\Scripts\python.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"

cd /d "%APP_DIR%\backend"
start "" "%PYW%" -m app.tray.main
