"""
CITA events collector v2 (DATEX II v3.6 SituationPublication) - keeps the real identifiers.

Feed: https://www.cita.lu/info_trafic/datex/situationrecord36  (refreshed every minute;
events are NOT flagged as terminated: they disappear from the feed - source: data.public.lu,
"Cita : Evenements trafic en Datex-II v3.6").

The earlier collectors (collect_cita.py, collect_all_luxembourg.py) dropped situation ids,
record ids and versions, so events had to be re-identified by (creation time, start time,
place). This collector writes two NEW files (never the legacy ones):

  cita_events_records_v2.csv    one row per (record_id, record_version) - first time seen
  cita_events_sightings_v2.csv  one row per collection x visible (record_id, record_version)
                                -> lets you date the disappearance (end) of an event

Record type = xsi:type of <situationRecord> (e.g. MaintenanceWorks) + its *Type sub-elements
(e.g. roadMaintenanceType) as published - nothing is deduced from free-text comments.

Usage (project root):
    python collect_cita_events_v2.py --once
    python collect_cita_events_v2.py --interval 300 --max-hours 168 --raw-dir data/raw/cita_events/snapshots
"""
from __future__ import annotations

import argparse
import csv
import io
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

PARSER_VERSION = "events-v2.1-2026-10-10"
EVENTS_URL = "https://www.cita.lu/info_trafic/datex/situationrecord36"
ROOT = Path(__file__).resolve().parent
EVENTS_DIR = ROOT / "data" / "historical" / "cita" / "events"
DEFAULT_RECORDS = EVENTS_DIR / "cita_events_records_v2.csv"
DEFAULT_SIGHTINGS = EVENTS_DIR / "cita_events_sightings_v2.csv"
LEGACY_FILES = {EVENTS_DIR / "cita_events_historical.csv", EVENTS_DIR / "cita_events_live.csv"}
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"

RECORD_COLUMNS = [
    "collection_timestamp_utc", "source_url", "source_publication_time",
    "situation_id", "record_id", "record_version", "record_type", "record_subtypes",
    "creation_time", "version_time", "probability", "safety_related_message",
    "validity_status", "overall_start_time", "overall_end_time",
    "lanes_restricted", "operational_lanes", "original_lanes", "carriageway",
    "road_name", "road_destination", "location_description", "length_affected_m",
    "latitude", "longitude", "bearing", "line_string_wgs84", "comment_type", "comment", "comment_lang",
    "parser_version",
]
SIGHTING_COLUMNS = ["collection_timestamp_utc", "source_publication_time", "situation_id", "record_id", "record_version"]


def local(tag: str) -> str:
    return tag.split("}")[-1]


def first(el, name):
    if el is None:
        return None
    for e in el.iter():
        if local(e.tag) == name and e.text and e.text.strip():
            return e.text.strip()
    return None


def parse_events_xml(content: bytes, collection_utc: str = "", source_url: str = EVENTS_URL) -> list[dict]:
    root = ET.fromstring(content)
    pub = first(root, "publicationTime")
    rows = []
    for sit in root.iter():
        if local(sit.tag) != "situation":
            continue
        for rec in sit:
            if local(rec.tag) != "situationRecord":
                continue
            r = dict.fromkeys(RECORD_COLUMNS)
            subtypes = sorted(f"{local(c.tag)}={c.text.strip()}" for c in rec
                              if local(c.tag).endswith("Type") and c.text and c.text.strip())
            comment_el = next((e for e in rec.iter() if local(e.tag) == "generalPublicComment"), None)
            comment_val = next((e for e in comment_el.iter() if local(e.tag) == "value"), None) if comment_el is not None else None
            point = next((e for e in rec.iter() if local(e.tag) == "pointByCoordinates"), None)
            carriage = next((e for e in rec.iter() if local(e.tag) == "carriageway" and len(e)), None)
            loc_desc = next((e for e in rec.iter() if local(e.tag) == "locationDescription"), None)
            r.update(
                collection_timestamp_utc=collection_utc, source_url=source_url, source_publication_time=pub,
                situation_id=sit.get("id"), record_id=rec.get("id"), record_version=rec.get("version"),
                record_type=(rec.get(XSI_TYPE) or "").split(":")[-1] or None,
                record_subtypes="|".join(subtypes) or None,
                creation_time=first(rec, "situationRecordCreationTime"),
                version_time=first(rec, "situationRecordVersionTime"),
                probability=first(rec, "probabilityOfOccurrence"),
                safety_related_message=first(rec, "safetyRelatedMessage"),
                validity_status=first(rec, "validityStatus"),
                overall_start_time=first(rec, "overallStartTime"),
                overall_end_time=first(rec, "overallEndTime"),
                lanes_restricted=first(rec, "numberOfLanesRestricted"),
                operational_lanes=first(rec, "numberOfOperationalLanes"),
                original_lanes=first(rec, "originalNumberOfLanes"),
                carriageway=first(carriage, "carriageway") if carriage is not None else None,
                road_name=first(rec, "roadName"), road_destination=first(rec, "roadDestination"),
                location_description=first(loc_desc, "value") if loc_desc is not None else None,
                length_affected_m=first(rec, "lengthAffected"),
                latitude=first(point, "latitude"), longitude=first(point, "longitude"), bearing=first(point, "bearing"),
                line_string_wgs84=first(rec, "posList"),
                comment_type=first(comment_el, "commentType"),
                comment=(comment_val.text or "").strip() or None if comment_val is not None else None,
                comment_lang=comment_val.get("lang") if comment_val is not None else None,
                parser_version=PARSER_VERSION,
            )
            rows.append(r)
    return rows


