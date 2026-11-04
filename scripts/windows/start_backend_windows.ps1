# Start the application backend (FastAPI: API under /api + built frontend) with a diagnostic first (2026-10-29).
# It explains WHY the backend is not reachable instead of failing silently:
#   python missing, Python packages missing, backend import error (exact traceback), port already used, frontend not built.
#
# Usage (PowerShell, from any folder):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\start_backend_windows.ps1              # check, then start on 8000
#   powershell -ExecutionPolicy Bypass -File scripts\windows\start_backend_windows.ps1 -CheckOnly   # diagnostic only
#   powershell -ExecutionPolicy Bypass -File scripts\windows\start_backend_windows.ps1 -Port 8010   # other port
# The development frontend (npm run dev, port 3000) calls the backend on port 8000.
# Stop the backend: Ctrl+C in this window (an active simulation is stopped cleanly and its outputs are written).
# Messages are ASCII on purpose (Windows PowerShell 5.1 reads scripts in the local code page).
param([int]$Port = 8000, [switch]$CheckOnly)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
Write-Host "Project folder : $root"

# 1. Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "FAILED: 'python' is not in the PATH of this window."
    exit 1
}
Write-Host ("Python         : " + (& python --version 2>&1))

# 2. Python packages needed by the backend
$missing = & python -c "import importlib.util as u; print(' '.join(m for m in ['fastapi','uvicorn','traci','sumolib','numpy'] if not u.find_spec(m)))"
if ($missing) {
    Write-Host "FAILED: missing Python packages: $missing"
    Write-Host "  -> python -m pip install -r requirements.txt"
    exit 1
}
Write-Host "Packages       : OK"

# 3. Import of the backend module (shows the exact error, e.g. a syntax or import error)
$importOutput = & python -c "import app.backend.server" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: the backend cannot be imported (the server would stop at once):"
    $importOutput | Select-Object -Last 15 | ForEach-Object { Write-Host "   $_" }
    exit 1
}
Write-Host "Backend import : OK"

# 4. Port
$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    $ownerId = ($listen | Select-Object -First 1).OwningProcess
    $owner = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 5
        Write-Host "The backend is ALREADY running on port $Port (process $ownerId $($owner.ProcessName)), simulation: $($health.simulation)."
        Write-Host "  Interface: http://127.0.0.1:$Port/   XAI: http://127.0.0.1:$Port/xai/"
        exit 0
    } catch {
        Write-Host "FAILED: port $Port is used by another program (process $ownerId $($owner.ProcessName)) that is not this backend."
        Write-Host "  -> close that program, or use -Port 8010 (the dev frontend on port 3000 expects 8000)."
        exit 1
    }
}
Write-Host "Port $Port      : free"

# 5. Built frontend (served by the backend on the same port)
if (Test-Path "app\frontend\out\index.html") {
    Write-Host "Frontend       : app\frontend\out found (rebuild with 'npm run build' in app\frontend after a frontend change)"
} else {
    Write-Host "WARNING: app\frontend\out is missing: the API will work, the pages will not be served on this port."
    Write-Host "  -> cd app\frontend ; npm run build     (or run 'npm run dev' there and open http://localhost:3000/)"
}

if ($CheckOnly) {
    Write-Host "Diagnostic finished (-CheckOnly): nothing was started."
    exit 0
}

$env:PYTHONDONTWRITEBYTECODE = "1"
Write-Host ""
Write-Host "Starting: python -m app.backend.server --port $Port --no-browser   (Ctrl+C to stop)"
Write-Host "  Interface: http://127.0.0.1:$Port/   XAI: http://127.0.0.1:$Port/xai/   API: http://127.0.0.1:$Port/api/health"
& python -m app.backend.server --port $Port --no-browser
exit $LASTEXITCODE
