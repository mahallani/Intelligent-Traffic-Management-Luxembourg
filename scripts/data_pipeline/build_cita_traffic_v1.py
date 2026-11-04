"""
Build the CITA traffic datasets (Luxembourg motorways, DATEX II v2 trafficstatus feeds).

REFERENCE dataset (reliable sensor attribution, usable for modelling):
  * every archived XML snapshot  data/raw/cita/trafficstatus_*.xml  (parsed with the v2.1 parser)
  * every v2 CSV written by collect_cita_fixed.py v2.x:
      data/historical/cita/traffic/cita_traffic_sites_v2*.csv
      data/interim/cita/validation_*/cita_traffic_sites_v2*.csv
  -> data/processed/cita_traffic/cita_traffic_reference_<tag>.csv

LEGACY DIAGNOSTIC dataset (sensor attribution NOT reliable - never for spatial models):
  * data/historical/cita/traffic/cita_traffic_historical.csv, _historical_fixed.csv, _live.csv
  -> data/interim/cita/cita_traffic_legacy_diagnostic_<tag>.csv

Report: data/reports/cita_traffic_build_<tag>.json  (dedup rules, timezone evidence, flags, coverage)

Nothing is overwritten (safe_path); sources are only read. Usage:
    python scripts/data_pipeline/build_cita_traffic_v1.py --tag v1
    python scripts/data_pipeline/build_cita_traffic_v1.py --tag v1 --check-only
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, ROOT, now_utc, read_csv_checked, rel, safe_path, write_csv, write_json  # noqa: E402

LEGACY = [DATA / "historical/cita/traffic" / n for n in
          ("cita_traffic_historical.csv", "cita_traffic_historical_fixed.csv", "cita_traffic_live.csv")]
VALUE_COLS = ["speed_kmh", "occupancy_percent", "vehicle_flow_rate", "flow_period_s", "latitude", "longitude",
              "direction", "road_number", "distance_along_m", "alertc_primary_location",
              "alertc_secondary_location", "alertc_direction", "equipment", "measured_values", "sensor_version"]
OUT_COLS = ["measurement_timestamp", "measurement_timestamp_utc", "collection_timestamp", "collection_timestamp_utc",
            "collection_timestamp_origin", "sensor_id", "sensor_version", "road", "road_number", "direction",
            "latitude", "longitude", "distance_along_m", "alertc_primary_location", "alertc_secondary_location",
            "alertc_direction", "speed_kmh", "occupancy_percent", "vehicle_flow_rate", "flow_period_s", "equipment",
            "measured_values", "source_publication_time", "source_url", "source_file", "source_raw_xml",
            "parser_version", "n_sightings", "data_origin", "quality_flags"]
# documented thresholds
SPEED_MAX_PLAUSIBLE = 200.0      # km/h - above: implausible
SPEED_ABOVE_LIMIT = 130.0        # km/h - general motorway limit in Luxembourg (flag only, not an error)
LAG_MAX_MIN = 15.0               # collection - measurement lag above this is flagged
LUX_BBOX = (49.44, 50.19, 5.73, 6.54)  # lat_min, lat_max, lon_min, lon_max (generous national bbox)


def load_collector():
    spec = importlib.util.spec_from_file_location("collector", ROOT / "collect_cita_fixed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reference_sources():
    xmls = sorted((DATA / "raw/cita").glob("trafficstatus_*.xml"))
    csvs = sorted((DATA / "historical/cita/traffic").glob("cita_traffic_sites_v2*.csv")) + \
        sorted((DATA / "interim/cita").glob("validation_*/cita_traffic_sites_v2*.csv"))
    return xmls, csvs


def load_reference(col):
    xmls, csvs = reference_sources()
    frames, inputs = [], []
    for f in xmls:
        road = f.stem.split("_")[1].upper()
        mtime = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat()
        rows = col.parse_traffic_xml(f.read_bytes(), road, mtime, "", "")
        d = pd.DataFrame(rows, columns=col.COLUMNS).astype(object).where(lambda x: x.notna(), None)
        d = d.astype(str).replace({"None": pd.NA, "": pd.NA})
        d["collection_timestamp_origin"] = "file_mtime_utc"
        d["source_file"] = rel(f)
        d["source_raw_xml"] = rel(f)
        frames.append(d)
        inputs.append({"file": rel(f), "kind": "raw_xml", "rows": len(d)})
    for f in csvs:
        d = read_csv_checked(f, expected_columns=col.COLUMNS)
        d["collection_timestamp_origin"] = "collector_utc_clock"
        d["source_file"] = rel(f)
        raw_dir = f.parent / "raw"

        def raw_for(r):
            try:
                ts = pd.Timestamp(r["collection_timestamp_utc"]).strftime("%Y%m%dT%H%M%SZ")
            except Exception:
                return pd.NA
            p = raw_dir / f"trafficstatus_{str(r['road']).lower()}_{ts}.xml"
            return rel(p) if p.exists() else pd.NA
        d["source_raw_xml"] = d.apply(raw_for, axis=1)
        frames.append(d)
        inputs.append({"file": rel(f), "kind": "collector_v2_csv", "rows": len(d)})
    return pd.concat(frames, ignore_index=True), inputs


def dedup_reference(df):
    """Key = (sensor_id, measurement_timestamp).
    identical repeat : same key AND same values in VALUE_COLS -> one row kept (earliest collection),
                       n_sightings counts the copies, all source files listed.
    contradiction    : same key, different values -> ALL rows kept, flagged conflict_same_key."""
    df = df.copy()
    sig = df[VALUE_COLS].fillna("<NA>").astype(str).agg("|".join, axis=1)
    df["_sig"] = sig
    key = ["sensor_id", "measurement_timestamp"]
    n_sig = df.groupby(key, dropna=False)["_sig"].transform("nunique")
    df["_conflict"] = n_sig > 1
    df = df.sort_values(["sensor_id", "measurement_timestamp", "collection_timestamp_utc"], kind="stable")
    grp = df.groupby(key + ["_sig"], dropna=False, sort=False)
    out = grp.head(1).copy()
    out["n_sightings"] = grp["_sig"].transform("size").loc[out.index]
    files = grp["source_file"].agg(lambda s: "|".join(sorted(set(s))))
    out["source_file"] = [files.loc[tuple(k)] for k in out[key + ["_sig"]].itertuples(index=False, name=None)]
    stats = {"input_rows": len(df), "output_rows": len(out),
             "identical_repeats_collapsed": int(len(df) - len(out) - 0),
             "keys_with_contradictions": int(df.loc[df["_conflict"]].groupby(key).ngroups),
             "rows_in_contradiction": int(out["_conflict"].sum())}
    return out, stats


def add_flags(df):
    f = {}
    num = {c: pd.to_numeric(df[c], errors="coerce") for c in
           ("speed_kmh", "occupancy_percent", "vehicle_flow_rate", "latitude", "longitude", "flow_period_s")}
    mts = pd.to_datetime(df["measurement_timestamp"], utc=True, errors="coerce", format="ISO8601")
    cts = pd.to_datetime(df["collection_timestamp_utc"], utc=True, errors="coerce", format="ISO8601")
    lag = (cts - mts).dt.total_seconds() / 60
    f["speed_missing"] = num["speed_kmh"].isna()
    f["occupancy_missing"] = num["occupancy_percent"].isna()
    f["flow_missing"] = num["vehicle_flow_rate"].isna()
    f["location_missing"] = num["latitude"].isna() | num["longitude"].isna()
    f["speed_above_130"] = num["speed_kmh"] > SPEED_ABOVE_LIMIT
    f["speed_implausible_gt200"] = num["speed_kmh"] > SPEED_MAX_PLAUSIBLE
    f["speed_zero_with_flow"] = (num["speed_kmh"] == 0) & (num["vehicle_flow_rate"] > 0)
    f["occupancy_out_of_range"] = (num["occupancy_percent"] < 0) | (num["occupancy_percent"] > 100)
    f["flow_negative"] = num["vehicle_flow_rate"] < 0
    f["flow_period_not_3600"] = num["flow_period_s"].notna() & (num["flow_period_s"] != 3600)
    lat, lon = num["latitude"], num["longitude"]
    f["outside_luxembourg_bbox"] = lat.notna() & ~(lat.between(*LUX_BBOX[:2]) & lon.between(*LUX_BBOX[2:]))
    f["measurement_ts_unparseable"] = mts.isna()
    f["measurement_after_collection"] = lag < 0
    f["collection_lag_over_15min"] = lag > LAG_MAX_MIN
    f["collection_ts_from_file_mtime"] = df["collection_timestamp_origin"].eq("file_mtime_utc")
    f["conflict_same_key"] = df["_conflict"].astype(bool)
    fl = pd.DataFrame(f).fillna(False)
    df["quality_flags"] = fl.apply(lambda r: "|".join(k for k, v in r.items() if v), axis=1)
    df["measurement_timestamp_utc"] = mts.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    df["collection_timestamp"] = df["collection_timestamp_utc"]
    return df, {k: int(v.sum()) for k, v in fl.items()}, lag


def build_legacy():
    frames, stats = [], {}
    for f in LEGACY:
        d = read_csv_checked(f)
        n_in = len(d)
        vcols = [c for c in d.columns if c != "collection_time"]
        sig = d[vcols].fillna("<NA>").astype(str).agg("|".join, axis=1)
        d["_sig"] = sig
        g = d.groupby("_sig", sort=False)
        out = g.head(1).copy()
        out["n_polls"] = g["_sig"].transform("size").loc[out.index]
        out["collection_time_first"] = g["collection_time"].transform("min").loc[out.index]
        out["collection_time_last"] = g["collection_time"].transform("max").loc[out.index]
        out = out.drop(columns=["collection_time", "_sig"])
        has_ts = "timestamp" in out and out["timestamp"].notna().any()
        flags = ["legacy_sensor_attribution_unreliable", "collection_time_naive_pc_clock_utc+01"]
        if "measurement_site" not in out or out["measurement_site"].isna().all():
            flags.append("no_site_code")
        if not has_ts:
            flags.append("no_measurement_timestamp")
        conflict = pd.Series(False, index=out.index)
        key = None
        if has_ts:
            site_ok = "measurement_site" in out and out["measurement_site"].notna().any()
            key = ["road", "measurement_site", "timestamp", "direction"] if site_ok else \
                ["road", "timestamp", "latitude", "longitude", "direction"]
            key = [k for k in key if k in out.columns]
            conflict = out.groupby(key, dropna=False)["n_polls"].transform("size") > 1
        out["quality_flags"] = "|".join(flags)
        out.loc[conflict, "quality_flags"] += "|conflict_same_key"
        out["source_file"] = rel(f)
        out["data_origin"] = "real_cita_legacy_v1_collector"
        frames.append(out)
        stats[rel(f)] = {"input_rows": n_in, "distinct_value_rows": len(out),
                         "identical_repeats_collapsed": n_in - len(out),
                         "rows_in_key_contradiction": int(conflict.sum()),
                         "key_for_contradictions": "+".join(key) if key else
                         "none (no measurement timestamp: contradictions undetectable)"}
    legacy = pd.concat(frames, ignore_index=True)
    return legacy, stats


def timezone_evidence():
    ev = []
    for f in LEGACY:
        d = read_csv_checked(f, usecols=["collection_time"], min_columns=1)
        last = pd.Timestamp(d["collection_time"].max())
        mtime = pd.Timestamp(datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)).tz_localize(None)
        ev.append({"file": rel(f), "last_naive_collection_time": str(last), "file_mtime_utc": str(mtime),
                   "offset_hours": round((last - mtime).total_seconds() / 3600, 3)})
    return ev


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args(argv)
    outs = {"reference": DATA / f"processed/cita_traffic/cita_traffic_reference_{a.tag}.csv",
            "legacy": DATA / f"interim/cita/cita_traffic_legacy_diagnostic_{a.tag}.csv",
            "report": REPORTS / f"cita_traffic_build_{a.tag}.json"}
    xmls, csvs = reference_sources()
    if a.check_only:
        print("inputs:", [rel(x) for x in xmls + csvs + LEGACY])
        for k, v in outs.items():
            print(f"{k}: {rel(v)} {'EXISTS (would refuse)' if v.exists() else 'would be created'}")
        return 0
    for v in outs.values():
        safe_path(v)
    col = load_collector()
    raw, inputs = load_reference(col)
    ref, dstats = dedup_reference(raw)
    ref, flag_counts, lag = add_flags(ref)
    ref["data_origin"] = "real_cita_datex2_v2"
    ref = ref.sort_values(["measurement_timestamp_utc", "road", "sensor_id"]).reset_index(drop=True)
    tz = timezone_evidence()
    legacy, lstats = build_legacy()
    write_csv(ref[OUT_COLS], outs["reference"])
    write_csv(legacy, outs["legacy"])
    mts = pd.to_datetime(ref["measurement_timestamp_utc"], utc=True)
    rep = {
        "generated_utc": now_utc(), "script": rel(Path(__file__)), "parser_version": col.PARSER_VERSION,
        "inputs": inputs + [{"file": rel(f), "kind": "legacy_csv_diagnostic_only"} for f in LEGACY],
        "outputs": {k: rel(v) for k, v in outs.items()},
        "reference": {
            "rows": len(ref), "columns": OUT_COLS, "sensors": int(ref.sensor_id.nunique()),
            "roads": ref.road.value_counts().to_dict(),
            "distinct_measurement_times_utc": sorted(mts.dt.strftime("%Y-%m-%dT%H:%M:%SZ").unique().tolist()),
            "coverage_utc": [str(mts.min()), str(mts.max())],
            "missing_pct": {c: round(100 * ref[c].isna().mean(), 2) for c in
                            ("speed_kmh", "occupancy_percent", "vehicle_flow_rate", "latitude", "longitude", "direction")},
            "bbox": {c: [float(pd.to_numeric(ref[c]).min()), float(pd.to_numeric(ref[c]).max())] for c in ("latitude", "longitude")},
            "collection_lag_min": pd.Series(lag).describe().round(2).to_dict(),
            "dedup": dstats, "quality_flag_counts": flag_counts,
            "absent_columns": {"vehicle_flow": "not published by the CITA feed (only vehicleFlowRate in veh/h); NOT created"},
        },
        "legacy_diagnostic": {"rows": len(legacy), "per_file": lstats,
                              "use": "diagnostic only: values of the last sensor of each road were written with the location of the first sensor (v1 parser bug); never use for spatial models or training"},
        "dedup_rules": {
            "reference_key": "sensor_id + measurement_timestamp (original text with offset)",
            "identical_repeat": "same key and identical values in " + ",".join(VALUE_COLS) + " -> one row (earliest collection), n_sightings = copies, source_file lists all files",
            "contradiction": "same key, different values -> all rows kept and flagged conflict_same_key; nothing is averaged or chosen",
            "legacy": "rows identical except collection_time collapsed (n_polls, first/last collection time); key contradictions flagged; no row removed otherwise"},
        "timezone_evidence": {
            "measurement_timestamp": "explicit ISO-8601 offset in the DATEX payload (e.g. +02:00 = CEST, Europe/Luxembourg until 2026-10-25); converted to UTC without assumption",
            "collection_timestamp_v2": "written by the v2 collector from datetime.now(timezone.utc): explicit UTC",
            "collection_timestamp_raw_xml": "no collection time in the payload; file modification time (filesystem, UTC) used and flagged collection_ts_from_file_mtime",
            "collection_time_legacy": "naive local clock of the collecting PC (datetime.now()). Evidence: last naive value of each legacy file vs its file modification time (UTC)",
            "legacy_offset_evidence": tz,
            "uncertainty": "assumes the PC clock offset stayed constant (UTC+01, consistent with Africa/Tunis which has no DST) during the collection and that file mtimes were not altered by a copy; legacy collection times are therefore converted only in the diagnostic notes, never used as keys"},
        "thresholds": {"speed_above_limit_kmh": SPEED_ABOVE_LIMIT, "speed_implausible_kmh": SPEED_MAX_PLAUSIBLE,
                       "collection_lag_max_min": LAG_MAX_MIN, "lux_bbox": LUX_BBOX},
        "units": {"speed_kmh": "km/h (DATEX II convention; CITA does not state the unit; values plausible)",
                  "occupancy_percent": "% of time the detector is occupied",
                  "vehicle_flow_rate": "vehicles/hour (DATEX II VehiclesPerHour)",
                  "flow_period_s": "measurementOrCalculationPeriod as published (3600): ambiguity rolling-hour vs hourly rate documented, not resolved"},
    }
    write_json(rep, outs["report"])
    print(f"reference: {len(ref)} rows, {ref.sensor_id.nunique()} sensors, times {rep['reference']['distinct_measurement_times_utc']}")
    print("dedup:", dstats)
    print("flags:", {k: v for k, v in flag_counts.items() if v})
    print(f"legacy diagnostic: {len(legacy)} rows", {k: (v['input_rows'], v['distinct_value_rows'], v['rows_in_key_contradiction']) for k, v in lstats.items()})
    print("tz evidence:", [(e['file'].split('/')[-1], e['offset_hours']) for e in tz])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
