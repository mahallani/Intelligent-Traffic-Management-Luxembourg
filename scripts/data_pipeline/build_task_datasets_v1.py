"""
Build the per-objective datasets and the measurable readiness assessment.

  A incident detection      -> label inventory + traffic observations with event context
  B forecasting +5/+10/+15  -> per-sensor panel on a 5-min grid, lags/targets only where the exact step exists,
                               chronological split, long gaps never filled
  C SUMO / RL               -> real observables (CITA, PCH potential demand) and SIMULATED KPIs in separate files
  D impact KPIs             -> KPI catalogue: definition, real source availability, simulated values (labelled)

Inputs are the *_v1 outputs of the previous steps; nothing is overwritten.
Outputs: data/processed/tasks/task_*_<tag>.csv, data/reports/readiness_by_objective_<tag>.{json,md}
Usage: python scripts/data_pipeline/build_task_datasets_v1.py --tag v1 [--check-only]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, now_utc, read_csv_checked, rel, safe_path, write_csv, write_json, write_text  # noqa: E402

IN = {"traffic": DATA / "processed/cita_traffic/cita_traffic_reference_v1.csv",
      "events": DATA / "processed/cita_events/cita_events_v1.csv",
      "pch_posts": DATA / "processed/pch/pch_posts_v1.csv",
      "pch_long": DATA / "processed/pch/pch_hourly_counts_long_lust_bbox_v1.csv.xz",
      "gtfs_kz": DATA / "processed/gtfs/gtfs_kirchberg_zone_stop_times_v1.csv",
      "sim": DATA / "interim/simulation/kirchberg_4tls_validation_report_phase2_SIMULATED.json"}
STEP_MIN = 5
HORIZONS = (5, 10, 15)
LUST = (49.55, 49.65, 6.03, 6.22)
# DATEX II situation record classes: planned operator actions vs unplanned (non-ordered) situations.
PLANNED = {"MaintenanceWorks", "ConstructionWorks", "RoadOrCarriagewayOrLaneManagement", "SpeedManagement",
           "NetworkManagement", "RoadsideAssistance", "GeneralNetworkManagement"}
UNPLANNED = {"Accident", "VehicleObstruction", "AnimalPresenceObstruction", "EnvironmentalObstruction",
             "GeneralObstruction", "InfrastructureDamageObstruction", "EquipmentOrSystemFault", "AbnormalTraffic",
             "PoorEnvironmentConditions", "PoorRoadInfrastructure", "NonWeatherRelatedRoadConditions",
             "WeatherRelatedRoadConditions", "DisturbanceActivity", "PublicEvent"}
# readiness thresholds (documented, measurable)
CRIT = {
    "A": {"min_unplanned_incident_events": 100, "min_accident_events": 30, "min_days_continuous_traffic": 28},
    "B": {"min_consecutive_days_per_sensor": 7, "min_steps_per_sensor": 7 * 288, "max_missing_step_pct": 10.0,
          "min_sensors": 20, "min_target_pairs_per_horizon": 10000},
    "C": {"min_real_observation_points_in_sim_zone": 1, "min_days_for_calibration": 5},
    "D": {"real_baseline_kpis_required": ["travel_time", "speed", "flow"]},
}


def haversine_m(lat1, lon1, lat2, lon2):
    r = np.pi / 180
    a = np.sin((lat2 - lat1) * r / 2) ** 2 + np.cos(lat1 * r) * np.cos(lat2 * r) * np.sin((lon2 - lon1) * r / 2) ** 2
    return 6371000.0 * 2 * np.arcsin(np.sqrt(a))


def task_a(tr, ev):
    sensors = tr.dropna(subset=["latitude"]).drop_duplicates("sensor_id")[["sensor_id", "road", "latitude", "longitude"]]
    slat, slon = sensors.latitude.astype(float).values, sensors.longitude.astype(float).values
    rows = []
    for e in ev.itertuples():
        best = (pd.NA, np.nan)
        if pd.notna(e.latitude):
            same = (sensors.road.values == (e.road_name if isinstance(e.road_name, str) else ""))
            if same.any():
                d = haversine_m(float(e.latitude), float(e.longitude), slat[same], slon[same])
                i = int(np.argmin(d))
                best = (sensors.sensor_id.values[same][i], round(float(d[i])))
        cls = "unplanned" if e.record_type in UNPLANNED else "planned" if e.record_type in PLANNED else "unknown"
        rows.append({"record_id": e.record_id, "situation_id": e.situation_id, "record_type": e.record_type,
                     "record_subtypes": e.record_subtypes, "event_class_from_datex_type": cls,
                     "road_name": e.road_name, "latitude": e.latitude, "longitude": e.longitude,
                     "creation_time_utc": e.creation_time_utc, "overall_start_time_utc": e.overall_start_time_utc,
                     "first_seen_utc": e.first_seen_utc, "last_seen_utc": e.last_seen_utc,
                     "nearest_sensor_same_road": best[0], "nearest_sensor_distance_m": best[1],
                     "label_source": "DATEX xsi:type as published (no inference from comments)",
                     "data_origin": "real_cita_datex2_v3.6"})
    inv = pd.DataFrame(rows)
    # traffic observation + events visible in a snapshot within 30 min, same road, <= 2 km
    ctx = tr.copy()
    mts = pd.to_datetime(ctx.measurement_timestamp_utc, utc=True)
    evs = ev.dropna(subset=["latitude"]).copy()
    for c in ("first_seen_utc", "last_seen_utc", "overall_start_time_utc"):
        evs[c] = pd.to_datetime(evs[c], utc=True, format="ISO8601")
    n_ev, ids = [], []
    for r, t in zip(ctx.itertuples(), mts):
        if pd.isna(r.latitude):
            n_ev.append(pd.NA); ids.append(pd.NA); continue
        m = (evs.road_name == r.road) & (evs.overall_start_time_utc <= t) & \
            (evs.first_seen_utc - pd.Timedelta(minutes=30) <= t) & (evs.last_seen_utc + pd.Timedelta(minutes=30) >= t)
        sub = evs[m]
        if len(sub):
            d = haversine_m(float(r.latitude), float(r.longitude), sub.latitude.astype(float).values, sub.longitude.astype(float).values)
            sub = sub[d <= 2000]
        n_ev.append(len(sub)); ids.append("|".join(sub.record_id) or pd.NA)
    ctx = ctx[["measurement_timestamp_utc", "sensor_id", "road", "direction", "latitude", "longitude", "speed_kmh",
               "occupancy_percent", "vehicle_flow_rate", "quality_flags"]].copy()
    ctx["events_visible_same_road_2km"] = n_ev
    ctx["event_record_ids"] = ids
    ctx["context_rule"] = "event visible in a snapshot within +/-30 min, started before the measurement, same road, <= 2 km"
    ctx["data_origin"] = "real_cita"
    return inv, ctx


def task_b(tr):
    d = tr.copy()
    d["ts"] = pd.to_datetime(d.measurement_timestamp_utc, utc=True)
    for c in ("speed_kmh", "occupancy_percent", "vehicle_flow_rate"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.sort_values(["sensor_id", "ts"], kind="stable")          # chronological sort BEFORE any lag
    d["on_5min_grid"] = (d.ts.dt.minute % STEP_MIN == 0) & (d.ts.dt.second == 0)
    d["gap_before_min"] = d.groupby("sensor_id").ts.diff().dt.total_seconds() / 60
    d["long_gap_before"] = d.gap_before_min > STEP_MIN               # never filled
    idx = d.set_index(["sensor_id", "ts"])
    for c in ("speed_kmh", "occupancy_percent", "vehicle_flow_rate"):
        prev = d.groupby("sensor_id")[c].shift()
        d[f"lag1_{c}"] = prev.where(d.gap_before_min == STEP_MIN)  # lag only when the previous step is exactly 5 min before
        for h in HORIZONS:
            key = list(zip(d.sensor_id, d.ts + pd.Timedelta(minutes=h)))
            d[f"target_{c}_t+{h}"] = idx[c].reindex(key).values     # exact future timestamp only, no interpolation
    times = np.sort(d.ts.unique())
    n = len(times)
    cut_train, cut_val = times[max(0, int(np.floor(0.7 * n)) - 1)], times[max(0, int(np.floor(0.85 * n)) - 1)]
    d["split"] = np.where(d.ts <= cut_train, "train", np.where(d.ts <= cut_val, "validation", "test"))
    d["split_rule"] = "chronological on global timestamps (70/15/15), no shuffling"
    d["measurement_timestamp_utc"] = d.ts.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    d["data_origin"] = "real_cita"
    cols = ["sensor_id", "road", "direction", "measurement_timestamp_utc", "on_5min_grid", "gap_before_min",
            "long_gap_before", "speed_kmh", "occupancy_percent", "vehicle_flow_rate"] + \
        [c for c in d.columns if c.startswith("lag1_") or c.startswith("target_")] + ["split", "split_rule", "quality_flags", "data_origin"]
    return d[cols]


def task_c(tr, posts, long):
    lat, lon = pd.to_numeric(tr.latitude), pd.to_numeric(tr.longitude)
    cita = tr[lat.between(LUST[0], LUST[1]) & lon.between(LUST[2], LUST[3])][
        ["measurement_timestamp_utc", "sensor_id", "road", "direction", "latitude", "longitude", "speed_kmh",
         "occupancy_percent", "vehicle_flow_rate", "quality_flags"]].copy()
    cita["data_origin"] = "real_cita"
    cita["shared_observable_with_sumo"] = "speed (km/h), occupancy (%), flow (veh/h) at a detector - SUMO inductionLoop/E1 equivalents"
    long = long.copy()
    long["weekday"] = pd.to_datetime(long.date).dt.dayofweek
    wk = long[long.weekday.between(1, 3) & long.vehicle_code.eq("U")]   # Tue-Thu, all vehicles
    prof = wk.groupby(["POSTE_ID", "DIRECTION", "direction_meaning", "hour_start_local"]).vehicle_count.agg(
        mean_count_tue_thu="mean", median_count_tue_thu="median", n_days="count").reset_index()
    prof["mean_count_tue_thu"] = prof.mean_count_tue_thu.round(1)
    prof = prof.merge(posts[["POSTE_ID", "LOCALITE", "ROUTE", "D1", "D2", "lat", "lon", "in_kirchberg_4tls",
                             "lust_edge_candidates_unverified"]], on="POSTE_ID", how="left")
    prof["unit"] = "vehicles per hour (count, all vehicle classes U)"
    prof["compatibility_status"] = "POTENTIAL demand only: 2025 counts vs ~2015 LuST network, edge mapping unverified; not a calibration"
    prof["data_origin"] = "real_pch_2025"
    return cita, prof


def sim_kpis(sim):
    rows = []
    base = sim.get("baseline_x1", {})
    for k, v in base.items():
        rows.append({"scenario": "baseline_x1 (real LuST demand 07-08)", "kpi": k, "value": v})
    for s, vals in sim.get("strategies", {}).items():
        for k, v in (vals or {}).items():
            if k != "extra":
                rows.append({"scenario": f"{s} (demand x{sim.get('congested_scale')})", "kpi": k, "value": v})
    out = pd.DataFrame(rows)
    out["data_origin"] = "SIMULATED_sumo_lust_kirchberg_4tls"
    out["source_file"] = rel(IN["sim"])
    out["note"] = "simulation output (SUMO 1.27.1, LuST ~2015 demand); NOT a measurement, NOT calibrated on real data"
    return out


def kpi_catalogue(sim_df):
    cat = [("avg_travel_time_s", "s", "mean trip duration of vehicles in the zone", "no (data/historical/cita/travel_time is empty)"),
           ("mean_speed_kmh", "km/h", "mean vehicle speed", "partly: CITA motorway sensors only, none inside the Kirchberg zone"),
           ("avg_waiting_per_vehicle_s", "s", "time with speed < 0.1 m/s per vehicle", "no"),
           ("avg_total_queue_m", "m", "mean total queue length at the 4 signals", "no"),
           ("time_loss_s", "s", "time lost vs free-flow", "no"),
           ("co2_kg", "kg", "CO2 emitted (SUMO HBEFA model)", "no"),
           ("completed_trips", "veh", "vehicles that finished their trip", "no (PCH counts are cross-section counts, not trips)"),
           ("emergency_travel_time_s", "s", "travel time of the emergency vehicle", "no"),
           ("vehicle_flow_veh_h", "veh/h", "flow at a cross-section", "yes: CITA sensors (motorways) + PCH posts (2025, none in the Kirchberg zone)")]
    out = []
    for k, u, dfn, real in cat:
        sv = sim_df[sim_df.kpi == k]
        out.append({"kpi": k, "unit": u, "definition": dfn, "real_source_available": real,
                    "simulated_values": "; ".join(f"{r.scenario}={r.value}" for r in sv.itertuples()) or pd.NA,
                    "simulated_values_origin": "SIMULATED_sumo_lust_kirchberg_4tls" if len(sv) else pd.NA})
    return pd.DataFrame(out)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args(argv)
    T = DATA / "processed/tasks"
    outs = {"A_labels": T / f"task_A_event_label_inventory_{a.tag}.csv",
            "A_ctx": T / f"task_A_traffic_with_event_context_{a.tag}.csv",
            "B_panel": T / f"task_B_forecast_panel_{a.tag}.csv",
            "C_cita": T / f"task_C_real_cita_observables_lust_bbox_{a.tag}.csv",
            "C_pch": T / f"task_C_real_pch_potential_demand_profiles_{a.tag}.csv",
            "C_sim": T / f"task_C_SIMULATED_kpis_kirchberg_{a.tag}.csv",
            "D_cat": T / f"task_D_kpi_catalogue_{a.tag}.csv",
            "json": REPORTS / f"readiness_by_objective_{a.tag}.json",
            "md": REPORTS / f"readiness_by_objective_{a.tag}.md"}
    if a.check_only:
        for k, v in IN.items():
            print(f"input {k}: {rel(v)} {'ok' if v.exists() else 'MISSING'}")
        for k, v in outs.items():
            print(f"{k}: {rel(v)} {'EXISTS (would refuse)' if v.exists() else 'would be created'}")
        return 0
    for v in outs.values():
        safe_path(v)
    tr = read_csv_checked(IN["traffic"])
    ev = read_csv_checked(IN["events"])
    posts = read_csv_checked(IN["pch_posts"])
    posts["in_kirchberg_4tls"] = posts["in_kirchberg_4tls"].eq("True")
    long = pd.read_csv(IN["pch_long"], sep=";", dtype={"POSTE_ID": str, "DIRECTION": str, "vehicle_code": str})
    gkz = read_csv_checked(IN["gtfs_kz"])
    sim = json.loads(IN["sim"].read_text(encoding="utf-8"))

    inv, ctx = task_a(tr, ev)
    panel = task_b(tr)
    cita_c, pch_c = task_c(tr, posts, long)
    simdf = sim_kpis(sim)
    cat = kpi_catalogue(simdf)

    # ---------- measurable readiness
    days_traffic = pd.to_datetime(tr.measurement_timestamp_utc).dt.date.nunique()
    steps = panel.groupby("sensor_id").size()
    pairs = {h: int(panel[f"target_speed_kmh_t+{h}"].notna().sum()) for h in HORIZONS}
    R = {"A": {"measured": {"events_with_real_id": len(inv),
                            "unplanned_events": int((inv.event_class_from_datex_type == "unplanned").sum()),
                            "accident_events": int((inv.record_type == "Accident").sum()),
                            "days_with_traffic_data": days_traffic,
                            "traffic_rows_with_event_context": int(pd.to_numeric(ctx.events_visible_same_road_2km).fillna(0).gt(0).sum())},
                "criteria": CRIT["A"]},
         "B": {"measured": {"sensors": int(steps.size), "max_steps_per_sensor": int(steps.max()),
                            "distinct_timestamps": int(panel.measurement_timestamp_utc.nunique()),
                            "target_pairs_per_horizon": pairs,
                            "lag1_available_rows": int(panel.lag1_speed_kmh.notna().sum())},
                "criteria": CRIT["B"]},
         "C": {"measured": {"cita_sensors_in_kirchberg_zone": 0,
                            "pch_posts_in_kirchberg_zone": int(posts.in_kirchberg_4tls.sum()),
                            "cita_sensors_in_lust_bbox": int(cita_c.sensor_id.nunique()),
                            "pch_posts_in_lust_bbox": int(pch_c.POSTE_ID.nunique()),
                            "pch_posts_with_unverified_lust_edge_candidates": int(posts.lust_edge_candidates_unverified.notna().sum()),
                            "gtfs_trips_at_kirchberg_zone_stops": int(gkz.trip_id.nunique()),
                            "simulated_kpi_rows": len(simdf)},
                "criteria": CRIT["C"]},
         "D": {"measured": {"kpis_catalogued": len(cat),
                            "kpis_with_real_source": int(cat.real_source_available.str.startswith(("yes", "partly")).sum()),
                            "kpis_with_simulated_values": int(cat.simulated_values.notna().sum())},
                "criteria": CRIT["D"]}}
    mA, mB, mC = R["A"]["measured"], R["B"]["measured"], R["C"]["measured"]
    R["A"]["verdict"] = "NOT TRAINABLE" if (mA["unplanned_events"] < CRIT["A"]["min_unplanned_incident_events"] or
                                            mA["days_with_traffic_data"] < CRIT["A"]["min_days_continuous_traffic"]) else "CANDIDATE"
    R["B"]["verdict"] = "NOT TRAINABLE" if (mB["max_steps_per_sensor"] < CRIT["B"]["min_steps_per_sensor"] or
                                            min(pairs.values()) < CRIT["B"]["min_target_pairs_per_horizon"]) else "CANDIDATE"
    R["C"]["verdict"] = ("SIMULATION ONLY: RL can be trained and evaluated in SUMO; no real observation inside the "
                         "Kirchberg zone, so no calibration or real validation") if mC["cita_sensors_in_kirchberg_zone"] + mC["pch_posts_in_kirchberg_zone"] < 1 else "CANDIDATE"
    R["D"]["verdict"] = "SIMULATED KPIs ONLY: no real baseline for travel time / queues / waiting in the zone"
    rep = {"generated_utc": now_utc(), "inputs": {k: rel(v) for k, v in IN.items()},
           "outputs": {k: rel(v) for k, v in outs.items()},
           "dimensions": {"A_labels": list(inv.shape), "A_ctx": list(ctx.shape), "B_panel": list(panel.shape),
                          "C_cita": list(cita_c.shape), "C_pch": list(pch_c.shape), "C_sim": list(simdf.shape),
                          "D_cat": list(cat.shape)},
           "readiness": R}
    write_csv(inv, outs["A_labels"]); write_csv(ctx, outs["A_ctx"]); write_csv(panel, outs["B_panel"])
    write_csv(cita_c, outs["C_cita"]); write_csv(pch_c, outs["C_pch"]); write_csv(simdf, outs["C_sim"])
    write_csv(cat, outs["D_cat"]); write_json(rep, outs["json"])
    md = ["# Readiness by objective (" + a.tag + ")", "", f"Generated {rep['generated_utc']} by `{rel(Path(__file__))}`.", ""]
    for k, name in (("A", "Incident detection"), ("B", "Forecasting +5/+10/+15 min"), ("C", "SUMO / RL"), ("D", "Impact KPIs")):
        md += [f"## {k}. {name}", "", f"**Verdict: {R[k]['verdict']}**", "", "| Measured | Value |", "|---|---|"]
        md += [f"| {m} | {v} |" for m, v in R[k]["measured"].items()]
        md += ["", "| Criterion | Threshold |", "|---|---|"] + [f"| {m} | {v} |" for m, v in R[k]["criteria"].items()] + [""]
    md += ["## Datasets", "", "| Output | Rows x columns |", "|---|---|"] + \
          [f"| `{rel(outs[k])}` | {v[0]} x {v[1]} |" for k, v in rep["dimensions"].items()]
    write_text("\n".join(md) + "\n", outs["md"])
    for k in "ABCD":
        print(k, R[k]["verdict"], R[k]["measured"])
    print("dims:", rep["dimensions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
