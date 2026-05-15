# ============================================================
#  AnomalyNet IDS вЂ” Windows Install Script
#  Requires: Windows 10/11, PowerShell 5.1+, Admin rights
#
#  Usage:
#    # Р—Р°РїСѓСЃС‚РёС‚СЊ РєР°Рє РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ:
#    powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1
#
#  РџР°СЂР°РјРµС‚СЂС‹:
#    -InstallDir    РљСѓРґР° СѓСЃС‚Р°РЅРѕРІРёС‚СЊ (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ C:\AnomalyNet)
#    -Port          РџРѕСЂС‚ РІРµР±-РёРЅС‚РµСЂС„РµР№СЃР° (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ 8000)
#    -InstallNpcap  РџСЂРµРґР»РѕР¶РёС‚СЊ СѓСЃС‚Р°РЅРѕРІРёС‚СЊ Npcap РµСЃР»Рё РЅРµ РЅР°Р№РґРµРЅ
#    -AutoBlock     Р’РєР»СЋС‡РёС‚СЊ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєСѓСЋ Р±Р»РѕРєРёСЂРѕРІРєСѓ Р°С‚Р°Рє
# ============================================================

param(
    [string]$InstallDir   = "C:\AnomalyNet",
    [int]   $Port         = 8000,
    [switch]$InstallNpcap,
    [switch]$AutoBlock
)

$ErrorActionPreference = "Stop"

# в”Ђв”Ђ Р¦РІРµС‚Р° Рё Р»РѕРіРёСЂРѕРІР°РЅРёРµ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
function Log  ($msg) { Write-Host "  $([char]0x25B6)  $msg" -ForegroundColor Cyan }
function Ok   ($msg) { Write-Host "  $([char]0x2713)  $msg" -ForegroundColor Green }
function Warn ($msg) { Write-Host "  $([char]0x26A0)  $msg" -ForegroundColor Yellow }
function Err  ($msg) { Write-Host "  $([char]0x2717)  $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  +=======================================+" -ForegroundColor White
Write-Host "  |   AnomalyNet IDS вЂ” РЈСЃС‚Р°РЅРѕРІРєР° Windows  |" -ForegroundColor White
Write-Host "  +=======================================+" -ForegroundColor White
Write-Host ""

# в”Ђв”Ђ РџСЂРѕРІРµСЂРєР° РїСЂР°РІ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР° в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Err "Р—Р°РїСѓСЃС‚РёС‚Рµ СЃРєСЂРёРїС‚ РѕС‚ РёРјРµРЅРё РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°."
}
Ok "РџСЂР°РІР° Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°: OK"

Log "РљР°С‚Р°Р»РѕРі СѓСЃС‚Р°РЅРѕРІРєРё : $InstallDir"
Log "РџРѕСЂС‚              : $Port"
Write-Host ""

# в”Ђв”Ђ РђРІС‚РѕСѓСЃС‚Р°РЅРѕРІРєР° Р·Р°РІРёСЃРёРјРѕСЃС‚РµР№ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

# РџРѕРїС‹С‚РєР° СѓСЃС‚Р°РЅРѕРІРёС‚СЊ РїР°РєРµС‚ С‡РµСЂРµР· winget (РІСЃС‚СЂРѕРµРЅ РІ Windows 10/11)
function Install-Via-Winget($packageId, $label) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Warn "winget РЅРµ РЅР°Р№РґРµРЅ вЂ” СѓСЃС‚Р°РЅРѕРІРёС‚Рµ $label РІСЂСѓС‡РЅСѓСЋ"
        return $false
    }
    Log "РЈСЃС‚Р°РЅР°РІР»РёРІР°РµРј $label С‡РµСЂРµР· winget..."
    winget install --id $packageId --silent --accept-package-agreements --accept-source-agreements 2>$null
    # РћР±РЅРѕРІР»СЏРµРј PATH С‚РµРєСѓС‰РµР№ СЃРµСЃСЃРёРё (winget РјРµРЅСЏРµС‚ PATH С‚РѕР»СЊРєРѕ РґР»СЏ РЅРѕРІС‹С… РїСЂРѕС†РµСЃСЃРѕРІ)
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH    = "$machinePath;$userPath"
    return $LASTEXITCODE -eq 0
}

