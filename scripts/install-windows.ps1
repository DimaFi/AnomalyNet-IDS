# ============================================================
#  AnomalyNet IDS — Windows Install Script
#  Requires: Windows 10/11, PowerShell 5.1+, Admin rights
#
#  Usage:
#    # Запустить как Администратор:
#    powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1
#
#  Параметры:
#    -InstallDir    Куда установить (по умолчанию C:\AnomalyNet)
#    -Port          Порт веб-интерфейса (по умолчанию 8000)
#    -InstallNpcap  Предложить установить Npcap если не найден
#    -AutoBlock     Включить автоматическую блокировку атак
# ============================================================

param(
    [string]$InstallDir   = "C:\AnomalyNet",
    [int]   $Port         = 8000,
    [switch]$InstallNpcap,
    [switch]$AutoBlock
)

$ErrorActionPreference = "Stop"

# ── Цвета и логирование ──────────────────────────────────────
function Log  ($msg) { Write-Host "  $([char]0x25B6)  $msg" -ForegroundColor Cyan }
function Ok   ($msg) { Write-Host "  $([char]0x2713)  $msg" -ForegroundColor Green }
function Warn ($msg) { Write-Host "  $([char]0x26A0)  $msg" -ForegroundColor Yellow }
function Err  ($msg) { Write-Host "  $([char]0x2717)  $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  +=======================================+" -ForegroundColor White
Write-Host "  |   AnomalyNet IDS — Установка Windows  |" -ForegroundColor White
Write-Host "  +=======================================+" -ForegroundColor White
Write-Host ""

# ── Проверка прав администратора ────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Err "Запустите скрипт от имени Администратора."
}
Ok "Права администратора: OK"

Log "Каталог установки : $InstallDir"
Log "Порт              : $Port"
Write-Host ""

# ── Проверка зависимостей ────────────────────────────────────
Log "Проверка зависимостей..."

# Python 3.10+
$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $maj = [int]$Matches[1]; $min = [int]$Matches[2]
            if ($maj -ge 3 -and $min -ge 10) { $pythonCmd = $candidate; break }
        }
    } catch {}
}
if (-not $pythonCmd) {
    Err "Python 3.10+ не найден. Скачайте с https://www.python.org/downloads/ и добавьте в PATH."
}
$pyVer = & $pythonCmd --version 2>&1
Ok "Python: $pyVer"

# Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Err "Git не найден. Скачайте с https://git-scm.com/ и добавьте в PATH."
}
Ok "Git: $(git --version)"

# Node.js 18+
$nodeOk = $false
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = (node --version) -replace 'v', ''
    $nodeMaj = [int]($nodeVer.Split('.')[0])
    if ($nodeMaj -ge 18) { $nodeOk = $true }
}
if (-not $nodeOk) {
    Err "Node.js 18+ не найден. Скачайте с https://nodejs.org/ и добавьте в PATH."
}
Ok "Node.js: $(node --version)"

# npm
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Err "npm не найден. Входит в состав Node.js — переустановите Node.js."
}
Ok "npm: $(npm --version)"

Write-Host ""

# ── Клонирование / обновление репозиториев ───────────────────
$guiRepo = "https://github.com/DimaFi/AnomalyNet-gui.git"
$mlRepo  = "https://github.com/DimaFi/AnomalyNet-ml.git"
$guiDir  = "$InstallDir\AnomalyNet-gui"
$mlDir   = "$InstallDir\AnomalyNet-ml"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

if (Test-Path "$guiDir\.git") {
    Log "Обновляем AnomalyNet-gui..."
    git -C $guiDir stash 2>$null
    git -C $guiDir pull --quiet
} else {
    Log "Клонируем AnomalyNet-gui..."
    git clone --quiet --depth 1 $guiRepo $guiDir
}
Ok "AnomalyNet-gui готов"

if (Test-Path "$mlDir\.git") {
    Log "Обновляем AnomalyNet-ml..."
    git -C $mlDir pull --quiet
} else {
    Log "Клонируем AnomalyNet-ml (модели, ~120 МБ, 1-2 мин)..."
    git clone --quiet --depth 1 $mlRepo $mlDir
}
Ok "AnomalyNet-ml готов"

# ── Структура моделей ────────────────────────────────────────
$modelsDir = "$InstallDir\models"
$modelPaths = @(
    "$modelsDir\stage1\catboost",
    "$modelsDir\stage1\artifacts",
    "$modelsDir\stage2\catboost",
    "$modelsDir\stage3\catboost",
    "$modelsDir\stage3\artifacts"
)
foreach ($p in $modelPaths) { New-Item -ItemType Directory -Force -Path $p | Out-Null }

