"""Static figures of the XAI (SHAP) results of the S3 Q-learning table, for the report and the defence.

The numbers are NEVER typed by hand: everything is read from the two existing JSON reports
    docs/shap_demo_v2/shap_result.json            (shap_qtable.py, visit-weighted background)
    docs/shap_stability_v2/shap_stability.json    (shap_stability.py, visits vs uniform weights)
and the two reports are cross-checked before anything is drawn (same decision, same delta, same
visit-weighted contributions and base value, additivity of both methods, ranks recomputed).

Three figures, each in PNG (200 dpi) and PDF, in French and/or English:
    fig1_shap_contributions_<lang>   signed contributions, method A (visits) next to method B (uniform)
    fig2_shap_ranking_<lang>         rank by |contribution| in each method (slope chart)
    fig3_shap_additivity_<lang>      base value + sum of contributions = common delta, for each method
plus figures_manifest.json (source files with SHA-256, every plotted value, checks) and README.md.

After drawing, the plotted geometry (bar lengths, bar heights, rank positions) is read back from the
Matplotlib objects and compared with the JSON values; any difference stops the script.

Read-only on the inputs. The output folder must not exist (it is never overwritten).

    python -m agents.xai.shap_figures --out docs/shap_visualizations_v1
    python -m agents.xai.shap_figures --out docs/shap_visualizations_v2 --lang en
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from agents.xai import shap_qtable as sx
from agents.xai import shap_stability as ss

DEFAULT_DEMO = sx.PROJECT_ROOT / "docs" / "shap_demo_v2" / "shap_result.json"
DEFAULT_STABILITY = sx.PROJECT_ROOT / "docs" / "shap_stability_v2" / "shap_stability.json"
MATCH_TOL = 1e-12            # the two reports must agree to this precision
DPI = 200

# colours (validated reference palette of the dataviz guidelines: diverging pair blue <-> red, neutral grey)
POS, NEG = "#2a78d6", "#e34948"          # positive -> towards "passer", negative -> towards "garder"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8f8e88"
GRID, SURFACE, BASE_GREY, DELTA_INK = "#e6e5e1", "#ffffff", "#a3a29c", "#3d3d3a"

EN_LABELS = {"file_servie": "stopped vehicles on the green lanes",
             "file_autre": "stopped vehicles on another phase",
             "en_mouvement": "moving vehicles on green",
             "durée_vert": "elapsed green time"}

TEXT = {
    "fr": {
        "context": "S3 (Q-learning tabulaire) · feu {tls} · {clock} · décision « passer » · données simulées SUMO (LuST Kirchberg)",
        "f1_title": "Contributions SHAP exactes à Δ = Q(passer) − Q(garder) = {delta}",
        "f1_a": "A · Pondération par visites (méthode actuelle)\nvaleur de référence = {base}",
        "f1_b": "B · Pondération uniforme (mêmes {n} états)\nvaleur de référence = {base}",
        "f1_x": "Contribution SHAP (unités de valeur Q)",
        "pos": "Positive : pousse vers « passer »",
        "neg": "Négative : pousse vers « garder »",
        "zero": "0 (constante)",
        "flip": "signe inversé",
        "const_note": "{var} est constante dans les {n} états retenus : contribution nulle par construction, "
                      "ce qui ne prouve pas l'absence d'effet.",
        "f2_title": "Classement des variables selon |contribution SHAP|",
        "f2_a": "A · visites", "f2_b": "B · uniforme",
        "rank": "rang {r}",
        "f2_changed": "Rangs modifiés : {vars}.  Signe inversé : {flips}.",
        "f2_same": "Classement identique dans les deux méthodes.",
        "none": "aucun",
        "f3_title": "Additivité : valeur de référence + somme des contributions = Δ",
        "f3_a": "A · Pondération par visites", "f3_b": "B · Pondération uniforme",
        "f3_bars": ("Valeur de\nréférence", "Somme des\ncontributions", "Δ expliqué"),
        "f3_y": "Valeur (unités de valeur Q)",
        "f3_delta": "Ligne tiretée : Δ commun = {delta} (identique dans les deux méthodes).",
        "f3_err": "erreur d'additivité = {err} (tolérance {tol})",
        "f3_note": "Seule la répartition entre valeur de référence et somme des contributions change d'une méthode à l'autre.",
        "unrel": "{u} des {n} états retenus ont des valeurs Q peu fiables (moins de 3 visites).",
    },
    "en": {
        "context": "S3 (tabular Q-learning) · signal {tls} · {clock} · decision \"switch\" · SUMO simulated data (LuST Kirchberg)",
        "f1_title": "Exact SHAP contributions to Δ = Q(switch) − Q(keep) = {delta}",
        "f1_a": "A · Visit-weighted background (current method)\nbase value = {base}",
        "f1_b": "B · Uniform weights (same {n} states)\nbase value = {base}",
        "f1_x": "SHAP contribution (Q-value units)",
        "pos": "Positive: pushes towards \"switch\"",
        "neg": "Negative: pushes towards \"keep\"",
        "zero": "0 (constant)",
        "flip": "sign flipped",
        "const_note": "{var} is constant in the {n} retained states: its contribution is zero by construction, "
                      "which does not prove the variable has no effect.",
        "f2_title": "Variable ranking by |SHAP contribution|",
        "f2_a": "A · visits", "f2_b": "B · uniform",
        "rank": "rank {r}",
        "f2_changed": "Ranks changed: {vars}.  Sign flipped: {flips}.",
        "f2_same": "Same ranking in both methods.",
        "none": "none",
        "f3_title": "Additivity: base value + sum of contributions = Δ",
        "f3_a": "A · Visit-weighted background", "f3_b": "B · Uniform weights",
        "f3_bars": ("Base\nvalue", "Sum of\ncontributions", "Explained Δ"),
        "f3_y": "Value (Q-value units)",
        "f3_delta": "Dashed line: common Δ = {delta} (identical in both methods).",
        "f3_err": "additivity error = {err} (tolerance {tol})",
        "f3_note": "Only the split between base value and sum of contributions changes from one method to the other.",
        "unrel": "{u} of the {n} retained states have unreliable Q-values (fewer than 3 visits).",
    },
}


class FigureDataError(Exception):
    """The JSON reports are missing, inconsistent with each other, or not additive."""


# ------------------------------------------------------------------------------------------- data
def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _close(a: float, b: float, what: str, tol: float = MATCH_TOL):
    if abs(float(a) - float(b)) > tol:
        raise FigureDataError(f"{what}: {a!r} != {b!r}")


def load_inputs(demo_path: Path = DEFAULT_DEMO, stability_path: Path = DEFAULT_STABILITY) -> dict:
    """Read both reports, cross-check them, and return exactly the values that will be plotted."""
    demo_path, stability_path = Path(demo_path), Path(stability_path)
    for p in (demo_path, stability_path):
        if not p.exists():
            raise FigureDataError(f"missing input file: {p}")
    demo = json.loads(demo_path.read_text(encoding="utf-8"))
    stab = json.loads(stability_path.read_text(encoding="utf-8"))

    dd, sd = demo["decision"], stab["decision"]
    if (str(dd["tls"]), float(dd["time_s"])) != (str(sd["tls"]), float(sd["time_s"])):
        raise FigureDataError("the two reports do not explain the same decision")
    _close(demo["delta"], stab["delta"], "delta (demo vs stability)")

    contrib = demo["contributions"]
    comp = stab["comparison"]
    if [c["variable"] for c in contrib] != list(sx.FEATURES) or [c["variable"] for c in comp] != list(sx.FEATURES):
        raise FigureDataError("unexpected variables or order in the reports")
    for c, k in zip(contrib, comp):
        _close(c["shap"], k["shap_visits"], f"visit-weighted contribution of {c['variable']} (demo vs stability)")
    mv, mu = stab["methods"]["visits"], stab["methods"]["uniform"]
    _close(demo["base_value"], mv["base_value"], "visit-weighted base value (demo vs stability)")

    delta = float(stab["delta"])
    tol = float(stab["summary"].get("additivity_tolerance", sx.ADDITIVITY_TOL))
    methods = {}
    for name, m, key in (("visits", mv, "shap_visits"), ("uniform", mu, "shap_uniform")):
        phi = [float(k[key]) for k in comp]
        s = sum(phi)
        _close(s, m["sum_contributions"], f"sum of contributions ({name})")
        err = abs(float(m["base_value"]) + s - delta)
        if err > tol:
            raise FigureDataError(f"additivity fails for {name}: |base + sum - delta| = {err:.3e} > {tol}")
        ranks = ss.ranks_by_abs(phi)
        if ranks != [int(k[f"rank_{name}"]) for k in comp]:
            raise FigureDataError(f"ranks in the report do not match |contribution| ({name})")
        methods[name] = {"phi": phi, "base_value": float(m["base_value"]), "sum_contributions": s,
                         "additivity_error_reported": float(m["additivity_error"]),
                         "additivity_error_recomputed": err, "ranks": ranks}

    variables = []
    for c, k in zip(contrib, comp):
        variables.append({"variable": k["variable"], "label_fr": k.get("label", c.get("label", "")),
                          "label_en": EN_LABELS.get(k["variable"], ""), "class": k.get("class", c.get("class", "")),
                          "constant_in_retained_background": bool(k["constant_in_retained_background"])})
    bg = stab["background"]
    return {
        "decision": {"tls": str(sd["tls"]), "time_s": float(sd["time_s"]), "clock": sd.get("clock", sx._clock(float(sd["time_s"])))},
        "data_origin": stab.get("data_origin", demo.get("data_origin", "")),
        "delta": delta, "additivity_tolerance": tol,
        "variables": variables, "methods": methods,
        "background": {"states_retained": int(bg["states_retained"]),
                       "states_unreliable": int(bg.get("retained_states_unreliable", -1))},
        "sources": [{"file": sx._rel(p), "sha256": _sha256(p)} for p in (demo_path, stability_path)],
    }


# ---------------------------------------------------------------------------------------- drawing
def fmt(v: float) -> str:
    """6 decimals, explicit sign, typographic minus (as in the reports, which round to 6 decimals)."""
    if abs(v) <= ss.SIGN_TOL:
        return "0.000000"
    return f"{v:+.6f}".replace("-", "−")


def _style(plt):
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
        "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 10.5, "axes.titleweight": "bold",
        "axes.titlecolor": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "pdf.fonttype": 42, "svg.fonttype": "none",
    })


def _header(fig, title, context):
    fig.text(0.012, 0.975, title, ha="left", va="top", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.012, 0.925, context, ha="left", va="top", fontsize=9, color=INK2)


def _footer(fig, lines):
    fig.text(0.012, 0.018, "\n".join(lines), ha="left", va="bottom", fontsize=8.6, color=INK2, linespacing=1.45)


def _var_tick(v, lang):
    label = v["label_fr"] if lang == "fr" else v["label_en"]
    return f"{v['variable']} = {v['class']}\n{label}"


def fig_contributions(plt, data, lang):
    t = TEXT[lang]
    V, M = data["variables"], data["methods"]
    n = data["background"]["states_retained"]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.6), sharey=True)
    fig.subplots_adjust(left=0.215, right=0.985, top=0.73, bottom=0.21, wspace=0.08)
    lim = max(abs(p) for m in M.values() for p in m["phi"]) * 1.55
    y = list(range(len(V)))[::-1]
    drawn = {}
    for ax, name, title in ((axes[0], "visits", t["f1_a"]), (axes[1], "uniform", t["f1_b"])):
        phi = M[name]["phi"]
        bars = []
        for yi, v, p in zip(y, V, phi):
            if abs(p) <= ss.SIGN_TOL:
                ax.plot([0], [yi], marker="o", ms=6, mfc=SURFACE, mec=MUTED, mew=1.6, zorder=3)
                ax.text(lim * 0.04, yi, t["zero"], va="center", ha="left", fontsize=9, color=INK2)
                bars.append(None)
                continue
            r = ax.barh(yi, p, left=0.0, height=0.5, color=POS if p > 0 else NEG, zorder=2)[0]
            bars.append(r)
            off = lim * 0.025
            ax.text(p + (off if p > 0 else -off), yi, fmt(p), va="center", ha="left" if p > 0 else "right",
                    fontsize=9.5, color=INK, fontweight="bold")
            if name == "uniform":
                i = len(V) - 1 - yi
                a = M["visits"]["phi"][i]
                if ss.sign(a) != ss.sign(p) and "0" not in (ss.sign(a), ss.sign(p)):
                    ax.text(p + (off if p > 0 else -off), yi - 0.36, "(" + t["flip"] + ")", va="center",
                            ha="left" if p > 0 else "right", fontsize=8.6, color=INK2, style="italic")
        drawn[name] = bars
        ax.axvline(0, color=INK, lw=1.1, zorder=3)
        ax.set_xlim(-lim, lim)
        ax.grid(axis="x", color=GRID, lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        ax.set_title(title.format(base=fmt(M[name]["base_value"]), n=n), loc="left", pad=10)
        ax.set_xlabel(t["f1_x"])
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="y", length=0)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels([_var_tick(v, lang) for v in V], fontsize=9.2)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=POS, label=t["pos"]), Patch(color=NEG, label=t["neg"])],
               loc="upper left", bbox_to_anchor=(0.005, 0.895), ncol=2, frameon=False, fontsize=9)
    _header(fig, t["f1_title"].format(delta=fmt(data["delta"])), t["context"].format(**data["decision"]))
    notes = [t["const_note"].format(var=v["variable"], n=n) for v in V if v["constant_in_retained_background"]]
    notes.append(t["unrel"].format(u=data["background"]["states_unreliable"], n=n))
    _footer(fig, notes)
    return fig, drawn


def fig_ranking(plt, data, lang):
    t = TEXT[lang]
    V, M = data["variables"], data["methods"]
    n = data["background"]["states_retained"]
    ra, rb = M["visits"]["ranks"], M["uniform"]["ranks"]
    fig, ax = plt.subplots(figsize=(10.8, 5.6))
    fig.subplots_adjust(left=0.30, right=0.66, top=0.76, bottom=0.17)

    def offsets(ranks):          # spread tied variables a little so labels never overlap
        out, seen = [], {}
        for r in ranks:
            out.append(r + 0.16 * seen.get(r, 0))
            seen[r] = seen.get(r, 0) + 1
        return out
    ya, yb = offsets(ra), offsets(rb)
    lines = []
    for i, v in enumerate(V):
        const = v["constant_in_retained_background"]
        changed = ra[i] != rb[i]
        color = MUTED if const else (INK if changed else INK2)
        ls = (0, (4, 3)) if const else "-"
        lw = 2.6 if changed else 2.0
        ln, = ax.plot([0, 1], [ya[i], yb[i]], color=color, lw=lw, ls=ls, marker="o", ms=8,
                      mfc=color, mec=SURFACE, mew=1.5, zorder=3, solid_capstyle="round")
        lines.append(ln)
        pa, pb = M["visits"]["phi"][i], M["uniform"]["phi"][i]
        ax.text(-0.05, ya[i], f"{v['variable']}   {fmt(pa)}", ha="right", va="center", fontsize=9.6,
                color=INK if not const else INK2, fontweight="bold" if changed else "normal")
        right = f"{fmt(pb)}   {v['variable']}"
        if ss.sign(pa) != ss.sign(pb) and "0" not in (ss.sign(pa), ss.sign(pb)):
            right += f"   ({t['flip']})"
        if const:
            right += "  *"
        ax.text(1.05, yb[i], right, ha="left", va="center", fontsize=9.6,
                color=INK if not const else INK2, fontweight="bold" if changed else "normal")
    nr = len(V)
    ax.set_ylim(nr + 0.6, 0.4)
    ax.set_xlim(-0.02, 1.02)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([t["f2_a"], t["f2_b"]], fontsize=10.5, fontweight="bold", color=INK)
    ax.xaxis.tick_top()
    ax.set_yticks(range(1, nr + 1))
    ax.set_yticklabels([])
    for r in range(1, nr + 1):
        ax.axhline(r, color=GRID, lw=0.8, zorder=0)
        fig.text(0.012, ax.transData.transform((0, r))[1] / fig.dpi / fig.get_figheight(),
                 t["rank"].format(r=r), ha="left", va="center", fontsize=9, color=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    _header(fig, t["f2_title"], t["context"].format(**data["decision"]))
    changed = [v["variable"] for v, a, b in zip(V, ra, rb) if a != b]
    flips = [v["variable"] for v, a, b in zip(V, M["visits"]["phi"], M["uniform"]["phi"])
             if ss.sign(a) != ss.sign(b) and "0" not in (ss.sign(a), ss.sign(b))]
    notes = [t["f2_changed"].format(vars=", ".join(changed) or t["none"], flips=", ".join(flips) or t["none"])
             if changed or flips else t["f2_same"]]
    notes += ["* " + t["const_note"].format(var=v["variable"], n=n) for v in V if v["constant_in_retained_background"]]
    _footer(fig, notes)
    return fig, {"lines": lines, "ya": ya, "yb": yb}


def fig_additivity(plt, data, lang):
    t = TEXT[lang]
    M, delta, tol = data["methods"], data["delta"], data["additivity_tolerance"]
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 5.7), sharey=True)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.80, bottom=0.20, wspace=0.08)
    top = max(max(m["base_value"], m["base_value"] + m["sum_contributions"]) for m in M.values())
    top = max(top, delta) * 1.22
    drawn = {}
    for ax, name, title in ((axes[0], "visits", t["f3_a"]), (axes[1], "uniform", t["f3_b"])):
        m = M[name]
        base, s = m["base_value"], m["sum_contributions"]
        b0 = ax.bar(0, base, bottom=0.0, width=0.56, color=BASE_GREY, zorder=2)[0]
        b1 = ax.bar(1, s, bottom=base, width=0.56, color=POS if s >= 0 else NEG, zorder=2)[0]
        b2 = ax.bar(2, delta, bottom=0.0, width=0.56, color=DELTA_INK, zorder=2)[0]
        drawn[name] = (b0, b1, b2)
        ax.plot([0.28, 0.72], [base, base], color=INK2, lw=1, ls=(0, (2, 2)), zorder=3)
        ax.plot([1.28, 1.72], [base + s, base + s], color=INK2, lw=1, ls=(0, (2, 2)), zorder=3)
        pad = top * 0.018
        ax.text(0, base + pad, fmt(base), ha="center", va="bottom", fontsize=9.5, fontweight="bold", color=INK)
        ax.text(1, max(base, base + s) + pad, fmt(s), ha="center", va="bottom", fontsize=9.5, fontweight="bold", color=INK)
        ax.text(2, delta + pad, fmt(delta), ha="center", va="bottom", fontsize=9.5, fontweight="bold", color=INK)
        ax.axhline(delta, color=INK, lw=1, ls=(0, (5, 3)), zorder=1)
        ax.axhline(0, color=INK, lw=1.1, zorder=3)
        err = m["additivity_error_reported"]
        ax.set_title(title + "\n" + t["f3_err"].format(err="0" if err == 0 else f"{err:.1e}", tol=f"{tol:g}"),
                     loc="left", pad=10)
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(t["f3_bars"], fontsize=9.4)
        ax.set_xlim(-0.6, 2.6)
        ax.set_ylim(min(0.0, min(m["base_value"] for m in M.values())) * 1.1, top)
        ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.tick_params(axis="x", length=0)
    axes[0].set_ylabel(t["f3_y"])
    _header(fig, t["f3_title"], t["context"].format(**data["decision"]))
    _footer(fig, [t["f3_delta"].format(delta=fmt(delta)), t["f3_note"]])
    return fig, drawn


# ----------------------------------------------------------------------------------- verification
def verify_geometry(data, drawn) -> list:
    """Read the plotted geometry back and compare it with the JSON values. Returns the list of checks."""
    checks = []
    M = data["methods"]
    for name in ("visits", "uniform"):
        for v, p, bar in zip(data["variables"], M[name]["phi"], drawn["contributions"][name]):
            got = 0.0 if bar is None else float(bar.get_width())
            if bar is not None and float(bar.get_x()) != 0.0:
                raise FigureDataError(f"fig1 {name} {v['variable']}: bar does not start at 0")
            if abs(got - p) > MATCH_TOL:
                raise FigureDataError(f"fig1 {name} {v['variable']}: plotted {got!r} != JSON {p!r}")
        checks.append(f"fig1 {name}: 4 bar lengths equal the JSON contributions (within 1e-12)")
        b0, b1, b2 = drawn["additivity"][name]
        m = M[name]
        for what, got, exp in (("base value", b0.get_height(), m["base_value"]),
                               ("sum bar start", b1.get_y(), m["base_value"]),
                               ("sum bar length", b1.get_height(), m["sum_contributions"]),
                               ("delta", b2.get_height(), data["delta"])):
            if abs(float(got) - float(exp)) > MATCH_TOL:
                raise FigureDataError(f"fig3 {name} {what}: plotted {got!r} != JSON {exp!r}")
        if abs(b1.get_y() + b1.get_height() - b2.get_height()) > data["additivity_tolerance"]:
            raise FigureDataError(f"fig3 {name}: top of the sum bar does not reach delta")
        checks.append(f"fig3 {name}: base, sum and delta bars equal the JSON values (within 1e-12); base + sum reaches delta")
    rk = drawn["ranking"]
    for i, ln in enumerate(rk["lines"]):
        ys = [float(y) for y in ln.get_ydata()]
        if ys != [rk["ya"][i], rk["yb"][i]]:
            raise FigureDataError("fig2: plotted rank positions differ from the ranks")
        if int(ys[0]) != M["visits"]["ranks"][i] or int(ys[1]) != M["uniform"]["ranks"][i]:
            raise FigureDataError(f"fig2 {data['variables'][i]['variable']}: plotted rank differs from |contribution| rank")
    checks.append("fig2: plotted ranks equal the ranks by |contribution| in both methods")
    return checks


def build_figures(data: dict, langs=("fr", "en")) -> dict:
    """Draw every figure in memory and verify it. Returns {lang: {name: (fig, checks)}}."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _style(plt)
    out = {}
    for lang in langs:
        f1, d1 = fig_contributions(plt, data, lang)
        f2, d2 = fig_ranking(plt, data, lang)
        f3, d3 = fig_additivity(plt, data, lang)
        checks = verify_geometry(data, {"contributions": d1, "ranking": d2, "additivity": d3})
        out[lang] = {"fig1_shap_contributions": f1, "fig2_shap_ranking": f2, "fig3_shap_additivity": f3,
                     "_checks": checks}
    return out


