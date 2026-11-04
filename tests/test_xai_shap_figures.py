"""Tests of agents/xai/shap_figures.py (static SHAP figures read from the existing JSON reports).
Small synthetic reports with known values; the last test uses the real reports when present."""
from __future__ import annotations

import hashlib
import json

import pytest

pytest.importorskip("matplotlib")

from agents.xai import shap_figures as sf
from agents.xai import shap_qtable as sx

PHI_V = [0.0, -0.4, 0.5, 0.2]
PHI_U = [0.0, 0.3, 0.8, 0.7]
DELTA = 3.0
BASE_V, BASE_U = DELTA - sum(PHI_V), DELTA - sum(PHI_U)


def _ranks(phi):
    return [1 + sum(abs(q) > abs(p) for q in phi) for p in phi]


def reports():
    dec = {"tls": "T1", "time_s": 100.0, "clock": "00:01:40"}
    demo = {"data_origin": "TEST", "decision": dict(dec), "delta": DELTA, "base_value": BASE_V,
            "contributions": [{"variable": v, "label": v, "class": "0", "shap": p}
                              for v, p in zip(sx.FEATURES, PHI_V)]}
    stab = {"data_origin": "TEST", "decision": dict(dec), "delta": DELTA,
            "background": {"states_retained": 5, "retained_states_unreliable": 2},
            "methods": {"visits": {"base_value": BASE_V, "sum_contributions": sum(PHI_V), "additivity_error": 0.0},
                        "uniform": {"base_value": BASE_U, "sum_contributions": sum(PHI_U), "additivity_error": 0.0}},
            "comparison": [{"variable": v, "label": v, "class": "0", "shap_visits": a, "shap_uniform": b,
                            "rank_visits": ra, "rank_uniform": rb, "constant_in_retained_background": i == 0}
                           for i, (v, a, b, ra, rb) in enumerate(zip(sx.FEATURES, PHI_V, PHI_U, _ranks(PHI_V), _ranks(PHI_U)))],
            "summary": {"additivity_tolerance": 1e-9}}
    return demo, stab


def write(tmp_path, demo, stab):
    d, s = tmp_path / "demo.json", tmp_path / "stab.json"
    d.write_text(json.dumps(demo), encoding="utf-8")
    s.write_text(json.dumps(stab), encoding="utf-8")
    return d, s


def test_values_are_read_from_the_json_not_typed(tmp_path):
    d, s = write(tmp_path, *reports())
    data = sf.load_inputs(d, s)
    assert data["methods"]["visits"]["phi"] == PHI_V and data["methods"]["uniform"]["phi"] == PHI_U
    assert data["methods"]["visits"]["base_value"] == BASE_V and data["delta"] == DELTA
    assert data["methods"]["visits"]["ranks"] == [4, 2, 1, 3] and data["methods"]["uniform"]["ranks"] == [4, 3, 1, 2]


@pytest.mark.parametrize("break_it", [
    lambda demo, stab: demo["contributions"][1].update(shap=-0.41),            # reports disagree
    lambda demo, stab: demo.update(delta=3.1),                                 # different delta
    lambda demo, stab: demo["decision"].update(time_s=101.0),                  # different decision
    lambda demo, stab: stab["methods"]["uniform"].update(base_value=BASE_U + 1e-6),   # additivity broken
    lambda demo, stab: stab["comparison"][2].update(rank_uniform=2),           # wrong rank in report
])
def test_inconsistent_reports_are_refused(tmp_path, break_it):
    demo, stab = reports()
    break_it(demo, stab)
    d, s = write(tmp_path, demo, stab)
    with pytest.raises(sf.FigureDataError):
        sf.load_inputs(d, s)


def test_plotted_geometry_equals_the_json_values(tmp_path):
    d, s = write(tmp_path, *reports())
    data = sf.load_inputs(d, s)
    figs = sf.build_figures(data, ("fr",))
    assert len(figs["fr"]["_checks"]) == 5
    bars = [p for p in figs["fr"]["fig1_shap_contributions"].axes[0].patches]
    assert sorted(b.get_width() for b in bars) == sorted(p for p in PHI_V if p != 0.0)


def test_constant_variable_warning_is_on_the_ranking_figure(tmp_path):
    d, s = write(tmp_path, *reports())
    figs = sf.build_figures(sf.load_inputs(d, s), ("fr", "en"))
    fr = " ".join(t.get_text() for t in figs["fr"]["fig2_shap_ranking"].texts)
    en = " ".join(t.get_text() for t in figs["en"]["fig2_shap_ranking"].texts)
    assert "file_servie est constante" in fr and "ne prouve pas l'absence d'effet" in fr
    assert "file_servie is constant" in en and "does not prove" in en


def test_all_files_written_and_manifest_matches(tmp_path):
    demo, stab = reports()
    d, s = write(tmp_path, demo, stab)
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (d, s)]
    out = tmp_path / "figs"
    assert sf.main(["--out", str(out), "--demo", str(d), "--stability", str(s)]) == 0
    names = {p.name for p in out.iterdir()}
    for fig in ("fig1_shap_contributions", "fig2_shap_ranking", "fig3_shap_additivity"):
        for lang in ("fr", "en"):
            for ext in ("png", "pdf"):
                assert f"{fig}_{lang}.{ext}" in names and (out / f"{fig}_{lang}.{ext}").stat().st_size > 1000
    m = json.loads((out / "figures_manifest.json").read_text(encoding="utf-8"))
    assert [r["shap_visits"] for r in m["plotted_values"]] == PHI_V
    assert [r["shap_uniform"] for r in m["plotted_values"]] == PHI_U
    assert m["sources"][0]["sha256"] == before[0]
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in (d, s)] == before     # inputs untouched


def test_output_folder_is_never_overwritten(tmp_path):
    d, s = write(tmp_path, *reports())
    out = tmp_path / "existing"
    out.mkdir()
    (out / "keep.txt").write_text("x", encoding="utf-8")
    assert sf.main(["--out", str(out), "--demo", str(d), "--stability", str(s)]) == 2
    assert [p.name for p in out.iterdir()] == ["keep.txt"]


def test_nothing_is_written_when_a_check_fails(tmp_path):
    demo, stab = reports()
    demo["delta"] = 9.0
    d, s = write(tmp_path, demo, stab)
    out = tmp_path / "never"
    assert sf.main(["--out", str(out), "--demo", str(d), "--stability", str(s)]) == 1
    assert not out.exists()


# ------------------------------------------------------------------------------------- real project files
REAL = sf.DEFAULT_DEMO.exists() and sf.DEFAULT_STABILITY.exists()


@pytest.mark.skipif(not REAL, reason="docs/shap_demo_v2 or docs/shap_stability_v2 not present")
def test_real_reports_figures_match_and_inputs_unchanged(tmp_path):
    files = [sf.DEFAULT_DEMO, sf.DEFAULT_STABILITY]
    before = [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files]
    out = tmp_path / "real_figs"
    assert sf.main(["--out", str(out), "--lang", "fr"]) == 0
    m = json.loads((out / "figures_manifest.json").read_text(encoding="utf-8"))
    stab = json.loads(sf.DEFAULT_STABILITY.read_text(encoding="utf-8"))
    for r, c in zip(m["plotted_values"], stab["comparison"]):
        assert r["variable"] == c["variable"]
        assert r["shap_visits"] == c["shap_visits"] and r["shap_uniform"] == c["shap_uniform"]
        assert (r["rank_visits"], r["rank_uniform"]) == (c["rank_visits"], c["rank_uniform"])
    assert m["delta"] == stab["delta"]
    assert [(hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in files] == before
