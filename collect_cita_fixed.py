"""
CITA traffic collector - corrected version (parser v2, 2026-10-10).

Why a v2
--------
The previous version looked for the "parent" of each <basicData> with
``for mv in root.iter(): if basic in list(mv.iter())``. The first element yielded is
the document ROOT, which contains everything, so the whole document was used as the
parent: site / latitude / longitude came from the FIRST site of the road and speed /
occupancy / flow / direction / time from the LAST one; all rows were then identical and
``drop_duplicates`` kept ONE row per road. ``measurement_site`` also held an ALERT-C
location code (specificLocation) instead of the site id. Backup of the old code:
collect_cita_fixed.py.bak_20261010.

DATEX II structure actually served by CITA (verified on data/raw/cita/*.xml)
-------------------------------------------------------------------------------
payloadPublication/siteMeasurements           -> ONE sensor (site)
    measurementSiteReference @id @version      -> site id, e.g. "B40.HR.18260"
    measurementTimeDefault                     -> measurement time (+02:00)
    measuredValue[@index=1]/measuredValue/basicData[@xsi:type=TrafficSpeed]
        pertinentLocation (lat/lon, direction, road, ALERT-C), averageVehicleSpeed/speed
    measuredValue[@index=2] ... TrafficConcentration -> occupancy/percentage
    measuredValue[@index=3] ... TrafficFlow          -> vehicleFlow/vehicleFlowRate (veh/h),
                                                      measurementOrCalculationPeriod (s)
Some sites only publish TrafficFlow (no speed, no occupancy and NO coordinates).

This version writes ONE row per (site, measurement time) to a NEW file
(default: data/historical/cita/traffic/cita_traffic_sites_v2.csv) and never appends to
cita_traffic_historical_fixed.csv, whose rows were produced by the faulty parser.

Usage (project root):
    python collect_cita_fixed.py --once                          # one collection, then stop
    python collect_cita_fixed.py --interval 300                  # loop every 5 min (CTRL+C to stop)
    python collect_cita_fixed.py --interval 300 --max-hours 168 --raw-dir data/raw/cita/snapshots
        # 7 days, stops by itself, every XML response archived (new files only)
Output columns (v2.1): see COLUMNS. Rows without sensor id or measurement time are not written.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

PARSER_VERSION = "v2.2-2026-10-10"

ROADS = ["a1", "a3", "a4", "a6", "a7", "a13", "b40"]
TRAFFIC_URL = "https://www.cita.lu/info_trafic/datex/trafficstatus_{}"

ROOT = Path(__file__).resolve().parent
TRAFFIC_DIR = ROOT / "data" / "historical" / "cita" / "traffic"
DEFAULT_OUTPUT = TRAFFIC_DIR / "cita_traffic_sites_v2.csv"
# Files written by earlier (faulty or differently structured) collectors: never appended to.
LEGACY_FILES = {TRAFFIC_DIR / "cita_traffic_historical_fixed.csv",
                TRAFFIC_DIR / "cita_traffic_historical.csv",
                TRAFFIC_DIR / "cita_traffic_live.csv"}
LEGACY_FILE = TRAFFIC_DIR / "cita_traffic_historical_fixed.csv"     # kept for backward compatibility

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"

# Units (DATEX II): speed in km/h (KilometresPerHour), vehicle_flow_rate in vehicles/hour,
# occupancy in %. flow_period_s = <measurementOrCalculationPeriod> as published (3600 s).
# measurement_timestamp = <measurementTimeDefault> exactly as published (explicit offset, e.g. +02:00).
# collection_timestamp_utc = clock of the collecting computer converted to UTC (explicit, no guess).
# There is NO <vehicleFlow> count in the feed (only the rate): no vehicle_flow column is invented.
COLUMNS = [
    "collection_timestamp_utc", "collection_timestamp_local", "source_url", "source_publication_time",
    "road", "road_number", "sensor_id", "sensor_version", "measurement_timestamp",
    "latitude", "longitude", "direction", "distance_along_m",
    "alertc_primary_location", "alertc_secondary_location", "alertc_direction",
    "speed_kmh", "occupancy_percent", "vehicle_flow_rate", "flow_period_s",
    "equipment", "measured_values", "parser_version",
]


# ------------------------------------------------------------------ XML helpers
def local(tag: str) -> str:
    """Tag name without namespace."""
    return tag.split("}")[-1]


def children(element, name):
    return [c for c in element if local(c.tag) == name]


def first_text(element, name):
    """Text of the first descendant called ``name`` (namespace-agnostic), or None."""
    if element is None:
        return None
    for e in element.iter():
        if local(e.tag) == name and e.text and e.text.strip():
            return e.text.strip()
    return None


# ------------------------------------------------------------------ parser
def parse_traffic_xml(content: bytes, road: str, collection_time_utc: str = "",
                      collection_time_local: str = "", source_url: str = "") -> list[dict]:
    """Parse one CITA trafficstatus response -> one dict per <siteMeasurements>.

    Every value comes from inside its own <siteMeasurements> element, so values can
    never be mixed between sensors. Missing measurements stay None (never invented).
    """
    root = ET.fromstring(content)
    publication_time = first_text(root, "publicationTime")
    rows = []
    for site in root.iter():
        if local(site.tag) != "siteMeasurements":
            continue
        ref = next((c for c in site if local(c.tag) == "measurementSiteReference"), None)
        row = dict.fromkeys(COLUMNS)
        row.update(
            collection_timestamp_utc=collection_time_utc,
            collection_timestamp_local=collection_time_local,
            source_url=source_url or TRAFFIC_URL.format(road.lower()),
            source_publication_time=publication_time,
            road=road.upper(),
            sensor_id=ref.get("id") if ref is not None else None,
            sensor_version=ref.get("version") if ref is not None else None,
            measurement_timestamp=next((c.text.strip() for c in site if local(c.tag) == "measurementTimeDefault" and c.text), None),
            parser_version=PARSER_VERSION,
        )
        measured = children(site, "measuredValue")
        row["measured_values"] = len(measured)
        for mv in measured:
            for basic in mv.iter():
                if local(basic.tag) != "basicData":
                    continue
                kind = basic.get(XSI_TYPE, "")
                if kind == "TrafficSpeed":
                    row["speed_kmh"] = first_text(basic, "speed")
                    loc = next((e for e in basic.iter() if local(e.tag) == "pertinentLocation"), None)
                    if loc is not None:
                        row["latitude"] = first_text(loc, "latitude")
                        row["longitude"] = first_text(loc, "longitude")
                        row["direction"] = first_text(loc, "directionBoundOnLinearSection")
                        row["road_number"] = first_text(loc, "roadNumber")
                        row["distance_along_m"] = first_text(next((e for e in loc.iter() if local(e.tag) == "fromPoint"), None), "distanceAlong")
                        row["alertc_direction"] = first_text(loc, "alertCDirectionCoded")
                        prim = next((e for e in loc.iter() if local(e.tag) == "alertCMethod4PrimaryPointLocation"), None)
                        sec = next((e for e in loc.iter() if local(e.tag) == "alertCMethod4SecondaryPointLocation"), None)
                        row["alertc_primary_location"] = first_text(prim, "specificLocation")
                        row["alertc_secondary_location"] = first_text(sec, "specificLocation")
                elif kind == "TrafficConcentration":
                    row["occupancy_percent"] = first_text(basic, "percentage")
                elif kind == "TrafficFlow":
                    row["vehicle_flow_rate"] = first_text(basic, "vehicleFlowRate")
                    row["flow_period_s"] = first_text(basic, "measurementOrCalculationPeriod")
            equipment = next((e for e in mv.iter() if local(e.tag) == "value" and e.get("lang") == "en"), None)
            if equipment is not None and not row["equipment"]:
                row["equipment"] = (equipment.text or "").strip() or None
        rows.append(row)
    return rows


# ------------------------------------------------------------------ writing
class ProtectedOutput(SystemExit):
    pass


def check_output(path: Path) -> None:
    """Refuse legacy files, anything under data/raw, and any existing file whose header
    is not exactly the v2 schema (never mix structures in one file)."""
    path = Path(path).resolve()
    if path in {f.resolve() for f in LEGACY_FILES}:
        raise ProtectedOutput(f"Refusing to write into legacy file {path.name} (produced by an older collector).")
    raw = (ROOT / "data" / "raw").resolve()
    if raw in path.parents:
        raise ProtectedOutput("Refusing to write into data/raw (source files are read-only).")
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as fh:
            header = next(csv.reader(fh, delimiter=";"), [])
        if header != COLUMNS:
            raise ProtectedOutput(f"Refusing to append to {path.name}: its columns differ from the v2 schema.")


def ensure_trailing_newline(path: Path) -> bool:
    """If a previous run was killed in the middle of a line, isolate that incomplete line by
    appending a newline (nothing is removed). Returns True when a repair was needed."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return False
    with open(path, "rb") as fh:
        fh.seek(-1, 2)
        last = fh.read(1)
    if last == b"\n":
        return False
    with open(path, "ab") as fh:
        fh.write(b"\n")
    return True


