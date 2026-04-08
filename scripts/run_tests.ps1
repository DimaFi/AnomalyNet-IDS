$backendDir = Join-Path $PSScriptRoot "..\\backend"
$venvPython = Join-Path $backendDir ".venv\\Scripts\\python.exe"
Set-Location $backendDir
& $venvPython -m pytest
Set-Location $PSScriptRoot\..\frontend
npm run test
