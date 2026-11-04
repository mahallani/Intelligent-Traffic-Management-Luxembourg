"""Diagnostic of the SUMO launch used by the control application (added 2026-10-15).

Starts SUMO exactly as the application does (Kirchberg scenario, S0, x1, seed 1) through the project's
TraCI launcher, without GUI and then with sumo-gui, runs 30 simulated seconds and closes it.
For each launch it records: command line, exit code (decoded), SUMO's own messages, SUMO log.
Report: data/reports/windows_validation/sumo_launch_diag_<date>.log (a new file each time, nothing overwritten).
Run outputs: sumo/lust_4_intersections/output/diagnostics/<date>_<mode>/

    python scripts\\windows\\diagnose_sumo_launch.py            # without and with sumo-gui (a window opens ~5 s)
    python scripts\\windows\\diagnose_sumo_launch.py --no-gui   # without sumo-gui only
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.common.sim_env import BEGIN, SCENARIO_DIR, SimEnv, libsumo_status  # noqa: E402
from traci_layer.config import find_sumo_binary  # noqa: E402
from traci_layer.launcher import SumoStartError  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "windows_validation"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-gui", action="store_true")
    a = p.parse_args(argv)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"sumo_launch_diag_{stamp}.log"
    lines: list[str] = []

    def log(text=""):
        print(text, flush=True)
        lines.append(str(text))

    log(f"SUMO launch diagnostic - {datetime.now().isoformat(timespec='seconds')} - {ROOT}")
    log(f"python: {sys.executable} {sys.version.split()[0]}")
    log(f"SUMO_HOME: {os.environ.get('SUMO_HOME')}")
    for var in ("PROJ_LIB", "PROJ_DATA", "PYTHONPATH", "ITM_SUMO_BACKEND"):
        log(f"{var}: {os.environ.get(var)}")
    suspicious = [d for d in os.environ.get("PATH", "").split(os.pathsep)
                  if any(k in d.lower() for k in ("sumo", "proj", "osgeo", "qgis", "conda", "gdal", "xerces", "postgres"))]
    log("PATH entries that may hold SUMO-related DLLs: " + (" | ".join(suspicious) or "none"))
    for gui in (False, True):
        b = find_sumo_binary(gui)
        log(f"{'sumo-gui' if gui else 'sumo'} binary: {b} (exists: {Path(b).exists()})")
    try:
        r = subprocess.run([find_sumo_binary(False), "--version"], capture_output=True, text=True, timeout=30)
        log(f"sumo --version -> exit {r.returncode}: {(r.stdout or r.stderr).strip().splitlines()[:1]}")
    except Exception as exc:  # noqa: BLE001
        log(f"sumo --version -> FAILED: {exc}")
    log(f"libsumo: {libsumo_status()}")

    ok_all = True
    for gui in ([False] if a.no_gui else [False, True]):
        mode = "sumo-gui" if gui else "sumo"
        out = SCENARIO_DIR / "output" / "diagnostics" / f"{stamp}_{mode}"
        log("")
        log(f"===== launch {mode} (TraCI), outputs in {out}")
        env = SimEnv(scale=1.0, seed=1, out_dir=out, gui=gui, use_libsumo=False, end=BEGIN + 30, label=f"diag_{mode}_{stamp}")
        try:
            env.start()
            while not env.done():
                env.step()
            log(f"OK: simulated time {env.time}, vehicles {env.api.vehicle.getIDCount()}, signals {sorted(env.tls)}")
        except SumoStartError as exc:
            ok_all = False
            d = exc.as_dict()
            log(f"FAILED: {d['error']}")
            log(f"exit code: {d['returncode_meaning']}  launches: {d['launches']}")
            log(f"command: {subprocess.list2cmdline(d['command'])}")
            log("SUMO output (tail):")
            log(d["sumo_output_tail"] or "(none)")
        except Exception as exc:  # noqa: BLE001
            ok_all = False
            log(f"FAILED: {type(exc).__name__}: {exc}")
        finally:
            env.close()
        for name in ("sumo_process.log", "sumo.log"):
            f = out / name
            log(f"--- {name}: " + ("absent" if not f.exists() else ""))
            if f.exists():
                log(f.read_text(encoding="utf-8", errors="replace")[-3000:])
    log("")
    log("RESULT: " + ("all launches OK" if ok_all else "at least one launch FAILED (see above)"))
    with open(report, "x", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nReport written to {report}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
