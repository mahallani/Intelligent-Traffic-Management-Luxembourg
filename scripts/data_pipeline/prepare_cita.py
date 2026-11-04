from pathlib import Path
import pandas as pd
import json

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
INTERIM = DATA / "interim" / "cita"
REPORTS = DATA / "reports"

INTERIM.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

FILES = {
    "traffic_historical": DATA / "historical/cita/traffic/cita_traffic_historical.csv",
    "traffic_fixed": DATA / "historical/cita/traffic/cita_traffic_historical_fixed.csv",
    "traffic_live": DATA / "historical/cita/traffic/cita_traffic_live.csv",
    "events_historical": DATA / "historical/cita/events/cita_events_historical.csv",
    "events_live": DATA / "historical/cita/events/cita_events_live.csv",
}

CANDIDATE_SEPARATORS = [",", ";", "\t", "|"]


def detect_separator(path):
    """Detect the separator from the header line.

    The CITA files do not share one format: cita_traffic_historical_fixed.csv uses ";"
    while the four other files use ",". Forcing sep=";" read those four files as ONE
    column (whose name contained all the commas), which made the initial reports wrong.
    """
    with open(path, encoding="utf-8-sig", newline="") as fh:
        header = fh.readline()
    counts = {sep: header.count(sep) for sep in CANDIDATE_SEPARATORS}
    sep = max(counts, key=counts.get)
    if counts[sep] == 0:
        raise ValueError(f"No known separator found in the header of {path}")
    return sep


def load_csv(path):
    if not path.exists():
        print(f"[ABSENT] {path}")
        return None
    sep = detect_separator(path)
    # keep_default_na=False + na_values=[""]: only truly empty cells are missing
    # (strings such as "NA" or "null" are kept as they are, nothing is reinterpreted)
    df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig",
                     keep_default_na=False, na_values=[""], on_bad_lines="error")
    df.columns = df.columns.str.strip()
    if len(df.columns) < 2:
        raise ValueError(f"{path}: only {len(df.columns)} column read with sep={sep!r} - wrong separator?")
    print(f"[LU] {path.name}: sep={sep!r}, {len(df)} lignes, {len(df.columns)} colonnes")
    df.attrs["separator"] = sep
    return df

def prepare_group(names, output_name, source_column):
    frames = []
    report = {}

    for name in names:
        df = load_csv(FILES[name])
        if df is None:
            continue

        df[source_column] = name
        report[name] = {
            "separator": df.attrs.get("separator"),
            "rows": int(len(df)),
            "columns": list(df.columns),
            "exact_duplicate_rows": int(df.duplicated().sum()),
            "missing_by_column": {
                col: int((df[col].isna() | df[col].astype(str).str.strip().eq("")).sum())
                for col in df.columns if col != source_column
            },
        }
        frames.append(df)

    if not frames:
        print(f"[ERREUR] Aucune source disponible pour {output_name}")
        return

    combined = pd.concat(frames, ignore_index=True, sort=False)

    # Les colonnes absentes d'une source restent vides : aucune valeur n'est inventée.
    output = INTERIM / output_name
    combined.to_csv(output, sep=";", index=False, encoding="utf-8-sig")

    report_path = REPORTS / output_name.replace(".csv", "_initial_report.json")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n[OK] {output}")
    print(f"Total de lignes réunies : {len(combined)}")
    print(f"Colonnes : {list(combined.columns)}")
    print(f"Rapport : {report_path}")

def check_only():
    """Load every source with the detected separator, without writing anything."""
    for name, path in FILES.items():
        df = load_csv(path)
        if df is not None:
            print(f"    colonnes: {list(df.columns)}")


if __name__ == "__main__" and "--check-only" in __import__("sys").argv:
    check_only()
    raise SystemExit(0)

prepare_group(
    ["traffic_historical", "traffic_fixed", "traffic_live"],
    "cita_traffic_combined.csv",
    "source_file"
)

prepare_group(
    ["events_historical", "events_live"],
    "cita_events_combined.csv",
    "source_file"
)