# РЎРєР°С‡Р°С‚СЊ Рё Р·Р°РїСѓСЃС‚РёС‚СЊ СѓСЃС‚Р°РЅРѕРІС‰РёРє С‡РµСЂРµР· HTTP (fallback Р±РµР· winget)
function Install-Via-Download($url, $label, $installArgs) {
    Log "РЎРєР°С‡РёРІР°РµРј $label..."
    $tmp = "$env:TEMP\anomalynet_dep_install.exe"
    try {
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        Log "Р—Р°РїСѓСЃРєР°РµРј СѓСЃС‚Р°РЅРѕРІС‰РёРє $label..."
        Start-Process -FilePath $tmp -ArgumentList $installArgs -Wait
        Remove-Item $tmp -ErrorAction SilentlyContinue
        # РћР±РЅРѕРІР»СЏРµРј PATH
        $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
        $env:PATH    = "$machinePath;$userPath"
        return $true
    } catch {
        Warn "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРєР°С‡Р°С‚СЊ $label`: $_"
        return $false
    }
}

# в”Ђв”Ђ Python 3.11 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РџСЂРѕРІРµСЂРєР° Python..."
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
    Warn "Python 3.10+ РЅРµ РЅР°Р№РґРµРЅ."
    $ans = Read-Host "  РЈСЃС‚Р°РЅРѕРІРёС‚СЊ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё? [Y/n]"
    if ($ans -eq '' -or $ans -match '^[YyР”Рґ]') {
        $ok = Install-Via-Winget "Python.Python.3.11" "Python 3.11"
        if (-not $ok) {
            Install-Via-Download `
                "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" `
                "Python 3.11" `
                "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1" | Out-Null
        }
        # РџРµСЂРµРїСЂРѕРІРµСЂРєР°
        foreach ($candidate in @("python", "python3", "py")) {
            try {
                $ver = & $candidate --version 2>&1
                if ($ver -match "Python (\d+)\.(\d+)") {
                    $maj = [int]$Matches[1]; $min = [int]$Matches[2]
                    if ($maj -ge 3 -and $min -ge 10) { $pythonCmd = $candidate; break }
                }
            } catch {}
        }
    }
    if (-not $pythonCmd) {
        Err "Python РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ. РЎРєР°С‡Р°Р№С‚Рµ РІСЂСѓС‡РЅСѓСЋ: https://www.python.org/downloads/"
    }
}
Ok "Python: $(& $pythonCmd --version 2>&1)"

# в”Ђв”Ђ Git в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РџСЂРѕРІРµСЂРєР° Git..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Warn "Git РЅРµ РЅР°Р№РґРµРЅ."
    $ans = Read-Host "  РЈСЃС‚Р°РЅРѕРІРёС‚СЊ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё? [Y/n]"
    if ($ans -eq '' -or $ans -match '^[YyР”Рґ]') {
        $ok = Install-Via-Winget "Git.Git" "Git"
        if (-not $ok) {
            Install-Via-Download `
                "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe" `
                "Git" `
                "/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /NOICONS" | Out-Null
        }
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Warn "Git РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ. РџСЂРёР»РѕР¶РµРЅРёРµ Р±СѓРґРµС‚ СЂР°Р±РѕС‚Р°С‚СЊ, РЅРѕ РѕР±РЅРѕРІР»РµРЅРёСЏ С‡РµСЂРµР· UI РЅРµРґРѕСЃС‚СѓРїРЅС‹."
        Warn "Р”Р»СЏ РѕР±РЅРѕРІР»РµРЅРёР№ СѓСЃС‚Р°РЅРѕРІРёС‚Рµ Git: https://git-scm.com/"
        $script:gitAvailable = $false
    } else {
        $script:gitAvailable = $true
    }
} else {
    $script:gitAvailable = $true
}
if ($script:gitAvailable) { Ok "Git: $(git --version)" }

