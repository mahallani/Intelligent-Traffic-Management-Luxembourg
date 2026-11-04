"""Real screenshots + a screen recording of the control application running scenario B (2026-10-22).

Starts the backend (python -m app.backend.server --no-browser) on a free port, drives the UI with a headless
Chromium (Playwright), and saves everything to a NEW folder docs/demo_captures_<tag>/ (refuses to overwrite):
  01_formulaire.png, 02_pause.png, 03_decisions_incident.png, 04_detections_incident.png, 05_previsions.png,
  06_fin_indicateurs.png, 07_resultats_comparaison.png, session.webm (video of the whole session), captures.json
  (sim time, run id and status at each capture, read from /api/sim/state).
The simulation is SIMULATED (SUMO, LuST demand x5); captures show the app on the machine where the script runs.

    python scripts/demo/capture_app_screens_v1.py --tag v1
Needs: pip install playwright ; python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import platform
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--strategy", default="S3_rl_qlearning")
    ap.add_argument("--seed", default="61")
    a = ap.parse_args()
    out = ROOT / "docs" / f"demo_captures_{a.tag}"
    if out.exists():
        sys.exit(f"{out} exists - use another --tag")
    out.mkdir(parents=True)
    from playwright.sync_api import sync_playwright

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    srv = subprocess.Popen([sys.executable, "-m", "app.backend.server", "--no-browser", "--port", str(port)], cwd=ROOT,
                           stdout=open(out / "backend.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    log = {"date": datetime.now().isoformat(timespec="seconds"), "machine": f"{platform.system()} {platform.release()}",
           "python": platform.python_version(), "url": base, "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls",
           "note": "scrollable tables (.scroll) expanded to full height for the captures; content unchanged", "captures": []}
    try:
        for _ in range(60):
            try:
                get(base + "/api/health")
                break
            except Exception:
                time.sleep(0.5)
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            ctx = br.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(out / "_video"),
                                 record_video_size={"width": 1440, "height": 900})
            pg = ctx.new_page()

            def shot(name, full=True):
                pg.wait_for_timeout(400)
                pg.screenshot(path=str(out / name), full_page=full)
                st = get(base + "/api/sim/state")
                log["captures"].append({"file": name, "status": st.get("status"), "clock": st.get("clock"),
                                        "sim_time": st.get("sim_time"), "run_id": st.get("run_id")})

            def wait_time(t, limit=150):
                t_end = time.time() + limit
                while time.time() < t_end:
                    st = get(base + "/api/sim/state")
                    if st.get("status") in ("finished", "stopped", "error") or (st.get("sim_time") or 0) >= t:
                        return st
                    time.sleep(0.5)
                return st

            pg.goto(base + "/")
            pg.add_style_tag(content=".scroll{max-height:none!important}")  # show whole tables in the captures
            pg.wait_for_selector("#st option[value='S3_rl_qlearning']", state="attached")
            pg.select_option("#st", a.strategy)
            pg.select_option("#dm", "5")
            pg.fill("#sd", a.seed)
            pg.select_option("#dl", "20")
            pg.select_option("#dr", "discharge")
            pg.select_option("#inc", "carrefour4")
            pg.check("#amb")
            pg.check("#ambp")
            shot("01_formulaire.png")
            pg.click("button:has-text('Lancer')")
            wait_time(25800)
            pg.click("button:has-text('Pause')")
            pg.wait_for_timeout(1500)
            shot("02_pause.png")
            pg.click("button:has-text('Reprendre')")
            wait_time(26700)
            pg.click("button[role=tab]:has-text('Décisions')")
            shot("03_decisions_incident.png")
            pg.click("button[role=tab]:has-text('Détections')")
            shot("04_detections_incident.png")
            wait_time(27300)
            pg.click("button[role=tab]:has-text('Prévisions')")
            shot("05_previsions.png")
            st = wait_time(10 ** 9, limit=150)
            pg.wait_for_timeout(2500)
            pg.click("button[role=tab]:has-text('Décisions')")
            shot("06_fin_indicateurs.png")
            log["final_status"] = st.get("status")
            log["final_kpis"] = {k: st.get("final_kpis", {}).get(k) for k in
                                 ("avg_travel_time_s", "avg_waiting_time_s", "avg_queue_veh", "co2_kg", "incident", "emergency")}
            if log["final_kpis"].get("emergency"):
                log["final_kpis"]["emergency"].pop("actions", None)
            log["final_kpis"]["safety_violations"] = (st.get("final_kpis", {}).get("safety") or {}).get("total_violations")
            pg.goto(base + "/resultats/")
            pg.add_style_tag(content=".scroll{max-height:none!important}")
            pg.wait_for_selector("#sa option[value='S3_rl_qlearning']", state="attached")
            pg.select_option("#sa", "S0_fixed_time")
            pg.select_option("#sb", "S3_rl_qlearning")
            pg.select_option("#cs", "5")
            pg.click("button:has-text('Comparer')")
            pg.wait_for_timeout(2500)
            shot("07_resultats_comparaison.png")
            vid = pg.video.path()
            ctx.close()
            br.close()
            Path(vid).rename(out / "session.webm")
    finally:
        srv.terminate()
        try:
            srv.wait(15)
        except Exception:
            srv.kill()
        (out / "captures.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