def manifest(data: dict, figures: dict, files: list) -> dict:
    V, M = data["variables"], data["methods"]
    return {
        "data_origin": data["data_origin"],
        "purpose": "Static figures of the exact SHAP explanation and its sensitivity to background weights",
        "sources": data["sources"],
        "decision": data["decision"],
        "delta": data["delta"],
        "plotted_values": [{"variable": v["variable"], "class": v["class"],
                            "shap_visits": M["visits"]["phi"][i], "shap_uniform": M["uniform"]["phi"][i],
                            "rank_visits": M["visits"]["ranks"][i], "rank_uniform": M["uniform"]["ranks"][i],
                            "constant_in_retained_background": v["constant_in_retained_background"]}
                           for i, v in enumerate(V)],
        "base_values": {k: M[k]["base_value"] for k in M},
        "sum_contributions": {k: M[k]["sum_contributions"] for k in M},
        "additivity_error_reported": {k: M[k]["additivity_error_reported"] for k in M},
        "additivity_error_recomputed": {k: M[k]["additivity_error_recomputed"] for k in M},
        "checks": ["reports explain the same decision (tls, time) and the same delta",
                   "visit-weighted contributions and base value identical in both reports (tolerance 1e-12)",
                   "additivity recomputed for both methods",
                   "ranks recomputed from |contribution| and equal to the report"]
                  + sorted({c for lang in figures for c in figures[lang]["_checks"]}),
        "files": files,
        "labels_note": "Values on the figures are rounded to 6 decimals, as in the source reports.",
    }


