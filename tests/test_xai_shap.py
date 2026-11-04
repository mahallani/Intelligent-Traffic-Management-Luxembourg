"""Unit tests of agents/xai/shap_qtable.py (exact Shapley values of delta = Q(passer) - Q(garder)).
Artificial tables whose exact contributions are known by hand; no SUMO needed.
The last tests use the real project files when they are present (skipped otherwise)."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
from pathlib import Path

import pytest

from agents.xai import shap_qtable as sx

TLS, G = "T", 0


def table_from(delta_fn, states, visits=(5, 5), extra=None):
    """Q-table with Q(garder) = 0 and Q(passer) = delta_fn(state) for every state in `states`."""
    q, n = {}, {}
    for s in states:
        k = sx.make_key(TLS, G, s)
        q[k] = [0.0, float(delta_fn(s))]
        n[k] = list(visits)
    for k, (qq, nn) in (extra or {}).items():
        q[k], n[k] = qq, nn
    return sx.QTable(q=q, n=n, meta={})


GRID = list(itertools.product(range(3), range(3), range(3), range(3)))


def test_additive_model_gives_known_exact_contributions():
    a = (1.5, -2.0, 0.25, 3.0)
    f = lambda s: sum(ai * si for ai, si in zip(a, s))          # noqa: E731
    t = table_from(f, GRID)
    bg = [((0, 0, 0, 0), 1.0), ((2, 1, 0, 2), 3.0)]            # weighted background
    x = (2, 2, 1, 0)
    r = sx.exact_shapley_delta(t, TLS, G, x, background=bg)
    mean_b = [(0 * 1 + b * 3) / 4 for b in (2, 1, 0, 2)]
    for i in range(4):                                          # phi_i = a_i (x_i - E_w[b_i]) exactly
        assert r.phi[i] == pytest.approx(a[i] * (x[i] - mean_b[i]), abs=1e-12)
    assert r.base + sum(r.phi) == pytest.approx(f(x), abs=1e-12)
    assert r.background_retained == 2 and r.background_excluded == 0


def test_variable_without_effect_gets_zero():
    t = table_from(lambda s: 2 * s[0] + s[1] * s[2], GRID)     # 4th variable has no effect
    r = sx.exact_shapley_delta(t, TLS, G, (2, 1, 2, 2), background=[((0, 0, 0, 0), 1.0), ((1, 2, 1, 1), 2.0)])
    assert r.phi[3] == pytest.approx(0.0, abs=1e-12)


def test_pure_interaction_is_split_equally():
    t = table_from(lambda s: s[0] * s[1], GRID)
    r = sx.exact_shapley_delta(t, TLS, G, (2, 2, 0, 0), background=[((0, 0, 0, 0), 1.0)])
    assert r.phi[0] == pytest.approx(2.0, abs=1e-12) and r.phi[1] == pytest.approx(2.0, abs=1e-12)
    assert r.phi[2] == r.phi[3] == 0.0 and r.base == 0.0


def test_constant_background_variable_is_flagged():
    t = table_from(lambda s: 5 * s[0] + s[1], GRID)              # variable 1 has a real effect...
    r = sx.exact_shapley_delta(t, TLS, G, (0, 2, 0, 0), background=[((0, 0, 1, 0), 1.0), ((0, 1, 2, 0), 1.0)])
    assert r.phi[0] == 0.0 and 0 in r.constant_variables         # ...but x and the background share its class: 0 by construction


def test_symmetric_variables_get_equal_contributions():
    t = table_from(lambda s: max(s[0], s[1]) + s[2], GRID)
    r = sx.exact_shapley_delta(t, TLS, G, (2, 2, 1, 0), background=[((0, 0, 0, 0), 1.0)])
    assert r.phi[0] == pytest.approx(r.phi[1], abs=1e-12)


def test_matches_an_independent_permutation_computation():
    """Non-additive table with fixed pseudo-random values: compare with the definition over the 4! = 24 orders."""
    import random
    rnd = random.Random(7)
    vals = {s: rnd.uniform(-5, 5) for s in GRID}
    t = table_from(lambda s: vals[s], GRID)
    bg = [((0, 1, 2, 0), 2.0), ((1, 0, 0, 2), 5.0), ((2, 2, 1, 1), 1.0)]
    x = (2, 1, 0, 1)
    r = sx.exact_shapley_delta(t, TLS, G, x, background=bg)
    wsum = sum(w for _, w in bg)
    for i in range(4):
        tot = 0.0
        for b, w in bg:
            acc = 0.0
            for order in itertools.permutations(range(4)):
                cur = list(b)
                before = vals[tuple(cur)]
                for j in order:
                    cur[j] = x[j]
                    if j == i:
                        acc += vals[tuple(cur)] - before
                        break
                    before = vals[tuple(cur)]
            tot += w * acc / 24
        assert r.phi[i] == pytest.approx(tot / wsum, abs=1e-12)


def test_background_weights_are_the_visits():
    t = table_from(lambda s: s[0], GRID)
    t.n[sx.make_key(TLS, G, (0, 0, 0, 0))] = [1, 2]             # weight 3
    t.n[sx.make_key(TLS, G, (2, 0, 0, 0))] = [0, 1]             # weight 1
    for k in list(t.q):
        if k not in (sx.make_key(TLS, G, (0, 0, 0, 0)), sx.make_key(TLS, G, (2, 0, 0, 0))):
            t.n[k] = [0, 0]                                     # weight 0: not in the background
    bg = sx.background_for(t, TLS, G)
    assert sorted(bg) == [((0, 0, 0, 0), 3.0), ((2, 0, 0, 0), 1.0)]
    r = sx.exact_shapley_delta(t, TLS, G, (2, 0, 0, 0))
    assert r.base == pytest.approx(0.5) and r.phi[0] == pytest.approx(1.5)


def test_background_keeps_signal_and_phase_fixed():
    t = table_from(lambda s: 1.0, [(0, 0, 0, 0), (1, 0, 0, 0)],
                   extra={sx.make_key(TLS, 1, (0, 0, 0, 0)): ([0.0, 9.0], [5, 5]),
                          sx.make_key("OTHER", G, (0, 0, 0, 0)): ([0.0, 9.0], [5, 5])})
    feats = [b for b, _ in sx.background_for(t, TLS, G)]
    assert sorted(feats) == [(0, 0, 0, 0), (1, 0, 0, 0)]


def test_missing_hybrid_state_excludes_the_background_state_and_keeps_additivity():
    states = [s for s in GRID if s != (2, 0, 0, 0)]             # hybrid (x1 from x, rest from b) missing
    f = lambda s: s[0] + 2 * s[1]                               # noqa: E731
    t = table_from(f, states)
    bg = [((0, 0, 0, 0), 1.0), ((1, 1, 1, 1), 1.0)]
    r = sx.exact_shapley_delta(t, TLS, G, (2, 1, 0, 0), background=bg)
    assert r.background_excluded == 1 and r.background_retained == 1
    assert r.excluded_examples[0]["background"] == [0, 0, 0, 0]
    assert r.base == pytest.approx(f((1, 1, 1, 1)))             # only the retained state, never an invented value
    assert r.base + sum(r.phi) == pytest.approx(f((2, 1, 0, 0)), abs=1e-12)


def test_all_background_excluded_raises():
    t = table_from(lambda s: 1.0, [(2, 2, 2, 2), (0, 0, 0, 0)])
    with pytest.raises(sx.ExplanationError):
        sx.exact_shapley_delta(t, TLS, G, (2, 2, 2, 2), background=[((0, 0, 0, 0), 1.0)])


def test_unseen_explained_state_raises():
    t = table_from(lambda s: 1.0, [(0, 0, 0, 0)])
    with pytest.raises(sx.ExplanationError, match="unseen"):
        sx.exact_shapley_delta(t, TLS, G, (1, 1, 1, 1), background=[((0, 0, 0, 0), 1.0)])


def test_unreliable_values_are_counted_not_replaced():
    t = table_from(lambda s: s[0], GRID)
    weak = sx.make_key(TLS, G, (0, 0, 0, 0))
    t.n[weak] = [2, 7]                                          # fewer than 3 visits for 'garder'
    r = sx.exact_shapley_delta(t, TLS, G, (2, 0, 0, 0), background=[((0, 0, 0, 0), 1.0)])
    assert r.background_unreliable == 1
    assert r.evaluations == 16 and r.evaluations_unreliable == 8   # coalitions where variable 1 comes from b
    assert r.phi[0] == pytest.approx(2.0)                       # the real (unreliable) value is used, not replaced


# ---------------------------------------------------------------------------------------- decision checks
def _write_decisions(path: Path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["time_s", "tls", "from_phase", "to_phase", "green_duration_s", "reason", "controller", "data_origin", "explanation"])
        for r in rows:
            w.writerow(r)


LEARNED = {"source": "table apprise", "situation": {"phase_verte": "0", "file_servie": "0", "file_autre": "3",
           "en_mouvement": "0", "durée_vert": "0"}, "q_garder": -4.651, "q_passer": -1.481,
           "visites_garder_passer": [10, 79], "action": "passer"}


def test_fallback_and_safety_decisions_are_refused(tmp_path):
    fb = dict(LEARNED, source="règle de secours S2 (situation trop peu vue)")
    sf = {"source": "sécurité : vert maximum atteint", "vert_s": 60.0, "limite_s": 60.0}
    p = tmp_path / "decisions.csv"
    _write_decisions(p, [[10.0, "T", 0, 1, 5, "agent_decision", "S3_rl_qlearning", "SIM", json.dumps(fb, ensure_ascii=False)],
                         [20.0, "T", 2, 3, 60, "max_green", "S3_rl_qlearning", "SIM", json.dumps(sf, ensure_ascii=False)],
                         [30.0, "T", 0, 1, 5, "agent_decision", "S2_demand_gap", "SIM", json.dumps(LEARNED, ensure_ascii=False)]])
    for t in (10.0, 20.0, 30.0):
        with pytest.raises(sx.NotExplainable):
            sx.check_learned_decision(sx.read_decision(p, "T", t))


def test_logged_values_must_match_the_table():
    key = sx.make_key(TLS, 0, (0, 3, 0, 0))
    t = sx.QTable(q={key: [-4.650686, -1.480660]}, n={key: [10, 79]}, meta={})
    out = sx.verify_logged_values(t, key, LEARNED)
    assert out["delta"] == pytest.approx(3.170026, abs=1e-9)
    bad = dict(LEARNED, q_passer=-1.6)
    with pytest.raises(sx.ExplanationError, match="differ"):
        sx.verify_logged_values(t, key, bad)
    with pytest.raises(sx.ExplanationError, match="visit"):
        sx.verify_logged_values(t, key, dict(LEARNED, visites_garder_passer=[9, 79]))


def test_load_qtable_is_read_only(tmp_path):
    f = tmp_path / "q.json"
    f.write_text(json.dumps({"meta": {}, "q": {"T|0|0|0|0|0": [0.0, 1.0]}, "n": {"T|0|0|0|0|0": [3, 3]}}), encoding="utf-8")
    h, m = hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns
    t = sx.load_qtable(f)
    sx.exact_shapley_delta(t, "T", 0, (0, 0, 0, 0))
    assert hashlib.sha256(f.read_bytes()).hexdigest() == h and f.stat().st_mtime_ns == m


# ------------------------------------------------------------------------------------- real project files
REAL = sx.DEFAULT_QTABLE.exists() and (sx.DEFAULT_RUN / "decisions.csv").exists()


@pytest.mark.skipif(not REAL, reason="project Q-table or XAI run not present")
def test_real_candidate_decision_is_learned_and_values_match():
    row = sx.read_decision(sx.DEFAULT_RUN / "decisions.csv", sx.DEFAULT_TLS, sx.DEFAULT_TIME_S)
    ex = sx.check_learned_decision(row)
    t = sx.load_qtable()
    out = sx.verify_logged_values(t, sx.state_key_from_explanation(sx.DEFAULT_TLS, ex), ex)
    assert round(out["q_garder"], 3) == -4.651 and round(out["q_passer"], 3) == -1.481
    assert round(out["delta"], 3) == 3.170


@pytest.mark.skipif(not REAL, reason="project Q-table or XAI run not present")
def test_real_fallback_decision_of_slide_14_is_refused():
    row = sx.read_decision(sx.DEFAULT_RUN / "decisions.csv", sx.DEFAULT_TLS, 26931.0)   # 07:28:51, fallback S2
    with pytest.raises(sx.NotExplainable):
        sx.check_learned_decision(row)


@pytest.mark.skipif(not REAL, reason="project Q-table or XAI run not present")
def test_real_explanation_is_additive_and_leaves_files_untouched():
    files = [sx.DEFAULT_QTABLE, sx.DEFAULT_RUN / "decisions.csv"]
    before = [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files]
    res = sx.explain_logged_decision()
    assert res["additivity"]["ok"] and res["additivity"]["abs_error"] <= sx.ADDITIVITY_TOL
    assert len(res["contributions"]) == 4
    assert [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files] == before