# в”Ђв”Ђ Node.js 20 LTS в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РџСЂРѕРІРµСЂРєР° Node.js..."
$nodeOk = $false
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = (node --version) -replace 'v', ''
    $nodeMaj = [int]($nodeVer.Split('.')[0])
    if ($nodeMaj -ge 18) { $nodeOk = $true }
}
if (-not $nodeOk) {
    Warn "Node.js 18+ РЅРµ РЅР°Р№РґРµРЅ."
    $ans = Read-Host "  РЈСЃС‚Р°РЅРѕРІРёС‚СЊ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё? [Y/n]"
    if ($ans -eq '' -or $ans -match '^[YyР”Рґ]') {
        $ok = Install-Via-Winget "OpenJS.NodeJS.LTS" "Node.js 20 LTS"
        if (-not $ok) {
            Install-Via-Download `
                "https://nodejs.org/dist/v20.14.0/node-v20.14.0-x64.msi" `
                "Node.js 20 LTS" `
                "/quiet /norestart" | Out-Null
        }
        # РџРµСЂРµРїСЂРѕРІРµСЂРєР°
        if (Get-Command node -ErrorAction SilentlyContinue) {
            $nodeVer = (node --version) -replace 'v', ''
            $nodeMaj = [int]($nodeVer.Split('.')[0])
            if ($nodeMaj -ge 18) { $nodeOk = $true }
        }
    }
    if (-not $nodeOk) {
        Err "Node.js РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ. РЎРєР°С‡Р°Р№С‚Рµ РІСЂСѓС‡РЅСѓСЋ: https://nodejs.org/"
    }
}
Ok "Node.js: $(node --version)"

Write-Host ""

# в”Ђв”Ђ РљР»РѕРЅРёСЂРѕРІР°РЅРёРµ / РѕР±РЅРѕРІР»РµРЅРёРµ СЂРµРїРѕР·РёС‚РѕСЂРёРµРІ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
$guiRepo = "https://github.com/DimaFi/AnomalyNet-gui.git"
$mlRepo  = "https://github.com/DimaFi/AnomalyNet-ml.git"
$guiDir  = "$InstallDir\AnomalyNet-gui"
$mlDir   = "$InstallDir\AnomalyNet-ml"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

if ($script:gitAvailable) {
    if (Test-Path "$guiDir\.git") {
        Log "РћР±РЅРѕРІР»СЏРµРј AnomalyNet-gui..."
        git -C $guiDir stash 2>$null
        git -C $guiDir pull --quiet
    } elseif (-not (Test-Path $guiDir)) {
        Log "РљР»РѕРЅРёСЂСѓРµРј AnomalyNet-gui..."
        git clone --quiet --depth 1 $guiRepo $guiDir
    } else {
        Log "AnomalyNet-gui СѓР¶Рµ СЂР°СЃРїР°РєРѕРІР°РЅ (РЅРµ .git-СЂРµРїРѕР·РёС‚РѕСЂРёР№) вЂ” РїСЂРѕРїСѓСЃРєР°РµРј РєР»РѕРЅРёСЂРѕРІР°РЅРёРµ"
    }
    Ok "AnomalyNet-gui РіРѕС‚РѕРІ"

    if (Test-Path "$mlDir\.git") {
        Log "РћР±РЅРѕРІР»СЏРµРј AnomalyNet-ml..."
        git -C $mlDir pull --quiet
    } elseif (-not (Test-Path $mlDir)) {
        Log "РљР»РѕРЅРёСЂСѓРµРј AnomalyNet-ml (РјРѕРґРµР»Рё, ~120 РњР‘, 1-2 РјРёРЅ)..."
        git clone --quiet --depth 1 $mlRepo $mlDir
    } else {
        Log "AnomalyNet-ml СѓР¶Рµ СЂР°СЃРїР°РєРѕРІР°РЅ (РЅРµ .git-СЂРµРїРѕР·РёС‚РѕСЂРёР№) вЂ” РїСЂРѕРїСѓСЃРєР°РµРј РєР»РѕРЅРёСЂРѕРІР°РЅРёРµ"
    }
    Ok "AnomalyNet-ml РіРѕС‚РѕРІ"
} else {
    if (-not (Test-Path $guiDir)) {
        Err "Git РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ Рё $guiDir РЅРµ РЅР°Р№РґРµРЅ вЂ” РЅРµРІРѕР·РјРѕР¶РЅРѕ РїСЂРѕРґРѕР»Р¶РёС‚СЊ. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Git Рё Р·Р°РїСѓСЃС‚РёС‚Рµ Р·Р°РЅРѕРІРѕ."
    }
    Warn "Git РЅРµРґРѕСЃС‚СѓРїРµРЅ вЂ” СЂРµРїРѕР·РёС‚РѕСЂРёРё РЅРµ РѕР±РЅРѕРІР»РµРЅС‹, РёСЃРїРѕР»СЊР·СѓСЋС‚СЃСЏ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёРµ С„Р°Р№Р»С‹"
}

# в”Ђв”Ђ РЎС‚СЂСѓРєС‚СѓСЂР° РјРѕРґРµР»РµР№ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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
        Warn "$label вЂ” РЅРµ РЅР°Р№РґРµРЅРѕ РІ $src"
    }
}

Copy-ModelDir "$mlDir\model"                              "$modelsDir\stage1\catboost"  "Stage1 РјРѕРґРµР»СЊ (binary)"
Copy-ModelDir "$mlDir\artifacts"                          "$modelsDir\stage1\artifacts" "Stage1 Р°СЂС‚РµС„Р°РєС‚С‹"
Copy-ModelDir "$mlDir\stage2_multiclass\models\catboost"  "$modelsDir\stage2\catboost"  "Stage2 РјРѕРґРµР»СЊ (simple)"
Copy-ModelDir "$mlDir\stage3_cic2023\models\catboost"     "$modelsDir\stage3\catboost"  "Stage3 РјРѕРґРµР»СЊ (advanced)"
Copy-ModelDir "$mlDir\stage3_cic2023\artifacts"           "$modelsDir\stage3\artifacts" "Stage3 Р°СЂС‚РµС„Р°РєС‚С‹"

# в”Ђв”Ђ Python venv + Р·Р°РІРёСЃРёРјРѕСЃС‚Рё в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РќР°СЃС‚СЂРѕР№РєР° Python venv..."
$venvDir  = "$guiDir\backend\.venv"
$venvPy   = "$venvDir\Scripts\python.exe"
$venvPip  = "$venvDir\Scripts\pip.exe"

& $pythonCmd -m venv $venvDir
& $venvPip install --quiet --upgrade pip setuptools wheel
& $venvPip install --quiet -r "$guiDir\backend\requirements.txt"
Ok "Python-Р·Р°РІРёСЃРёРјРѕСЃС‚Рё СѓСЃС‚Р°РЅРѕРІР»РµРЅС‹"

# в”Ђв”Ђ РЎР±РѕСЂРєР° С„СЂРѕРЅС‚РµРЅРґР° в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РЎР±РѕСЂРєР° React-С„СЂРѕРЅС‚РµРЅРґР° (2-4 РјРёРЅ)..."
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
Ok "Р¤СЂРѕРЅС‚РµРЅРґ СЃРѕР±СЂР°РЅ"

# в”Ђв”Ђ РџСЂРѕРІРµСЂРєР° Npcap в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РџСЂРѕРІРµСЂРєР° Npcap..."
$npcapInstalled = Test-Path "C:\Windows\System32\Npcap\wpcap.dll"
if ($npcapInstalled) {
    Ok "Npcap СѓСЃС‚Р°РЅРѕРІР»РµРЅ вЂ” Р°РєС‚РёРІРЅС‹Р№ ARP-СЃРєР°РЅРµСЂ РґРѕСЃС‚СѓРїРµРЅ"
} else {
    Warn "Npcap РЅРµ РЅР°Р№РґРµРЅ вЂ” ARP-СЃРєР°РЅРµСЂ Р±СѓРґРµС‚ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ fallback (arp -a)"
    if ($InstallNpcap) {
        Log "РЎРєР°С‡РёРІР°РµРј Npcap..."
        $npcapUrl  = "https://npcap.com/dist/npcap-1.79.exe"
        $npcapPath = "$env:TEMP\npcap-install.exe"
        try {
            Invoke-WebRequest -Uri $npcapUrl -OutFile $npcapPath -UseBasicParsing
            Log "Р—Р°РїСѓСЃРєР°РµРј СѓСЃС‚Р°РЅРѕРІС‰РёРє Npcap (РїРѕС‚СЂРµР±СѓРµС‚СЃСЏ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ)..."
            Start-Process -FilePath $npcapPath -ArgumentList "/S" -Wait
            Ok "Npcap СѓСЃС‚Р°РЅРѕРІР»РµРЅ"
        } catch {
            Warn "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРєР°С‡Р°С‚СЊ Npcap: $_"
            Warn "РЎРєР°С‡Р°Р№С‚Рµ РІСЂСѓС‡РЅСѓСЋ: https://npcap.com/"
        }
    } else {
        Warn "Р”Р»СЏ Р°РєС‚РёРІРЅРѕРіРѕ ARP-СЃРєР°РЅРёСЂРѕРІР°РЅРёСЏ СѓСЃС‚Р°РЅРѕРІРёС‚Рµ Npcap: https://npcap.com/"
        Warn "РР»Рё РїРѕРІС‚РѕСЂРёС‚Рµ СѓСЃС‚Р°РЅРѕРІРєСѓ СЃ С„Р»Р°РіРѕРј -InstallNpcap"
    }
}

# в”Ђв”Ђ РћРїСЂРµРґРµР»РµРЅРёРµ СЂРµР¶РёРјР° в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
$stage1Cbm = Get-ChildItem "$modelsDir\stage1\catboost\*.cbm" -ErrorAction SilentlyContinue
$runMode     = if ($stage1Cbm) { "windows_live" } else { "mock" }
$activeModel = if ($stage1Cbm) { "catboost-cascade-simple" } else { "mock-default" }
if (-not $stage1Cbm) {
    Warn "РњРѕРґРµР»Рё stage1 РЅРµ РЅР°Р№РґРµРЅС‹ вЂ” Р·Р°РїСѓСЃРєР°РµРј РІ Demo-СЂРµР¶РёРјРµ"
}

# в”Ђв”Ђ Р—Р°РїРёСЃСЊ settings.json в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "Р—Р°РїРёСЃСЊ config\settings.json..."
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
Ok "settings.json Р·Р°РїРёСЃР°РЅ"

# в”Ђв”Ђ РџРµСЂРµРјРµРЅРЅР°СЏ РѕРєСЂСѓР¶РµРЅРёСЏ ANOMALYNET_APP_ROOT в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РЈСЃС‚Р°РЅРѕРІРєР° СЃРёСЃС‚РµРјРЅРѕР№ РїРµСЂРµРјРµРЅРЅРѕР№ ANOMALYNET_APP_ROOT..."
[System.Environment]::SetEnvironmentVariable(
    "ANOMALYNET_APP_ROOT", $guiDir,
    [System.EnvironmentVariableTarget]::Machine)
[System.Environment]::SetEnvironmentVariable(
    "ANOMALYNET_MODELS_ROOT", $modelsDir,
    [System.EnvironmentVariableTarget]::Machine)
Ok "РЎРёСЃС‚РµРјРЅС‹Рµ РїРµСЂРµРјРµРЅРЅС‹Рµ СѓСЃС‚Р°РЅРѕРІР»РµРЅС‹"

# в”Ђв”Ђ РЎРѕР·РґР°РЅРёРµ Р·Р°РґР°С‡Рё РІ Task Scheduler в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РќР°СЃС‚СЂРѕР№РєР° Р°РІС‚РѕР·Р°РїСѓСЃРєР° С‡РµСЂРµР· Task Scheduler..."
$taskName   = "AnomalyNet"
$workingDir = "$guiDir\backend"
$uvicornArgs = "-m uvicorn app.main:app --host 0.0.0.0 --port $Port --log-level info --timeout-graceful-shutdown 3"

# РЈРґР°Р»СЏРµРј СЃС‚Р°СЂСѓСЋ Р·Р°РґР°С‡Сѓ РµСЃР»Рё РµСЃС‚СЊ
schtasks /delete /tn $taskName /f 2>$null

# РЎРѕР·РґР°С‘Рј С‡РµСЂРµР· XML вЂ” РїРѕР·РІРѕР»СЏРµС‚ Р·Р°РґР°С‚СЊ СЂР°Р±РѕС‡СѓСЋ РґРёСЂРµРєС‚РѕСЂРёСЋ Рё РїРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>AnomalyNet IDS вЂ” СЃРµС‚РµРІРѕР№ РјРѕРЅРёС‚РѕСЂРёРЅРі Рё РѕР±РЅР°СЂСѓР¶РµРЅРёРµ РІС‚РѕСЂР¶РµРЅРёР№</Description>
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

$cred = Get-Credential -UserName $env:USERNAME -Message "Р’РІРµРґРёС‚Рµ РїР°СЂРѕР»СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РґР»СЏ Р·Р°РґР°С‡Рё РїР»Р°РЅРёСЂРѕРІС‰РёРєР° (РЅСѓР¶РµРЅ РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ РІС‹СЃРѕРєРёРјРё РїСЂРёРІРёР»РµРіРёСЏРјРё)"
if ($cred) {
    $pass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password))
    schtasks /create /tn $taskName /xml $xmlPath /ru $env:USERNAME /rp $pass /f 2>$null
    Remove-Variable pass -ErrorAction SilentlyContinue
    Ok "Р—Р°РґР°С‡Р° '$taskName' СЃРѕР·РґР°РЅР° РІ Task Scheduler"
} else {
    Warn "РџР°СЂРѕР»СЊ РЅРµ РІРІРµРґС‘РЅ вЂ” Р·Р°РґР°С‡Р° РЅРµ СЃРѕР·РґР°РЅР°. РСЃРїРѕР»СЊР·СѓР№С‚Рµ: schtasks /create /tn AnomalyNet ..."
}
Remove-Item $xmlPath -ErrorAction SilentlyContinue

# в”Ђв”Ђ Р—Р°РїСѓСЃРє СЃРµСЂРІРёСЃР° РїСЂСЏРјРѕ СЃРµР№С‡Р°СЃ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "Р—Р°РїСѓСЃРє AnomalyNet..."
$proc = Start-Process -FilePath $venvPy `
    -ArgumentList $uvicornArgs `
    -WorkingDirectory $workingDir `
    -WindowStyle Hidden `
    -PassThru
Start-Sleep -Seconds 3

# РџСЂРѕРІРµСЂСЏРµРј С‡С‚Рѕ Р·Р°РїСѓСЃС‚РёР»СЃСЏ
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$Port/api/health" -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) {
        Ok "РЎРµСЂРІРёСЃ Р·Р°РїСѓС‰РµРЅ Рё РѕС‚РІРµС‡Р°РµС‚ РЅР° http://localhost:$Port"
    }
} catch {
    Warn "РЎРµСЂРІРёСЃ Р·Р°РїСѓС‰РµРЅ, РЅРѕ РЅРµ РѕС‚РІРµС‡Р°РµС‚ РїРѕРєР° вЂ” РїРѕРґРѕР¶РґРёС‚Рµ 10-15 СЃРµРє"
}

# в”Ђв”Ђ РЇСЂР»С‹РєРё РЅР° СЂР°Р±РѕС‡РµРј СЃС‚РѕР»Рµ Рё РІ РјРµРЅСЋ РџСѓСЃРє в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Log "РЎРѕР·РґР°С‘Рј СЏСЂР»С‹РєРё..."
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

# Р Р°Р±РѕС‡РёР№ СЃС‚РѕР» С‚РµРєСѓС‰РµРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
$desktopPath = [System.Environment]::GetFolderPath("Desktop")
New-UrlShortcut "$desktopPath\$shortcutName" $appUrl $iconPath
Ok "РЇСЂР»С‹Рє РЅР° СЂР°Р±РѕС‡РµРј СЃС‚РѕР»Рµ: $desktopPath\$shortcutName"

# РњРµРЅСЋ РџСѓСЃРє вЂ” Programs
$startMenuPath = [System.Environment]::GetFolderPath("Programs")
$startMenuDir  = "$startMenuPath\AnomalyNet"
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
New-UrlShortcut "$startMenuDir\$shortcutName" $appUrl $iconPath
Ok "РЇСЂР»С‹Рє РІ РјРµРЅСЋ РџСѓСЃРє: $startMenuDir\$shortcutName"

# в”Ђв”Ђ РС‚РѕРі в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
Write-Host ""
Write-Host "  +=======================================+" -ForegroundColor Green
Write-Host "  |       РЈСЃС‚Р°РЅРѕРІРєР° Р·Р°РІРµСЂС€РµРЅР°!            |" -ForegroundColor Green
Write-Host "  +=======================================+" -ForegroundColor Green
Write-Host ""
Write-Host "  Р’РµР±-РёРЅС‚РµСЂС„РµР№СЃ  : " -NoNewline; Write-Host $appUrl -ForegroundColor Green
Write-Host "  API health     : $appUrl/api/health"
Write-Host "  РљР°С‚Р°Р»РѕРі        : $InstallDir"
Write-Host "  Р РµР¶РёРј          : $runMode / $activeModel"
Write-Host ""
Write-Host "  РЇСЂР»С‹Рє СЃРѕР·РґР°РЅ РЅР° Р Р°Р±РѕС‡РµРј СЃС‚РѕР»Рµ Рё РІ РјРµРЅСЋ РџСѓСЃРє." -ForegroundColor Cyan
Write-Host "  Р”РІРѕР№РЅРѕР№ РєР»РёРє вЂ” РѕС‚РєСЂРѕРµС‚ Р±СЂР°СѓР·РµСЂ РЅР° $appUrl" -ForegroundColor Cyan
Write-Host ""
if (-not $stage1Cbm) {
    Write-Host "  Р’РќРРњРђРќРР•: РњРѕРґРµР»Рё РЅРµ РЅР°Р№РґРµРЅС‹ вЂ” СЂР°Р±РѕС‚Р°РµС‚ Demo-СЂРµР¶РёРј." -ForegroundColor Yellow
    Write-Host "  РџРѕР»РѕР¶РёС‚Рµ РјРѕРґРµР»Рё РІ $modelsDir Рё РїРµСЂРµР№РґРёС‚Рµ РІ Settings." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  РЈРїСЂР°РІР»РµРЅРёРµ:"
Write-Host "    Р—Р°РїСѓСЃС‚РёС‚СЊ     : schtasks /run /tn AnomalyNet"
Write-Host "    РћСЃС‚Р°РЅРѕРІРёС‚СЊ    : taskkill /f /im python.exe  (РѕСЃС‚РѕСЂРѕР¶РЅРѕ!)"
Write-Host "    РЈРґР°Р»РёС‚СЊ       : powershell -File scripts\uninstall-windows.ps1"
Write-Host ""
