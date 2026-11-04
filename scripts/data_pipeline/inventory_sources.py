"""
Reproducible inventory of every data source and existing output of the project.

All figures are RECOMPUTED from the files (nothing copied from previous reports). Known issues
found in earlier diagnostics are listed separately under "inherited_findings" and each one
is re-checked here when possible ("rechecked": true/false).

Usage:  python scripts/data_pipeline/inventory_sources.py [--tag v1] [--check-only]
Writes: data/reports/source_inventory_<tag>.json and .md   (refuses to overwrite)
"""
from __future__ import annotations

import argparse
import glob
import gzip
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, ROOT, detect_separator, missing_table, now_utc, read_csv_checked, rel, sha256, write_json, write_text  # noqa: E402

TIME_COLUMNS = ["collection_time", "timestamp", "creation_time", "start_time", "version_time",
                "collection_time_utc", "measurement_timestamp"]
CANDIDATE_KEYS = {
    "cita_traffic_historical_fixed.csv": [["measurement_site", "timestamp", "direction"]],
    "cita_traffic_historical.csv": [["road", "timestamp", "latitude", "longitude"]],
    "cita_traffic_live.csv": [["collection_time", "road", "latitude", "longitude", "direction"]],
    "cita_events_historical.csv": [["creation_time", "start_time", "destination", "latitude", "longitude"]],
    "cita_events_live.csv": [["creation_time", "start_time", "destination", "latitude", "longitude", "version_time"]],
    "routes.txt": [["route_id"]], "trips.txt": [["trip_id"]], "stops.txt": [["stop_id"]],
    "stop_times.txt": [["trip_id", "stop_sequence"]], "calendar.txt": [["service_id"]],
    "calendar_dates.txt": [["service_id", "date"]], "agency.txt": [["agency_id"]],
    "shapes.txt": [["shape_id", "shape_pt_sequence"]],
    "transfers.txt": [["from_stop_id", "to_stop_id", "from_route_id", "to_route_id", "from_trip_id", "to_trip_id"]],
}
INHERITED = [
    {"finding": "cita_traffic_historical_fixed.csv: values of the LAST sensor of each road XML with the "
                "position of the FIRST one (faulty v1 collector)", "source": "diagnostic 2026-10-10",
     "rechecked": "by tests/test_collect_cita_fixed.py (old parser executed on raw XML)"},
    {"finding": "cita_traffic_live.csv: speed rows and flow rows separate, no sensor id, no measurement time",
     "source": "diagnostic 2026-10-10", "rechecked": "here (fully empty columns)"},
    {"finding": "data/interim/cita/*_combined.csv and *_combined_initial_report.json produced with sep=';' forced: INVALID",
     "source": "diagnostic 2026-10-10", "rechecked": "here (column count of the combined files)"},
]


def csv_profile(path: Path) -> dict:
    df = read_csv_checked(path)
    info = {"path": rel(path), "bytes": path.stat().st_size, "separator": df.attrs["separator"],
            "rows": len(df), "columns": list(df.columns), "n_columns": len(df.columns),
            "exact_duplicate_rows": int(df.duplicated().sum()),
            "fully_empty_columns": [c for c in df.columns if df[c].isna().all()],
            "missing_pct": {c: v["pct"] for c, v in missing_table(df).items() if v["missing"]}}
    for c in TIME_COLUMNS:
        if c in df and df[c].notna().any():
            s = df[c].dropna()
            info.setdefault("period", {})[c] = {"min": s.min(), "max": s.max(), "distinct": int(s.nunique())}
    keys = []
    for k in CANDIDATE_KEYS.get(path.name, []):
        if all(c in df for c in k):
            keys.append({"key": k, "distinct": int(df.drop_duplicates(k).shape[0]),
                         "duplicated_rows_on_key": int(df.duplicated(k).sum()),
                         "unique": bool(not df.duplicated(k).any())})
    info["candidate_keys"] = keys
    return info