function Copy-ModelDir($src, $dst, $label) {
    if (Test-Path $src) {
        Copy-Item "$src\*" -Destination $dst -Recurse -Force -ErrorAction SilentlyContinue
        Ok "$label"
    } else {
        Warn "$label — не найдено в $src"
    }
}

Copy-ModelDir "$mlDir\model"                              "$modelsDir\stage1\catboost"  "Stage1 модель (binary)"
Copy-ModelDir "$mlDir\artifacts"                          "$modelsDir\stage1\artifacts" "Stage1 артефакты"
Copy-ModelDir "$mlDir\stage2_multiclass\models\catboost"  "$modelsDir\stage2\catboost"  "Stage2 модель (simple)"
Copy-ModelDir "$mlDir\stage3_cic2023\models\catboost"     "$modelsDir\stage3\catboost"  "Stage3 модель (advanced)"
Copy-ModelDir "$mlDir\stage3_cic2023\artifacts"           "$modelsDir\stage3\artifacts" "Stage3 артефакты"

# ── Python venv + зависимости ────────────────────────────────
Log "Настройка Python venv..."
$venvDir  = "$guiDir\backend\.venv"
$venvPy   = "$venvDir\Scripts\python.exe"
$venvPip  = "$venvDir\Scripts\pip.exe"

& $pythonCmd -m venv $venvDir
& $venvPip install --quiet --upgrade pip setuptools wheel
& $venvPip install --quiet -r "$guiDir\backend\requirements.txt"
Ok "Python-зависимости установлены"

# ── Сборка фронтенда ─────────────────────────────────────────
Log "Сборка React-фронтенда (2-4 мин)..."
Push-Location "$guiDir\frontend"
try {
    if (Test-Path "node_modules") { Remove-Item -Recurse -Force "node_modules" }
    npm install --silent
    $env:NODE_OPTIONS = "--max-old-space-size=1536"
    npm run build
    $env:NODE_OPTIONS = ""
} finally {
    Pop-Location
}
Ok "Фронтенд собран"

# ── Проверка Npcap ───────────────────────────────────────────
Log "Проверка Npcap..."
$npcapInstalled = Test-Path "C:\Windows\System32\Npcap\wpcap.dll"
if ($npcapInstalled) {
    Ok "Npcap установлен — активный ARP-сканер доступен"
} else {
    Warn "Npcap не найден — ARP-сканер будет использовать fallback (arp -a)"
    if ($InstallNpcap) {
        Log "Скачиваем Npcap..."
        $npcapUrl  = "https://npcap.com/dist/npcap-1.79.exe"
        $npcapPath = "$env:TEMP\npcap-install.exe"
        try {
            Invoke-WebRequest -Uri $npcapUrl -OutFile $npcapPath -UseBasicParsing
            Log "Запускаем установщик Npcap (потребуется подтверждение)..."
            Start-Process -FilePath $npcapPath -ArgumentList "/S" -Wait
            Ok "Npcap установлен"
        } catch {
            Warn "Не удалось скачать Npcap: $_"
            Warn "Скачайте вручную: https://npcap.com/"
        }
    } else {
        Warn "Для активного ARP-сканирования установите Npcap: https://npcap.com/"
        Warn "Или повторите установку с флагом -InstallNpcap"
    }
}

# ── Определение режима ───────────────────────────────────────
$stage1Cbm = Get-ChildItem "$modelsDir\stage1\catboost\*.cbm" -ErrorAction SilentlyContinue
$runMode     = if ($stage1Cbm) { "windows_live" } else { "mock" }
$activeModel = if ($stage1Cbm) { "catboost-cascade-simple" } else { "mock-default" }
if (-not $stage1Cbm) {
    Warn "Модели stage1 не найдены — запускаем в Demo-режиме"
}

# ── Запись settings.json ─────────────────────────────────────
Log "Запись config\settings.json..."
$autoBlockVal = if ($AutoBlock) { "true" } else { "false" }
$settingsJson = @"
{
  "language": "ru",
  "theme": "dark",
  "run_mode": "$runMode",
  "retention_days": 14,
  "active_model_id": "$activeModel",
  "capture_enabled": true,
  "stream_autostart": true,
  "interface_name": "",
  "catboost_threshold": 0.70,
  "catboost_model_dir": "$($modelsDir.Replace('\','/'))/stage1/catboost",
  "preprocessing_artifacts_dir": "$($modelsDir.Replace('\','/'))/stage1/artifacts",
  "auto_block": $autoBlockVal,
  "auto_block_level": "anomaly",
  "whitelist_ips": [],
  "detection_mode": "simple",
  "catboost_secondary_model_dir": "$($modelsDir.Replace('\','/'))/stage2/catboost",
  "catboost_secondary_artifacts_dir": "",
  "catboost_stage3_model_dir": "$($modelsDir.Replace('\','/'))/stage3/catboost",
  "catboost_stage3_artifacts_dir": "$($modelsDir.Replace('\','/'))/stage3/artifacts",
  "interface_names": []
}
"@
New-Item -ItemType Directory -Force -Path "$guiDir\config" | Out-Null
$settingsJson | Out-File -Encoding utf8 -FilePath "$guiDir\config\settings.json"
Ok "settings.json записан"

