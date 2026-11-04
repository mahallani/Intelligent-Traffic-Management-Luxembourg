# Start the control application (backend + built frontend) on http://127.0.0.1:8000
# Usage (PowerShell, project root):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\run_app_windows.ps1
# Stop: Ctrl+C in this window (an active simulation is stopped and its partial outputs are written).
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$env:PYTHONDONTWRITEBYTECODE = "1"
$missing = python -c "import importlib.util as u; print(' '.join(m for m in ['fastapi','uvicorn','traci','sumolib','numpy'] if not u.find_spec(m)))"
if ($missing) {
    Write-Host "Missing Python packages: $missing"
    Write-Host "Install them with:  python -m pip install -r requirements.txt"
    exit 1
}
if (-not (Test-Path "app\frontend\out\index.html")) {
    Write-Host "Frontend not built (app\frontend\out missing). With Node.js: cd app\frontend; npm install; npm run build"
    exit 1
}
python -m app.backend.server
