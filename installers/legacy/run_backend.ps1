$backendDir = Join-Path $PSScriptRoot "..\\backend"
$venvPython = Join-Path $backendDir ".venv\\Scripts\\python.exe"
Set-Location $backendDir
& $venvPython -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