# ── Переменная окружения ANOMALYNET_APP_ROOT ─────────────────
Log "Установка системной переменной ANOMALYNET_APP_ROOT..."
[System.Environment]::SetEnvironmentVariable(
    "ANOMALYNET_APP_ROOT", $guiDir,
    [System.EnvironmentVariableTarget]::Machine)
[System.Environment]::SetEnvironmentVariable(
    "ANOMALYNET_MODELS_ROOT", $modelsDir,
    [System.EnvironmentVariableTarget]::Machine)
Ok "Системные переменные установлены"

# ── Создание задачи в Task Scheduler ─────────────────────────
Log "Настройка автозапуска через Task Scheduler..."
$taskName   = "AnomalyNet"
$workingDir = "$guiDir\backend"
$uvicornArgs = "-m uvicorn app.main:app --host 0.0.0.0 --port $Port --log-level info --timeout-graceful-shutdown 3"

# Удаляем старую задачу если есть
schtasks /delete /tn $taskName /f 2>$null

# Создаём через XML — позволяет задать рабочую директорию и переменные окружения
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>AnomalyNet IDS — сетевой мониторинг и обнаружение вторжений</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$($env:USERDOMAIN)\$($env:USERNAME)</UserId>
      <LogonType>Password</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <StartWhenAvailable>true</StartWhenAvailable>
  </Settings>
  <Actions>
    <Exec>
      <Command>"$venvPy"</Command>
      <Arguments>$uvicornArgs</Arguments>
      <WorkingDirectory>$workingDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

$xmlPath = "$env:TEMP\anomalynet-task.xml"
$taskXml | Out-File -Encoding Unicode -FilePath $xmlPath

$cred = Get-Credential -UserName $env:USERNAME -Message "Введите пароль пользователя для задачи планировщика (нужен для работы с высокими привилегиями)"
if ($cred) {
    $pass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password))
    schtasks /create /tn $taskName /xml $xmlPath /ru $env:USERNAME /rp $pass /f 2>$null
    Remove-Variable pass -ErrorAction SilentlyContinue
    Ok "Задача '$taskName' создана в Task Scheduler"
} else {
    Warn "Пароль не введён — задача не создана. Используйте: schtasks /create /tn AnomalyNet ..."
}
Remove-Item $xmlPath -ErrorAction SilentlyContinue

# ── Запуск сервиса прямо сейчас ─────────────────────────────
Log "Запуск AnomalyNet..."
$proc = Start-Process -FilePath $venvPy `
    -ArgumentList $uvicornArgs `
    -WorkingDirectory $workingDir `
    -WindowStyle Hidden `
    -PassThru
Start-Sleep -Seconds 3

# Проверяем что запустился
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$Port/api/health" -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) {
        Ok "Сервис запущен и отвечает на http://localhost:$Port"
    }
} catch {
    Warn "Сервис запущен, но не отвечает пока — подождите 10-15 сек"
}

# ── Итог ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "  +=======================================+" -ForegroundColor Green
Write-Host "  |       Установка завершена!            |" -ForegroundColor Green
Write-Host "  +=======================================+" -ForegroundColor Green
Write-Host ""
Write-Host "  Веб-интерфейс  : " -NoNewline; Write-Host "http://localhost:$Port" -ForegroundColor Green
Write-Host "  API health     : http://localhost:$Port/api/health"
Write-Host "  Каталог        : $InstallDir"
Write-Host "  Режим          : $runMode / $activeModel"
Write-Host ""
if (-not $stage1Cbm) {
    Write-Host "  ВНИМАНИЕ: Модели не найдены — работает Demo-режим." -ForegroundColor Yellow
    Write-Host "  Положите модели в $modelsDir и перейдите в Settings." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Управление:"
Write-Host "    Запустить     : schtasks /run /tn AnomalyNet"
Write-Host "    Остановить    : taskkill /f /im python.exe  (осторожно!)"
Write-Host "    Удалить       : powershell -File scripts\uninstall-windows.ps1"
Write-Host ""