def existing_keys(path: Path) -> set[tuple[str, str]]:
    """(sensor_id, measurement_timestamp) already written -> polling never re-writes a value."""
    if not Path(path).exists():
        return set()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {(r["sensor_id"], r["measurement_timestamp"]) for r in csv.DictReader(fh, delimiter=";")}


def append_rows(rows: list[dict], path: Path, seen: set) -> int:
    new, batch = [], set()
    for r in rows:
        k = (r["sensor_id"], r["measurement_timestamp"])
        if not k[0] or not k[1]:      # cannot be attributed to a sensor / a time: not written
            continue
        if k in seen or k in batch:
            continue
        batch.add(k)
        new.append(r)
    if not new:
        return 0
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with open(path, "a", encoding="utf-8-sig" if write_header else "utf-8", newline="") as fh:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=COLUMNS, delimiter=";")
        if write_header:
            writer.writeheader()
        writer.writerows({k: ("" if v is None else v) for k, v in r.items()} for r in new)
        fh.write(buf.getvalue())      # one write per batch
        fh.flush()
    seen.update(batch)
    return len(new)


def collect_once(output: Path, seen: set, fetch=None, raw_dir: Path | None = None) -> int:
    """Download every road once, parse, append new rows. ``fetch(road) -> bytes`` can be
    injected (tests). ``raw_dir``: also save each XML response (traceability)."""
    check_output(output)
    if fetch is None:
        import requests

        def fetch(road):
            r = requests.get(TRAFFIC_URL.format(road), timeout=30)
            r.raise_for_status()
            return r.content
    now = datetime.now(timezone.utc)
    t_utc, t_local = now.isoformat(), now.astimezone().isoformat()
    total = 0
    for road in ROADS:
        try:
            content = fetch(road)
            if raw_dir is not None:
                raw_dir = Path(raw_dir)
                raw_dir.mkdir(parents=True, exist_ok=True)
                target = raw_dir / f"trafficstatus_{road}_{now:%Y%m%dT%H%M%SZ}.xml"
                if not target.exists():
                    target.write_bytes(content)
            rows = parse_traffic_xml(content, road, t_utc, t_local, TRAFFIC_URL.format(road))
        except ET.ParseError as exc:
            print(f"[{road.upper()}] XML error: {exc}")
            continue
        except Exception as exc:  # network etc.: keep collecting the other roads
            print(f"[{road.upper()}] error: {exc}")
            continue
        try:
            n = append_rows(rows, output, seen)
        except PermissionError:
            print(f"[{road.upper()}] cannot write {output} (file open in Excel / another program?)")
            continue
        total += n
        print(f"[{road.upper()}] {len(rows)} sensors in XML, {n} new rows")
    return total


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="CITA traffic collector (parser v2)")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--interval", type=int, default=60, help="seconds between collections")
    p.add_argument("--once", action="store_true", help="collect once and stop")
    p.add_argument("--raw-dir", type=Path, default=None, help="also save every XML response here")
    p.add_argument("--max-hours", type=float, default=None, help="stop automatically after N hours")
    args = p.parse_args(argv)
    check_output(args.output)
    if ensure_trailing_newline(args.output):
        print(f"WARNING: last line of {args.output} was incomplete (interrupted write); isolated by a newline, nothing removed")
    seen = existing_keys(args.output)
    print(f"CITA collector {PARSER_VERSION} -> {args.output} ({len(seen)} measurements already present)"
          f" interval={args.interval}s max_hours={args.max_hours} raw_dir={args.raw_dir}", flush=True)
    t_end = time.time() + args.max_hours * 3600 if args.max_hours else None
    from single_instance import SingleInstance
    lock = SingleInstance(args.output)
    lock.__enter__()          # refuses a second concurrent collector on the same file
    try:
        while True:
            start = time.time()
            try:
                n = collect_once(args.output, seen, raw_dir=args.raw_dir)
                print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  cycle ok  new rows: {n}  total keys: {len(seen)}", flush=True)
            except SystemExit:
                raise
            except Exception as exc:  # never let one bad cycle stop a 7-day collection
                print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  CYCLE ERROR: {exc!r}", flush=True)
            if args.once:
                return 0
            if t_end and time.time() >= t_end:
                print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  max-hours reached: clean stop", flush=True)
                return 0
            time.sleep(max(0, args.interval - (time.time() - start)))
    except KeyboardInterrupt:
        print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  stopped by user (Ctrl+C); data already written is kept", flush=True)
        return 0
    finally:
        lock.__exit__(None, None, None)

if __name__ == "__main__":
    raise SystemExit(main())
