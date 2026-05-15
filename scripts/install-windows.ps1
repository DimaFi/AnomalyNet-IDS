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

# ── Автоустановка зависимостей ───────────────────────────────

# Попытка установить пакет через winget (встроен в Windows 10/11)
function Install-Via-Winget($packageId, $label) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Warn "winget не найден — установите $label вручную"
        return $false
    }
    Log "Устанавливаем $label через winget..."
    winget install --id $packageId --silent --accept-package-agreements --accept-source-agreements 2>$null
    # Обновляем PATH текущей сессии (winget меняет PATH только для новых процессов)
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH    = "$machinePath;$userPath"
    return $LASTEXITCODE -eq 0
}

# Скачать и запустить установщик через HTTP (fallback без winget)
function Install-Via-Download($url, $label, $installArgs, $fileExt = "exe") {
    Log "Скачиваем $label..."
    $tmp = "$env:TEMP\anomalynet_dep_install.$fileExt"
    try {
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        Log "Запускаем установщик $label..."
        if ($fileExt -eq "msi") {
            Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$tmp`" $installArgs" -Wait
        } else {
            Start-Process -FilePath $tmp -ArgumentList $installArgs -Wait
        }
        Remove-Item $tmp -ErrorAction SilentlyContinue
        $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
        $env:PATH    = "$machinePath;$userPath"
        return $true
    } catch {
        Warn "Не удалось скачать $label`: $_"
        return $false
    }
}

# ── Python 3.11 ──────────────────────────────────────────────
Log "Проверка Python..."

function Find-Python {
    # Refresh PATH from registry
    $mp = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $up = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$mp;$up"

    foreach ($candidate in @("python", "python3", "py")) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 10) { return $candidate }
            }
        } catch {}
    }

    # Scan all drives/paths where Python might end up (elevated context shifts LOCALAPPDATA)
    $candidates = @()
    # Program Files (InstallAllUsers=1 puts it here)
    $candidates += Get-ChildItem "C:\Program Files" -Directory -Filter "Python3*" -ErrorAction SilentlyContinue
    $candidates += Get-ChildItem "C:\Program Files (x86)" -Directory -Filter "Python3*" -ErrorAction SilentlyContinue
    # All user profiles (winget may install per-user)
    $candidates += Get-ChildItem "C:\Users\*\AppData\Local\Programs\Python\*" -Directory -ErrorAction SilentlyContinue
    # Fallback roots
    foreach ($r in @("C:\Python311","C:\Python310","C:\Python312","C:\Python313")) {
        if (Test-Path $r) { $candidates += Get-Item $r }
    }
    foreach ($dir in $candidates) {
        $exe = Join-Path $dir.FullName "python.exe"
        if (Test-Path $exe) {
            $env:PATH = "$($dir.FullName);$env:PATH"
            try {
                $ver = & $exe --version 2>&1
                if ($ver -match "Python (\d+)\.(\d+)") {
                    if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 10) { return $exe }
                }
            } catch {}
        }
    }
    return $null
}

$pythonCmd = Find-Python
if (-not $pythonCmd) {
    Warn "Python 3.10+ не найден."
    $ans = Read-Host "  Установить автоматически? [Y/n]"
    if ($ans -eq '' -or $ans -match '^[YyДд]') {
        # Try winget first
        $ok = Install-Via-Winget "Python.Python.3.11" "Python 3.11"
        $pythonCmd = Find-Python
        # winget sometimes succeeds but PATH is stale — always try direct download as fallback
        if (-not $pythonCmd) {
            if ($ok) { Warn "winget завершился, но Python не найден — пробуем прямую загрузку..." }
            Install-Via-Download `
                "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" `
                "Python 3.11" `
                "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1" | Out-Null
            $pythonCmd = Find-Python
        }
    }
    if (-not $pythonCmd) {
        Err "Python не установлен. Скачайте вручную: https://www.python.org/downloads/"
    }
}
Ok "Python: $(& $pythonCmd --version 2>&1)"

# ── Git ───────────────────────────────────────────────────────
Log "Проверка Git..."

function Find-Git {
    $mp = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $up = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$mp;$up"
    if (Get-Command git -ErrorAction SilentlyContinue) { return $true }
    # Known install path after silent installer
    $gitExe = "C:\Program Files\Git\cmd\git.exe"
    if (Test-Path $gitExe) {
        $env:PATH = "C:\Program Files\Git\cmd;C:\Program Files\Git\bin;$env:PATH"
        return $true
    }
    return $false
}

if (-not (Find-Git)) {
    Warn "Git не найден."
    $ans = Read-Host "  Установить автоматически? [Y/n]"
    if ($ans -eq '' -or $ans -match '^[YyДд]') {
        Install-Via-Winget "Git.Git" "Git" | Out-Null
        if (-not (Find-Git)) {
            Install-Via-Download `
                "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe" `
                "Git" `
                "/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS" | Out-Null
        }
    }
}
if (Find-Git) {
    $script:gitAvailable = $true
    Ok "Git: $(git --version)"
} else {
    $script:gitAvailable = $false
    Warn "Git не установлен — обновления через UI недоступны. Установите вручную: https://git-scm.com/"
}

# ── Node.js 20 LTS ────────────────────────────────────────────
Log "Проверка Node.js..."

