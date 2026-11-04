"""Tests of agents/xai/shap_multi_decision.py (multi-decision SHAP stability study, approved protocol).
Synthetic tables and logs with known answers first; the last tests use the real project files when present."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json

import pytest

from agents.xai import shap_multi_decision as md
from agents.xai import shap_qtable as sx
from agents.xai import shap_stability as ss

TLS, G = "T", 0
GRID = list(itertools.product(range(3), repeat=4))
COEF = (1.0, 2.0, -1.0, 0.5)


def delta_fn(s):
    return 3.0 + sum(c * v for c, v in zip(COEF, s))          # additive and always > 0


def make_table(states=GRID, visits=None, fn=delta_fn):
    q, n = {}, {}
    for s in states:
        k = sx.make_key(TLS, G, s)
        q[k] = [0.0, float(fn(s))]
        n[k] = list((visits or {}).get(s, (5, 5)))
    return sx.QTable(q=q, n=n, meta={})


def write_table(path, table):
    path.write_text(json.dumps({"meta": {}, "q": table.q, "n": table.n}), encoding="utf-8")
    return path


def explanation(table, s, source="table apprise", q_passer=None):
    k = sx.make_key(TLS, G, s)
    return json.dumps({"source": source,
                       "situation": {"phase_verte": str(G), **{f: str(v) for f, v in zip(sx.FEATURES, s)}},
                       "q_garder": round(table.q[k][0], 3),
                       "q_passer": round(table.q[k][1], 3) if q_passer is None else q_passer,
                       "visites_garder_passer": table.n[k], "action": "passer"})


def write_run(run_dir, rows, with_explanation=True):
    run_dir.mkdir(parents=True)
    cols = ["time_s", "tls", "from_phase", "to_phase", "green_duration_s", "reason", "controller", "data_origin"]
    if with_explanation:
        cols.append("explanation")
    with open(run_dir / "decisions.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return run_dir


def row(t, expl="", reason="agent_decision", controller="S3_rl_qlearning"):
    return {"time_s": f"{t:.1f}", "tls": TLS, "from_phase": "0", "to_phase": "1", "green_duration_s": "10.0",
            "reason": reason, "controller": controller, "data_origin": "TEST", "explanation": expl}


@pytest.fixture
def synthetic(tmp_path):
    table = make_table()
    qt = write_table(tmp_path / "qtable.json", table)
    x1, x2 = (2, 1, 0, 0), (1, 2, 1, 1)
    run1 = write_run(tmp_path / "runs" / "r1_S3_rl_qlearning_x1", [
        row(10, explanation(table, x1)),
        row(20, explanation(table, x1)),                                             # same state again
        row(30, explanation(table, x2)),
        row(40, json.dumps({"source": "sécurité : vert maximum atteint"}), reason="max_green"),
        row(50, explanation(table, x2, source="règle de secours S2 (situation trop peu vue)")),
        row(60, explanation(table, x2, q_passer=99.0)),                              # log differs from table
    ])
    run2 = write_run(tmp_path / "runs" / "r2_S3_rl_qlearning_x5", [row(70), row(80)], with_explanation=False)
    return {"table": table, "qtable": qt, "runs": [run1, run2], "x1": x1, "x2": x2}


# --------------------------------------------------------------------------------------- inclusion / units
def test_every_row_is_included_or_excluded_with_a_reason(synthetic):
    cases, excl, runs = md.collect_cases(synthetic["runs"], synthetic["table"])
    assert len(cases) == 3 and len(excl) == 5 and sum(r["rows"] for r in runs) == 8
    assert sorted(e["code"] for e in excl) == sorted(["rule:max_green", "fallback_S2", "log_vs_table_mismatch",
                                                      "run_without_logged_state", "run_without_logged_state"])
    assert all(e["detail"] for e in excl)


def test_repeated_decisions_of_one_state_are_one_unit(synthetic):
    cases, _, _ = md.collect_cases(synthetic["runs"], synthetic["table"])
    states = md.group_by_state(cases)
    assert len(states) == 2
    assert states[sx.make_key(TLS, G, synthetic["x1"])]["n_decisions"] == 2
    r = md.study(synthetic["runs"], synthetic["qtable"])
    T = r["summary"]["total"]
    assert T["states"] == 2 and T["decisions"] == 3
    assert sum(T["unweighted"].values()) == 2 and sum(T["weighted_by_decisions"].values()) == 3


# ---------------------------------------------------------------------------------------------- backgrounds
def _mixed_table():
    visits = {s: ((1, 9) if (s[0] + s[3]) % 2 else (6, 4 + s[1])) for s in GRID}       # about half unreliable
    states = [s for s in GRID if s != (2, 2, 2, 2)]                                         # one hybrid missing
    return make_table(states, visits), visits


def test_backgrounds_A_B_C_are_built_exactly_as_in_the_protocol():
    t, visits = _mixed_table()
    x = (0, 1, 2, 0)
    bg = md.build_backgrounds(t, TLS, G, x)
    assert bg["A"] == ss.retained_background(t, TLS, G, x)
    assert [s for s, _ in bg["B"]] == [s for s, _ in bg["A"]] and all(w == 1.0 for _, w in bg["B"])
    assert bg["C"] == [(s, w) for s, w in bg["A"] if min(visits[s]) >= 3]
    assert all(w == sum(visits[s]) for s, w in bg["C"])
    assert 0 < len(bg["C"]) < len(bg["A"]) and not bg["C_equals_A"] and bg["C_computable"]


def test_additivity_and_reproduction_of_A_for_the_three_backgrounds():
    t, _ = _mixed_table()
    x = (0, 1, 2, 0)
    e = md.explain_three(t, TLS, G, x)
    default = sx.exact_shapley_delta(t, TLS, G, x)
    assert e["results"]["A"].phi == pytest.approx(default.phi, abs=1e-12)
    for m in ("A", "B", "C"):
        r = e["results"][m]
        assert abs(r.base + r.sum_phi - t.delta(sx.make_key(TLS, G, x))) <= sx.ADDITIVITY_TOL


def test_known_values_for_an_additive_table():
    t, visits = _mixed_table()
    x = (2, 0, 1, 2)
    e = md.explain_three(t, TLS, G, x)
    for m in ("A", "B", "C"):
        bg = e["backgrounds"][m]
        W = sum(w for _, w in bg)
        for i in range(4):
            mean = sum(w * s[i] for s, w in bg) / W
            assert e["results"][m].phi[i] == pytest.approx(COEF[i] * (x[i] - mean), abs=1e-12)


def test_C_equals_A_is_flagged_when_every_retained_state_is_reliable():
    bg = md.build_backgrounds(make_table(), TLS, G, (1, 1, 1, 1))
    assert bg["C_equals_A"] and bg["C"] == bg["A"]


def test_C_not_computable_below_five_reliable_states_gives_non_evaluable():
    visits = {s: ((5, 5) if s in GRID[:4] else (1, 9)) for s in GRID}
    t = make_table(visits=visits)
    bg = md.build_backgrounds(t, TLS, G, GRID[0])
    assert len(bg["C"]) == 4 and not bg["C_computable"]
    e = md.explain_three(t, TLS, G, GRID[0])
    assert "C" not in e["results"]
    cl = md.classify({m: list(r.phi) for m, r in e["results"].items()},
                     {m: list(r.constant_variables) for m, r in e["results"].items()}, False, False)
    assert cl["category"] == "non_evaluable" and "C not computable" in cl["reason"]


# ------------------------------------------------------------------------------------------------- measures
def test_pair_measures_on_hand_values():
    p1, p2 = [0.0, -0.45, 0.52, 0.20], [0.0, 0.26, 0.81, 0.79]
    m = md.pair_measures(p1, p2, [0], [0])
    assert m["informative"] == ["file_autre", "en_mouvement", "durée_vert"]
    assert m["sign_inversions"] == ["file_autre"] and m["same_main_variable"]
    assert m["shape_distance"] == pytest.approx((0.71 + 0.29 + 0.59) / (1.17 + 1.86))
    assert m["kendall_tau_b"] == pytest.approx(1 / 3)                 # 2 concordant, 1 discordant pair


def test_negligible_variables_are_not_informative_and_cannot_invert():
    m = md.pair_measures([0.01, 1.0, 0.0, 0.5], [-0.01, 1.0, 0.0, 0.5], [], [])
    assert "file_servie" not in m["informative"] and m["sign_inversions"] == []
    assert m["kendall_tau_b"] is None                                  # only 2 informative variables


def test_kendall_tau_b_with_ties():
    assert md.kendall_tau_b([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert md.kendall_tau_b([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert md.kendall_tau_b([1, 2, 2], [1, 2, 3]) == pytest.approx(2 / 6 ** 0.5)


def test_classification_rules():
    c = {"A": [], "B": [], "C": []}
    stable = md.classify({"A": [0.5, 0.2, 0.1, 0], "B": [0.6, 0.1, 0.2, 0], "C": [0.4, 0.3, 0.1, 0]}, c, True, False)
    partial = md.classify({"A": [0.5, 0.2, 0.1, 0], "B": [0.6, -0.2, 0.1, 0], "C": [0.4, 0.3, 0.1, 0]}, c, True, False)
    unstable = md.classify({"A": [0.5, 0.2, 0.1, 0], "B": [0.2, 0.5, 0.1, 0], "C": [0.4, 0.3, 0.1, 0]}, c, True, False)
    one_var = md.classify({"A": [0.5, 0, 0, 0], "B": [0.6, 0, 0, 0], "C": [0.4, 0, 0, 0]}, c, True, False)
    main_inv = md.classify({"A": [0.5, 0.2, 0, 0], "B": [0.6, 0.1, 0, 0], "C": [-0.4, 0.1, 0, 0]}, c, True, False)
    assert stable["category"] == "stable" and stable["pattern"] == "all agree"
    assert partial["category"] == "partial" and partial["inversion_on_main_variable"] == []
    assert unstable["category"] == "unstable"
    assert one_var["category"] == "non_evaluable"
    assert main_inv["category"] == "partial" and main_inv["inversion_on_main_variable"] == ["file_servie"]


def test_constant_variables_are_never_informative():
    cl = md.classify({"A": [0.0, 0.5, 0.3, 0.0], "B": [0.0, 0.6, 0.2, 0.0], "C": [0.0, 0.4, 0.3, 0.0]},
                     {"A": [0, 3], "B": [0, 3], "C": [0, 3]}, True, False)
    assert cl["informative_variables"] == ["file_autre", "en_mouvement"] and cl["category"] == "stable"


def test_reading_thresholds_fixed_in_the_protocol():
    assert md.verdict(0.80) == "plutôt robuste" and md.verdict(0.79) == "mitigé"
    assert md.verdict(0.50) == "mitigé" and md.verdict(0.49) == "sensible" and md.verdict(None) == "aucun état évaluable"


# --------------------------------------------------------------------------------------------- outputs
def test_outputs_written_once_and_inputs_unchanged(synthetic, tmp_path):
    files = [synthetic["qtable"]] + [r / "decisions.csv" for r in synthetic["runs"]]
    before = [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files]
    out = tmp_path / "study"
    args = ["--out", str(out), "--qtable", str(synthetic["qtable"]), "--runs", *map(str, synthetic["runs"])]
    assert md.main(args) == 0
    assert sorted(p.name for p in out.iterdir()) == ["README.md", "REPORT.md", "cases.csv", "exclusions.csv",
                                                     "per_state.csv", "per_state.json", "summary.json"]
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert s["decisions_included"] == 3 and s["rows_excluded"] == 5 and s["inputs_unchanged"]
    with open(out / "exclusions.csv", encoding="utf-8") as fh:
        assert len(list(csv.reader(fh, delimiter=";"))) == 1 + 5
    assert [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files] == before
    assert md.main(args) == 2                                           # never overwritten


def test_nothing_is_written_when_the_study_stops(synthetic, tmp_path):
    out = tmp_path / "never"
    bad = tmp_path / "not_a_table.json"
    bad.write_text("{}", encoding="utf-8")
    assert md.main(["--out", str(out), "--qtable", str(bad), "--runs", *map(str, synthetic["runs"])]) == 1
    assert not out.exists()


# ------------------------------------------------------------------------------------- real project files
REAL_RUN = sx.DEFAULT_RUN
REAL = sx.DEFAULT_QTABLE.exists() and (REAL_RUN / "decisions.csv").exists()


@pytest.fixture(scope="module")
def real_study():
    return md.study([REAL_RUN])


@pytest.mark.skipif(not REAL, reason="project Q-table or S3 x1 run not present")
def test_real_inclusion_matches_the_protocol_precheck(real_study):
    r = real_study
    assert r["rows_total"] == 613 and r["decisions_included"] == 259
    assert r["exclusions_by_code"] == {"fallback_S2": 280, "rule:max_green": 74}
    T, by = r["summary"]["total"], r["summary"]["by_signal"]
    assert T["states"] == 32
    assert {t: (b["decisions"], b["states"]) for t, b in by.items()} == {
        "-20484": (97, 13), "-23354": (71, 9), "-28692": (41, 4), "-29958": (50, 6)}
    assert T["C_equals_A_states"] == 2


@pytest.mark.skipif(not REAL, reason="project Q-table or S3 x1 run not present")
def test_real_known_decision_is_reproduced(real_study):
    s = next(p for p in real_study["per_state"] if p["state_key"] == "-29958|1|0|3|0|0")
    pub = sx.explain_logged_decision()
    for d in pub["contributions"]:
        assert s["methods"]["A"]["phi"][d["variable"]] == pytest.approx(d["shap"], abs=1e-12)
    cmp = ss.run()
    for c in cmp["comparison"]:
        assert s["methods"]["B"]["phi"][c["variable"]] == pytest.approx(c["shap_uniform"], abs=1e-12)
    assert s["retained_A"] == 29 and s["retained_C"] == 7


@pytest.mark.skipif(not REAL, reason="project Q-table or S3 x1 run not present")
def test_real_every_state_passes_the_checks(real_study):
    assert real_study["inputs_unchanged"]
    for s in real_study["per_state"]:
        assert s["C_computable"] and s["retained_C"] >= md.MIN_RELIABLE_BG
        for m in ("A", "B", "C"):
            mm = s["methods"][m]
            assert abs(mm["base_value"] + mm["sum_phi"] - s["delta"]) <= sx.ADDITIVITY_TOL
        assert s["category"] in ("stable", "partial", "unstable", "non_evaluable")


@pytest.mark.skipif(not REAL, reason="project Q-table or S3 x1 run not present")
def test_real_cli_writes_a_new_folder_and_leaves_inputs_untouched(tmp_path):
    files = [sx.DEFAULT_QTABLE] + sorted(md.RUNS_DIR.glob(md.S3_RUN_GLOB + "/decisions.csv"))
    before = [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files]
    out = tmp_path / "real_study"
    assert md.main(["--out", str(out)]) == 0
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert s["decisions_included"] == 259 and s["inputs_unchanged"]
    assert s["rows_total"] == s["decisions_included"] + s["rows_excluded"]
    assert [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files] == before
    assert md.main(["--out", str(out)]) == 2
