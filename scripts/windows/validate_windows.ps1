# Validation of the project on Windows (read-only checks + tests + scenario validation).
# Usage (PowerShell, project root):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\validate_windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\windows\validate_windows.ps1 -SkipLust     # faster (no full LuST test)
# Writes a log to data\reports\windows_validation\validation_<date>.log  (nothing is deleted or overwritten)
param([switch]$SkipLust)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = Join-Path $root "data\reports\windows_validation"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "validation_$stamp.log"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONIOENCODING = "utf-8"

function Log([string]$text) { $text | Tee-Object -FilePath $log -Append | Out-Host }
function Run([string]$title, [scriptblock]$cmd) {
    Log ""
    Log "===== $title ====="
    $t0 = Get-Date
    & $cmd 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append | Out-Host
    Log ("exit code: {0}   duration: {1:N0} s" -f $LASTEXITCODE, ((Get-Date) - $t0).TotalSeconds)
}

Log "Windows validation - $(Get-Date -Format s) - $root"
Run "Windows / PowerShell" { [System.Environment]::OSVersion.VersionString; $PSVersionTable.PSVersion.ToString() }
Run "Python" { python --version; python -c "import sys; print(sys.executable)" }
Run "SUMO_HOME and binaries" {
    "SUMO_HOME=$env:SUMO_HOME"
    $cands = @()
    if ($env:SUMO_HOME) { $cands += (Join-Path $env:SUMO_HOME "bin\sumo.exe") }
    $cands += "C:\Program Files (x86)\Eclipse\Sumo\bin\sumo.exe", "C:\Program Files\Eclipse\Sumo\bin\sumo.exe"
    foreach ($c in $cands) { "{0} -> {1}" -f $c, (Test-Path $c) }
    $w = Get-Command sumo -ErrorAction SilentlyContinue; "sumo in PATH: $($w.Source)"
    $g = Get-Command sumo-gui -ErrorAction SilentlyContinue; "sumo-gui in PATH: $($g.Source)"
}
Run "SUMO version" { python -c "import sys; sys.path.insert(0,'.'); from traci_layer.config import find_sumo_binary; import subprocess; b=find_sumo_binary(); print(b); print(subprocess.run([b,'--version'],capture_output=True,text=True).stdout.splitlines()[0])" }
Run "Python packages" { python scripts\windows\check_packages.py }
Run "TraCI quick start (60 s of the Kirchberg scenario)" { python -c "import sys; sys.path.insert(0,'.'); from agents.common.sim_env import SimEnv, BEGIN; e=SimEnv(scale=1.0, seed=1, end=BEGIN+60, use_libsumo=False); e.start(); [e.step() for _ in range(60)]; print('TraCI OK - time', e.time, '- vehicles', e.api.vehicle.getIDCount(), '- signals', sorted(e.tls)); e.close()" }
# libsumo compared with TraCI in its OWN Python process (2026-10-22): in the full suite, pandas (imported by
# tests/test_data_quality.py at collection) loads pyarrow and its Arrow DLL first, and libsumo then fails to load
# (0xc0000139 / "DLL load failed"). Run alone, this test shows whether libsumo itself works on this PC.
# The verdict reads ONLY the log lines written by this step (lines after $logLinesBefore) and the real pytest exit code.
$logLinesBefore = @(Get-Content -LiteralPath $log).Count
Run "libsumo vs TraCI test (separate Python process, pandas/pyarrow not loaded)" { python -m pytest -p no:cacheprovider "tests/test_synthetic.py::test_libsumo_gives_identical_results" -v -rs }
$libsumoExit = $LASTEXITCODE
$libsumoSection = @(Get-Content -LiteralPath $log | Select-Object -Skip $logLinesBefore)
$libsumoSummaries = @($libsumoSection | Select-String -CaseSensitive -Pattern '^=+ .*\b(passed|failed|skipped|error|errors|no tests ran)\b.*=+$')
if ($libsumoSummaries.Count -eq 1) { $libsumoSummary = $libsumoSummaries[0].Line } else { $libsumoSummary = "<$($libsumoSummaries.Count) pytest summary lines in this step: missing or ambiguous>" }
if (($libsumoExit -eq 0) -and ($libsumoSummaries.Count -eq 1) -and ($libsumoSummary -match '\b1 passed\b') -and ($libsumoSummary -notmatch 'skipped|failed|error|xfail|xpass|deselected|no tests ran')) {
    $libsumoVerdict = "PASSED - libsumo gives the same results as TraCI on this PC (separate process)"
} else {
    $libsumoVerdict = "NOT VALIDATED - exit code $libsumoExit, pytest summary: $libsumoSummary"
}
Log "RESULT libsumo isolated test: $libsumoVerdict"
$deselect = "--deselect=tests/test_synthetic.py::test_libsumo_gives_identical_results"   # evaluated in the step above
if ($SkipLust) {
    Run "pytest (all tests except full LuST and the libsumo test run above)" { python -m pytest -p no:cacheprovider tests -q --ignore=tests/test_lust_integration.py $deselect }
} else {
    Run "pytest (all tests except the libsumo test run above)" { python -m pytest -p no:cacheprovider tests -q $deselect }
}
$suiteExit = $LASTEXITCODE
Run "SUMO launch diagnostic (exact command of the application, sumo then sumo-gui)" { python scripts\windows\diagnose_sumo_launch.py }
Run "SUMO launch / TraCI life-cycle tests forced to TraCI (as the application on this PC)" { $env:ITM_SUMO_BACKEND = "traci"; python -m pytest -p no:cacheprovider tests/test_sumo_launch.py tests/test_app_api.py -v; Remove-Item Env:ITM_SUMO_BACKEND }
Run "Application, agents, safety and cascade tests (detail)" { python -m pytest -p no:cacheprovider tests/test_app_api.py tests/test_demo_scenarios.py tests/test_ambulance_tracking.py tests/test_safety_emergency.py tests/test_cascade.py tests/test_agents.py -v }
Run "Application backend: real HTTP start/stop of the server" { python -c "import sys,threading,time,urllib.request,json; sys.path.insert(0,'.'); import uvicorn; from app.backend.server import create_app; s=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8765,log_level='warning')); th=threading.Thread(target=s.run,daemon=True); th.start(); time.sleep(4); print('health', urllib.request.urlopen('http://127.0.0.1:8765/api/health').read().decode()); print('index.html', urllib.request.urlopen('http://127.0.0.1:8765/').status); s.should_exit=True; th.join(10); print('server stopped:', not th.is_alive())" }
Run "Scenario validation (8 checks + strategies S0..S3)" { python sumo\lust_4_intersections\scripts\validate_scenario.py }
Log ""
Log "SUMMARY libsumo isolated test: $libsumoVerdict"
Log ("SUMMARY full pytest suite (libsumo test excluded, see above): exit code {0}" -f $suiteExit)
Log "Log written to $log"
