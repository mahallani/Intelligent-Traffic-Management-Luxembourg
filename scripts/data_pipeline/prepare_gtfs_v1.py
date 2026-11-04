"""
Validate and prepare the Luxembourg GTFS feed (data/raw/gtfs/extracted/*.txt, never modified).

Checks: separator/columns, primary keys, foreign keys between agency, routes, trips, stop_times, stops,
calendar, calendar_dates, shapes and transfers, time format (H:MM:SS, hours >= 24 allowed by GTFS for
trips running past midnight of their service day), time monotonicity inside each trip.
Prepared tables (separate from the originals, tag-versioned, never overwritten):
  data/processed/gtfs/gtfs_stop_times_prepared_<tag>.csv.xz   + seconds since service-day start, flags
  data/processed/gtfs/gtfs_stops_prepared_<tag>.csv           + zone membership / distance (coordinates only)
  data/processed/gtfs/gtfs_trips_prepared_<tag>.csv           + route, first/last time, stops in Kirchberg zone
  data/processed/gtfs/gtfs_service_dates_<tag>.csv            active dates per service_id (calendar + exceptions)
  data/processed/gtfs/gtfs_kirchberg_zone_stop_times_<tag>.csv stop_times at stops inside the Kirchberg SUMO zone
  data/reports/gtfs_preparation_<tag>.json
PT <-> road association: ONLY by stop coordinates inside the SUMO zone bbox (+ buffer); no matching to road edges
is claimed. GTFS is a timetable (planned service), not observed traffic.
Usage: python scripts/data_pipeline/prepare_gtfs_v1.py --tag v1 [--check-only]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, now_utc, read_csv_checked, rel, safe_path, write_csv, write_json  # noqa: E402

SRC = DATA / "raw/gtfs/extracted"
KIRCHBERG = (49.6227, 49.6307, 6.1418, 6.1573)
LUST = (49.55, 49.65, 6.03, 6.22)
BUFFER_DEG_LAT, BUFFER_DEG_LON = 0.0018, 0.0028   # ~200 m
PK = {"agency": ["agency_id"], "routes": ["route_id"], "trips": ["trip_id"], "stops": ["stop_id"],
      "calendar": ["service_id"], "calendar_dates": ["service_id", "date"], "stop_times": ["trip_id", "stop_sequence"]}


def load(name, **kw):
    return read_csv_checked(SRC / f"{name}.txt", min_columns=1, **kw)


def to_seconds(s):
    parts = s.str.extract(r"^\s*(\d{1,3}):(\d{2}):(\d{2})\s*$").astype(float)
    ok = parts.notna().all(axis=1) & (parts[1] < 60) & (parts[2] < 60)
    sec = (parts[0] * 3600 + parts[1] * 60 + parts[2]).where(ok)
    return sec.astype("Int64"), ok


def fk(child, ccol, parent, pcol, allow_empty=False):
    vals = child[ccol]
    if allow_empty:
        vals = vals.dropna()
    missing = ~vals.isin(set(parent[pcol]))
    return {"child_rows": int(len(vals)), "orphans": int(missing.sum()),
            "examples": sorted(vals[missing].unique().tolist())[:5]}


def service_dates(cal, cd):
    rows = []
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for r in cal.itertuples():
        d0 = date(int(r.start_date[:4]), int(r.start_date[4:6]), int(r.start_date[6:]))
        d1 = date(int(r.end_date[:4]), int(r.end_date[4:6]), int(r.end_date[6:]))
        flags = [getattr(r, d) == "1" for d in days]
        d = d0
        while d <= d1:
            if flags[d.weekday()]:
                rows.append((r.service_id, d.strftime("%Y%m%d"), "calendar"))
            d += timedelta(days=1)
    base = pd.DataFrame(rows, columns=["service_id", "date", "origin"])
    add = cd[cd.exception_type == "1"][["service_id", "date"]].assign(origin="calendar_dates_added")
    rem = set(map(tuple, cd[cd.exception_type == "2"][["service_id", "date"]].values))
    base = base[[(a, b) not in rem for a, b in zip(base.service_id, base.date)]]
    out = pd.concat([base, add]).drop_duplicates(["service_id", "date"]).sort_values(["service_id", "date"])
    return out, len(rem)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args(argv)
    outs = {"stop_times": DATA / f"processed/gtfs/gtfs_stop_times_prepared_{a.tag}.csv.xz",
            "stops": DATA / f"processed/gtfs/gtfs_stops_prepared_{a.tag}.csv",
            "trips": DATA / f"processed/gtfs/gtfs_trips_prepared_{a.tag}.csv",
            "service_dates": DATA / f"processed/gtfs/gtfs_service_dates_{a.tag}.csv",
            "kirchberg": DATA / f"processed/gtfs/gtfs_kirchberg_zone_stop_times_{a.tag}.csv",
            "report": REPORTS / f"gtfs_preparation_{a.tag}.json"}
    if a.check_only:
        for k, v in outs.items():
            print(f"{k}: {rel(v)} {'EXISTS (would refuse)' if v.exists() else 'would be created'}")
        return 0
    for v in outs.values():
        safe_path(v)
    t = {n: load(n) for n in ("agency", "routes", "trips", "stops", "calendar", "calendar_dates", "transfers", "frequencies")}
    t["stop_times"] = load("stop_times")
    shape_ids = load("shapes", usecols=["shape_id"])
    rep = {"generated_utc": now_utc(), "source": rel(SRC),
           "tables": {n: {"rows": len(d), "separator": d.attrs.get("separator"), "columns": list(d.columns)} for n, d in t.items()}}
    rep["tables"]["shapes"] = {"rows": len(shape_ids), "distinct_shape_id": int(shape_ids.shape_id.nunique())}
    rep["primary_keys_unique"] = {n: bool(not t[n].duplicated(k).any()) for n, k in PK.items()}
    services = pd.concat([t["calendar"].service_id, t["calendar_dates"].service_id]).drop_duplicates().to_frame()
    rep["foreign_keys"] = {
        "routes.agency_id->agency": fk(t["routes"], "agency_id", t["agency"], "agency_id"),
        "trips.route_id->routes": fk(t["trips"], "route_id", t["routes"], "route_id"),
        "trips.service_id->calendar|calendar_dates": fk(t["trips"], "service_id", services, "service_id"),
        "trips.shape_id->shapes": fk(t["trips"], "shape_id", shape_ids.drop_duplicates(), "shape_id", allow_empty=True),
        "stop_times.trip_id->trips": fk(t["stop_times"], "trip_id", t["trips"], "trip_id"),
        "stop_times.stop_id->stops": fk(t["stop_times"], "stop_id", t["stops"], "stop_id"),
        "stops.parent_station->stops": fk(t["stops"], "parent_station", t["stops"], "stop_id", allow_empty=True),
        "transfers.from_stop_id->stops": fk(t["transfers"], "from_stop_id", t["stops"], "stop_id"),
        "transfers.to_stop_id->stops": fk(t["transfers"], "to_stop_id", t["stops"], "stop_id"),
        "transfers.from_route_id->routes": fk(t["transfers"], "from_route_id", t["routes"], "route_id", allow_empty=True),
        "transfers.from_trip_id->trips": fk(t["transfers"], "from_trip_id", t["trips"], "trip_id", allow_empty=True),
        "calendar_dates.service_id->calendar": fk(t["calendar_dates"], "service_id", t["calendar"], "service_id"),
    }
    rep["unused"] = {"trips_without_stop_times": int((~t["trips"].trip_id.isin(set(t["stop_times"].trip_id))).sum()),
                     "stops_never_served": int((~t["stops"].stop_id.isin(set(t["stop_times"].stop_id))).sum()),
                     "routes_without_trips": int((~t["routes"].route_id.isin(set(t["trips"].route_id))).sum())}
    # ---- times
    st = t["stop_times"]
    st["arrival_s"], ok_a = to_seconds(st.arrival_time)
    st["departure_s"], ok_d = to_seconds(st.departure_time)
    st["stop_sequence_int"] = pd.to_numeric(st.stop_sequence, errors="coerce").astype("Int64")
    st = st.sort_values(["trip_id", "stop_sequence_int"], kind="stable")
    prev_dep = st.groupby("trip_id").departure_s.shift()
    flags = pd.DataFrame({
        "time_unparseable": ~(ok_a & ok_d).loc[st.index],
        "departure_before_arrival": st.departure_s < st.arrival_s,
        "time_decreases_in_trip": st.arrival_s < prev_dep,
        "after_24h_service_day": (st.arrival_s >= 86400) | (st.departure_s >= 86400),
    }).fillna(False)
    st["quality_flags"] = flags.apply(lambda r: "|".join(k for k, v in r.items() if v), axis=1)
    st["data_origin"] = "real_gtfs_timetable"
    rep["times"] = {"format": "H:MM:SS or HH:MM:SS (hour not zero-padded below 10 in this feed)",
                    "flag_counts": {k: int(v.sum()) for k, v in flags.items()},
                    "max_time": str(st.departure_s.max()), "min_time": str(st.arrival_s.min()),
                    "handling": "times kept as text + seconds since the service day start; values >= 86400 kept (next calendar day)"}
    # ---- stops
    s = t["stops"].copy()
    lat, lon = pd.to_numeric(s.stop_lat, errors="coerce"), pd.to_numeric(s.stop_lon, errors="coerce")
    s["in_kirchberg_zone"] = lat.between(KIRCHBERG[0], KIRCHBERG[1]) & lon.between(KIRCHBERG[2], KIRCHBERG[3])
    s["in_kirchberg_zone_200m_buffer"] = lat.between(KIRCHBERG[0] - BUFFER_DEG_LAT, KIRCHBERG[1] + BUFFER_DEG_LAT) & \
        lon.between(KIRCHBERG[2] - BUFFER_DEG_LON, KIRCHBERG[3] + BUFFER_DEG_LON)
    s["in_lust_bbox"] = lat.between(LUST[0], LUST[1]) & lon.between(LUST[2], LUST[3])
    s["coords_missing_or_outside_lux"] = lat.isna() | ~lat.between(49.3, 50.3) | ~lon.between(5.6, 6.6)
    s["data_origin"] = "real_gtfs_timetable"
    rep["stops"] = {"in_kirchberg_zone": int(s.in_kirchberg_zone.sum()),
                    "in_kirchberg_zone_200m_buffer": int(s.in_kirchberg_zone_200m_buffer.sum()),
                    "in_lust_bbox": int(s.in_lust_bbox.sum()),
                    "coords_missing_or_outside_lux": int(s.coords_missing_or_outside_lux.sum()),
                    "kirchberg_zone_stop_names": sorted(s.loc[s.in_kirchberg_zone, "stop_name"].unique().tolist())}
    kz = set(s.loc[s.in_kirchberg_zone, "stop_id"])
    # ---- trips
    tr = t["trips"].merge(t["routes"][["route_id", "route_short_name", "route_type", "agency_id"]], on="route_id", how="left")
    agg = st.groupby("trip_id").agg(n_stops=("stop_id", "size"), first_departure_s=("departure_s", "min"),
                                    last_arrival_s=("arrival_s", "max"),
                                    n_stops_in_kirchberg_zone=("stop_id", lambda x: int(x.isin(kz).sum())))
    tr = tr.merge(agg, left_on="trip_id", right_index=True, how="left")
    tr["runs_past_24h"] = tr.last_arrival_s >= 86400
    tr["data_origin"] = "real_gtfs_timetable"
    sd, n_removed = service_dates(t["calendar"], t["calendar_dates"])
    rep["calendar"] = {"service_ids": int(services.service_id.nunique()), "active_service_dates": len(sd),
                       "dates_removed_by_exceptions": n_removed,
                       "period": [sd.date.min(), sd.date.max()],
                       "trips_with_no_active_date": int((~tr.service_id.isin(set(sd.service_id))).sum())}
    rep["route_types"] = tr.drop_duplicates("route_id").route_type.value_counts().to_dict()
    kst = st[st.stop_id.isin(kz)].merge(tr[["trip_id", "route_short_name", "route_type", "service_id", "trip_headsign"]], on="trip_id")
    kst = kst.merge(s[["stop_id", "stop_name", "stop_lat", "stop_lon"]], on="stop_id")
    rep["kirchberg_zone"] = {"stop_times": len(kst), "trips": int(kst.trip_id.nunique()),
                             "routes": sorted(kst.route_short_name.dropna().unique().tolist()),
                             "association_rule": "stop coordinates inside the bbox of sumo/lust_4_intersections (49.6227-49.6307 N, 6.1418-6.1573 E); NOT matched to SUMO edges or LuST bus stops (LuST lines date from ~2015)"}
    rep["timezone"] = {"agency_timezone": t["agency"].agency_timezone.unique().tolist(),
                       "note": "Europe/Berlin declared by the operator; same UTC offsets as Europe/Luxembourg (CET/CEST)"}
    rep["outputs"] = {k: rel(v) for k, v in outs.items()}
    cols_st = ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time", "arrival_s", "departure_s",
               "pickup_type", "drop_off_type", "quality_flags", "data_origin"]
    rep["dimensions"] = {"stop_times": [len(st), len(cols_st)], "stops": list(s.shape), "trips": list(tr.shape),
                         "service_dates": list(sd.shape), "kirchberg_zone_stop_times": list(kst.shape)}
    write_csv(st[cols_st], outs["stop_times"])
    write_csv(s, outs["stops"])
    write_csv(tr, outs["trips"])
    write_csv(sd, outs["service_dates"])
    write_csv(kst, outs["kirchberg"])
    write_json(rep, outs["report"])
    print("PK unique:", rep["primary_keys_unique"])
    print("FK orphans:", {k: v["orphans"] for k, v in rep["foreign_keys"].items()})
    print("times:", rep["times"]["flag_counts"], "| calendar:", rep["calendar"])
    print("stops:", {k: v for k, v in rep["stops"].items() if k != "kirchberg_zone_stop_names"}, "| kirchberg:", rep["kirchberg_zone"]["trips"], "trips", rep["kirchberg_zone"]["routes"])
    print("dims:", rep["dimensions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
