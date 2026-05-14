# ============================================================
#  AnomalyNet IDS — Windows Uninstall Script
#  Requires: Admin rights
#
#  Usage:
#    powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1
#    powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1 -Purge
# ============================================================

param(
    [switch]$Purge,
    [string]$InstallDir = ""
)

$ErrorActionPreference = "SilentlyContinue"

function Log  ($msg) { Write-Host "  $([char]0x25B6)  $msg" -ForegroundColor Cyan }
function Ok   ($msg) { Write-Host "  $([char]0x2713)  $msg" -ForegroundColor Green }
function Warn ($msg) { Write-Host "  $([char]0x26A0)  $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  +========================================+" -ForegroundColor White
Write-Host "  |   AnomalyNet IDS — Удаление Windows   |" -ForegroundColor White
Write-Host "  +========================================+" -ForegroundColor White
Write-Host ""

# Определяем каталог
if (-not $InstallDir) {
    $envRoot = [System.Environment]::GetEnvironmentVariable("ANOMALYNET_APP_ROOT", "Machine")
    if ($envRoot) {
        $InstallDir = Split-Path $envRoot -Parent
    } else {
        $InstallDir = "C:\AnomalyNet"
    }
}
Log "Каталог установки: $InstallDir"
if ($Purge) { Warn "Режим -Purge: будет удалён каталог $InstallDir" }
Write-Host ""

# Проверка прав
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "  Запустите от имени Администратора." -ForegroundColor Red
    exit 1
}

# ── 1. Удаление задачи Task Scheduler ───────────────────────
Log "Удаление задачи AnomalyNet из Task Scheduler..."
$result = schtasks /delete /tn "AnomalyNet" /f 2>&1
if ($LASTEXITCODE -eq 0) {
    Ok "Задача 'AnomalyNet' удалена"
} else {
    Warn "Задача не найдена или уже удалена"
}

# ── 2. Завершение процессов ──────────────────────────────────
Log "Поиск и завершение процессов AnomalyNet..."
$guiDir = [System.Environment]::GetEnvironmentVariable("ANOMALYNET_APP_ROOT", "Machine")
if (-not $guiDir) { $guiDir = "$InstallDir\AnomalyNet-gui" }

# Ищем python.exe с uvicorn из нашего venv
$venvPy = "$guiDir\backend\.venv\Scripts\python.exe"
$procs = Get-WmiObject Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    if ($p.CommandLine -like "*uvicorn*app.main*") {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Ok "Процесс PID=$($p.ProcessId) завершён"
    }
}

# ── 3. Удаление правил брандмауэра Windows (netsh advfirewall) ──
Log "Удаление правил брандмауэра ANOMALYNET_BLOCK_*..."
$rules = netsh advfirewall firewall show rule name=all 2>$null | Select-String "ANOMALYNET_BLOCK_"
$count = 0
foreach ($line in $rules) {
    $name = ($line -split "Rule Name:\s*")[1].Trim()
    if ($name) {
        netsh advfirewall firewall delete rule name="$name" 2>$null
        $count++
    }
}

# Альтернативный метод через PowerShell (Windows 8+)
try {
    $psRules = Get-NetFirewallRule -DisplayName "ANOMALYNET_BLOCK_*" -ErrorAction SilentlyContinue
    foreach ($r in $psRules) {
        Remove-NetFirewallRule -DisplayName $r.DisplayName -ErrorAction SilentlyContinue
        $count++
    }
} catch {}

if ($count -gt 0) { Ok "Удалено правил брандмауэра: $count" }
else { Warn "Правила ANOMALYNET_BLOCK_* не найдены" }

# ── 4. Удаление системных переменных ────────────────────────
Log "Удаление системных переменных..."
[System.Environment]::SetEnvironmentVariable("ANOMALYNET_APP_ROOT", $null, [System.EnvironmentVariableTarget]::Machine)
[System.Environment]::SetEnvironmentVariable("ANOMALYNET_MODELS_ROOT", $null, [System.EnvironmentVariableTarget]::Machine)
Ok "Переменные ANOMALYNET_APP_ROOT, ANOMALYNET_MODELS_ROOT удалены"

# ── 5. Удаление каталога (только --Purge) ──────────────────
if ($Purge) {
    Log "Удаление каталога $InstallDir..."
    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue
        if (-not (Test-Path $InstallDir)) {
            Ok "Каталог $InstallDir удалён"
        } else {
            Warn "Не удалось удалить $InstallDir (возможно, заняты файлы) — удалите вручную"
        }
    } else {
        Warn "Каталог $InstallDir не найден"
    }
} else {
    Warn "Каталог $InstallDir сохранён (используйте -Purge для полного удаления)"
}

# ── Итог ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "  +========================================+" -ForegroundColor Green
Write-Host "  |         Удаление завершено!            |" -ForegroundColor Green
Write-Host "  +========================================+" -ForegroundColor Green
Write-Host ""
if (-not $Purge) {
    Write-Host "  Данные сохранены в: $InstallDir"
    Write-Host "  Для полного удаления: powershell -File scripts\uninstall-windows.ps1 -Purge"
}
Write-Host ""
