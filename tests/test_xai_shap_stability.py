"""Tests of agents/xai/shap_stability.py (SHAP sensitivity to the background weights: visits vs uniform).
Artificial tables with hand-computable results; the last tests use the real project files when present."""
from __future__ import annotations

import hashlib
import itertools
import json

import pytest

from agents.xai import shap_qtable as sx
from agents.xai import shap_stability as ss

TLS, G = "T", 0
GRID = list(itertools.product(range(3), range(3), range(3), range(3)))


def table(delta_fn, states, visits=None):
    q, n = {}, {}
    for s in states:
        k = sx.make_key(TLS, G, s)
        q[k] = [0.0, float(delta_fn(s))]
        n[k] = list((visits or {}).get(s, (5, 5)))
    return sx.QTable(q=q, n=n, meta={})


def test_retained_set_is_the_exclusion_rule_of_shap_qtable():
    states = [s for s in GRID if s != (2, 0, 0, 0)]           # hybrid missing for background (0, 0, 0, 0)
    t = table(lambda s: s[0] + s[1], states)
    bg = [((0, 0, 0, 0), 4.0), ((1, 1, 1, 1), 2.0), ((2, 2, 0, 1), 1.0)]
    x = (2, 1, 0, 0)
    kept = ss.retained_background(t, TLS, G, x, bg)
    assert [b for b, _ in kept] == [(1, 1, 1, 1), (2, 2, 0, 1)]
    assert sx.exact_shapley_delta(t, TLS, G, x, background=bg).background_retained == len(kept)


def test_uniform_uses_exactly_the_same_states_with_weight_one():
    visits = {s: (1 + s[0], 2 + s[3]) for s in GRID}            # unequal visit weights
    t = table(lambda s: 2 * s[0] - s[2], GRID, visits)
    r = ss.compare_weightings(t, TLS, G, (2, 1, 1, 0))
    kept = r["background"]["retained_states"]
    assert len(kept) == r["background"]["states_retained"] == len(GRID)
    for c in r["comparison"]:                                   # uniform counts sum to the number of retained states
        assert sum(v["uniform_count"] for v in c["retained_classes"].values()) == len(kept)


def test_known_values_for_an_additive_table():
    a = (1.5, -2.0, 0.5, 3.0)
    visits = {s: (s[0] + 1, 0) for s in GRID}                   # weight = s0 + 1
    t = table(lambda s: sum(ai * si for ai, si in zip(a, s)), GRID, visits)
    x = (2, 0, 1, 2)
    r = ss.compare_weightings(t, TLS, G, x)
    W = sum(s[0] + 1 for s in GRID)
    for i, c in enumerate(r["comparison"]):
        mean_w = sum((s[0] + 1) * s[i] for s in GRID) / W
        mean_u = sum(s[i] for s in GRID) / len(GRID)
        assert c["shap_visits"] == pytest.approx(a[i] * (x[i] - mean_w), abs=1e-12)
        assert c["shap_uniform"] == pytest.approx(a[i] * (x[i] - mean_u), abs=1e-12)
        assert c["abs_difference"] == pytest.approx(abs(c["shap_visits"] - c["shap_uniform"]), abs=1e-15)


def test_additivity_and_same_delta_in_both_methods():
    import random
    rnd = random.Random(3)
    vals = {s: rnd.uniform(-4, 4) for s in GRID}
    visits = {s: (rnd.randint(1, 9), rnd.randint(1, 9)) for s in GRID}
    t = table(lambda s: vals[s], GRID, visits)
    x = (1, 2, 0, 2)
    r = ss.compare_weightings(t, TLS, G, x)
    for m in ("visits", "uniform"):
        mm = r["methods"][m]
        assert abs(mm["base_value"] + mm["sum_contributions"] - vals[x]) <= sx.ADDITIVITY_TOL
        assert mm["additivity_error"] <= sx.ADDITIVITY_TOL
    assert r["delta"] == vals[x] and r["summary"]["additivity_ok_both"]


def test_equal_visits_give_identical_methods():
    t = table(lambda s: s[0] * s[1] - s[3], GRID)              # every state has 10 visits
    r = ss.compare_weightings(t, TLS, G, (2, 2, 1, 0))
    assert r["summary"]["max_abs_difference"] <= 1e-12 and r["summary"]["same_ranking"]


def test_signs_and_ranks_with_ties_and_zero():
    assert ss.ranks_by_abs([0.0, -0.45, 0.52, 0.20]) == [4, 2, 1, 3]
    assert ss.ranks_by_abs([0.5, -0.5, 0.1, 0.0]) == [1, 1, 3, 4]
    assert [ss.sign(v) for v in (0.0, 1e-15, -0.3, 0.2)] == ["0", "0", "-", "+"]


def test_constant_variable_is_flagged_in_both_methods():
    t = table(lambda s: 5 * s[0] + s[1], [s for s in GRID if s[0] == 0])   # variable 1 constant everywhere
    r = ss.compare_weightings(t, TLS, G, (0, 2, 1, 1))
    c0 = r["comparison"][0]
    assert c0["constant_in_retained_background"] and c0["shap_visits"] == c0["shap_uniform"] == 0.0


def test_verdict_rule():
    base = {"same_signs_all_variables": True, "same_ranking": True, "max_abs_difference": 0.1}
    assert ss.conclusion({"summary": base}).startswith("Relativement stable")
    assert ss.conclusion({"summary": dict(base, same_ranking=False)}).startswith("Sensible")
    assert ss.conclusion({"summary": dict(base, same_signs_all_variables=False)}).startswith("Sensible")


def test_output_folder_is_never_overwritten(tmp_path):
    out = tmp_path / "existing"
    out.mkdir()
    (out / "keep.txt").write_text("x", encoding="utf-8")
    assert ss.main(["--out", str(out)]) == 2
    assert (out / "keep.txt").read_text(encoding="utf-8") == "x" and len(list(out.iterdir())) == 1


# ------------------------------------------------------------------------------------- real project files
REAL = sx.DEFAULT_QTABLE.exists() and (sx.DEFAULT_RUN / "decisions.csv").exists()


@pytest.mark.skipif(not REAL, reason="project Q-table or XAI run not present")
def test_real_same_29_states_and_method_a_reproduces_the_current_explanation():
    files = [sx.DEFAULT_QTABLE, sx.DEFAULT_RUN / "decisions.csv"]
    before = [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files]
    r = ss.run()
    assert r["background"]["states_total"] == 36 and r["background"]["states_retained"] == 29
    assert r["background"]["visit_weight_retained"] == 1688.0
    default = sx.explain_logged_decision()
    for c, d in zip(r["comparison"], default["contributions"]):
        assert c["variable"] == d["variable"] and c["shap_visits"] == pytest.approx(d["shap"], abs=1e-12)
    assert r["methods"]["visits"]["base_value"] == pytest.approx(default["base_value"], abs=1e-12)
    assert round(r["delta"], 6) == 3.170026
    assert r["summary"]["additivity_ok_both"]
    assert [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files] == before


@pytest.mark.skipif(not REAL, reason="project Q-table or XAI run not present")
def test_real_report_is_written_in_a_new_folder_only(tmp_path):
    out = tmp_path / "shap_stability_test"
    assert ss.main(["--out", str(out)]) == 0
    data = json.loads((out / "shap_stability.json").read_text(encoding="utf-8"))
    assert len(data["comparison"]) == 4 and (out / "shap_stability.md").exists()
    assert ss.main(["--out", str(out)]) == 2
