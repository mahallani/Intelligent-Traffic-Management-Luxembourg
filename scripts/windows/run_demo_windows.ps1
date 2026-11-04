# Graphical demonstration: the RL agent controls the 4 Kirchberg signals in sumo-gui.
# Usage (PowerShell, project root):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\run_demo_windows.ps1            # demand x5, 100 ms per step (~6 min)
#   powershell -ExecutionPolicy Bypass -File scripts\windows\run_demo_windows.ps1 -Delay 50 -Scale 1
# Output (new folder per run, never overwritten): sumo\lust_4_intersections\output\experiments_demo_<date>\
#   decisions.csv = every phase change decided by the agent; kpis.json; queue_timeseries.csv
param([double]$Scale = 5, [double]$Delay = 100, [string]$Strategy = "S3_rl_qlearning")
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$env:PYTHONDONTWRITEBYTECODE = "1"
$tag = "demo_" + (Get-Date -Format "yyyyMMdd_HHmmss")
$logDir = Join-Path $root "data\reports\windows_validation"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "$tag.log"
"Demo $Strategy x$Scale delay=$Delay ms - $(Get-Date -Format s)" | Tee-Object -FilePath $log
python -u scripts\simulation\run_experiment.py --strategy $Strategy --scale $Scale --seeds 1 --tag $tag --gui --gui-delay $Delay --progress 60 2>&1 |
    ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
"exit code: $LASTEXITCODE - outputs: sumo\lust_4_intersections\output\experiments_$tag" | Tee-Object -FilePath $log -Append
