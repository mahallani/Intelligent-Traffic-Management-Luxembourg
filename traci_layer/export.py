"""
Export of observations, tables and KPIs: JSON / JSON Lines / CSV / pandas DataFrame.

Recommended exchange formats between agents
-------------------------------------------
* ``observations.jsonl`` - one observation (dict) per line, appended in real time.
  Streamable: the Cascade / Prediction agents can tail it.
* ``<table>.csv``         - long tables (edges, lanes, traffic_lights, buses, vehicles,
  trips, stop_events) with a ``time`` column -> time series / ML features.
* ``kpis.json``           - one :class:`ScenarioKPIs` per scenario run (Decision Agent).
* :func:`observations_to_dataframe` - flat DataFrame (one row per observation).
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


def _clean(obj: Any) -> Any:
    """Make an object JSON-serialisable (tuples, sets, dataclasses, NaN...)."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return _clean(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def to_json(obj: Any, indent: Optional[int] = 2) -> str:
    return json.dumps(_clean(obj), indent=indent, ensure_ascii=False)


def write_json(obj: Any, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(obj), encoding="utf-8")
    return path


def append_jsonl(obj: Any, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(to_json(obj, indent=None) + "\n")


def read_jsonl(path: Path | str) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_csv(rows: Iterable[dict], path: Path | str) -> Optional[Path]:
    """Write a list of flat dicts to CSV (UTF-8, ``;``-free, Excel friendly)."""
    rows = list(rows)
    if not rows:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(_clean(v)) if isinstance(v, (list, dict, tuple)) else v) for k, v in r.items()})
    return path


def flatten(d: dict, prefix: str = "", sep: str = ".") -> dict:
    """Flatten nested dicts; lists are skipped (they belong to tables)."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}{sep}{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key, sep))
        elif isinstance(v, (list, tuple, set)):
            continue
        else:
            out[key] = v
    return out


def observations_to_dataframe(observations: Iterable[dict]):
    """One row per observation, nested keys joined with '.' (requires pandas)."""
    import pandas as pd

    return pd.DataFrame([flatten(o) for o in observations if o])


def tables_to_dataframes(tables: dict[str, list]) -> dict:
    import pandas as pd

    return {name: pd.DataFrame(rows) for name, rows in tables.items()}


class RunExporter:
    """Writes everything produced by one collector run into ``out_dir/<run_name>/``."""

    def __init__(self, out_dir: Path | str, run_name: str):
        self.dir = Path(out_dir) / run_name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jsonl = self.dir / "observations.jsonl"
        if self.jsonl.exists():
            self.jsonl.unlink()

    def write_observation(self, obs: dict) -> None:
        append_jsonl(obs, self.jsonl)

    def finalize(self, collector) -> dict[str, Path]:
        """Write summary CSV, tables, trips, bus stop events and KPIs."""
        written: dict[str, Path] = {"observations_jsonl": self.jsonl}
        summary_rows = [flatten(o) for o in collector.history]
        p = write_csv(summary_rows, self.dir / "observations_summary.csv")
        if p:
            written["observations_summary_csv"] = p
        tables = collector.tables or collector.latest_tables
        for name, rows in tables.items():
            p = write_csv(rows, self.dir / f"{name}.csv")
            if p:
                written[name] = p
        p = write_csv(collector.trips_table(), self.dir / "trips.csv")
        if p:
            written["trips"] = p
        if collector.buses is not None:
            p = write_csv(collector.buses.stop_events_table(), self.dir / "bus_stop_events.csv")
            if p:
                written["bus_stop_events"] = p
        written["kpis"] = write_json(collector.kpis(), self.dir / "kpis.json")
        if collector.history:
            written["last_observation"] = write_json(collector.history[-1], self.dir / "last_observation.json")
        return written
