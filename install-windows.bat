@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

title AnomalyNet IDS — Установка Windows

echo.
echo  ╔═══════════════════════════════════════════╗
echo  ║    AnomalyNet IDS — Установка Windows     ║
echo  ╚═══════════════════════════════════════════╝
echo.

:: ── Проверка прав администратора ─────────────────────────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  Требуются права администратора.
    echo  Сейчас откроется запрос UAC — нажмите "Да".
    echo.
    powershell -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

:: ── Проверка наличия установщика ─────────────────────────────
if not exist "%~dp0scripts\install-windows.ps1" (
    echo  ОШИБКА: файл scripts\install-windows.ps1 не найден.
    echo  Убедитесь, что вы распаковали полный архив AnomalyNet.
    echo.
    pause
    exit /b 1
)

:: ── Запуск PowerShell-установщика ────────────────────────────
cd /d "%~dp0"
echo  Запускаем установщик...
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "scripts\install-windows.ps1" %*

echo.
echo  Нажмите любую клавишу для закрытия...
pause >nul