README = """# Figures XAI (SHAP) — S3, feu {tls}, {clock}

Générées par `python -m agents.xai.shap_figures` à partir de :
{sources}

Les valeurs ne sont pas recopiées à la main : elles sont lues dans ces fichiers, contrôlées
(cohérence des deux rapports, additivité, rangs), puis relues dans les graphiques avant l'export.
Les valeurs exactes tracées sont dans `figures_manifest.json`.

| Figure | Contenu |
|---|---|
| `fig1_shap_contributions_*` | contributions signées des 4 variables, méthode A (visites) à côté de la méthode B (uniforme) |
| `fig2_shap_ranking_*` | rang de chaque variable selon \\|contribution\\| dans chaque méthode |
| `fig3_shap_additivity_*` | valeur de référence + somme des contributions = Δ commun, pour chaque méthode |

Suffixe `_fr` / `_en` : langue des libellés. Formats PNG (200 dpi) et PDF (vectoriel).

À lire avec les limites du rapport de stabilité : une seule décision, {u} des {n} états
retenus ont des valeurs Q peu fiables, `file_servie` est constante dans le fond retenu
(contribution nulle par construction, ce qui ne prouve pas l'absence d'effet), et SHAP
décrit la sortie de la table Q, pas un effet causal sur le trafic.
Données : simulation SUMO ({origin}).
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Static SHAP figures from the existing JSON reports (never overwrites).")
    ap.add_argument("--out", required=True, help="new output folder (must not exist)")
    ap.add_argument("--demo", default=str(DEFAULT_DEMO), help="shap_result.json of shap_qtable")
    ap.add_argument("--stability", default=str(DEFAULT_STABILITY), help="shap_stability.json of shap_stability")
    ap.add_argument("--lang", choices=("fr", "en", "both"), default="both")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if not out.is_absolute():
        out = sx.PROJECT_ROOT / out
    if out.exists():
        print(f"REFUSED: {out} already exists (results are never overwritten). Choose a new folder.", file=sys.stderr)
        return 2
    langs = ("fr", "en") if a.lang == "both" else (a.lang,)
    try:
        data = load_inputs(Path(a.demo), Path(a.stability))
        figs = build_figures(data, langs)
    except (FigureDataError, KeyError, ValueError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 1
    out.mkdir(parents=True)
    files = []
    for lang in langs:
        for name, fig in figs[lang].items():
            if name.startswith("_"):
                continue
            for ext in ("png", "pdf"):
                p = out / f"{name}_{lang}.{ext}"
                kw = {"dpi": DPI} if ext == "png" else {"metadata": {"CreationDate": None}}
                fig.savefig(p, facecolor=SURFACE, **kw)
                files.append(p.name)
    (out / "figures_manifest.json").write_text(
        json.dumps(manifest(data, figs, files), ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "README.md").write_text(README.format(
        sources="\n".join(f"- `{s['file']}` (SHA-256 `{s['sha256'][:16]}…`)" for s in data["sources"]),
        u=data["background"]["states_unreliable"], n=data["background"]["states_retained"],
        origin=data["data_origin"], **data["decision"]), encoding="utf-8")
    print(f"{len(files)} figure files + figures_manifest.json + README.md written to {out}")
    for c in figs[langs[0]]["_checks"]:
        print("  OK", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
