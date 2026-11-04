"""
Clean the CITA events (roadworks / obstructions) from BOTH sources:
  data/historical/cita/events/cita_events_historical.csv  (collect_cita.py, 07 Oct 18:30-18:41)
  data/historical/cita/events/cita_events_live.csv        (collect_all_luxembourg.py, 07 Oct 18:57 -> 09 Oct)
Sources are only read. Outputs:
  data/interim/cita/cita_events_states.csv          one row per distinct STATE of an event per source,
                                                    original text values and times kept
  data/processed/cita_events/cita_events_clean.csv  typed, UTC times, safety_message boolean, enrichment
  data/reports/cita_events_matching.csv             historical <-> live correspondences + confidence
  data/reports/cita_events_cleaning_report.json

Event identity. The raw DATEX II XML carries situation ids and record ids/versions
(e.g. situation 237604, record 237604-2 version 4) but BOTH collectors dropped them. The
identity is therefore RECONSTRUCTED from the fields present in both files:
    event_key = (creation_time, start_time, destination, latitude, longitude)
It is documented as a reconstruction; correspondences that rely on fewer fields are marked
uncertain and never used to fill values.

Run from the project root:  python scripts/data_pipeline/clean_cita_events.py
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "historical" / "cita" / "events"
SOURCES = {"historical": SRC / "cita_events_historical.csv", "live": SRC / "cita_events_live.csv"}
INTERIM = ROOT / "data" / "interim" / "cita" / "cita_events_states.csv"
PROCESSED = ROOT / "data" / "processed" / "cita_events" / "cita_events_clean.csv"
MATCHING = ROOT / "data" / "reports" / "cita_events_matching.csv"
REPORT = ROOT / "data" / "reports" / "cita_events_cleaning_report.json"

EVENT_KEY = ["creation_time", "start_time", "destination", "latitude", "longitude"]
COLLECTOR_TZ = timezone(timedelta(hours=1), "UTC+01:00 (Africa/Tunis)")   # see clean_cita_traffic.py
TRUE_VALUES, FALSE_VALUES = {"true", "1", "yes"}, {"false", "0", "no"}


def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        header = fh.readline()
    return max([",", ";", "\t", "|"], key=header.count)


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=detect_sep(path), dtype=str, encoding="utf-8-sig",
                     keep_default_na=False, na_values=[""], on_bad_lines="error")
    df.columns = df.columns.str.strip()
    return df


def to_bool(s: pd.Series) -> tuple[pd.Series, int]:
    low = s.str.strip().str.lower()
    out = pd.Series(pd.NA, index=s.index, dtype="boolean")
    out[low.isin(TRUE_VALUES)] = True
    out[low.isin(FALSE_VALUES)] = False
    unknown = int((s.notna() & out.isna()).sum())        # non-empty but not interpretable -> NA, counted
    return out, unknown


def counts(s: pd.Series) -> dict:
    """value_counts with missing values reported as the key "<NA>" (JSON-safe)."""
    return {("<NA>" if pd.isna(k) else str(k)): int(v) for k, v in s.value_counts(dropna=False).items()}


def event_uid(row) -> str:
    raw = "|".join("" if pd.isna(row[c]) else str(row[c]) for c in EVENT_KEY)
    return "EV" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def main() -> None:
    report: dict = {"event_key": EVENT_KEY,
                    "event_key_note": "reconstructed; raw XML situation/record ids were not collected"}
    states = []
    for source, path in SOURCES.items():
        df = load(path)
        info = {"file": str(path.relative_to(ROOT)), "separator": detect_sep(path), "rows": len(df),
                "columns": list(df.columns),
                "missing_pct": {c: round(100 * df[c].isna().mean(), 1) for c in df.columns if df[c].isna().any()}}
        if "safety_message" in df:
            info["safety_message_raw_values"] = counts(df["safety_message"])
            # normalise the TEXT before computing states, so True/true is not a change of state
            b, unknown = to_bool(df["safety_message"])
            info["safety_message_uninterpretable"] = unknown
            df["safety_message"] = b.map({True: "true", False: "false"})
        attrs = [c for c in df.columns if c != "collection_time"]
        info["distinct_states_before_bool_normalisation"] = int(load(path).drop_duplicates(attrs).shape[0])
        g = df.groupby(attrs, dropna=False, sort=False)
        st = g.agg(first_seen=("collection_time", "min"), last_seen=("collection_time", "max"),
                   n_polls=("collection_time", "size")).reset_index()
        st.insert(0, "source", source)
        info["distinct_events"] = int(st.drop_duplicates(EVENT_KEY).shape[0])
        info["distinct_states"] = len(st)
        info["rows_collapsed_identical_repeats"] = int(len(df) - len(st))
        report[source] = info
        states.append(st)

    allst = pd.concat(states, ignore_index=True, sort=False)
    allst.insert(1, "event_uid", allst.apply(event_uid, axis=1))
    allst = allst.sort_values(["event_uid", "first_seen", "source"]).reset_index(drop=True)
    allst["state_index"] = allst.groupby(["event_uid", "source"]).cumcount() + 1

    # ---------- correspondences historical <-> live
    hist = allst[allst.source == "historical"].drop_duplicates("event_uid")
    live = allst[allst.source == "live"]
    rows = []
    for _, h in hist.iterrows():
        exact = live[live.event_uid == h.event_uid]
        if len(exact):
            rows.append({"historical_event_uid": h.event_uid, "live_event_uid": h.event_uid, "confidence": "exact",
                         "matched_on": "+".join(EVENT_KEY)})
            continue
        cand = live[(live.creation_time == h.creation_time) & (live.start_time == h.start_time)].drop_duplicates("event_uid")
        for _, c in cand.iterrows():
            rows.append({"historical_event_uid": h.event_uid, "live_event_uid": c.event_uid, "confidence": "uncertain",
                         "matched_on": "creation_time+start_time only (location/destination differ)"})
        if not len(cand):
            rows.append({"historical_event_uid": h.event_uid, "live_event_uid": None, "confidence": "none",
                         "matched_on": ""})
    # live events sharing creation+start but at another location: probably two records of one situation
    lv = live.drop_duplicates("event_uid")
    multi = lv.groupby(["creation_time", "start_time"]).event_uid.apply(list)
    for (ct, stt), uids in multi[multi.str.len() > 1].items():
        for i, a in enumerate(uids):
            for b in uids[i + 1:]:
                rows.append({"historical_event_uid": None, "live_event_uid": f"{a} / {b}", "confidence": "uncertain",
                             "matched_on": f"live-live: same creation_time {ct} and start_time, different location "
                                           "-> probably 2 records of one DATEX situation (ids not collected)"})
    matching = pd.DataFrame(rows)
    MATCHING.parent.mkdir(parents=True, exist_ok=True)
    matching.to_csv(MATCHING, sep=";", index=False, encoding="utf-8-sig")
    report["matching"] = matching["confidence"].value_counts().to_dict()

    # ---------- enrichment: road / event_type / location_description ONLY from exact matches
    exact_uids = set(matching.loc[matching.confidence == "exact", "historical_event_uid"])
    enrich = hist[hist.event_uid.isin(exact_uids)].set_index("event_uid")[["road", "event_type", "location_description"]]
    report["enrichment_conflicts"] = int((hist.groupby("event_uid")[["road", "event_type"]].nunique() > 1).any(axis=1).sum())

    INTERIM.parent.mkdir(parents=True, exist_ok=True)
    allst.to_csv(INTERIM, sep=";", index=False, encoding="utf-8-sig")

    p = allst.copy()
    for col in ("road", "event_type"):
        p[f"{col}_provenance"] = pd.Series(pd.NA, index=p.index, dtype="string")
        p.loc[p[col].notna(), f"{col}_provenance"] = "original"
        fill = p[col].isna() & p.event_uid.isin(enrich.index)
        vals = p.loc[fill, "event_uid"].map(enrich[col])
        p.loc[fill & vals.notna(), col] = vals[vals.notna()]
        p.loc[fill & vals.notna(), f"{col}_provenance"] = "historical_exact_match"
    p["safety_message"], _ = to_bool(p["safety_message"])          # boolean, NA kept as NA
    for c in ("creation_time", "version_time", "start_time"):
        p[f"{c}_utc"] = pd.to_datetime(p[c], utc=True, errors="coerce")
    for c in ("first_seen", "last_seen"):
        p[f"{c}_utc"] = pd.to_datetime(p[c], errors="coerce").dt.tz_localize(COLLECTOR_TZ).dt.tz_convert("UTC")
    for c in ("latitude", "longitude", "lanes_restricted", "operational_lanes", "original_lanes", "length_affected"):
        p[c] = pd.to_numeric(p[c], errors="coerce")
    p = p.rename(columns={"creation_time": "creation_time_original", "version_time": "version_time_original",
                          "start_time": "start_time_original", "first_seen": "first_seen_original",
                          "last_seen": "last_seen_original"})
    p["flag_lanes_inconsistent"] = (p["operational_lanes"] > p["original_lanes"]) | \
                                   (p["lanes_restricted"] > p["original_lanes"])
    p["flag_lanes_inconsistent"] = p["flag_lanes_inconsistent"].fillna(False)
    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    p.to_csv(PROCESSED, sep=";", index=False, encoding="utf-8-sig")

    report["output"] = {
        "states": len(p), "events": int(p.event_uid.nunique()),
        "states_per_event": p.groupby("event_uid").size().value_counts().to_dict(),
        "road_provenance": counts(p["road_provenance"]),
        "event_type_provenance": counts(p["event_type_provenance"]),
        "safety_message": counts(p["safety_message"]),
        "flag_lanes_inconsistent": int(p["flag_lanes_inconsistent"].sum()),
        "missing_pct": {c: round(100 * p[c].isna().mean(), 1) for c in p.columns if p[c].isna().any()},
    }
    report["columns_decisions"] = {
        "impact, comment": "kept although 100% empty in both sources (documented, not dropped)",
        "event_type": "100% empty in live; 78.5% empty in historical -> filled only from an exact historical match",
        "location_description": "100% empty in historical, absent from live",
        "safety_message": "'True'/'true' -> boolean True; empty stays NA; historical has no such column -> NA",
    }
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[OK] interim   : {INTERIM.relative_to(ROOT)} ({len(allst)} states)")
    print(f"[OK] processed : {PROCESSED.relative_to(ROOT)} ({len(p)} states, {p.event_uid.nunique()} events)")
    print(f"[OK] matching  : {MATCHING.relative_to(ROOT)}")
    print(f"[OK] report    : {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
