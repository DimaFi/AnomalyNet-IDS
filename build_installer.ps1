<#
.SYNOPSIS
    Build AnomalyNet installer archive (AnomalyNet-v1.0-win64.zip)

.DESCRIPTION
    1. Builds the React frontend  (npm run build)
    2. Installs Python deps + PyInstaller into a temp venv
    3. Runs PyInstaller → single AnomalyNet.exe (~80-120 MB)
    4. Packages exe + model files + default config into a ZIP

.REQUIREMENTS
    - Python 3.10+ in PATH
    - Node 18+ in PATH
    - Internet access (pip, npm)

.USAGE
    cd AppCode
    .\build_installer.ps1

    Optional: pass model path
    .\build_installer.ps1 -ModelDir "G:\Диплом\IoT\stage1_v2_cl"
#>

param(
    [string]$ModelDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ROOT     = $PSScriptRoot                           # AppCode/
$BACKEND  = Join-Path $ROOT "backend"
$FRONTEND = Join-Path $ROOT "frontend"
$OUT      = Join-Path $ROOT "installer"
$VENV     = Join-Path $BACKEND ".venv_build"

function Log($msg) { Write-Host "► $msg" -ForegroundColor Cyan }
function OK($msg)  { Write-Host "✓ $msg" -ForegroundColor Green }
function Err($msg) { Write-Host "✗ $msg" -ForegroundColor Red; exit 1 }

# ── 0. Clean output dir ────────────────────────────────────────
Log "Cleaning output dir..."
if (Test-Path $OUT) { Remove-Item $OUT -Recurse -Force }
New-Item $OUT -ItemType Directory | Out-Null

# ── 1. Build frontend ──────────────────────────────────────────
Log "Building frontend (npm run build)..."
Push-Location $FRONTEND
    npm install --silent
    npm run build
    if ($LASTEXITCODE -ne 0) { Err "Frontend build failed" }
Pop-Location
OK "Frontend built → frontend/dist"

# ── 2. Create build venv ───────────────────────────────────────
Log "Creating build venv..."
python -m venv $VENV
$PIP = Join-Path $VENV "Scripts\pip.exe"
$PY  = Join-Path $VENV "Scripts\python.exe"

& $PIP install --quiet --upgrade pip
& $PIP install --quiet -r (Join-Path $BACKEND "requirements.txt")
& $PIP install --quiet pyinstaller
OK "Build venv ready"

# ── 3. Run PyInstaller ─────────────────────────────────────────
Log "Running PyInstaller (this takes 1-3 min)..."
Push-Location $BACKEND
    & $PY -m PyInstaller anomalynet.spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { Err "PyInstaller failed" }
Pop-Location
OK "PyInstaller done → backend/dist/AnomalyNet.exe"

$EXE = Join-Path $BACKEND "dist\AnomalyNet.exe"
if (-not (Test-Path $EXE)) { Err "AnomalyNet.exe not found after build" }

# ── 4. Assemble release folder ─────────────────────────────────
Log "Assembling release folder..."
$RELEASE = Join-Path $OUT "AnomalyNet"
New-Item $RELEASE -ItemType Directory | Out-Null

# Exe
Copy-Item $EXE $RELEASE

# Model files (optional — user can add manually)
if ($ModelDir -and (Test-Path $ModelDir)) {
    Log "Copying model files from $ModelDir..."
    $ML_SRC = Join-Path $ModelDir "models\catboost"
    $ART_SRC = Join-Path $ModelDir "artifacts"

    if (Test-Path $ML_SRC) {
        $ML_DEST = Join-Path $RELEASE "model"
        New-Item $ML_DEST -ItemType Directory | Out-Null
        Copy-Item "$ML_SRC\model.cbm"    $ML_DEST
        Copy-Item "$ML_SRC\metrics.json" $ML_DEST -ErrorAction SilentlyContinue
    }
    if (Test-Path $ART_SRC) {
        $ART_DEST = Join-Path $RELEASE "artifacts"
        New-Item $ART_DEST -ItemType Directory | Out-Null
        Copy-Item "$ART_SRC\feature_contract.json"    $ART_DEST
        Copy-Item "$ART_SRC\preprocessing_params.json" $ART_DEST
        Copy-Item "$ART_SRC\scaler.joblib"             $ART_DEST
    }
    OK "Model files copied"
} else {
    Log "No -ModelDir provided — model files not bundled (add manually)"
}

# Default config
$CFG_SRC  = Join-Path $ROOT "config"
$CFG_DEST = Join-Path $RELEASE "config"
New-Item $CFG_DEST -ItemType Directory | Out-Null
Copy-Item (Join-Path $CFG_SRC "settings.json")        $CFG_DEST
Copy-Item (Join-Path $CFG_SRC "models_registry.json") $CFG_DEST

# README for the archive
@"
# AnomalyNet v1.0 — Windows

## Quick start
1. Run AnomalyNet.exe (double-click)
2. Browser opens automatically at http://127.0.0.1:8000
3. Default mode: mock (demo) — no capture hardware required

## To use live capture + CatBoost model
1. Install Npcap: https://npcap.com/#download
2. Download the model from https://github.com/DimaFi/AnomalyNet-ml
   and place model/ and artifacts/ folders next to AnomalyNet.exe
3. Edit config\settings.json:
   - set run_mode to "linux_live"
   - set catboost_model_dir to the path of the model\ folder
   - set preprocessing_artifacts_dir to the artifacts\ folder
   - set interface_name to your network adapter name

## Folders
  AnomalyNet.exe       — main application
  config\              — settings (edit to configure)
  model\               — model.cbm (if bundled)
  artifacts\           — preprocessing files (if bundled)
"@ | Set-Content (Join-Path $RELEASE "README.txt") -Encoding UTF8

OK "Release folder ready at $RELEASE"

# ── 5. Create ZIP ──────────────────────────────────────────────
Log "Creating ZIP archive..."
$ZIP = Join-Path $OUT "AnomalyNet-v1.0-win64.zip"
Compress-Archive -Path $RELEASE -DestinationPath $ZIP -Force
OK "Archive created: $ZIP"

$SIZE = [math]::Round((Get-Item $ZIP).Length / 1MB, 1)
Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor White
Write-Host "  AnomalyNet installer ready!" -ForegroundColor Green
Write-Host "  $ZIP ($SIZE MB)" -ForegroundColor White
Write-Host "══════════════════════════════════════════" -ForegroundColor White
