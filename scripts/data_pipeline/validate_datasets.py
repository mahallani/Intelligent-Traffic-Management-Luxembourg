"""
Automated validation of the prepared datasets (all *_<tag> outputs).

Checks per dataset: expected columns, types (numeric parse), value ranges, timestamp format/offset, keys,
missing rates against documented thresholds, id integrity, absence of artificial duplicates, units,
traceability (source_file / data_origin), real vs simulated separation, legacy exclusion, temporal leakage.

  python scripts/data_pipeline/validate_datasets.py --check-only          # read-only, prints, exit code 0/1
  python scripts/data_pipeline/validate_datasets.py --report v1           # also writes data/reports/data_validation_v1.{json,md}
                                                                          # (refuses to overwrite an existing report)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, ROOT, now_utc, read_csv_checked, rel, write_json, write_text  # noqa: E402

UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$")
OFFSET_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
LUX = (49.44, 50.19, 5.73, 6.54)
KIRCHBERG = (49.6227, 49.6307, 6.1418, 6.1573)
# documented thresholds: maximum missing rate (%) tolerated per column before the check fails
MISSING_MAX = {"traffic": {"sensor_id": 0, "measurement_timestamp": 0, "speed_kmh": 15, "occupancy_percent": 15,
                           "vehicle_flow_rate": 5, "latitude": 15, "source_file": 0, "data_origin": 0},
               "events": {"record_id": 0, "situation_id": 0, "record_type": 0, "creation_time": 0, "overall_start_time": 0}}
REAL_ORIGINS = {"real_cita_datex2_v2", "real_cita_datex2_v3.6", "real_cita", "real_pch_2025", "real_gtfs_timetable"}


class V:
    def __init__(self):
        self.results = []

    def check(self, dataset, name, ok, detail=""):
        self.results.append({"dataset": dataset, "check": name, "passed": bool(ok), "detail": str(detail)[:300]})
        return ok


def num(s):
    return pd.to_numeric(s, errors="coerce")


def validate_traffic(v, tag):
    ds = f"cita_traffic_reference_{tag}"
    f = DATA / f"processed/cita_traffic/{ds}.csv"
    if not v.check(ds, "file exists", f.exists(), rel(f)):
        return
    d = read_csv_checked(f)
    req = ["measurement_timestamp", "collection_timestamp", "sensor_id", "road", "direction", "latitude", "longitude",
           "speed_kmh", "occupancy_percent", "vehicle_flow_rate", "source_file", "quality_flags"]
    v.check(ds, "recommended columns present", set(req) <= set(d.columns), sorted(set(req) - set(d.columns)))
    v.check(ds, "no fabricated vehicle_flow column", "vehicle_flow" not in d.columns)
    v.check(ds, "numeric columns parse", all(num(d[c]).notna().sum() == d[c].notna().sum() for c in
                                             ("speed_kmh", "occupancy_percent", "vehicle_flow_rate", "latitude", "longitude")))
    sp, oc, fl = num(d.speed_kmh), num(d.occupancy_percent), num(d.vehicle_flow_rate)
    v.check(ds, "speed 0-250 km/h", sp.dropna().between(0, 250).all(), sp.describe().to_dict())
    v.check(ds, "occupancy 0-100 %", oc.dropna().between(0, 100).all())
    v.check(ds, "flow >= 0 veh/h", (fl.dropna() >= 0).all())
    v.check(ds, "flow period 3600 s (unit)", num(d.flow_period_s).dropna().eq(3600).all())
    lat, lon = num(d.latitude), num(d.longitude)
    v.check(ds, "coordinates inside Luxembourg bbox", (lat.dropna().between(*LUX[:2]) & lon.dropna().between(*LUX[2:])).all())
    v.check(ds, "measurement_timestamp keeps explicit offset", d.measurement_timestamp.str.match(OFFSET_RE).all())
    v.check(ds, "*_utc timestamps end in +00:00", d.measurement_timestamp_utc.str.match(UTC_RE).all() and
            d.collection_timestamp_utc.str.match(UTC_RE).all())
    lag = (pd.to_datetime(d.collection_timestamp_utc, utc=True, format="ISO8601") -
           pd.to_datetime(d.measurement_timestamp_utc, utc=True)).dt.total_seconds()
    v.check(ds, "collection after measurement", (lag >= 0).all(), f"min lag {lag.min()} s")
    v.check(ds, "key sensor_id+measurement_timestamp unique (no artificial duplicate)",
            not d.duplicated(["sensor_id", "measurement_timestamp"]).any() or d.quality_flags.str.contains("conflict_same_key").any())
    v.check(ds, "sensor id prefix matches road", d.apply(lambda r: r.sensor_id.upper().startswith(str(r.road).upper() + "."), axis=1).all())
    v.check(ds, "data_origin real only", d.data_origin.isin(REAL_ORIGINS).all(), d.data_origin.unique())
    v.check(ds, "no legacy rows", ~d.source_file.str.contains("cita_traffic_historical|cita_traffic_live").any())
    srcs = set("|".join(d.source_file).split("|"))
    v.check(ds, "every source_file exists", all((ROOT / s).exists() for s in srcs), sorted(srcs)[:5])
    for c, mx in MISSING_MAX["traffic"].items():
        pct = 100 * d[c].isna().mean()
        v.check(ds, f"missing {c} <= {mx}%", pct <= mx, f"{pct:.1f}%")
    v.check(ds, "no CITA sensor inside the Kirchberg 4-signal zone (documented fact)",
            not (lat.between(*KIRCHBERG[:2]) & lon.between(*KIRCHBERG[2:])).any())


def validate_events(v, tag):
    ds = f"cita_events_{tag}"
    st_f = DATA / f"processed/cita_events/cita_events_record_versions_{tag}.csv"
    ev_f = DATA / f"processed/cita_events/{ds}.csv"
    co_f = REPORTS / f"cita_events_correspondence_{tag}.csv"
    if not all(v.check(ds, f"file exists {p.name}", p.exists()) for p in (st_f, ev_f, co_f)):
        return
    st, ev, co = read_csv_checked(st_f), read_csv_checked(ev_f), read_csv_checked(co_f)
    v.check(ds, "states: (record_id, record_version) unique", not st.duplicated(["record_id", "record_version"]).any() or
            st.quality_flags.str.contains("conflict_same_record_version").any())
    v.check(ds, "events: record_id unique", not ev.record_id.duplicated().any())
    v.check(ds, "record_id prefixed by situation_id", (ev.apply(lambda r: r.record_id.startswith(r.situation_id + "-"), axis=1)).all())
    v.check(ds, "every event has its states", set(ev.record_id) == set(st.record_id))
    v.check(ds, "versions are integers", num(st.record_version).notna().all())
    v.check(ds, "DATEX times keep explicit offsets", st.creation_time.str.match(OFFSET_RE).all() and
            st.overall_start_time.str.match(OFFSET_RE).all())
    v.check(ds, "safety_related_message normalised (true/false/NA)", st.safety_related_message.dropna().isin(["True", "False", "true", "false"]).all())
    v.check(ds, "correspondence record_ids exist", co.record_id.dropna().isin(set(st.record_id)).all())
    v.check(ds, "correspondence confidence in exact/uncertain/none", co.confidence.isin(["exact", "uncertain", "none"]).all())
    for c, mx in MISSING_MAX["events"].items():
        pct = 100 * st[c].isna().mean()
        v.check(ds, f"missing {c} <= {mx}%", pct <= mx, f"{pct:.1f}%")
    v.check(ds, "data_origin real only", ev.data_origin.isin(REAL_ORIGINS).all())


def validate_pch(v, tag):
    ds = f"pch_{tag}"
    pf = DATA / f"processed/pch/pch_posts_{tag}.csv"
    df = DATA / f"processed/pch/pch_daily_counts_{tag}.csv.xz"
    if not (v.check(ds, "posts file exists", pf.exists()) and v.check(ds, "daily file exists", df.exists())):
        return
    posts = read_csv_checked(pf)
    v.check(ds, "POSTE_ID unique in posts", not posts.POSTE_ID.duplicated().any())
    v.check(ds, "WGS84 coordinates inside Luxembourg bbox (+border posts margin)",
            num(posts.lat).between(49.40, 50.22).all() and num(posts.lon).between(5.70, 6.56).all())
    hours = [f"P{h:02d}_{h + 1:02d}" for h in range(24)]
    rows, dup, bad_sum, neg, origin_bad, speed_cols = 0, 0, 0, 0, 0, False
    seen = set()
    for ch in pd.read_csv(df, sep=";", dtype=str, chunksize=200_000, keep_default_na=False, na_values=[""]):
        rows += len(ch)
        speed_cols |= any("speed" in c.lower() for c in ch.columns)
        k = list(zip(ch.POSTE_ID, ch.date, ch.DIRECTION, ch.vehicle_code))
        dup += len(k) - len(set(k)) + len(seen.intersection(k))
        seen.update(k)
        x = ch[hours + ["SUM_TRAF"]].apply(pd.to_numeric)
        bad_sum += int((x[hours].sum(axis=1) != x.SUM_TRAF).sum())
        neg += int((x < 0).sum().sum())
        origin_bad += int((ch.data_origin != "real_pch_2025").sum())
    v.check(ds, "daily: key post+date+direction+vehicle unique", dup == 0, dup)
    v.check(ds, "daily: hours sum == SUM_TRAF", bad_sum == 0, bad_sum)
    v.check(ds, "daily: counts >= 0", neg == 0)
    v.check(ds, "daily: no speed column (counts are not speeds)", not speed_cols)
    v.check(ds, "daily: data_origin real_pch_2025", origin_bad == 0)
    v.check(ds, "daily: row count equals source export (815739)", rows == 815739, rows)


def validate_gtfs(v, tag):
    import json
    ds = f"gtfs_{tag}"
    rf = REPORTS / f"gtfs_preparation_{tag}.json"
    if not v.check(ds, "report exists", rf.exists()):
        return
    r = json.loads(rf.read_text(encoding="utf-8"))
    v.check(ds, "primary keys unique", all(r["primary_keys_unique"].values()), r["primary_keys_unique"])
    v.check(ds, "foreign keys: no orphan", all(x["orphans"] == 0 for x in r["foreign_keys"].values()))
    v.check(ds, "times parse, no decrease inside trips", r["times"]["flag_counts"]["time_unparseable"] == 0 and
            r["times"]["flag_counts"]["time_decreases_in_trip"] == 0)
    trips = read_csv_checked(DATA / f"processed/gtfs/gtfs_trips_prepared_{tag}.csv")
    v.check(ds, "trips prepared = trips source", len(trips) == r["tables"]["trips"]["rows"])
    v.check(ds, ">24h times kept (not wrapped)", (num(trips.last_arrival_s) >= 86400).sum() > 0)


def validate_tasks(v, tag):
    T = DATA / "processed/tasks"
    ds = f"tasks_{tag}"
    files = sorted(T.glob(f"task_*_{tag}.csv"))
    if not v.check(ds, "task files exist", len(files) >= 7, len(files)):
        return
    for f in files:
        d = read_csv_checked(f)
        origins = set(d.get("data_origin", pd.Series(dtype=str)).dropna())
        if "SIMULATED" in f.name:
            v.check(ds, f"{f.name}: only simulated rows", origins and all(o.startswith("SIMULATED") for o in origins), origins)
        elif "catalogue" in f.name:
            v.check(ds, f"{f.name}: simulated values labelled", d.simulated_values.isna().eq(d.simulated_values_origin.isna()).all())
        else:
            v.check(ds, f"{f.name}: only real rows", origins <= REAL_ORIGINS and len(origins) > 0, origins)
        if "source_file" in d:
            v.check(ds, f"{f.name}: no legacy source", ~d.source_file.fillna("").str.contains("historical.csv|_live.csv|_fixed.csv").any())
    b = read_csv_checked(T / f"task_B_forecast_panel_{tag}.csv")
    ts = pd.to_datetime(b.measurement_timestamp_utc, utc=True)
    order = {"train": 0, "validation": 1, "test": 2}
    sp = b.split.map(order)
    v.check(ds, "B: split chronological (max train < min test)", ts[sp == 0].max() < ts[sp == 2].min() if (sp == 2).any() else True)
    gap = num(b.gap_before_min)
    v.check(ds, "B: lag only when previous step exactly 5 min", b.loc[gap != 5, "lag1_speed_kmh"].isna().all())
    keys = set(zip(b.sensor_id, ts))
    ok = True
    for h in (5, 10, 15):
        m = b[f"target_speed_kmh_t+{h}"].notna()
        ok &= all((sid, t + pd.Timedelta(minutes=h)) in keys for sid, t in zip(b.sensor_id[m], ts[m]))
    v.check(ds, "B: targets only where the exact future step exists (no filled gaps)", ok)
    v.check(ds, "B: chronological order inside each sensor", (b.groupby("sensor_id").measurement_timestamp_utc.apply(lambda s: s.is_monotonic_increasing)).all())


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1", help="dataset tag to validate")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--check-only", action="store_true", help="read-only (default)")
    g.add_argument("--report", metavar="REPORT_TAG", help="also write data/reports/data_validation_<REPORT_TAG>.json/.md")
    a = p.parse_args(argv)
    v = V()
    for fn in (validate_traffic, validate_events, validate_pch, validate_gtfs, validate_tasks):
        try:
            fn(v, a.tag)
        except Exception as exc:  # a crash is a failed check, never a silent pass
            v.check(fn.__name__, "validator ran without error", False, repr(exc))
    res = pd.DataFrame(v.results)
    failed = res[~res.passed]
    for r in res.itertuples():
        print(("PASS " if r.passed else "FAIL ") + f"[{r.dataset}] {r.check}" + ("" if r.passed else f" -> {r.detail}"))
    print(f"\n{int(res.passed.sum())}/{len(res)} checks passed")
    if a.report:
        out = {"generated_utc": now_utc(), "dataset_tag": a.tag, "passed": int(res.passed.sum()), "total": len(res),
               "thresholds_missing_pct": MISSING_MAX, "results": v.results}
        write_json(out, REPORTS / f"data_validation_{a.report}.json")
        md = [f"# Data validation ({a.tag})", "", f"{out['passed']}/{out['total']} checks passed - {out['generated_utc']}", "",
              "| Dataset | Check | Result | Detail |", "|---|---|---|---|"] + \
             [f"| {r['dataset']} | {r['check']} | {'PASS' if r['passed'] else 'FAIL'} | {'' if r['passed'] else r['detail']} |" for r in v.results]
        write_text("\n".join(md) + "\n", REPORTS / f"data_validation_{a.report}.md")
    return 0 if failed.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
