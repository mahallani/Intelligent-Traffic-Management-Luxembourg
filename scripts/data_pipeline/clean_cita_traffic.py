"""
Clean the CITA traffic data (provisional main source: cita_traffic_historical_fixed.csv).

Reads only (never modifies) data/historical/cita/traffic/*.csv and writes:
  data/interim/cita/cita_traffic_fixed_unique.csv      one row per (site, timestamp, direction),
                                                       ORIGINAL text values and timestamps kept
  data/processed/cita_traffic/cita_traffic_clean.csv   typed values, UTC times, quality flags
  data/reports/cita_traffic_cleaning_report.json       counts, exclusions, anomalies, coverage

Major limitation (verified 2026-10-10): the file was produced by the faulty v1 parser of
collect_cita_fixed.py. Each row holds the speed/occupancy/flow/direction/time of the LAST
sensor listed in the road's XML response, but the measurement_site (ALERT-C code), latitude
and longitude of the FIRST one. Values are real measurements of an UNIDENTIFIED sensor of
that road; their location is not reliable. Every row is flagged site_attribution_reliable=False.

Run from the project root:  python scripts/data_pipeline/clean_cita_traffic.py
"""
from __future__ import annotations

import json
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "historical" / "cita" / "traffic"
FIXED = SRC / "cita_traffic_historical_fixed.csv"
OTHERS = {"traffic_historical": SRC / "cita_traffic_historical.csv", "traffic_live": SRC / "cita_traffic_live.csv"}
INTERIM = ROOT / "data" / "interim" / "cita" / "cita_traffic_fixed_unique.csv"
PROCESSED = ROOT / "data" / "processed" / "cita_traffic" / "cita_traffic_clean.csv"
REPORT = ROOT / "data" / "reports" / "cita_traffic_cleaning_report.json"

KEY = ["measurement_site", "timestamp", "direction"]
# collection_time is the NAIVE local clock of the collecting PC. Verified: assuming UTC+1
# gives a 2-8 min lag behind the measurement time (UTC+0 -> 62-68 min, UTC+2 -> negative).
# Tunisia (Africa/Tunis) is UTC+1 all year (no DST).
COLLECTOR_TZ = timezone(timedelta(hours=1), "UTC+01:00 (Africa/Tunis)")
LU_BBOX = (49.44, 50.19, 5.73, 6.53)          # lat_min, lat_max, lon_min, lon_max (Luxembourg)
SPEED_LIMIT_KMH = 130                         # motorway limit in Luxembourg


def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        header = fh.readline()
    return max([",", ";", "\t", "|"], key=header.count)


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=detect_sep(path), dtype=str, encoding="utf-8-sig",
                     keep_default_na=False, na_values=[""], on_bad_lines="error")
    df.columns = df.columns.str.strip()
    df.insert(0, "source_line", range(2, len(df) + 2))   # line number in the source file (header = 1)
    return df


def missing(df: pd.DataFrame) -> dict:
    return {c: {"missing": int(df[c].isna().sum()), "pct": round(100 * df[c].isna().mean(), 2)}
            for c in df.columns}


