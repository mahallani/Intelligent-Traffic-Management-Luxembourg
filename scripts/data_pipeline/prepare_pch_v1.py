"""
Prepare the PCH (Ponts et Chaussées) 2025 traffic counts - Luxembourg national counting posts.

Input  : data/interim/pch/pch_trafic_2025_export_v1.csv.xz  (faithful export of data/raw/traffic/trafic_2025.xlsx,
         sheet "Data", made by export_pch_xlsx.py; the xlsx itself is never modified)
Outputs (never overwritten):
  data/processed/pch/pch_posts_<tag>.csv                     272 counting posts, coordinates LUREF + WGS84, coverage,
                                                             zone membership, candidate LuST edges (unverified)
  data/processed/pch/pch_daily_counts_<tag>.csv.xz           one row per post x day x direction x vehicle class,
                                                             24 hourly COUNTS (vehicles/hour) + checks
  data/processed/pch/pch_hourly_counts_long_lust_bbox_<tag>.csv.xz
                                                             same counts in long format, only posts inside the LuST bbox
  data/reports/pch_preparation_<tag>.json

These are COUNTS (vehicles per hour per direction / class). They are never speeds.

Field meanings - what is VERIFIED here and what is NOT:
  * P00_01..P23_24 : hourly counts; sum == SUM_TRAF verified on every row.
  * DIRECTION      : 1 = "D1 vers D2", 2 = "D2 vers D1", 3 = "D1 <-> D2 deux sens" (verified against the SENS text on all
                     posts) and DIRECTION 3 == 1 + 2 checked row by row.
  * VEHICULE       : U == C + V checked row by row -> U = all vehicles, C and V = a partition. The letters' meaning
                     (C = camions / heavy, V = voitures / light) is NOT documented by the publisher: kept as codes.
  * COORD_X/COORD_Y: treated as LUREF (EPSG:2169); verified by converting and comparing the result with the
                     known position of named localities (see report). Requires pyproj.
  * Hour reference : local time is assumed (not documented); 2025-03-30 (DST change day) is absent from the file.
Zone association: a post is associated to a simulation zone only by its coordinates (inside the zone bbox). LuST edge
candidates are the nearest edges of the ~2015 LuST network and are flagged as UNVERIFIED (manual check required).

Usage: python scripts/data_pipeline/prepare_pch_v1.py --tag v1 [--check-only] [--lust-net path/to/lust.net.xml]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, now_utc, rel, safe_path, sha256, write_csv, write_json  # noqa: E402

EXPORT = DATA / "interim/pch/pch_trafic_2025_export_v1.csv.xz"
HOURS = [f"P{h:02d}_{h + 1:02d}" for h in range(24)]
KEY = ["POSTE_ID", "DATECOM", "DIRECTION", "VEHICULE"]
ZONES = {  # lat_min, lat_max, lon_min, lon_max (from the SUMO networks of this project)
    "kirchberg_4tls": (49.6227, 49.6307, 6.1418, 6.1573),
    "lust_full": (49.55, 49.65, 6.03, 6.22),
}
# reference positions used to verify the CRS (approximate centres, public gazetteer values)
CRS_CHECKS = {"CLEMENCY": (49.597, 5.875), "WEMPERHARDT": (50.158, 6.046), "ECHTERNACH": (49.812, 6.418),
              "REMICH": (49.545, 6.367), "WASSERBILLIG": (49.715, 6.500), "ETTELBRUCK": (49.847, 6.104)}
CRS_TOLERANCE_KM = 3.0


def haversine_km(lat1, lon1, lat2, lon2):
    r = np.pi / 180
    a = np.sin((lat2 - lat1) * r / 2) ** 2 + np.cos(lat1 * r) * np.cos(lat2 * r) * np.sin((lon2 - lon1) * r / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def lust_candidates(posts, net_path, radius=60.0):
    try:
        import sumolib
    except ImportError:
        return None, "sumolib not available: LuST edge candidates not computed"
    net = sumolib.net.readNet(str(net_path))
    out = []
    for r in posts.itertuples():
        if not r.in_lust_full:
            out.append(pd.NA)
            continue
        x, y = net.convertLonLat2XY(r.lon, r.lat)
        near = sorted(net.getNeighboringEdges(x, y, radius), key=lambda t: t[1])
        out.append("|".join(f"{e.getID()}@{d:.0f}m" for e, d in near[:4]) or pd.NA)
    return out, f"nearest LuST edges within {radius:.0f} m of the post ({rel(net_path)}); UNVERIFIED"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1")
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--lust-net", type=Path, default=None)
    a = p.parse_args(argv)
    outs = {"posts": DATA / f"processed/pch/pch_posts_{a.tag}.csv",
            "daily": DATA / f"processed/pch/pch_daily_counts_{a.tag}.csv.xz",
            "long_lust": DATA / f"processed/pch/pch_hourly_counts_long_lust_bbox_{a.tag}.csv.xz",
            "report": REPORTS / f"pch_preparation_{a.tag}.json"}
    if a.check_only:
        print("input:", rel(EXPORT), "exists" if EXPORT.exists() else "MISSING")
        for k, v in outs.items():
            print(f"{k}: {rel(v)} {'EXISTS (would refuse)' if v.exists() else 'would be created'}")
        return 0
    for v in outs.values():
        safe_path(v)
    from pyproj import Transformer

    df = pd.read_csv(EXPORT, sep=";", dtype=str, keep_default_na=False, na_values=[""])
    expected = ["source_row"] + KEY + HOURS + ["SUM_TRAF", "LOCALITE", "ROUTE", "SENS", "D1", "D2", "COORD_X", "COORD_Y"]
    if list(df.columns) != expected:
        raise SystemExit(f"unexpected columns: {list(df.columns)}")
    rep = {"generated_utc": now_utc(), "input": rel(EXPORT), "input_sha256": sha256(EXPORT), "rows": len(df)}
    num = df[HOURS + ["SUM_TRAF"]].apply(pd.to_numeric, errors="coerce")
    rep["missing_values"] = int(df[KEY + HOURS + ["SUM_TRAF"]].isna().sum().sum())
    rep["non_integer_or_negative_counts"] = int(((num % 1 != 0) | (num < 0)).sum().sum())
    rep["duplicate_keys"] = int(df.duplicated(KEY).sum())
    rep["exact_duplicate_rows"] = int(df.drop(columns="source_row").duplicated().sum())

    # ---- posts
    first = df.groupby("POSTE_ID", sort=False)
    attrs = first[["LOCALITE", "ROUTE", "D1", "D2", "COORD_X", "COORD_Y"]].nunique()
    rep["posts_with_varying_attributes"] = int((attrs > 1).any(axis=1).sum())
    posts = first.agg(LOCALITE=("LOCALITE", "first"), ROUTE=("ROUTE", "first"), D1=("D1", "first"), D2=("D2", "first"),
                      COORD_X=("COORD_X", "first"), COORD_Y=("COORD_Y", "first"), n_days=("DATECOM", "nunique"),
                      first_date=("DATECOM", "min"), last_date=("DATECOM", "max"),
                      directions=("DIRECTION", lambda s: "|".join(sorted(s.unique()))),
                      vehicle_codes=("VEHICULE", lambda s: "|".join(sorted(s.unique())))).reset_index()
    posts["LOCALITE"] = posts["LOCALITE"].str.strip()
    tr = Transformer.from_crs(2169, 4326, always_xy=True)
    lon, lat = tr.transform(posts.COORD_X.astype(float).values, posts.COORD_Y.astype(float).values)
    posts["lat"], posts["lon"] = np.round(lat, 6), np.round(lon, 6)
    posts["crs_source"] = "EPSG:2169 (LUREF) - assumed, verified by locality positions"
    checks = []
    for name, (rlat, rlon) in CRS_CHECKS.items():
        m = posts[posts.LOCALITE.str.upper().str.startswith(name)]
        for r in m.itertuples():
            checks.append({"post": r.POSTE_ID, "locality": r.LOCALITE, "lat": r.lat, "lon": r.lon,
                           "reference": [rlat, rlon], "distance_km": round(float(haversine_km(r.lat, r.lon, rlat, rlon)), 2)})
    rep["crs_verification"] = {"method": "LUREF->WGS84 with pyproj, compared with locality centres",
                               "tolerance_km": CRS_TOLERANCE_KM, "checks": checks,
                               "all_within_tolerance": all(c["distance_km"] <= CRS_TOLERANCE_KM for c in checks)}
    for z, (a1, a2, o1, o2) in ZONES.items():
        posts[f"in_{z}"] = posts.lat.between(a1, a2) & posts.lon.between(o1, o2)
    kb = ZONES["kirchberg_4tls"]
    posts["distance_to_kirchberg_zone_centre_km"] = np.round(haversine_km(posts.lat, posts.lon, (kb[0] + kb[1]) / 2, (kb[2] + kb[3]) / 2), 2)
    if a.lust_net:
        cand, note = lust_candidates(posts, a.lust_net)
        posts["lust_edge_candidates_unverified"] = cand if cand is not None else pd.NA
        rep["lust_edge_candidates"] = note
    else:
        posts["lust_edge_candidates_unverified"] = pd.NA
        rep["lust_edge_candidates"] = "not computed (no --lust-net)"
    posts["data_origin"] = "real_pch_2025"

    # ---- direction semantics
    s = df.drop_duplicates(["POSTE_ID", "DIRECTION"])
    def sens_kind(r):
        txt = str(r.SENS).strip()
        if txt == f"{r.D1} vers {r.D2}":
            return "D1->D2"
        if txt == f"{r.D2} vers {r.D1}":
            return "D2->D1"
        return "both" if "<->" in txt else "other"
    rep["direction_vs_sens_text"] = pd.crosstab(s.DIRECTION, s.apply(sens_kind, axis=1)).to_dict()

    # ---- daily table + checks
    d = df[["source_row"] + KEY].copy()
    d["date"] = d.DATECOM.str[:10]
    for c in HOURS + ["SUM_TRAF"]:
        d[c] = num[c].astype("Int64")
    d["check_hours_sum_eq_SUM_TRAF"] = num[HOURS].sum(axis=1).eq(num.SUM_TRAF)
    tot = d.pivot_table(index=["POSTE_ID", "date", "VEHICULE"], columns="DIRECTION", values="SUM_TRAF", aggfunc="first")
    dir_ok = (tot.get("1") + tot.get("2")).eq(tot.get("3")).where(tot[["1", "2", "3"]].notna().all(axis=1))
    veh = d.pivot_table(index=["POSTE_ID", "date", "DIRECTION"], columns="VEHICULE", values="SUM_TRAF", aggfunc="first")
    veh_ok = (veh.C + veh.V).eq(veh.U).where(veh[["C", "U", "V"]].notna().all(axis=1))
    d["check_dir3_eq_dir1_plus_dir2"] = pd.MultiIndex.from_frame(d[["POSTE_ID", "date", "VEHICULE"]]).map(dir_ok.to_dict()).astype("boolean")
    d["check_U_eq_C_plus_V"] = pd.MultiIndex.from_frame(d[["POSTE_ID", "date", "DIRECTION"]]).map(veh_ok.to_dict()).astype("boolean")
    d["flag_zero_day"] = num.SUM_TRAF.eq(0)
    d["flag_isolated_zero_hours"] = (num[HOURS] == 0).sum(axis=1).between(1, 23) & num.SUM_TRAF.gt(0) & \
        ((num[HOURS] == 0).sum(axis=1) >= 6)
    d["direction_meaning"] = d.DIRECTION.map({"1": "D1->D2", "2": "D2->D1", "3": "both (1+2)"})
    d["data_origin"] = "real_pch_2025"
    d = d.drop(columns="DATECOM").rename(columns={"VEHICULE": "vehicle_code"})
    d = d[["POSTE_ID", "date", "DIRECTION", "direction_meaning", "vehicle_code"] + HOURS + ["SUM_TRAF",
          "check_hours_sum_eq_SUM_TRAF", "check_dir3_eq_dir1_plus_dir2", "check_U_eq_C_plus_V", "flag_zero_day",
          "flag_isolated_zero_hours", "source_row", "data_origin"]]
    rep["checks"] = {
        "hours_sum_eq_SUM_TRAF_pct": round(100 * d.check_hours_sum_eq_SUM_TRAF.mean(), 4),
        "dir3_eq_dir1_plus_dir2": {"evaluable_rows": int(d.check_dir3_eq_dir1_plus_dir2.notna().sum()),
                                   "true_pct": round(100 * d.check_dir3_eq_dir1_plus_dir2.mean(), 4),
                                   "false_rows": int((d.check_dir3_eq_dir1_plus_dir2 == False).sum())},  # noqa: E712
        "U_eq_C_plus_V": {"evaluable_rows": int(d.check_U_eq_C_plus_V.notna().sum()),
                          "true_pct": round(100 * d.check_U_eq_C_plus_V.mean(), 4),
                          "false_rows": int((d.check_U_eq_C_plus_V == False).sum())},  # noqa: E712
        "zero_days": int(d.flag_zero_day.sum()), "rows_with_6_to_23_zero_hours": int(d.flag_isolated_zero_hours.sum()),
    }
    dates = pd.to_datetime(d.date.unique())
    rep["period"] = {"first": str(dates.min().date()), "last": str(dates.max().date()), "distinct_days": len(dates),
                     "missing_days": sorted(str(x.date()) for x in pd.date_range("2025-01-01", "2025-12-31").difference(dates))}
    rep["posts"] = {"count": len(posts), "days_per_post": posts.n_days.describe().round(1).to_dict(),
                    "in_zone": {z: int(posts[f"in_{z}"].sum()) for z in ZONES},
                    "nearest_to_kirchberg_zone": posts.nsmallest(5, "distance_to_kirchberg_zone_centre_km")[
                        ["POSTE_ID", "LOCALITE", "ROUTE", "distance_to_kirchberg_zone_centre_km"]].to_dict("records"),
                    "one_direction_only": int((posts.directions == "1").sum())}
    rep["field_semantics"] = {
        "P00_01..P23_24": "vehicles counted in each hour (local time assumed, undocumented); sum == SUM_TRAF verified",
        "DIRECTION": "1 = D1->D2, 2 = D2->D1, 3 = both directions (=1+2); verified (SENS text, sums)",
        "VEHICULE": "U = C + V verified; U = all vehicles; C/V letters undocumented (probably heavy/light) -> kept as codes",
        "SUM_TRAF": "daily total of the row (vehicles/day)", "COORD_X/Y": "LUREF EPSG:2169 (verified)",
        "unit": "vehicles per hour (counts); NEVER a speed"}
    rep["limits"] = ["publisher page notes counts are 'encore sans compteurs pc' (some permanent counters missing)",
                     "no official data dictionary: semantics derived from the data and verified arithmetically",
                     "2025 counts vs LuST network (~2015): any use as SUMO demand must be labelled as an assumption"]

    # ---- long format for LuST-bbox posts
    lust_ids = set(posts.loc[posts.in_lust_full, "POSTE_ID"])
    sub = d[d.POSTE_ID.isin(lust_ids)]
    long = sub.melt(id_vars=["POSTE_ID", "date", "DIRECTION", "direction_meaning", "vehicle_code"], value_vars=HOURS,
                    var_name="hour_slot", value_name="vehicle_count")
    long["hour_start_local"] = long.hour_slot.str[1:3].astype(int)
    long["data_origin"] = "real_pch_2025"
    long = long.sort_values(["POSTE_ID", "date", "DIRECTION", "vehicle_code", "hour_start_local"])
    rep["outputs"] = {k: rel(v) for k, v in outs.items()}
    rep["dimensions"] = {"posts": list(posts.shape), "daily": list(d.shape), "long_lust_bbox": list(long.shape)}
    write_csv(posts, outs["posts"])
    write_csv(d, outs["daily"])
    write_csv(long, outs["long_lust"])
    write_json(rep, outs["report"])
    print("dimensions:", rep["dimensions"])
    print("checks:", rep["checks"])
    print("crs all within tolerance:", rep["crs_verification"]["all_within_tolerance"], "| period:", rep["period"])
    print("zones:", rep["posts"]["in_zone"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
