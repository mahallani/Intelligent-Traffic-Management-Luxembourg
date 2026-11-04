"""Shared fixtures. Run all tests from the project root:  python -m pytest -v"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from traci_layer.config import DEFAULT_SUMOCFG  # noqa: E402


def _sumo_tool(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    if os.environ.get("SUMO_HOME"):
        cand = Path(os.environ["SUMO_HOME"]) / "bin" / exe
        if cand.exists():
            return str(cand)
    found = shutil.which(name)
    if found:
        return found
    win = Path(r"C:\Program Files (x86)\Eclipse\Sumo\bin") / exe
    return str(win) if win.exists() else None


lust_available = pytest.mark.skipif(not DEFAULT_SUMOCFG.exists(), reason="LuST scenario not installed (run setup_lust.ps1)")


ROUTES = """<routes>
    <vType id="car" vClass="passenger" accel="2.6" decel="4.5" sigma="0.5" length="5" maxSpeed="30"/>
    <vType id="bus" vClass="bus" accel="1.2" decel="4" sigma="0" length="12" maxSpeed="20"/>
    <flow id="ew" type="car" begin="0" end="240" period="5" from="A0B0" to="C1C2" departSpeed="max"/>
    <flow id="ns" type="car" begin="0" end="240" period="7" from="A2A1" to="B0C0" departSpeed="max"/>
    <flow id="cr" type="car" begin="0" end="240" period="9" from="C2B2" to="A1A0" departSpeed="max"/>
    <vehicle id="L1_0" type="bus" depart="10">
        <route edges="A0B0 B0C0 C0C1"/>
        <stop busStop="stopB" duration="20"/>
    </vehicle>
    <vehicle id="L1_1" type="bus" depart="70">
        <route edges="A0B0 B0C0 C0C1"/>
        <stop busStop="stopB" duration="20"/>
    </vehicle>
</routes>
"""

ADDITIONAL = """<additional>
    <busStop id="stopB" lane="B0C0_0" startPos="60" endPos="80" lines="L1"/>
</additional>
"""


@pytest.fixture(scope="session")
def synthetic_scenario(tmp_path_factory) -> Path:
    """3x3 signalised grid (200 m blocks) with car flows, 2 buses and a bus stop."""
    netgen = _sumo_tool("netgenerate")
    if netgen is None:
        pytest.skip("netgenerate not found (SUMO not installed?)")
    d = tmp_path_factory.mktemp("grid")
    subprocess.run([netgen, "--grid", "--grid.number", "3", "--grid.length", "200",
                    "--default-junction-type", "traffic_light", "--default.lanenumber", "2",
                    "--no-turnarounds", "true", "-o", str(d / "grid.net.xml")],
                   check=True, capture_output=True)
    (d / "grid.rou.xml").write_text(ROUTES)
    (d / "grid.add.xml").write_text(ADDITIONAL)
    (d / "grid.sumocfg").write_text("""<configuration>
    <input>
        <net-file value="grid.net.xml"/>
        <route-files value="grid.rou.xml"/>
        <additional-files value="grid.add.xml"/>
    </input>
    <time><begin value="0"/><step-length value="1"/></time>
</configuration>
""")
    return d / "grid.sumocfg"
