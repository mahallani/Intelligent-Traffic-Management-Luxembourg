"""Movement-conflict check of every signal program used by the controllers (SIMULATED network, read-only).

For each of the 4 signals and each program loaded in the scenario (LuST fixed-time "0" + actuated programs of
tls_actuated_v1.add.xml when present), every phase state is checked pair by pair with SUMO's own conflict matrix
(traci.lane.getFoes on the internal 'via' lanes of the controlled links):
  priority conflict  = two links both 'G' (priority green) whose paths cross            -> must be 0
  permissive pairs   = 'G' with 'g' (the 'g' movement yields, e.g. left turn across traffic) -> allowed, counted
  yellow/green mix   = informative only
Writes sumo/lust_4_intersections/output/safety/signal_conflicts_<tag>.csv (+ .md); never overwrites.

    python scripts/simulation/check_signal_conflicts_v1.py --tag v1
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents.common.sim_env import BEGIN, SimEnv  # noqa: E402

OUTDIR = ROOT / "sumo" / "lust_4_intersections" / "output" / "safety"
ACT = ROOT / "sumo" / "lust_4_intersections" / "additional" / "tls_actuated_v1.add.xml"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1")
    a = p.parse_args(argv)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out_csv, out_md = OUTDIR / f"signal_conflicts_{a.tag}.csv", OUTDIR / f"signal_conflicts_{a.tag}.md"
    for f in (out_csv, out_md):
        if f.exists():
            sys.exit(f"{f} exists - use another --tag")
    extra = [str(ACT)] if ACT.exists() else []
    env = SimEnv(scale=1.0, seed=1, end=BEGIN + 5, additional_files=extra)
    rows = []
    with env:
        tl, lane = env.api.trafficlight, env.api.lane
        for tls in sorted(env.tls):
            links = tl.getControlledLinks(tls)
            via = [lk[0][2] if lk else None for lk in links]
            foes = {}
            for i, v in enumerate(via):
                if v:
                    try:
                        foes[i] = set(lane.getFoes(v, ""))
                    except Exception:  # noqa: BLE001
                        foes[i] = set()
            for logic in tl.getAllProgramLogics(tls):
                for k, ph in enumerate(logic.phases):
                    s = ph.state
                    prio, perm = [], 0
                    for i in range(len(s)):
                        for j in range(i + 1, len(s)):
                            if i not in foes or j not in foes or not via[i] or not via[j]:
                                continue
                            if via[j] not in foes[i] and via[i] not in foes[j]:
                                continue
                            if links[i][0][0] == links[j][0][0]:
                                continue  # same incoming lane: queued one after the other, not a crossing conflict
                            if s[i] == "G" and s[j] == "G":
                                prio.append(f"{i}-{j}")
                            elif {s[i], s[j]} == {"G", "g"} or (s[i] == "g" and s[j] == "g"):
                                perm += 1
                    rows.append({"tls": tls, "program": logic.programID, "type": logic.type, "phase": k, "state": s,
                                 "duration_s": ph.duration, "links": len(s), "links_with_conflict_data": len(foes),
                                 "priority_conflicts": len(prio), "priority_conflict_pairs": " ".join(prio),
                                 "permissive_conflict_pairs": perm, "data_origin": "SIMULATED_network_LuST"})
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    tot = sum(r["priority_conflicts"] for r in rows)
    md = [f"# Conflits de mouvements des programmes de feux ({a.tag})", "",
          f"{len(rows)} phases vérifiées ({len({(r['tls'], r['program']) for r in rows})} programmes, 4 feux) avec la matrice "
          "de conflits de SUMO (`lane.getFoes` sur les voies internes).", "",
          f"**Conflits prioritaires (deux mouvements 'G' qui se croisent) : {tot}.**", "",
          "| Feu | Programme | Phases | Conflits prioritaires | Paires permissives (G/g, cédez-le-passage) |", "|---|---|---|---|---|"]
    for key in sorted({(r["tls"], r["program"]) for r in rows}):
        rs = [r for r in rows if (r["tls"], r["program"]) == key]
        md.append(f"| {key[0]} | {key[1]} | {len(rs)} | {sum(r['priority_conflicts'] for r in rs)} | {sum(r['permissive_conflict_pairs'] for r in rs)} |")
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    for r in rows:
        if r["priority_conflicts"]:
            print("CONFLICT", r["tls"], r["program"], r["phase"], r["state"], r["priority_conflict_pairs"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