def check_output(path: Path, columns: list[str]) -> None:
    path = Path(path).resolve()
    if path in {f.resolve() for f in LEGACY_FILES}:
        raise SystemExit(f"Refusing to write into legacy file {path.name}.")
    if (ROOT / "data" / "raw").resolve() in path.parents:
        raise SystemExit("Refusing to write into data/raw.")
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as fh:
            if next(csv.reader(fh, delimiter=";"), []) != columns:
                raise SystemExit(f"Refusing to append to {path.name}: different columns.")


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


def existing_keys(path: Path, key: tuple) -> set:
    if not Path(path).exists():
        return set()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {tuple(r[k] for k in key) for r in csv.DictReader(fh, delimiter=";")}


def append(path: Path, columns: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, delimiter=";", extrasaction="ignore")
    if header:
        w.writeheader()
    w.writerows({k: ("" if r.get(k) is None else r.get(k)) for k in columns} for r in rows)
    with open(path, "a", encoding="utf-8-sig" if header else "utf-8", newline="") as fh:
        fh.write(buf.getvalue())      # one write per batch
        fh.flush()


def collect_once(records_path: Path, sightings_path: Path, seen: set, fetch=None, raw_dir=None) -> tuple[int, int]:
    check_output(records_path, RECORD_COLUMNS)
    check_output(sightings_path, SIGHTING_COLUMNS)
    if fetch is None:
        import requests

        def fetch():
            r = requests.get(EVENTS_URL, timeout=30)
            r.raise_for_status()
            return r.content
    now = datetime.now(timezone.utc)
    content = fetch()
    if raw_dir is not None:
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
        target = Path(raw_dir) / f"situationrecord36_{now:%Y%m%dT%H%M%SZ}.xml"
        if not target.exists():
            target.write_bytes(content)
    rows = parse_events_xml(content, now.isoformat())
    rows = [r for r in rows if r["record_id"] and r["record_version"]]
    new = []
    for r in rows:
        k = (r["record_id"], r["record_version"])
        if k not in seen:
            seen.add(k)
            new.append(r)
    sightings = {(r["record_id"], r["record_version"]): r for r in rows}.values()
    append(records_path, RECORD_COLUMNS, new)
    append(sightings_path, SIGHTING_COLUMNS, list(sightings))
    return len(new), len(list(sightings))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="CITA events collector v2 (keeps DATEX ids/versions)")
    p.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    p.add_argument("--sightings", type=Path, default=DEFAULT_SIGHTINGS)
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--once", action="store_true")
    p.add_argument("--raw-dir", type=Path, default=None)
    p.add_argument("--max-hours", type=float, default=None)
    a = p.parse_args(argv)
    check_output(a.records, RECORD_COLUMNS)
    check_output(a.sightings, SIGHTING_COLUMNS)
    for f in (a.records, a.sightings):
        if ensure_trailing_newline(f):
            print(f"WARNING: last line of {f} was incomplete (interrupted write); isolated by a newline, nothing removed")
    seen = existing_keys(a.records, ("record_id", "record_version"))
    print(f"CITA events collector {PARSER_VERSION} -> {a.records} ({len(seen)} record versions already present)"
          f" interval={a.interval}s max_hours={a.max_hours} raw_dir={a.raw_dir}", flush=True)
    t_end = time.time() + a.max_hours * 3600 if a.max_hours else None
    from single_instance import SingleInstance
    lock = SingleInstance(a.records)
    lock.__enter__()          # refuses a second concurrent collector on the same file
    try:
        while True:
            start = time.time()
            try:
                n_new, n_seen = collect_once(a.records, a.sightings, seen, raw_dir=a.raw_dir)
                print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  cycle ok  records visible: {n_seen}, new versions: {n_new}, total versions: {len(seen)}", flush=True)
            except SystemExit:
                raise
            except Exception as exc:
                print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  CYCLE ERROR: {exc!r}", flush=True)
            if a.once:
                return 0
            if t_end and time.time() >= t_end:
                print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  max-hours reached: clean stop", flush=True)
                return 0
            time.sleep(max(0, a.interval - (time.time() - start)))
    except KeyboardInterrupt:
        print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  stopped by user (Ctrl+C); data already written is kept", flush=True)
        return 0
    finally:
        lock.__exit__(None, None, None)

if __name__ == "__main__":
    raise SystemExit(main())
