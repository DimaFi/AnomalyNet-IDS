<#
.SYNOPSIS
    Build the offline wheel set used by the installers' offline fallback.

.DESCRIPTION
    Downloads prebuilt wheels for every dependency in backend/requirements.txt
    for the installer's target Python (3.11, win_amd64) and packs them into
    dist-wheels/wheels-win-py311.zip.

    Run this on ANY machine with internet (pypi access) — it does NOT need
    Python 3.11 itself, pip cross-downloads for the target version.

    Then upload the resulting zip to the GitHub Release:
        repo:  DimaFi/AnomalyNet-IDS
        tag:   deps-py311
        asset: wheels-win-py311.zip   (exact name — the installers fetch this URL)

    The installers download it automatically when pypi is unreachable
    (typical for RU networks: ConnectionReset 10054).

.USAGE
    cd AppCode
    .\installers\shared\build_wheels.ps1
#>
param(
    [string]$PyVersion = "3.11",
    [string]$Platform  = "win_amd64"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$req  = Join-Path $root "backend\requirements.txt"
$out  = Join-Path $root "dist-wheels\win-py311"
$zip  = Join-Path $root "dist-wheels\wheels-win-py311.zip"

Write-Host "Downloading wheels for Python $PyVersion / $Platform ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $out | Out-Null

python -m pip download -r $req -d $out `
    --only-binary=:all: --python-version $PyVersion --platform $Platform `
    --timeout 60 --retries 5
if ($LASTEXITCODE -ne 0) { throw "pip download failed" }

Write-Host "Packing $zip ..." -ForegroundColor Cyan
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$out\*" -DestinationPath $zip -CompressionLevel Optimal

$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Done: $zip ($mb MB, $((Get-ChildItem "$out\*.whl").Count) wheels)" -ForegroundColor Green
Write-Host "Upload it to the 'deps-py311' GitHub Release as 'wheels-win-py311.zip'." -ForegroundColor Yellow
