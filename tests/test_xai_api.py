"""Tests of the XAI routes of the application backend (app/backend/xai_api.py) - no SUMO, no browser.

The SimulationManager uses a temporary runs folder. 'Running' is reproduced by putting the manager in its running state
and feeding its decision log with real rows (the same tuples as TLSActuator.log); nothing starts SUMO."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import threading

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from agents.xai import shap_qtable as sx  # noqa: E402
from app.backend.server import create_app  # noqa: E402
from app.backend.sim_manager import APP_RUNS, SimulationManager  # noqa: E402

S3_RUN = "20261022_141518_S3_rl_qlearning_x1_seed1_ambulance_prio"
REAL_S3 = APP_RUNS / S3_RUN / "decisions.csv"
HEADER = ["time_s", "tls", "from_phase", "to_phase", "green_duration_s", "reason", "controller", "data_origin", "explanation"]
real = pytest.mark.skipif(not (REAL_S3.exists() and sx.DEFAULT_QTABLE.exists()), reason="recorded S3 run or Q-table not present")


@pytest.fixture
def env(tmp_path):
    mgr = SimulationManager(runs_dir=tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    with TestClient(create_app(mgr)) as c:
        yield c, mgr, tmp_path / "runs"


def add_run(runs, name, rows=None, strategy=None, src=None, header=HEADER):
    d = runs / name
    d.mkdir()
    if src is not None:
        shutil.copy(src, d / "decisions.csv")
    else:
        with open(d / "decisions.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(header)
            for r in rows or []:
                w.writerow(r)
    (d / "kpis.json").write_text(json.dumps({"strategy": strategy}), encoding="utf-8")
    return d


def log_rows(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8", newline=""), delimiter=";"))
    return [(float(r["time_s"]), r["tls"], int(r["from_phase"]), int(r["to_phase"]), float(r["green_duration_s"]), r["reason"],
             json.loads(r["explanation"]) if r["explanation"] else None) for r in rows]


def target_index(decisions, tls="-29958", time_s=26941.0):
    return next(d["index"] for d in decisions if d["tls"] == tls and d["time_s"] == time_s)


# ------------------------------------------------------------------------------------------------ states
def test_no_simulation_gives_an_explicit_waiting_state(env):
    c, _, _ = env
    d = c.get("/api/xai/decisions").json()
    assert d["status"] == "idle" and d["count"] == 0 and d["decisions"] == [] and "Aucune simulation" in d["note"]
    assert c.get("/api/xai/shap", params={"index": 0}).status_code == 404


def test_s1_run_has_no_decision_and_says_why(env):
    c, _, runs = env
    add_run(runs, "20261029_193005_S1_actuated_x1_seed1", strategy="S1_actuated")
    d = c.get("/api/xai/decisions", params={"run": "20261029_193005_S1_actuated_x1_seed1"}).json()
    assert d["strategy"] == "S1_actuated" and d["count"] == 0 and "actuated" in d["note"]


def test_runs_list_and_path_validation(env):
    c, _, runs = env
    add_run(runs, "a_S1_actuated", strategy="S1_actuated")
    (runs / "no_csv").mkdir()
    assert [r["run"] for r in c.get("/api/xai/runs").json()["runs"]] == ["a_S1_actuated"]
    for bad, code in (("../x", 400), ("a/b", 400), ("..", 404), ("unknown", 404), ("no_csv", 404)):
        assert c.get("/api/xai/decisions", params={"run": bad}).status_code == code, bad


def test_other_strategy_decision_is_listed_but_never_gets_shap(env):
    c, _, runs = env
    ex = json.dumps({"source": "règle S2", "arrêtés_vert": 0, "en_mouvement_vert": 0, "attente_autre_phase": 3, "seuils": [1, 2],
                     "action": "passer"}, ensure_ascii=False)
    add_run(runs, "r_S2", [[25300.0, "-28692", 0, 1, 12.0, "agent_decision", "S2_demand_gap", "SIM", ex]], "S2_demand_gap")
    d = c.get("/api/xai/decisions", params={"run": "r_S2"}).json()
    assert d["count"] == 1 and d["eligible"] == 0 and not d["decisions"][0]["shap"]["eligible"]
    assert "S2_demand_gap" in d["decisions"][0]["shap"]["reason"]
    r = c.get("/api/xai/shap", params={"run": "r_S2", "index": 0})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_eligible"


def test_old_run_without_logged_explanation_is_not_eligible(env):
    c, _, runs = env
    add_run(runs, "old_S3", [[25216.0, "-23354", 2, 3, 15.0, "agent_decision", "S3_rl_qlearning", "SIM"]], "S3_rl_qlearning",
            header=HEADER[:-1])
    d = c.get("/api/xai/decisions", params={"run": "old_S3"}).json()
    assert not d["decisions"][0]["shap"]["eligible"] and "pas enregistré" in d["decisions"][0]["shap"]["reason"]


# -------------------------------------------------------------------------------------------- real S3 run
@real
def test_recorded_s3_run_and_exact_shap_of_a_learned_decision(env):
    c, _, runs = env
    before = hashlib.sha256(REAL_S3.read_bytes()).hexdigest()
    add_run(runs, S3_RUN, src=REAL_S3, strategy="S3_rl_qlearning")
    d = c.get("/api/xai/decisions", params={"run": S3_RUN}).json()
    assert d["count"] == 613 and d["eligible"] == 259 and d["source"] == "decisions.csv"
    i = target_index(d["decisions"])
    r = c.get("/api/xai/shap", params={"run": S3_RUN, "index": i})
    assert r.status_code == 200
    ref = sx.explain_logged_decision()
    got = r.json()
    assert [x["shap"] for x in got["contributions"]] == pytest.approx([x["shap"] for x in ref["contributions"]], abs=1e-12)
    assert got["base_value"] == pytest.approx(ref["base_value"], abs=1e-12) and got["additivity"]["ok"]
    assert got["decision"]["run"] == S3_RUN and got["index"] == i
    assert hashlib.sha256(REAL_S3.read_bytes()).hexdigest() == before


@real
def test_fallback_and_safety_decisions_get_a_clear_refusal(env):
    c, _, runs = env
    add_run(runs, S3_RUN, src=REAL_S3, strategy="S3_rl_qlearning")
    d = c.get("/api/xai/decisions", params={"run": S3_RUN}).json()
    fallback = next(x for x in d["decisions"] if str((x["explanation"] or {}).get("source", "")).startswith("règle de secours"))
    safety = next(x for x in d["decisions"] if x["reason"] == "max_green")
    for x, word in ((fallback, "règle de secours"), (safety, "vert maximum")):
        r = c.get("/api/xai/shap", params={"run": S3_RUN, "index": x["index"]})
        assert r.status_code == 422 and word in r.json()["detail"]["message"]


@real
def test_tampered_log_is_refused_by_the_engine_checks(env):
    c, _, runs = env
    rows = list(csv.reader(open(REAL_S3, encoding="utf-8", newline=""), delimiter=";"))
    i = next(k for k, r in enumerate(rows[1:]) if r[1] == "-29958" and float(r[0]) == 26941.0)
    ex = json.loads(rows[i + 1][8])
    ex["q_passer"] = ex["q_passer"] + 1.0                       # no longer what the frozen table says
    rows[i + 1][8] = json.dumps(ex, ensure_ascii=False)
    add_run(runs, "tampered", rows[1:], "S3_rl_qlearning")
    r = c.get("/api/xai/shap", params={"run": "tampered", "index": i})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "verification_failed" and "contributions" not in r.json()


@real
def test_running_then_finished_current_run(env):
    """Current run: decisions served from memory while the run is active, from decisions.csv after it ends;
    same indices and identical SHAP values in both phases."""
    c, mgr, runs = env
    log = log_rows(REAL_S3)
    run_dir = runs / "20261029_200000_S3_rl_qlearning_x1_seed1"
    run_dir.mkdir()
    stop = threading.Event()
    worker = threading.Thread(target=stop.wait, daemon=True)
    worker.start()
    with mgr._lock:
        mgr._thread, mgr._run_dir, mgr._decision_log = worker, run_dir, log[:300]
        mgr._state = {"status": "running", "strategy": "S3_rl_qlearning", "run_id": run_dir.name}
    d = c.get("/api/xai/decisions").json()
    assert d["status"] == "running" and d["count"] == 300 and d["source"].startswith("mémoire")
    i = target_index(d["decisions"])
    live = c.get("/api/xai/shap", params={"index": i}).json()
    mgr._decision_log.extend(log[300:])                        # the run goes on
    assert c.get("/api/xai/decisions").json()["count"] == 613
    shutil.copy(REAL_S3, run_dir / "decisions.csv")            # what run_episode writes at the end
    with mgr._lock:
        mgr._state["status"] = "finished"
    stop.set()
    worker.join()
    d2 = c.get("/api/xai/decisions").json()
    assert d2["status"] == "finished" and d2["source"] == "decisions.csv" and d2["count"] == 613
    assert target_index(d2["decisions"]) == i
    after = c.get("/api/xai/shap", params={"index": i}).json()
    assert [x["shap"] for x in live["contributions"]] == pytest.approx([x["shap"] for x in after["contributions"]], abs=1e-12)
    assert mgr.state()["status"] == "finished"
