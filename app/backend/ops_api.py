"""Incident history of the application runs (2026-11-03), read only.

GET /api/incidents/runs            runs launched from the application, newest first, with their number of alerts
GET /api/incidents?run=<name>      alerts of one run (alerts.csv written by the detection agent at the end of the run)
                                   + the simulated incident and ambulance summaries of its kpis.json, when present
Nothing is computed beyond reading these files: an alert is "in progress" when the run ended before its end time.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .network import LABELS
from .sim_manager import clock

RUN_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,160}$")


def _run_dir(runs_dir: Path, name: str) -> Path:
    if not RUN_RE.match(name or ""):
        raise LookupError("nom de run invalide")
    d = (runs_dir / name).resolve()
    if d.parent != runs_dir.resolve() or not d.is_dir():
        raise LookupError("run inconnu")
    return d


def _alerts(d: Path) -> list[dict]:
    f = d / "alerts.csv"
    if not f.exists():
        return []
    out = []
    with f.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            try:
                end = float(r["end_s"]) if r.get("end_s") not in (None, "", "None") else None
                out.append({"clock": clock(float(r["raised_s"])), "start_clock": clock(float(r["start_s"])),
                            "end_clock": clock(end) if end is not None else None, "lane": r["lane"], "tls": r["tls"],
                            "carrefour": LABELS.get(r["tls"], r["tls"]), "rule": r["rule"],
                            "max_halting": int(float(r["max_halting"] or 0))})
            except (KeyError, ValueError):
                continue
    return out


def make_router(mgr):
    from fastapi import APIRouter, HTTPException

    r = APIRouter(prefix="/api/incidents")

    @r.get("/runs")
    def runs():
        root = Path(mgr.runs_dir)
        items = []
        if root.is_dir():
            for d in sorted((p for p in root.iterdir() if p.is_dir() and (p / "kpis.json").exists()), reverse=True):
                try:
                    k = json.loads((d / "kpis.json").read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                items.append({"run": d.name, "strategy": k.get("strategy"), "scale": k.get("scale"), "seed": k.get("seed"),
                              "alerts": len(_alerts(d)), "incident": bool(k.get("incident")), "ambulance": bool(k.get("emergency")),
                              "stopped_early": bool(k.get("stopped_early"))})
        return {"runs": items}

    @r.get("")
    def incidents(run: str):
        try:
            d = _run_dir(Path(mgr.runs_dir), run)
        except LookupError as e:
            raise HTTPException(404, str(e))
        k = {}
        if (d / "kpis.json").exists():
            try:
                k = json.loads((d / "kpis.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                k = {}
        return {"run": d.name, "strategy": k.get("strategy"), "alerts": _alerts(d), "incident": k.get("incident"),
                "emergency": k.get("emergency"), "data_origin": k.get("data_origin")}

    return r
