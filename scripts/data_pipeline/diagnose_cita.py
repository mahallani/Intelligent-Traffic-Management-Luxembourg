"""Read-only diagnostic of the CITA CSV files (separator, schema, malformed rows,
duplicates, missing values, value ranges, overlaps). Writes data/reports/cita_diagnostic.json.
Never modifies the source files."""
import csv, io, json, sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "historical" / "cita"
FILES = {
 "traffic_historical": D/"traffic/cita_traffic_historical.csv",
 "traffic_fixed": D/"traffic/cita_traffic_historical_fixed.csv",
 "traffic_live": D/"traffic/cita_traffic_live.csv",
 "events_historical": D/"events/cita_events_historical.csv",
 "events_live": D/"events/cita_events_live.csv",
}
def detect(path):
    head = path.read_text(encoding="utf-8-sig").splitlines()[0]
    return max([",", ";", "\t", "|"], key=head.count)
out = {}
for name, p in FILES.items():
    sep = detect(p)
    # structural check with csv module: field count per row
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=sep))
    hdr = rows[0]; counts = {}
    bad = []
    for i, r in enumerate(rows[1:], start=2):
        counts[len(r)] = counts.get(len(r), 0) + 1
        if len(r) != len(hdr) and len(bad) < 3: bad.append((i, len(r), r[:4]))
    df = pd.read_csv(p, sep=sep, dtype=str, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    miss = {c: int(df[c].isna().sum()) for c in df.columns}
    info = {"sep": sep, "rows": len(df), "n_cols": len(df.columns), "columns": list(df.columns),
            "field_count_distribution": counts, "bad_rows_sample": bad,
            "exact_duplicates": int(df.duplicated().sum()),
            "missing": {c: f"{v} ({100*v/len(df):.1f}%)" for c, v in miss.items() if v},
            "fully_empty_cols": [c for c, v in miss.items() if v == len(df)]}
    for c in ("collection_time", "timestamp", "creation_time", "start_time"):
        if c in df:
            s = df[c].dropna()
            info[f"{c}_range"] = [s.min(), s.max(), f"{s.nunique()} distinct"]
    if "road" in df: info["roads"] = df["road"].value_counts(dropna=False).to_dict()
    for c in ("speed_kmh", "occupancy_percent", "vehicle_flow", "vehicle_flow_rate", "latitude", "longitude",
              "lanes_restricted", "operational_lanes", "original_lanes", "length_affected"):
        if c in df:
            num = pd.to_numeric(df[c], errors="coerce")
            nonnum = int(df[c].notna().sum() - num.notna().sum())
            info[f"{c}_stats"] = {"min": num.min(), "max": num.max(), "mean": round(num.mean(), 2) if num.notna().any() else None,
                                  "non_numeric": nonnum, "negative": int((num < 0).sum())}
    for c in ("direction", "event_type", "impact", "probability", "validity", "safety_message"):
        if c in df: info[f"{c}_values"] = df[c].value_counts(dropna=False).head(8).to_dict()
    if "measurement_site" in df:
        info["measurement_site_distinct"] = int(df["measurement_site"].nunique())
    out[name] = info
    globals()[name] = df
# key-based duplicates & overlaps
def key_dups(df, keys):
    k = [c for c in keys if c in df]
    return k, int(df.duplicated(subset=k).sum())
out["_key_duplicates"] = {
 "traffic_fixed[measurement_site,timestamp,direction]": key_dups(traffic_fixed, ["measurement_site","timestamp","direction"]),
 "traffic_fixed[all except collection_time]": int(traffic_fixed.drop(columns=["collection_time"]).duplicated().sum()),
 "traffic_live[all except collection_time]": int(traffic_live.drop(columns=["collection_time"]).duplicated().sum()),
 "traffic_historical[all except collection_time]": int(traffic_historical.drop(columns=["collection_time"]).duplicated().sum()),
 "events_live[all except collection_time]": int(events_live.drop(columns=["collection_time"]).duplicated().sum()),
 "events_historical[all except collection_time]": int(events_historical.drop(columns=["collection_time"]).duplicated().sum()),
}
# overlap between files on common columns (excluding collection_time)
def overlap(a, b):
    common = [c for c in a.columns if c in b.columns and c != "collection_time"]
    ka = set(map(tuple, a[common].fillna("").values)); kb = set(map(tuple, b[common].fillna("").values))
    return {"common_cols": common, "a_distinct": len(ka), "b_distinct": len(kb), "shared": len(ka & kb)}
out["_overlap"] = {"traffic_historical vs fixed": overlap(traffic_historical, traffic_fixed),
                   "traffic_live vs fixed": overlap(traffic_live, traffic_fixed),
                   "traffic_historical vs live": overlap(traffic_historical, traffic_live),
                   "events_historical vs live": overlap(events_historical, events_live)}
REPORT = ROOT / "data" / "reports" / "cita_diagnostic.json"
REPORT.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
print(f"[OK] {REPORT}")
