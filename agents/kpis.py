"""KPIs of one simulation run, computed from SUMO's own outputs (tripinfo + summary) and from
the queue samples of the collection agent. All values are SIMULATED."""
from __future__ import annotations

import statistics as st
import xml.etree.ElementTree as ET
from pathlib import Path

from . import DATA_ORIGIN


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def trip_kpis(tripinfo: Path) -> dict:
    done, unfinished = [], []
    co2 = nox = pmx = fuel = 0.0
    for _, el in ET.iterparse(str(tripinfo), events=("end",)):
        if el.tag != "tripinfo":
            continue
        rec = {k: _f(el.get(k)) for k in ("duration", "waitingTime", "timeLoss", "departDelay", "routeLength")}
        em = el.find("emissions")
        if em is not None:
            co2 += _f(em.get("CO2_abs")); nox += _f(em.get("NOx_abs"))
            pmx += _f(em.get("PMx_abs")); fuel += _f(em.get("fuel_abs"))
        (unfinished if _f(el.get("arrival"), -1) < 0 else done).append(rec)
        el.clear()
    mean = lambda rows, k: round(st.mean(r[k] for r in rows), 2) if rows else None  # noqa: E731
    return {
        "completed_trips": len(done), "unfinished_trips_at_end": len(unfinished),
        "avg_travel_time_s": mean(done, "duration"), "avg_waiting_time_s": mean(done, "waitingTime"),
        "avg_time_loss_s": mean(done, "timeLoss"), "avg_depart_delay_s": mean(done, "departDelay"),
        "p95_travel_time_s": round(sorted(r["duration"] for r in done)[int(0.95 * (len(done) - 1))], 1) if done else None,
        "total_waiting_time_all_h": round(sum(r["waitingTime"] for r in done + unfinished) / 3600, 2),
        "total_time_loss_all_h": round(sum(r["timeLoss"] for r in done + unfinished) / 3600, 2),
        # emissions: SUMO HBEFA model, mg -> kg / g ; fuel mg -> kg (SUMO >= 1.14 reports fuel in mg)
        "co2_kg": round(co2 / 1e6, 2), "nox_g": round(nox / 1e3, 2), "pmx_g": round(pmx / 1e3, 3),
        "fuel_kg": round(fuel / 1e6, 2),
    }


def summary_kpis(summary: Path) -> dict:
    last = None
    for _, el in ET.iterparse(str(summary), events=("end",)):
        if el.tag == "step":
            last = dict(el.attrib)
            el.clear()
    if last is None:
        return {}
    return {"loaded": int(_f(last.get("loaded"))), "inserted": int(_f(last.get("inserted"))),
            "running_at_end": int(_f(last.get("running"))), "waiting_insertion_at_end": int(_f(last.get("waiting"))),
            "arrived": int(_f(last.get("arrived"))),
            # vehicles removed because they could not enter within max-depart-delay (600 s, LuST value)
            "discarded_not_inserted": int(_f(last.get("discarded", 0))),
            "teleports": int(_f(last.get("teleports", 0))),
            "collisions": int(_f(last.get("collisions", 0)))}


def queue_kpis(samples: list[dict], warmup_end: float) -> dict:
    s = [x for x in samples if x["time"] >= warmup_end]
    if not s:
        return {}
    tot = [x["halting_total"] for x in s]
    out = {"avg_queue_veh": round(st.mean(tot), 2), "max_queue_veh": max(tot),
           "avg_queue_m": round(st.mean(x["queue_m_total"] for x in s), 1)}
    for t in s[0]["halting_by_tls"]:
        out[f"avg_queue_veh_tls_{t}"] = round(st.mean(x["halting_by_tls"][t] for x in s), 2)
    return out


def run_kpis(out_dir: Path, samples: list[dict], warmup_end: float, meta: dict) -> dict:
    k = {**meta, "data_origin": DATA_ORIGIN}
    k.update(summary_kpis(Path(out_dir) / "summary.xml"))
    k.update(trip_kpis(Path(out_dir) / "tripinfo.xml"))
    k.update(queue_kpis(samples, warmup_end))
    return k