def main() -> None:
    report: dict = {"source": str(FIXED.relative_to(ROOT)), "separator": detect_sep(FIXED)}
    raw = load(FIXED)
    value_cols = [c for c in raw.columns if c not in ("source_line", "collection_time")]
    report["input_rows"] = len(raw)
    report["input_missing"] = missing(raw.drop(columns="source_line"))

    # ---------- 1. uniqueness on (site, timestamp, direction)
    groups = raw.groupby(KEY, dropna=False, sort=False)
    n_states = raw.drop_duplicates(value_cols).groupby(KEY, dropna=False).size()
    conflicts = n_states[n_states > 1]
    report["uniqueness"] = {
        "key": KEY,
        "distinct_keys": int(groups.ngroups),
        "rows_with_identical_values_repeated": int(len(raw) - raw.drop_duplicates(value_cols).shape[0]),
        "keys_with_conflicting_values": int(len(conflicts)),
        "rows_with_missing_key_part": int(raw[KEY].isna().any(axis=1).sum()),
        "distinct_(road,timestamp)": int(raw.drop_duplicates(["road", "timestamp"]).shape[0]),
        "explanation": "the collector polled every 60 s while CITA updates every 5 min: the same "
                       "measurement was written up to N times with identical values",
    }
    if len(conflicts):
        raise SystemExit(f"{len(conflicts)} keys have conflicting values - stop, needs a decision")

    raw = raw.sort_values(["collection_time", "source_line"])
    agg = groups.agg(n_polls=("source_line", "size"), first_collection_time=("collection_time", "min"),
                     last_collection_time=("collection_time", "max")).reset_index()
    unique = raw.drop_duplicates(KEY, keep="first").merge(agg, on=KEY, how="left")
    unique = unique.rename(columns={"collection_time": "collection_time_original",
                                    "timestamp": "timestamp_original",
                                    "source_line": "source_line_first"})
    unique["site_attribution_reliable"] = False
    unique["value_origin"] = "last sensor listed in the road XML (identity not recorded)"
    unique["location_origin"] = "first sensor listed in the road XML (ALERT-C code + coordinates)"
    unique = unique.sort_values(["timestamp_original", "road"]).reset_index(drop=True)
    report["rows_removed_as_polling_duplicates"] = int(len(raw) - len(unique))
    report["polls_per_measurement"] = unique["n_polls"].describe().round(2).to_dict()
    INTERIM.parent.mkdir(parents=True, exist_ok=True)
    unique.to_csv(INTERIM, sep=";", index=False, encoding="utf-8-sig")

    # ---------- 2. typed + UTC + flags (processed)
    p = pd.DataFrame({
        "road": unique["road"],
        "measurement_site_alertc": unique["measurement_site"],
        "timestamp_original": unique["timestamp_original"],
        "timestamp_utc": pd.to_datetime(unique["timestamp_original"], utc=True, errors="coerce"),
        "collection_time_original": unique["first_collection_time"],
        "collection_time_utc": pd.to_datetime(unique["first_collection_time"], errors="coerce")
                                 .dt.tz_localize(COLLECTOR_TZ).dt.tz_convert("UTC"),
        "latitude": pd.to_numeric(unique["latitude"], errors="coerce"),
        "longitude": pd.to_numeric(unique["longitude"], errors="coerce"),
        "direction": unique["direction"],
        "speed_kmh": pd.to_numeric(unique["speed_kmh"], errors="coerce"),
        "occupancy_percent": pd.to_numeric(unique["occupancy_percent"], errors="coerce"),
        "vehicle_flow_rate_veh_h": pd.to_numeric(unique["vehicle_flow_rate"], errors="coerce"),
        "n_polls": unique["n_polls"],
        "site_attribution_reliable": unique["site_attribution_reliable"],
    })
    lag = (p["collection_time_utc"] - p["timestamp_utc"]).dt.total_seconds() / 60
    p["collection_lag_min"] = lag.round(2)
    lat0, lat1, lon0, lon1 = LU_BBOX
    flags = {
        "flag_timestamp_unparseable": p["timestamp_utc"].isna(),
        "flag_speed_above_limit": p["speed_kmh"] > SPEED_LIMIT_KMH,
        "flag_speed_zero": p["speed_kmh"] == 0,
        "flag_speed_zero_with_flow": (p["speed_kmh"] == 0) & (p["vehicle_flow_rate_veh_h"] > 0),
        "flag_occupancy_out_of_range": ~p["occupancy_percent"].between(0, 100) & p["occupancy_percent"].notna(),
        "flag_negative_flow": p["vehicle_flow_rate_veh_h"] < 0,
        "flag_outside_luxembourg": ~(p["latitude"].between(lat0, lat1) & p["longitude"].between(lon0, lon1)),
        "flag_collection_lag_unusual": ~lag.between(0, 15),
    }
    for k, v in flags.items():
        p[k] = v.fillna(False)
    p["any_anomaly_flag"] = pd.concat(flags.values(), axis=1).fillna(False).any(axis=1)
    excluded = p[p["flag_timestamp_unparseable"]]
    p = p[~p["flag_timestamp_unparseable"]].drop(columns="flag_timestamp_unparseable")
    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    p.to_csv(PROCESSED, sep=";", index=False, encoding="utf-8-sig")

    report["columns_decisions"] = {
        "vehicle_flow": "NOT carried to processed: 100% empty in all 106,808 rows. The XML element "
                        "<vehicleFlow> is a container whose only content is <vehicleFlowRate>; the parser "
                        "could never fill it. Kept as-is in the interim file.",
        "measurement_site": "renamed measurement_site_alertc in processed: it is an ALERT-C location code "
                            "of the FIRST sensor of the road, not a sensor id.",
        "collection_time": "original naive text kept (collection_time_original); collection_time_utc assumes "
                           "the collecting PC clock was UTC+1 (verified by the 2-8 min lag).",
        "timestamp": "original text with +02:00 offset kept (timestamp_original); timestamp_utc derived.",
    }
    report["excluded_rows"] = {"timestamp_unparseable": int(len(excluded))}
    report["output_rows"] = int(len(p))
    report["anomaly_flags"] = {k: int(v.sum()) for k, v in flags.items()}
    report["collection_lag_min"] = lag.describe().round(2).to_dict()
    report["value_ranges"] = {c: p[c].describe().round(2).to_dict()
                              for c in ("speed_kmh", "occupancy_percent", "vehicle_flow_rate_veh_h")}
    report["output_missing"] = {c: v for c, v in missing(p).items() if v["missing"]}

    # ---------- 3. coverage (this is what limits any model)
    ts = p["timestamp_utc"].drop_duplicates().sort_values()
    steps = ts.diff().dt.total_seconds().div(60)
    gaps = [{"after_utc": str(ts.iloc[i - 1]), "before_utc": str(ts.iloc[i]), "minutes": float(steps.iloc[i])}
            for i in range(1, len(ts)) if steps.iloc[i] > 5]
    span_min = (ts.max() - ts.min()).total_seconds() / 60
    report["coverage"] = {
        "first_utc": str(ts.min()), "last_utc": str(ts.max()),
        "span_hours": round(span_min / 60, 2),
        "distinct_5min_timestamps": int(len(ts)),
        "expected_5min_timestamps_in_span": int(span_min // 5 + 1),
        "gaps_over_5min": gaps,
        "rows_per_timestamp": p.groupby("timestamp_utc").size().value_counts().to_dict(),
        "rows_per_road": p["road"].value_counts().to_dict(),
        "sensors_per_road_in_one_raw_xml_snapshot": {"A1": 40, "A3": 29, "A4": 25, "A6": 36, "A7": 48, "A13": 51, "B40": 18},
        "share_of_sensor_measurements_captured_pct": round(100 * 7 / 247, 2),
    }

    # ---------- 4. the two other traffic files: kept as raw sources, not integrated
    report["not_integrated_sources"] = {}
    for name, path in OTHERS.items():
        o = load(path).drop(columns="source_line")
        report["not_integrated_sources"][name] = {
            "file": str(path.relative_to(ROOT)), "separator": detect_sep(path), "rows": len(o),
            "columns": list(o.columns), "exact_duplicates": int(o.duplicated().sum()),
            "missing_pct": {c: round(100 * o[c].isna().mean(), 1) for c in o.columns if o[c].isna().any()},
            "reason_not_integrated": {
                "traffic_historical": "first 10 min only (19:28-19:38 local), no sensor id, no speed/occupancy, "
                                      "written by the first collector (collect_cita.py)",
                "traffic_live": "collect_all_luxembourg.py read each <basicData> alone: speed rows and flow rows "
                                "are separate and carry neither sensor id nor measurement time",
            }[name],
        }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[OK] interim   : {INTERIM.relative_to(ROOT)} ({len(unique)} rows)")
    print(f"[OK] processed : {PROCESSED.relative_to(ROOT)} ({len(p)} rows)")
    print(f"[OK] report    : {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
