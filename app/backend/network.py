"""Geometry of the reduced SUMO network for the map (read once from the .net.xml, no TraCI needed)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from agents.common.sim_env import SCENARIO_DIR, TLS_IDS

NET = SCENARIO_DIR / "net" / "kirchberg_4tls.net.xml"
LABELS = {tid: f"Carrefour {i + 1}" for i, tid in enumerate(TLS_IDS)}     # SW -> NE along Avenue J.F. Kennedy


STOP_LINE_M = 14.0      # length of the lane end drawn in the colour of its signal (map only)


def _tail(pts: list, length: float) -> list:
    """Last `length` metres of a polyline (the approach just before the stop line)."""
    out, left = [pts[-1]], length
    for (x0, y0), (x1, y1) in zip(reversed(pts[:-1]), reversed(pts[1:])):
        d = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if d >= left:
            f = left / d if d else 0.0
            out.append((x1 + (x0 - x1) * f, y1 + (y0 - y1) * f))
            break
        out.append((x0, y0))
        left -= d
    return [[round(x, 1), round(y, 1)] for x, y in reversed(out)]


@lru_cache(maxsize=1)
def network(net_file: Path = NET) -> dict:
    lanes, xs, ys, junctions, shapes, links = [], [], [], {}, {}, {}
    lane_m = 0.0
    for _, el in ET.iterparse(str(net_file), events=("end",)):
        if el.tag == "edge" and el.get("function") != "internal":
            for ln in el.findall("lane"):
                pts = [tuple(float(v) for v in p.split(",")[:2]) for p in ln.get("shape", "").split()]
                if pts:
                    lanes.append({"id": ln.get("id"), "shape": [[round(x, 1), round(y, 1)] for x, y in pts]})
                    shapes[ln.get("id")] = pts
                    lane_m += float(ln.get("length") or 0.0)
                    xs += [p[0] for p in pts]
                    ys += [p[1] for p in pts]
        elif el.tag == "junction" and el.get("id") in TLS_IDS:
            junctions[el.get("id")] = (float(el.get("x")), float(el.get("y")))
        elif el.tag == "connection" and el.get("tl") in TLS_IDS and el.get("linkIndex") is not None:
            # 2026-11-03: which signal-state characters control each incoming lane (to colour its stop line on the map)
            lane = f"{el.get('from')}_{el.get('fromLane')}"
            links.setdefault((el.get("tl"), lane), set()).add(int(el.get("linkIndex")))
    pad = 20.0
    stop_lines = [{"tls": t, "lane": lane, "links": sorted(ix), "shape": _tail(shapes[lane], STOP_LINE_M)}
                  for (t, lane), ix in sorted(links.items()) if lane in shapes and len(shapes[lane]) > 1]
    return {"bbox": [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad], "lanes": lanes,
            "signals": [{"id": t, "label": LABELS[t], "x": junctions[t][0], "y": junctions[t][1]} for t in TLS_IDS],
            "stop_lines": stop_lines,                      # 2026-11-03 (additive)
            "lane_km": round(lane_m / 1000.0, 3),          # 2026-11-03: total lane length, for the density indicator
            "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls"}