function Find-Node {
    $mp = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $up = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$mp;$up"
    if (Get-Command node -ErrorAction SilentlyContinue) {
        $v = (node --version) -replace 'v',''
        if ([int]($v.Split('.')[0]) -ge 18) { return $true }
    }
    # Known install path after MSI
    foreach ($nodeDir in @("C:\Program Files\nodejs", "C:\Program Files (x86)\nodejs")) {
        if (Test-Path "$nodeDir\node.exe") {
            $env:PATH = "$nodeDir;$env:PATH"
            $v = (& "$nodeDir\node.exe" --version 2>&1) -replace 'v',''
            if ([int]($v.Split('.')[0]) -ge 18) { return $true }
        }
    }
    return $false
}

if (-not (Find-Node)) {
    Warn "Node.js 18+ не найден."
    $ans = Read-Host "  Установить автоматически? [Y/n]"
    if ($ans -eq '' -or $ans -match '^[YyДд]') {
        Install-Via-Winget "OpenJS.NodeJS.LTS" "Node.js 20 LTS" | Out-Null
        if (-not (Find-Node)) {
            Install-Via-Download `
                "https://nodejs.org/dist/v20.14.0/node-v20.14.0-x64.msi" `
                "Node.js 20 LTS" `
                "/quiet /norestart ADDLOCAL=ALL" `
                "msi" | Out-Null
        }
    }
    if (-not (Find-Node)) {
        Err "Node.js не установлен. Скачайте вручную: https://nodejs.org/"
    }
}
Ok "Node.js: $(node --version)"

Write-Host ""

# ── Клонирование / обновление репозиториев ───────────────────
$guiRepo = "https://github.com/DimaFi/AnomalyNet-gui.git"
$mlRepo  = "https://github.com/DimaFi/AnomalyNet-ml.git"
$guiDir  = "$InstallDir\AnomalyNet-gui"
$mlDir   = "$InstallDir\AnomalyNet-ml"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

if ($script:gitAvailable) {
    if (Test-Path "$guiDir\.git") {
        Log "Обновляем AnomalyNet-gui..."
        git -C $guiDir stash 2>$null
        git -C $guiDir pull --quiet
    } elseif (-not (Test-Path $guiDir)) {
        Log "Клонируем AnomalyNet-gui..."
        git clone --quiet --depth 1 $guiRepo $guiDir
    } else {
        Log "AnomalyNet-gui уже распакован (не .git-репозиторий) — пропускаем клонирование"
    }
    Ok "AnomalyNet-gui готов"

    if (Test-Path "$mlDir\.git") {
        Log "Обновляем AnomalyNet-ml..."
        git -C $mlDir pull --quiet
    } elseif (-not (Test-Path $mlDir)) {
        Log "Клонируем AnomalyNet-ml (модели, ~120 МБ, 1-2 мин)..."
        git clone --quiet --depth 1 $mlRepo $mlDir
    } else {
        Log "AnomalyNet-ml уже распакован (не .git-репозиторий) — пропускаем клонирование"
    }
    Ok "AnomalyNet-ml готов"
} else {
    if (-not (Test-Path $guiDir)) {
        Err "Git не установлен и $guiDir не найден — невозможно продолжить. Установите Git и запустите заново."
    }
    Warn "Git недоступен — репозитории не обновлены, используются существующие файлы"
}

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

# ── Ярлыки на рабочем столе и в меню Пуск ───────────────────
Log "Создаём ярлыки..."
$appUrl = "http://localhost:$Port"

function New-UrlShortcut($path, $url, $iconSrc) {
    $content = "[InternetShortcut]`r`nURL=$url`r`n"
    if ($iconSrc -and (Test-Path $iconSrc)) {
        $content += "IconFile=$iconSrc`r`nIconIndex=0`r`n"
    }
    [System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::ASCII)
}

$iconPath = "$guiDir\frontend\public\favicon.ico"
$shortcutName = "AnomalyNet IDS.url"

# Рабочий стол текущего пользователя
$desktopPath = [System.Environment]::GetFolderPath("Desktop")
New-UrlShortcut "$desktopPath\$shortcutName" $appUrl $iconPath
Ok "Ярлык на рабочем столе: $desktopPath\$shortcutName"

# Меню Пуск — Programs
$startMenuPath = [System.Environment]::GetFolderPath("Programs")
$startMenuDir  = "$startMenuPath\AnomalyNet"
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
New-UrlShortcut "$startMenuDir\$shortcutName" $appUrl $iconPath
Ok "Ярлык в меню Пуск: $startMenuDir\$shortcutName"

# ── Итог ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "  +=======================================+" -ForegroundColor Green
Write-Host "  |       Установка завершена!            |" -ForegroundColor Green
Write-Host "  +=======================================+" -ForegroundColor Green
Write-Host ""
Write-Host "  Веб-интерфейс  : " -NoNewline; Write-Host $appUrl -ForegroundColor Green
Write-Host "  API health     : $appUrl/api/health"
Write-Host "  Каталог        : $InstallDir"
Write-Host "  Режим          : $runMode / $activeModel"
Write-Host ""
Write-Host "  Ярлык создан на Рабочем столе и в меню Пуск." -ForegroundColor Cyan
Write-Host "  Двойной клик — откроет браузер на $appUrl" -ForegroundColor Cyan
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
