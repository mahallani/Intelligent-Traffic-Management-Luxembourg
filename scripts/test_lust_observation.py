"""
Real test of the TraCI observation layer on LuST Luxembourg (dua.actuated.sumocfg).

Run from the project root:

    python scripts/test_lust_observation.py                    # 00:00 -> 00:05, report every 100 s
    python scripts/test_lust_observation.py --start-at 25200 --duration 900 --interval 300
    python scripts/test_lust_observation.py --gui              # same, in sumo-gui

All options of ``python -m traci_layer --help`` are accepted.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from traci_layer.__main__ import main  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--duration" not in args:
        args += ["--duration", "300"]
    if "--interval" not in args:
        args += ["--interval", "100"]
    sys.exit(main(args))
