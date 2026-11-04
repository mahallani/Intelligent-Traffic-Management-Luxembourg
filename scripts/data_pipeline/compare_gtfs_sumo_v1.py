"""Compatibility of the REAL GTFS timetable (2026) with the SIMULATED Kirchberg SUMO scenario (LuST ~2015).

* stops : each GTFS stop inside the zone bbox (+200 m) -> nearest lane of the reduced network and nearest
          LuST bus stop (distance in metres, sumolib projection of the network);
* lines : GTFS route_short_name serving the zone vs LuST bus lines of the scenario routes;
* tram  : GTFS route_type 0 in the zone vs tram lanes in the network.
Outputs: data/reports/gtfs_vs_sumo_kirchberg_<tag>.csv and .json (never overwritten). Needs sumolib.
Usage  : python scripts/data_pipeline/compare_gtfs_sumo_v1.py --tag v1"""
import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, ROOT, now_utc, read_csv_checked, safe_path  # noqa: E402

SC = ROOT / "sumo/lust_4_intersections"


def main(argv=None):
    import sumolib
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1")
    a = p.parse_args(argv)
    out_csv = safe_path(REPORTS / f"gtfs_vs_sumo_kirchberg_{a.tag}.csv")
    out_json = safe_path(REPORTS / f"gtfs_vs_sumo_kirchberg_{a.tag}.json")
    net = sumolib.net.readNet(str(SC / "net/kirchberg_4tls.net.xml"))
    stops = read_csv_checked(DATA / "processed/gtfs/gtfs_stops_prepared_v1.csv")
    zone = stops[stops.in_kirchberg_zone_200m_buffer == "True"]
    lust_stops = []
    for bs in ET.parse(SC / "additional/busstops_kirchberg.add.xml").getroot().iter("busStop"):
        lane = net.getLane(bs.get("lane"))
        x, y = sumolib.geomhelper.positionAtShapeOffset(lane.getShape(), (float(bs.get("startPos")) + float(bs.get("endPos"))) / 2)
        lust_stops.append((bs.get("id"), bs.get("lines", ""), x, y))
    rows = []
    for s in zone.itertuples():
        x, y = net.convertLonLat2XY(float(s.stop_lon), float(s.stop_lat))
        near = sorted(net.getNeighboringLanes(x, y, 100), key=lambda t: t[1])
        nb = min(lust_stops, key=lambda b: (b[2] - x) ** 2 + (b[3] - y) ** 2)
        d_bs = ((nb[2] - x) ** 2 + (nb[3] - y) ** 2) ** 0.5
        rows.append({"gtfs_stop_id": s.stop_id, "stop_name": s.stop_name, "in_zone_strict": s.in_kirchberg_zone,
                     "nearest_sumo_lane": near[0][0].getID() if near else "", "dist_lane_m": round(near[0][1], 1) if near else "",
                     "nearest_lust_busstop": nb[0], "dist_lust_busstop_m": round(d_bs, 1),
                     "compatible_stop_le_50m": d_bs <= 50, "data_origin": "real_gtfs_vs_simulated_network"})
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    kz = read_csv_checked(DATA / "processed/gtfs/gtfs_kirchberg_zone_stop_times_v1.csv")
    gtfs_lines = sorted(kz.route_short_name.dropna().unique())
    tram_gtfs = sorted(kz[kz.route_type == "0"].route_short_name.unique())
    rou = (SC / "routes/kirchberg_0700_0800.rou.xml").read_text(encoding="utf-8")
    lust_lines = sorted(set(re.findall(r'<vehicle id="AVL---_([^_"]+)_', rou)))   # LuST bus ids: AVL---_<line>_<n>
    tram_lanes = [l.getID() for e in net.getEdges() for l in e.getLanes()
                  if l.allows("tram") and not l.allows("passenger")]                # tram-only infrastructure
    rep = {"generated_utc": now_utc(), "gtfs_stops_in_zone_200m": len(rows),
           "stops_with_lust_busstop_within_50m": sum(r["compatible_stop_le_50m"] for r in rows),
           "gtfs_lines_serving_zone": gtfs_lines, "lust_bus_lines_in_scenario": lust_lines,
           "lines_in_both": sorted(set(gtfs_lines) & set(lust_lines)),
           "gtfs_tram_lines_in_zone": tram_gtfs, "tram_only_lanes_in_sumo_network": len(tram_lanes),
           "conclusion": "GTFS 2026 and LuST ~2015 bus supply are not directly compatible: compare stops/lines listed; "
                         "the tram (T1) has no infrastructure in the SUMO network; GTFS is not merged into the scenario."}
    out_json.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
