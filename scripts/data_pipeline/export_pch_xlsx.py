"""
Stream-export data/raw/traffic/trafic_2025.xlsx (sheet "Data") to a gzipped CSV, row by
row, without changing any value (only the cell text representation). The xlsx is never
modified. A column `source_row` keeps the Excel row number (header = row 1).

Usage:  python scripts/data_pipeline/export_pch_xlsx.py [--tag v1]
Output: data/interim/pch/pch_trafic_2025_export_<tag>.csv.xz  (separator ";", xz-compressed, read with pandas)
"""
import argparse, csv, lzma, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, rel, safe_path  # noqa: E402
import openpyxl  # noqa: E402

SRC = DATA / "raw" / "traffic" / "trafic_2025.xlsx"


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v1")
    a = ap.parse_args()
    out = safe_path(DATA / "interim" / "pch" / f"pch_trafic_2025_export_{a.tag}.csv.xz")
    t0 = time.time()
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb["Data"]
    n = 0
    with lzma.open(out, "wt", encoding="utf-8", newline="", preset=6) as fh:
        w = csv.writer(fh, delimiter=";")
        for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if i == 1:
                header = list(row)
                w.writerow(["source_row"] + header)
                continue
            if all(v is None for v in row):
                continue
            w.writerow([i] + [fmt(v) for v in row])
            n += 1
            if n % 100000 == 0:
                print(f"{n} rows, {time.time()-t0:.0f}s", flush=True)
    print(f"[OK] {rel(out)}: {n} data rows, {len(header)} columns, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
