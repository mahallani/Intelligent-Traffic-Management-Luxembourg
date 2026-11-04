"""
Build the CITA events datasets (DATEX II v3.6 situation records, Luxembourg motorways).

Sources (read only):
  id-bearing : data/raw/cita_events/situationrecord36*.xml          (raw snapshots)
               data/historical/cita/events/cita_events_records_v2*.csv (collect_cita_events_v2.py)
               data/interim/cita/validation_*/cita_events_records_v2*.csv
  legacy     : data/historical/cita/events/cita_events_historical.csv, cita_events_live.csv
               (situation/record ids and versions were NOT collected)

Outputs (never overwritten, tag-versioned):
  data/processed/cita_events/cita_events_record_versions_<tag>.csv  one row per (record_id, record_version) = a STATE
  data/processed/cita_events/cita_events_<tag>.csv                  one row per record_id = a unique EVENT
  data/interim/cita/cita_events_legacy_states_<tag>.csv             legacy distinct states + candidate record id
  data/reports/cita_events_correspondence_<tag>.csv                 legacy event -> record_id (exact / uncertain / none)
  data/reports/cita_events_completeness_<tag>.json

Rules: real ids are the key; legacy rows are attached to a record only through an EXACT match on
(creation_time, start_time, latitude, longitude, destination); weaker matches are kept as 'uncertain'
and never used to fill values. Booleans normalised to true/false, unknown kept as NA (raw text kept).
Event type = DATEX xsi:type (+ *Type sub-elements) as published; nothing is inferred from comments.
Usage:  python scripts/data_pipeline/build_cita_events_v1.py --tag v1 [--check-only]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, ROOT, now_utc, read_csv_checked, rel, safe_path, write_csv, write_json  # noqa: E402

LEGACY = {"historical": DATA / "historical/cita/events/cita_events_historical.csv",
          "live": DATA / "historical/cita/events/cita_events_live.csv"}
LEGACY_CLOCK = timezone(timedelta(hours=1))   # evidence: build_cita_traffic report (file mtime vs naive time)
TRUE, FALSE = {"true", "1", "yes"}, {"false", "0", "no"}
STATE_VALUE_COLS = ["record_type", "record_subtypes", "creation_time", "version_time", "probability",
                    "safety_related_message", "validity_status", "overall_start_time", "overall_end_time",
                    "lanes_restricted", "operational_lanes", "original_lanes", "carriageway", "road_name",
                    "road_destination", "location_description", "length_affected_m", "latitude", "longitude",
                    "bearing", "line_string_wgs84", "comment_type", "comment", "comment_lang"]
LEGACY_KEY = ["creation_time", "start_time", "destination", "latitude", "longitude"]


def load_parser():
    spec = importlib.util.spec_from_file_location("evc", ROOT / "collect_cita_events_v2.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sources():
    xmls = sorted((DATA / "raw/cita_events").glob("situationrecord36*.xml"))
    csvs = sorted((DATA / "historical/cita/events").glob("cita_events_records_v2*.csv")) + \
        sorted((DATA / "interim/cita").glob("validation_*/cita_events_records_v2*.csv"))
    return xmls, csvs


def to_bool(s):
    low = s.astype("string").str.strip().str.lower()
    out = pd.Series(pd.NA, index=s.index, dtype="boolean")
    out[low.isin(TRUE)] = True
    out[low.isin(FALSE)] = False
    return out


def load_records(ev):
    xmls, csvs = sources()
    frames, inputs = [], []
    for f in xmls:
        mt = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat()
        d = pd.DataFrame(ev.parse_events_xml(f.read_bytes(), mt), columns=ev.RECORD_COLUMNS)
        d = d.astype(object).where(d.notna(), None).astype(str).replace({"None": pd.NA, "": pd.NA})
        d["collection_timestamp_origin"] = "file_mtime_utc"
        d["source_file"] = rel(f)
        frames.append(d)
        inputs.append({"file": rel(f), "kind": "raw_xml", "records": len(d)})
    for f in csvs:
        d = read_csv_checked(f, expected_columns=ev.RECORD_COLUMNS)
        d["collection_timestamp_origin"] = "collector_utc_clock"
        d["source_file"] = rel(f)
        frames.append(d)
        inputs.append({"file": rel(f), "kind": "collector_v2_csv", "records": len(d)})
    return pd.concat(frames, ignore_index=True), inputs


def dedup_states(df):
    df = df.copy()
    df["_sig"] = df[STATE_VALUE_COLS].fillna("<NA>").astype(str).agg("|".join, axis=1)
    key = ["record_id", "record_version"]
    df["_conflict"] = df.groupby(key)["_sig"].transform("nunique") > 1
    df = df.sort_values(key + ["collection_timestamp_utc"], kind="stable")
    g = df.groupby(key + ["_sig"], sort=False)
    out = g.head(1).copy()
    out["n_sightings"] = g["_sig"].transform("size").loc[out.index]
    out["first_seen_utc"] = g["collection_timestamp_utc"].transform("min").loc[out.index]
    out["last_seen_utc"] = g["collection_timestamp_utc"].transform("max").loc[out.index]
    files = g["source_file"].agg(lambda s: "|".join(sorted(set(s))))
    out["source_file"] = [files.loc[k] for k in out[key + ["_sig"]].itertuples(index=False, name=None)]
    out["safety_related_message_raw"] = out["safety_related_message"]
    out["safety_related_message"] = to_bool(out["safety_related_message"])
    flags = pd.DataFrame({
        "conflict_same_record_version": out["_conflict"],
        "collection_ts_from_file_mtime": out["collection_timestamp_origin"].eq("file_mtime_utc"),
        "record_type_missing": out["record_type"].isna(),
        "location_missing": out["latitude"].isna(),
        "lanes_inconsistent": (pd.to_numeric(out.operational_lanes, errors="coerce") > pd.to_numeric(out.original_lanes, errors="coerce")) |
                              (pd.to_numeric(out.lanes_restricted, errors="coerce") > pd.to_numeric(out.original_lanes, errors="coerce")),
        "safety_flag_unknown": out["safety_related_message"].isna(),
    }).fillna(False)
    out["quality_flags"] = flags.apply(lambda r: "|".join(k for k, v in r.items() if v), axis=1)
    for c in ("creation_time", "version_time", "overall_start_time", "overall_end_time"):
        out[c + "_utc"] = pd.to_datetime(out[c], utc=True, errors="coerce", format="ISO8601").dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    out["data_origin"] = "real_cita_datex2_v3.6"
    stats = {"input_rows": len(df), "states": len(out), "identical_repeats_collapsed": len(df) - len(out),
             "record_versions_in_contradiction": int(df.loc[df._conflict].groupby(key).ngroups)}
    return out.drop(columns=["_sig", "_conflict"]), stats, {k: int(v.sum()) for k, v in flags.items()}


def events_from_states(st):
    st = st.copy()
    st["_v"] = pd.to_numeric(st["record_version"], errors="coerce")
    st = st.sort_values(["record_id", "_v", "first_seen_utc"])
    last = st.groupby("record_id").tail(1).set_index("record_id")
    g = st.groupby("record_id")
    ev = pd.DataFrame({
        "situation_id": last["situation_id"], "record_type": last["record_type"],
        "record_subtypes": last["record_subtypes"],
        "creation_time": g["creation_time"].first(), "overall_start_time": g["overall_start_time"].first(),
        "overall_end_time_latest": last["overall_end_time"],
        "first_version": g["record_version"].first(), "latest_version": last["record_version"],
        "n_versions_observed": g["record_version"].nunique(),
        "latest_version_time": last["version_time"],
        "first_seen_utc": g["first_seen_utc"].min(), "last_seen_utc": g["last_seen_utc"].max(),
        "road_name": last["road_name"], "road_destination": last["road_destination"],
        "carriageway": last["carriageway"], "latitude": last["latitude"], "longitude": last["longitude"],
        "lanes_restricted_latest": last["lanes_restricted"], "validity_status_latest": last["validity_status"],
        "safety_related_message_latest": last["safety_related_message"],
        "comment_latest": last["comment"], "comment_lang": last["comment_lang"],
        "types_differ_between_versions": g["record_type"].nunique() > 1,
        "end_observed": False,
        "end_note": "events are not flagged terminated by CITA; they disappear from the feed. With isolated snapshots the disappearance time is unknown",
    }).reset_index()
    for c in ("creation_time", "overall_start_time"):
        ev[c + "_utc"] = pd.to_datetime(ev[c], utc=True, errors="coerce", format="ISO8601").dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    ev["data_origin"] = "real_cita_datex2_v3.6"
    return ev


def legacy_states():
    frames, info = [], {}
    for src, f in LEGACY.items():
        d = read_csv_checked(f)
        if "safety_message" in d:
            d["safety_message_raw"] = d["safety_message"]
            d["safety_message"] = to_bool(d["safety_message"]).map({True: "true", False: "false"})
        attrs = [c for c in d.columns if c not in ("collection_time", "safety_message_raw")]
        g = d.groupby(attrs, dropna=False, sort=False)
        st = g.agg(first_seen=("collection_time", "min"), last_seen=("collection_time", "max"),
                   n_polls=("collection_time", "size"),
                   safety_message_raw=("safety_message_raw", lambda s: "|".join(sorted(set(s.dropna())))) if "safety_message_raw" in d else ("collection_time", "size")).reset_index()
        if "safety_message_raw" not in d:
            st = st.drop(columns=["safety_message_raw"])
        st.insert(0, "source", src)
        st["source_file"] = rel(f)
        info[src] = {"file": rel(f), "rows": len(d), "distinct_states": len(st), "identical_repeats_collapsed": len(d) - len(st)}
        frames.append(st)
    allst = pd.concat(frames, ignore_index=True, sort=False)
    allst.insert(1, "legacy_event_uid", allst[LEGACY_KEY].fillna("").astype(str).agg("|".join, axis=1)
                 .map(lambda s: "LEG" + hashlib.sha1(s.encode()).hexdigest()[:10]))
    for c in ("first_seen", "last_seen"):
        allst[c + "_utc"] = pd.to_datetime(allst[c]).dt.tz_localize(LEGACY_CLOCK).dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    allst["quality_flags"] = "legacy_no_datex_ids|collection_time_naive_pc_clock_utc+01"
    allst["data_origin"] = "real_cita_legacy_collector"
    return allst, info


def correspond(leg, ev_states):
    rec = ev_states.drop_duplicates(["record_id", "creation_time", "overall_start_time", "latitude", "longitude", "road_destination"])
    rows = []
    for uid, g in leg.groupby("legacy_event_uid"):
        h = g.iloc[0]
        exact = rec[(rec.creation_time == h.creation_time) & (rec.overall_start_time == h.start_time) &
                    (rec.latitude == h.latitude) & (rec.longitude == h.longitude) & (rec.road_destination == h.destination)]
        ids = sorted(set(exact.record_id))
        if len(ids) == 1:
            rows.append((uid, ids[0], "exact", "creation_time+start_time+latitude+longitude+destination", len(g)))
            continue
        if len(ids) > 1:
            for i in ids:
                rows.append((uid, i, "uncertain", "exact key matches several records", len(g)))
            continue
        cand = sorted(set(rec[(rec.creation_time == h.creation_time) & (rec.overall_start_time == h.start_time)].record_id))
        for i in cand:
            rows.append((uid, i, "uncertain", "creation_time+start_time only (location/destination differ)", len(g)))
        if not cand:
            rows.append((uid, pd.NA, "none", "no record with same creation_time+start_time in id-bearing snapshots", len(g)))
    return pd.DataFrame(rows, columns=["legacy_event_uid", "record_id", "confidence", "matched_on", "legacy_states"])


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args(argv)
    outs = {"states": DATA / f"processed/cita_events/cita_events_record_versions_{a.tag}.csv",
            "events": DATA / f"processed/cita_events/cita_events_{a.tag}.csv",
            "legacy": DATA / f"interim/cita/cita_events_legacy_states_{a.tag}.csv",
            "correspondence": REPORTS / f"cita_events_correspondence_{a.tag}.csv",
            "report": REPORTS / f"cita_events_completeness_{a.tag}.json"}
    if a.check_only:
        xmls, csvs = sources()
        print("inputs:", [rel(x) for x in xmls + csvs + list(LEGACY.values())])
        for k, v in outs.items():
            print(f"{k}: {rel(v)} {'EXISTS (would refuse)' if v.exists() else 'would be created'}")
        return 0
    for v in outs.values():
        safe_path(v)
    evp = load_parser()
    raw, inputs = load_records(evp)
    states, sstats, flags = dedup_states(raw)
    events = events_from_states(states)
    leg, linfo = legacy_states()
    corr = correspond(leg, states)
    best = corr[corr.confidence == "exact"].set_index("legacy_event_uid")["record_id"]
    leg["record_id_exact_match"] = leg["legacy_event_uid"].map(best)
    unc = corr[corr.confidence == "uncertain"].groupby("legacy_event_uid")["record_id"].agg("|".join)
    leg["record_id_uncertain_candidates"] = leg["legacy_event_uid"].map(unc)
    write_csv(states, outs["states"])
    write_csv(events, outs["events"])
    write_csv(leg, outs["legacy"])
    write_csv(corr, outs["correspondence"])
    rep = {
        "generated_utc": now_utc(), "script": rel(Path(__file__)), "parser_version": evp.PARSER_VERSION,
        "inputs": inputs + [{"file": rel(f), "kind": "legacy_csv_no_ids"} for f in LEGACY.values()],
        "outputs": {k: rel(v) for k, v in outs.items()},
        "states": {"rows": len(states), **sstats, "quality_flag_counts": flags,
                   "missing_pct": {c: round(100 * states[c].isna().mean(), 1) for c in STATE_VALUE_COLS},
                   "snapshots_utc": sorted(states.first_seen_utc.unique().tolist())},
        "events": {"rows": len(events), "situations": int(events.situation_id.nunique()),
                   "record_types": events.record_type.value_counts().to_dict(),
                   "record_subtypes": events.record_subtypes.value_counts().to_dict(),
                   "roads": events.road_name.value_counts(dropna=False).rename(index=lambda x: "<NA>" if pd.isna(x) else x).to_dict(),
                   "seen_in_both_snapshots": int((events.first_seen_utc != events.last_seen_utc).sum()),
                   "end_times_observed": 0},
        "legacy": {"per_source": linfo, "distinct_states": len(leg), "distinct_events": int(leg.legacy_event_uid.nunique())},
        "correspondence": {"by_confidence_rows": corr.confidence.value_counts().to_dict(),
                           "legacy_events_exact": int(corr.loc[corr.confidence == "exact", "legacy_event_uid"].nunique()),
                           "legacy_events_uncertain": int(corr.loc[corr.confidence == "uncertain", "legacy_event_uid"].nunique()),
                           "legacy_events_unmatched": int(corr.loc[corr.confidence == "none", "legacy_event_uid"].nunique()),
                           "rule": "exact = same creation_time, start_time, latitude, longitude and destination as a record with real id; uncertain values are never used to fill fields"},
        "labels": {
            "incident_types_available": "record_type from DATEX xsi:type only",
            "accident_records": int(events.record_type.isin(["Accident", "VehicleObstruction", "AbnormalTraffic"]).sum()),
            "note": "the observed feed contains roadworks, equipment faults and general obstructions; no accident record was observed in the snapshots. No type was inferred from comments (comments are in Luxembourgish, free text)."},
        "booleans": {"safety_related_message": "true/false/NA; raw text kept in *_raw",
                     "legacy safety_message": "'True'/'true' -> true; empty -> NA; historical file has no such column -> absent"},
        "timezone": {"datex_times": "explicit offsets in the payload (+01:00/+02:00), converted to *_utc",
                     "legacy_collection_time": "naive PC clock, UTC+01 per file-mtime evidence (see cita_traffic_build_v1.json); *_utc columns derived with that assumption and flagged"},
    }
    write_json(rep, outs["report"])
    print(f"states {len(states)} | events {len(events)} ({events.situation_id.nunique()} situations) | legacy states {len(leg)} / events {leg.legacy_event_uid.nunique()}")
    print("dedup:", sstats, "| flags:", {k: v for k, v in flags.items() if v})
    print("correspondence:", rep["correspondence"])
    print("types:", rep["events"]["record_types"], "| seen in both snapshots:", rep["events"]["seen_in_both_snapshots"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
