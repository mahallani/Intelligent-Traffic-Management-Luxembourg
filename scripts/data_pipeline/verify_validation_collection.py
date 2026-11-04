"""Independent check of a single validation collection (traffic v2 + events v2) against the
archived XML responses (namespaced XPath, not the collector's parser).
Usage: python scripts/data_pipeline/verify_validation_collection.py data/interim/cita/validation_20261010 --tag v1
Writes data/reports/cita_validation_collection_<tag>.json (refuses to overwrite)."""
from __future__ import annotations
import argparse, re, sys, xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPORTS, read_csv_checked, safe_path, write_json, now_utc, rel  # noqa: E402

NS = {"d": "http://datex2.eu/schema/2/2_0", "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"
OFFSET = re.compile(r"(?:Z|[+-]\d\d:\d\d)$")


def xml_truth(path):
    out = {}
    for sm in ET.parse(path).getroot().iter("{%s}siteMeasurements" % NS["d"]):
        sid = sm.find("d:measurementSiteReference", NS).get("id")
        t = {"ts": sm.findtext("d:measurementTimeDefault", namespaces=NS),
             "lat": sm.findtext(".//d:locationForDisplay/d:latitude", namespaces=NS),
             "lon": sm.findtext(".//d:locationForDisplay/d:longitude", namespaces=NS)}
        for bd in sm.iterfind(".//d:basicData", NS):
            ty = bd.get(XSI).split(":")[-1]
            if ty == "TrafficSpeed":
                t["speed"] = bd.findtext(".//d:averageVehicleSpeed/d:speed", namespaces=NS)
            elif ty == "TrafficConcentration":
                t["occ"] = bd.findtext(".//d:occupancy/d:percentage", namespaces=NS)
            elif ty == "TrafficFlow":
                t["flow"] = bd.findtext(".//d:vehicleFlow/d:vehicleFlowRate", namespaces=NS)
        out[sid] = t
    return out


def _missing(v):
    return v is None or (isinstance(v, float) and v != v) or (isinstance(v, str) and v.strip() == "")


def num_eq(a, b):
    if _missing(a) or _missing(b):
        return _missing(a) and _missing(b)
    return float(a) == float(b)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("--tag", default="v1")
    a = p.parse_args(argv)
    out_path = safe_path(REPORTS / f"cita_validation_collection_{a.tag}.json")
    tr = read_csv_checked(next(a.folder.glob("cita_traffic_sites_v2*.csv")))
    rep = {"generated_utc": now_utc(), "folder": rel(a.folder), "traffic": {}, "events": {}, "checks": {}}
    truth = {}
    for f in sorted((a.folder / "raw").glob("trafficstatus_*.xml")):
        truth.update(xml_truth(f))
    mism = []
    for r in tr.itertuples():
        t = truth.get(r.sensor_id)
        if t is None:
            mism.append((r.sensor_id, "not in XML")); continue
        for col, k in (("speed_kmh", "speed"), ("occupancy_percent", "occ"), ("vehicle_flow_rate", "flow"),
                       ("latitude", "lat"), ("longitude", "lon")):
            if not num_eq(getattr(r, col), t.get(k)):
                mism.append((r.sensor_id, col))
        if r.measurement_timestamp != t["ts"]:
            mism.append((r.sensor_id, "ts"))
    num = {c: tr[c].astype(float) for c in ("speed_kmh", "occupancy_percent", "vehicle_flow_rate", "latitude", "longitude")}
    c = rep["checks"]
    c["rows_equal_sensors_in_xml"] = len(tr) == len(truth)
    c["values_match_xml"] = not mism
    c["unique_sensor_measurement_key"] = not tr.duplicated(["sensor_id", "measurement_timestamp"]).any()
    c["sensor_prefix_matches_road"] = bool((tr.apply(lambda r: r.sensor_id.upper().startswith(r.road.upper() + "."), axis=1)).all())
    c["measurement_ts_has_explicit_offset"] = bool(tr.measurement_timestamp.str.contains(OFFSET).all())
    c["collection_ts_utc"] = bool(tr.collection_timestamp_utc.str.endswith("+00:00").all())
    c["speed_in_0_250"] = bool(num["speed_kmh"].dropna().between(0, 250).all())
    c["occupancy_in_0_100"] = bool(num["occupancy_percent"].dropna().between(0, 100).all())
    c["flow_nonneg"] = bool((num["vehicle_flow_rate"].dropna() >= 0).all())
    c["coords_in_luxembourg_bbox_when_present"] = bool(num["latitude"].dropna().between(49.44, 50.19).all() and num["longitude"].dropna().between(5.73, 6.54).all())
    c["flow_period_3600_s"] = bool(tr.flow_period_s.dropna().astype(float).eq(3600).all())
    rep["traffic"] = {"rows": len(tr), "sensors_in_xml": len(truth), "mismatches": mism[:20],
                      "rows_per_road": tr.road.value_counts().to_dict(),
                      "missing": {k: int(v.isna().sum()) for k, v in num.items()},
                      "sensors_without_location_in_xml": sorted(k for k, v in truth.items() if not v.get("lat")),
                      "measurement_ts_values": tr.measurement_timestamp.value_counts().head(5).to_dict(),
                      "collection_utc": sorted(tr.collection_timestamp_utc.unique().tolist())}
    ev = read_csv_checked(next(a.folder.glob("cita_events_records_v2*.csv")))
    xml_ev = next((a.folder / "raw").glob("situationrecord36_*.xml"))
    recs = {(e.get("id"), e.get("version")) for e in ET.parse(xml_ev).getroot().iter()
            if e.tag.endswith("}situationRecord")}
    c["events_records_equal_xml"] = set(zip(ev.record_id, ev.record_version)) == recs
    c["events_unique_record_version"] = not ev.duplicated(["record_id", "record_version"]).any()
    c["events_type_present"] = bool((ev.record_type != "").all())
    rep["events"] = {"records": len(ev), "situations": ev.situation_id.nunique(), "records_in_xml": len(recs),
                     "record_types": ev.record_type.value_counts().to_dict(),
                     "validity_status": ev.validity_status.value_counts().to_dict()}
    rep["all_passed"] = all(c.values())
    write_json(rep, out_path)
    for k, v in c.items():
        print(("PASS " if v else "FAIL ") + k)
    print("traffic rows", len(tr), "| events", len(ev), "->", rel(out_path))
    return 0 if rep["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
