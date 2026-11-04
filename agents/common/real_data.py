"""Guard between the agents and the REAL datasets (CITA, PCH, GTFS) prepared in data/processed.

The agents run on SIMULATED data. Before an agent is trained or evaluated on real data, it must ask
`require_trainable(objective)`: the answer comes from the measured readiness report
data/reports/readiness_by_objective_v1.json (objective A = incidents, B = forecasting, C = SUMO/RL,
D = impact KPIs). Today A and B are NOT TRAINABLE, so the call raises instead of silently training
on 2 observations per sensor."""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
READINESS = PROJECT_ROOT / "data" / "reports" / "readiness_by_objective_v1.json"
AGENT_OBJECTIVE = {"detection": "A", "prediction": "B", "decision": "C", "kpi": "D"}


class NotEnoughRealData(RuntimeError):
    pass


def readiness(objective: str, path: Path = READINESS) -> dict:
    if not path.exists():
        raise NotEnoughRealData(f"readiness report missing: {path} (run scripts/data_pipeline/build_task_datasets_v1.py)")
    return json.loads(path.read_text(encoding="utf-8"))["readiness"][objective]


def require_trainable(objective: str, path: Path = READINESS) -> dict:
    r = readiness(objective, path)
    if not r["verdict"].startswith("CANDIDATE"):
        raise NotEnoughRealData(f"objective {objective}: {r['verdict']} - measured {r['measured']} vs criteria {r['criteria']}")
    return r