def xml_profile(path: Path) -> dict:
    root = ET.parse(path).getroot()
    tags = [e.tag.split("}")[-1] for e in root.iter()]
    info = {"path": rel(path), "bytes": path.stat().st_size, "root": root.tag,
            "publicationTime": next((e.text for e in root.iter() if e.tag.endswith("publicationTime")), None)}
    if "siteMeasurements" in tags:
        sm = [e for e in root.iter() if e.tag.endswith("siteMeasurements")]
        ids = [next((c.get("id") for c in s if c.tag.endswith("measurementSiteReference")), None) for s in sm]
        times = {next((c.text for c in s if c.tag.endswith("measurementTimeDefault")), None) for s in sm}
        info.update(kind="DATEX II v2 MeasuredDataPublication (traffic status)", sites=len(sm),
                    unique_site_ids=len(set(ids)), measurement_times=sorted(t for t in times if t))
    elif "situation" in tags:
        sit = [e for e in root.iter() if e.tag.split("}")[-1] == "situation"]
        rec = [e for e in root.iter() if e.tag.split("}")[-1] == "situationRecord"]
        info.update(kind="DATEX II v3 SituationPublication (events)", situations=len(sit), records=len(rec),
                    unique_record_ids=len({r.get("id") for r in rec}))
    elif "measurementSiteRecord" in tags:
        info.update(kind="DATEX II v2 MeasurementSiteTablePublication (static site table, no values)",
                    site_records=tags.count("measurementSiteRecord"))
    return info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--check-only", action="store_true", help="print, write nothing")
    a = ap.parse_args()
    inv: dict = {"generated_utc": now_utc(), "root": str(ROOT), "sources": {}, "outputs": {}}

    # ---------- CITA CSV (historical folder)
    for p in sorted((DATA / "historical" / "cita").rglob("*.csv")):
        inv["sources"][rel(p)] = {"type": "CITA csv", **csv_profile(p), "sha256": sha256(p)}
    # ---------- XML (raw)
    for p in sorted((DATA / "raw").rglob("*.xml")):
        inv["sources"][rel(p)] = {"type": "XML", **xml_profile(p), "sha256": sha256(p)}
    # ---------- GTFS
    for p in sorted((DATA / "raw" / "gtfs" / "extracted").glob("*.txt")):
        inv["sources"][rel(p)] = {"type": "GTFS", **csv_profile(p)}
    z = DATA / "raw" / "gtfs" / "luxembourg_gtfs.zip"
    if z.exists():
        inv["sources"][rel(z)] = {"type": "GTFS zip", "bytes": z.stat().st_size, "sha256": sha256(z)}
    # ---------- PCH xlsx (+ export if present)
    x = DATA / "raw" / "traffic" / "trafic_2025.xlsx"
    if x.exists():
        import openpyxl
        wb = openpyxl.load_workbook(x, read_only=True, data_only=True)
        sheets = {ws.title: {"max_row": ws.max_row, "max_column": ws.max_column} for ws in wb.worksheets}
        header = next(wb["Data"].iter_rows(values_only=True))
        inv["sources"][rel(x)] = {"type": "PCH xlsx", "bytes": x.stat().st_size, "sheets": sheets,
                                  "data_rows": sheets["Data"]["max_row"] - 1, "columns": list(header),
                                  "sql_sheet": next(iter(list(wb["SQL"].iter_rows(values_only=True))[-1])),
                                  "sha256": sha256(x)}
    exports = sorted((DATA / "interim" / "pch").glob("pch_trafic_2025_export_v*.csv.*"))
    for e in exports:
        if "PARTIAL" in e.name:
            inv["outputs"][rel(e)] = {"status": "INVALID - truncated partial export (process killed), kept, not used"}
            continue
        # chunked reading (815k rows): missing counts, key duplicates, exact duplicates via row hashes
        miss, n, hashes, keys = None, 0, [], []
        dmin, dmax, postes, dirs, vehs = None, None, set(), {}, {}
        for ch in pd.read_csv(e, sep=";", dtype=str, keep_default_na=False, na_values=[""], chunksize=200_000):
            n += len(ch)
            m = ch.isna().sum()
            miss = m if miss is None else miss + m
            hashes.append(pd.util.hash_pandas_object(ch.drop(columns="source_row"), index=False))
            keys.append(ch[["POSTE_ID", "DATECOM", "DIRECTION", "VEHICULE"]])
            dmin = min(filter(None, [dmin, ch.DATECOM.min()])); dmax = max(filter(None, [dmax, ch.DATECOM.max()]))
            postes |= set(ch.POSTE_ID.dropna())
            for col, acc in (("DIRECTION", dirs), ("VEHICULE", vehs)):
                for k, v in ch[col].value_counts(dropna=False).items():
                    acc[str(k)] = acc.get(str(k), 0) + int(v)
        allkeys = pd.concat(keys, ignore_index=True)
        inv["sources"][rel(x)]["export"] = {
            "path": rel(e), "rows": n,
            "exact_duplicate_rows_excl_source_row": int(pd.concat(hashes, ignore_index=True).duplicated().sum()),
            "missing_pct": {c: round(100 * int(v) / n, 2) for c, v in miss.items() if v},
            "DATECOM_range": [dmin, dmax], "POSTE_ID_distinct": len(postes),
            "DIRECTION_values": dirs, "VEHICULE_values": vehs,
            "duplicated_rows_on_POSTE_ID_DATECOM_DIRECTION_VEHICULE": int(allkeys.duplicated().sum())}
    # ---------- empty source folders
    inv["empty_source_folders"] = [rel(d) for d in sorted((DATA / "raw").rglob("*")) + sorted((DATA / "historical").rglob("*"))
                                   if d.is_dir() and not any(d.iterdir())]
    # ---------- existing outputs and their status
    status_rules = {
        "_combined.csv": "INVALID - produced by prepare_cita.py with sep=';' forced (4/5 sources read as 1 column)",
        "_combined_initial_report.json": "INVALID - same cause as the *_combined.csv files",
        "processed/cita_traffic.csv": "LEGACY - convert_cita.py output from one XML snapshot: no sensor id, no speed; not used",
        "processed/cita_events.csv": "LEGACY - convert_events.py output from one XML snapshot, no ids; superseded",
        "cita_traffic_clean.csv": "DIAGNOSTIC ONLY - site attribution unreliable (faulty v1 collector); never for spatial models",
        "cita_traffic_fixed_unique.csv": "DIAGNOSTIC ONLY - site attribution unreliable",
    }
    for folder in ("interim", "processed", "reports"):
        for p in sorted((DATA / folder).rglob("*")):
            if p.is_file() and rel(p) not in inv["outputs"]:
                st = next((v for k, v in status_rules.items() if rel(p).endswith(k)), "current")
                entry = {"bytes": p.stat().st_size, "status": st}
                if p.suffix == ".csv" and "combined" in p.name:
                    with open(p, encoding="utf-8-sig") as fh:
                        entry["header_columns_when_split_on_;"] = len(fh.readline().split(";"))
                inv["outputs"][rel(p)] = entry
    inv["scripts"] = sorted(rel(Path(p)) for p in glob.glob(str(ROOT / "*.py")) + glob.glob(str(ROOT / "scripts" / "**" / "*.py"), recursive=True))
    inv["tests"] = sorted(rel(Path(p)) for p in glob.glob(str(ROOT / "tests" / "*.py")))
    inv["inherited_findings"] = INHERITED

    # ---------- markdown summary
    lines = [f"# Inventaire des sources ({inv['generated_utc']})", "",
             "Toutes les valeurs sont recalculées à partir des fichiers. Constats hérités : section dédiée.", "",
             "| Source | Type | Taille | Lignes | Col. | Sép. | Période | Doublons exacts | Clé candidate unique ? |",
             "|---|---|---|---|---|---|---|---|---|"]
    for k, v in inv["sources"].items():
        per = "; ".join(f"{c}: {d['min']} → {d['max']}" for c, d in v.get("period", {}).items()) or "-"
        keys = "; ".join(f"{'+'.join(c['key'])}: {'oui' if c['unique'] else 'non (' + str(c['duplicated_rows_on_key']) + ' doublons)'}"
                         for c in v.get("candidate_keys", [])) or "-"
        rows = v.get("rows", v.get("data_rows", v.get("sites", v.get("records", "-"))))
        lines.append(f"| `{k}` | {v['type']} | {v['bytes']/1e6:.2f} Mo | {rows} | {v.get('n_columns', len(v.get('columns', [])) or '-')} | "
                     f"`{v.get('separator', '-')}` | {per} | {v.get('exact_duplicate_rows', '-')} | {keys} |")
    lines += ["", "## Colonnes entièrement vides", ""]
    lines += [f"- `{k}` : {', '.join(v['fully_empty_columns'])}" for k, v in inv["sources"].items() if v.get("fully_empty_columns")]
    lines += ["", "## Sorties existantes et statut", "", "| Fichier | Statut |", "|---|---|"]
    lines += [f"| `{k}` | {v['status']} |" for k, v in inv["outputs"].items()]
    lines += ["", "## Dossiers sources vides", ""] + [f"- `{d}`" for d in inv["empty_source_folders"]]
    lines += ["", "## Constats hérités", ""] + [f"- {f['finding']} — revérifié : {f['rechecked']}" for f in INHERITED]
    md = "\n".join(lines) + "\n"
    if a.check_only:
        print(md)
        return
    print("[OK]", rel(write_json(inv, REPORTS / f"source_inventory_{a.tag}.json")))
    print("[OK]", rel(write_text(md, REPORTS / f"source_inventory_{a.tag}.md")))


if __name__ == "__main__":
    main()
