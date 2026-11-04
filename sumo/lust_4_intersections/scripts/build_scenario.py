"""
Build the reduced "Kirchberg - 4 signalised intersections" scenario from LuST.

The generated files are already provided in this folder; re-running this script is only
needed to rebuild them (e.g. another time window). LuST itself is never modified.

Steps
-----
1. area      : 4 consecutive signals of Avenue J.F. Kennedy (Kirchberg) + streets within
               250 m, + every approach of the 4 signals (keeps their programs intact),
               + a short secondary-road loop used by through traffic.
2. network   : netconvert --keep-edges.input-file (neighbouring signals -14384/-13608
               become plain boundary nodes with --tls.unset)
3. demand    : (optional, slow ~7 min) full LuST run 07:00 -> 08:30 from a saved state
               with --vehroute-output.exit-times, then the real routes are cut to the
               area with SUMO's cutRoutes.py and the real area-entry time of every vehicle
               is recomputed from the exit times (see fix_entry_times()).
4. config    : vehicle types, bus stops, .sumocfg

Usage (PowerShell, from the project root):
    python sumo\\lust_4_intersections\\scripts\\build_scenario.py              # rebuild net + routes from cached vehroutes
    python sumo\\lust_4_intersections\\scripts\\build_scenario.py --run-lust --state data\\states\\lust_0700.xml.gz
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]                 # sumo/lust_4_intersections
PROJECT_ROOT = HERE.parents[1]
LUST = Path(os.environ.get("LUST_SCENARIO_DIR", PROJECT_ROOT / "LuSTScenario" / "scenario"))

# ---------------------------------------------------------------- area definition
SIGNALS = ["-28692", "-23354", "-20484", "-29958"]          # SW -> NE along Avenue J.F. Kennedy
MARGIN_M = 250.0
NEIGHBOUR_SIGNALS_TO_UNSET = ["-14384", "-13608"]           # end nodes of the avenue approaches
EXTRA_EDGES = ["--30596#1", "--30596#0", "-30596#1", "-31800"]  # secondary loop (no signal)
WINDOW = (25200.0, 28800.0)                                 # 07:00 - 08:00 (area entry times)

NET = HERE / "net" / "kirchberg_4tls.net.xml"
KEEP = HERE / "net" / "keep_edges.txt"
ROUTES = HERE / "routes" / "kirchberg_0700_0800.rou.xml"
STOPS = HERE / "additional" / "busstops_kirchberg.add.xml"
VTYPES = HERE / "additional" / "vtypes.add.xml"
EMERGENCY = HERE / "additional" / "emergency_vtypes.add.xml"
CACHE = HERE / "build_cache"


def sumo_home() -> Path:
    if os.environ.get("SUMO_HOME"):
        return Path(os.environ["SUMO_HOME"])
    try:
        import sumo  # pip package eclipse-sumo
        return Path(sumo.SUMO_HOME)
    except ImportError:
        return Path(r"C:\Program Files (x86)\Eclipse\Sumo")


def binary(name: str) -> str:
    exe = name + (".exe" if os.name == "nt" else "")
    cand = sumo_home() / "bin" / exe
    return str(cand) if cand.exists() else (shutil.which(name) or name)


# ------------------------------------------------------------------ 1. area
def select_edges() -> list[str]:
    import sumolib

    net = sumolib.net.readNet(str(LUST / "lust.net.xml"))
    xs = [net.getNode(n).getCoord()[0] for n in SIGNALS]
    ys = [net.getNode(n).getCoord()[1] for n in SIGNALS]
    x0, x1, y0, y1 = min(xs) - MARGIN_M, max(xs) + MARGIN_M, min(ys) - MARGIN_M, max(ys) + MARGIN_M
    inside = {n.getID() for n in net.getNodes() if x0 <= n.getCoord()[0] <= x1 and y0 <= n.getCoord()[1] <= y1}
    keep = {e.getID() for e in net.getEdges() if e.getFromNode().getID() in inside and e.getToNode().getID() in inside}
    for n in SIGNALS:  # every approach / exit of the 4 signals -> programs stay identical
        keep |= {e.getID() for e in net.getNode(n).getIncoming() + net.getNode(n).getOutgoing()}
    keep |= set(EXTRA_EDGES)
    return sorted(keep)


# --------------------------------------------------------------- 2. network
def build_network(edges: list[str]) -> None:
    KEEP.parent.mkdir(parents=True, exist_ok=True)
    KEEP.write_text("\n".join(edges) + "\n")
    subprocess.run([binary("netconvert"), "-s", str(LUST / "lust.net.xml"),
                    "--keep-edges.input-file", str(KEEP),
                    "--tls.unset=" + ",".join(NEIGHBOUR_SIGNALS_TO_UNSET),
                    "--remove-edges.isolated", "true", "--keep-edges.components", "1",
                    "--no-warnings", "true", "-o", str(NET)], check=True)


# ---------------------------------------------------------------- 3. demand
def run_lust(state: Path, out: Path) -> None:
    """Full LuST run 07:00 -> 08:30 recording every route with edge exit times."""
    subprocess.run([binary("sumo"), "-c", str(LUST / "dua.actuated.sumocfg"), "--load-state", str(state),
                    "--begin", "25200", "--end", "30600",
                    "--vehroute-output", str(out), "--vehroute-output.exit-times", "true",
                    "--vehroute-output.write-unfinished", "true",
                    "--summary-output", str(CACHE / "lust_summary.xml"),
                    "--tripinfo-output", str(CACHE / "lust_tripinfo.xml"),
                    "--no-step-log", "true", "--no-warnings", "true"], check=True)


def flatten_vehroutes(src: Path, dst: Path) -> dict[str, tuple[float, list[str], list[float]]]:
    """Keep only the FINAL route (with its exit times) of every vehicle.

    cutRoutes.py takes the edges of the last route of a <routeDistribution> but drops its
    exitTimes, then silently falls back to the ORIGINAL departure time. LuST reroutes 70 %
    of the vehicles, so this pre-processing is required for correct entry times.
    """
    info: dict[str, tuple[float, list[str], list[float]]] = {}
    opener = gzip.open if src.suffix == ".gz" else open
    with opener(src, "rb") as fin, open(dst, "w", encoding="utf-8") as fout:
        fout.write("<routes>\n")
        for _, el in ET.iterparse(fin):
            if el.tag != "vehicle":
                continue
            dist = el.find("routeDistribution")
            route = dist.findall("route")[-1] if dist is not None else el.find("route")
            if route is None or not route.get("exitTimes"):
                el.clear()
                continue
            edges = route.get("edges").split()
            exits = [float(t) for t in route.get("exitTimes").split()]
            info[el.get("id")] = (float(el.get("depart")), edges, exits)
            attrs = {k: v for k, v in el.attrib.items() if k not in ("arrival", "routeLength")}
            v = ET.Element("vehicle", attrs)
            ET.SubElement(v, "route", {"edges": " ".join(edges), "exitTimes": route.get("exitTimes")})
            for stop in el.findall("stop"):
                ET.SubElement(v, "stop", {k: stop.get(k) for k in ("busStop", "duration") if stop.get(k)})
            fout.write(ET.tostring(v, encoding="unicode") + "\n")
            el.clear()
        fout.write("</routes>\n")
    return info


def fix_entry_times(cut_file: Path, info: dict, area_edges: set[str]) -> tuple[list[ET.Element], dict]:
    """Recompute the real area-entry time of every cut vehicle and fix boundary attributes."""
    stats = {"kept": 0, "dropped_unknown_entry": 0, "dropped_outside_window": 0, "time_corrected": 0}
    root = ET.parse(cut_file).getroot()
    vehicles = []
    search_from: dict[str, int] = {}

    def key(v):  # process the parts of one vehicle in route order (cutRoutes sorts by its own times)
        vid = v.get("id")
        if "_part" in vid and vid.rsplit("_part", 1)[0] in info:
            return vid.rsplit("_part", 1)[0], int(vid.rsplit("_part", 1)[1])
        return vid, 0

    for v in sorted(root.findall("vehicle"), key=key):
        base = key(v)[0]
        depart, edges, exits = info[base]
        cut_edges = v.find("route").get("edges").split()
        start = search_from.get(base, 0)
        idx = next(i for i in range(start, len(edges)) if edges[i:i + len(cut_edges)] == cut_edges)
        search_from[base] = idx + len(cut_edges)
        entry = depart if idx == 0 else exits[idx - 1]
        if entry < 0:  # vehicle had not reached the area when the LuST run ended
            stats["dropped_unknown_entry"] += 1
            continue
        if not (WINDOW[0] <= entry < WINDOW[1]):
            stats["dropped_outside_window"] += 1
            continue
        if abs(float(v.get("depart")) - entry) > 0.5:
            stats["time_corrected"] += 1
        v.set("depart", f"{entry:.2f}")
        if idx > 0:  # enters through the boundary
            v.set("departPos", "base")
            v.set("departLane", "best")
            v.set("departSpeed", "max")
        if idx + len(cut_edges) < len(edges):  # leaves through the boundary
            v.set("arrivalPos", "max")
            v.attrib.pop("arrivalSpeed", None)
        for stop in v.findall("stop"):
            for k in ("started", "ended", "until", "arrival"):
                stop.attrib.pop(k, None)
        vehicles.append(v)
        stats["kept"] += 1
    vehicles.sort(key=lambda x: float(x.get("depart")))
    return vehicles, stats


def build_demand(vehroutes: Path) -> dict:
    import sumolib

    CACHE.mkdir(exist_ok=True)
    flat = CACHE / "vehroutes_flat.xml"
    info = flatten_vehroutes(vehroutes, flat)
    cut = CACHE / "cut_raw.rou.xml"
    stops_raw = CACHE / "cut_busstops.add.xml"
    subprocess.run([sys.executable, str(sumo_home() / "tools" / "route" / "cutRoutes.py"), str(NET), str(flat),
                    "-o", str(cut), "-a", str(LUST / "busstops.add.xml"), "--stops-output", str(stops_raw),
                    "-d", "keep", "--default.departLane", "best", "--default.departSpeed", "max"],
                   check=True, stdout=subprocess.DEVNULL)
    area = {e.getID() for e in sumolib.net.readNet(str(NET)).getEdges()}
    vehicles, stats = fix_entry_times(cut, info, area)
    ROUTES.parent.mkdir(parents=True, exist_ok=True)
    with open(ROUTES, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!-- LuST routes 07:00-08:00 cut to the Kirchberg '
                '4-signal area; depart = real area-entry time measured in the full LuST run -->\n<routes>\n')
        for v in vehicles:
            f.write("    " + ET.tostring(v, encoding="unicode").strip() + "\n")
        f.write("</routes>\n")
    # bus stops actually used by the kept buses
    used = {s.get("busStop") for v in vehicles for s in v.findall("stop")}
    stops_root = ET.parse(stops_raw).getroot()
    with open(STOPS, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!-- LuST bus stops located in the Kirchberg area -->\n<additional>\n')
        for s in stops_root.iter("busStop"):
            f.write("    " + ET.tostring(s, encoding="unicode").strip() + "\n")
        f.write("</additional>\n")
    stats["bus_stops_in_area"] = len(list(stops_root.iter("busStop")))
    stats["bus_stops_used"] = len(used)
    return stats


# ---------------------------------------------------------------- 4. config
def copy_types() -> None:
    STOPS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(LUST / "vtypes.add.xml", VTYPES)                      # LuST types (MIT licence)
    shutil.copy(PROJECT_ROOT / "sumo" / "additional" / "emergency_vtypes.add.xml", EMERGENCY)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-lust", action="store_true", help="re-run the full LuST 07:00-08:30 (slow)")
    p.add_argument("--state", type=Path, default=PROJECT_ROOT / "data" / "states" / "lust_0700.xml.gz")
    p.add_argument("--vehroutes", type=Path, default=CACHE / "vehroutes_0700_0830.xml.gz")
    args = p.parse_args()
    if not (LUST / "lust.net.xml").exists():
        sys.exit(f"LuST not found in {LUST} (run setup_lust.ps1)")
    edges = select_edges()
    print(f"[1] area: {len(edges)} edges")
    build_network(edges)
    print(f"[2] network written: {NET}")
    copy_types()
    if args.run_lust:
        CACHE.mkdir(exist_ok=True)
        run_lust(args.state, args.vehroutes)
    if not args.vehroutes.exists():
        sys.exit(f"{args.vehroutes} missing: use --run-lust (needs a 07:00 state)")
    stats = build_demand(args.vehroutes)
    print(f"[3] demand: {stats}")
    print(f"[4] routes: {ROUTES}\n    stops : {STOPS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
