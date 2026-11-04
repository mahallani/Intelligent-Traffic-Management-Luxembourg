"""
Shared helpers for the data pipeline (Luxembourg traffic project).

* read_csv_checked : detects the separator from the header, reads everything as text
                     (no type guessing), only truly empty cells are missing, and validates
                     the columns after reading.
* safe_path        : refuses to overwrite an existing output (pipeline outputs are versioned
                     with a tag, e.g. "_v1"; re-running with the same tag stops instead of
                     silently replacing previous results).
* write_json / write_csv : JSON-safe writing through safe_path.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
REPORTS = DATA / "reports"
CANDIDATE_SEPARATORS = [",", ";", "\t", "|"]


class OutputExists(RuntimeError):
    pass


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def detect_separator(path: Path) -> str:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as fh:
        header = fh.readline()
    counts = {s: header.count(s) for s in CANDIDATE_SEPARATORS}
    sep = max(counts, key=counts.get)
    if counts[sep] == 0:
        raise ValueError(f"{path}: no known separator in header")
    return sep


def read_csv_checked(path: Path, expected_columns: list[str] | None = None,
                     min_columns: int = 2, **kw) -> pd.DataFrame:
    sep = detect_separator(path)
    df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig", keep_default_na=False,
                     na_values=[""], on_bad_lines="error", **kw)
    df.columns = df.columns.str.strip()
    if len(df.columns) < min_columns:
        raise ValueError(f"{path}: {len(df.columns)} column(s) read with sep={sep!r}")
    if expected_columns is not None and list(df.columns) != list(expected_columns):
        raise ValueError(f"{path}: unexpected columns {list(df.columns)}")
    df.attrs["separator"] = sep
    df.attrs["source"] = rel(path)
    return df


def safe_path(path: Path) -> Path:
    path = Path(path)
    if path.exists():
        raise OutputExists(f"refusing to overwrite existing file {rel(path)} (use another --tag)")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if o is pd.NA or o is pd.NaT:
        return None
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return o


def write_json(obj, path: Path) -> Path:
    p = safe_path(path)
    p.write_text(json.dumps(_clean(obj), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return p


def write_text(text: str, path: Path) -> Path:
    p = safe_path(path)
    p.write_text(text, encoding="utf-8")
    return p


def write_csv(df: pd.DataFrame, path: Path, sep: str = ";") -> Path:
    p = safe_path(path)
    compression = "gzip" if str(p).endswith(".gz") else "xz" if str(p).endswith(".xz") else None
    df.to_csv(p, sep=sep, index=False, encoding="utf-8" if compression else "utf-8-sig",
              compression=compression, date_format="%Y-%m-%dT%H:%M:%S%z")
    return p


def sha256(path: Path, limit_mb: int | None = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        read = 0
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            read += 1
            if limit_mb and read >= limit_mb:
                break
    return h.hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def value_counts(s: pd.Series, n: int = 10) -> dict:
    return {("<NA>" if pd.isna(k) else str(k)): int(v) for k, v in s.value_counts(dropna=False).head(n).items()}


def missing_table(df: pd.DataFrame) -> dict:
    return {c: {"missing": int(df[c].isna().sum()), "pct": round(100 * float(df[c].isna().mean()), 2)}
            for c in df.columns}
