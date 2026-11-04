"""Control application backend: REST API over agents.orchestrator (SUMO/TraCI) + static Next.js frontend.

Run from the project root (Windows PowerShell or Linux):
    python -m app.backend.server              # http://127.0.0.1:8000
    python -m app.backend.server --port 8010 --no-browser
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agents.orchestrator import STRATEGIES  # noqa: E402
from agents.prediction.cascade_agent import DEFAULT_MODEL  # noqa: E402

from . import results  # noqa: E402
from .network import network  # noqa: E402
from .sim_manager import DETECTION_MODES, SCENARIOS, Busy, SimulationManager, _default_qtable  # noqa: E402

FRONTEND = ROOT / "app" / "frontend" / "out"
DESCRIPTIONS = {
    "S0_fixed_time": "Programmes de feux LuST d'origine, sans intervention.",
    "S1_actuated": "Feux adaptatifs intégrés à SUMO (mêmes phases et jaunes).",
    "S2_demand_gap": "Agent à règle : termine le vert quand ses voies sont vides et qu'une autre phase attend.",
    "S2F_forecast_gap": "S2 informé par la prévision en cascade (+5 min).",
    "S2b_max_pressure": "Agent max-pressure (moins bon que S0 dans nos essais).",
    "S3_rl_qlearning": "Agent RL Q-learning entraîné en simulation (26 épisodes).",
}


class StartRequest(BaseModel):
    scenario: str = "kirchberg_4tls"
    strategy: str = "S0_fixed_time"
    scale: float = Field(1.0, ge=0.1, le=10)
    seed: int = Field(1, ge=0)
    delay_ms: float = Field(0.0, ge=0, le=2000)
    gui: bool = False
    use_forecast: bool = True
    detection_mode: str = "discharge"
    incident: str = "none"            # simulated blocked lane 07:20-07:40 (see sim_manager.INCIDENTS) - 2026-10-22
    ambulance: bool = False           # simulated ambulance inserted at 07:20
    ambulance_priority: bool = True   # emergency-priority module on/off for that ambulance


def create_app(manager: SimulationManager | None = None, auth=False) -> FastAPI:
    """auth: False = no authentication (tests, local development); True = accounts of config/users.json;
    or an app.backend.auth.Auth instance (tests of the authentication). 2026-11-03."""
    from contextlib import asynccontextmanager

    from .auth import Auth, install as install_auth

    mgr = manager or SimulationManager()
    auth_obj = (Auth() if auth is True else auth) or None

    @asynccontextmanager
    async def lifespan(_app):
        yield
        mgr.shutdown()               # backend stopped (Ctrl+C): stop SUMO cleanly, write the partial outputs

    app = FastAPI(title="Kirchberg traffic control console", version="1.0", lifespan=lifespan)
    app.state.manager = mgr
    app.state.auth = auth_obj
    install_auth(app, auth_obj)                         # sessions, roles, /api/auth/* (2026-11-03)
    from .ops_api import make_router as ops_router      # incident history of the application runs (2026-11-03)
    app.include_router(ops_router(mgr))
    from .xai_api import make_router as xai_router      # XAI: real decisions + exact SHAP on demand (2026-10-29)
    app.include_router(xai_router(mgr))

    @app.get("/api/diagnostics")
    def diagnostics():
        """SUMO binary and version, backend that will be used (libsumo or TraCI) and why."""
        import os
        import subprocess
        from agents.common.sim_env import choose_backend, libsumo_status
        from traci_layer.config import find_sumo_binary
        out = {"python": sys.executable, "sumo_home": os.environ.get("SUMO_HOME"),
               "ITM_SUMO_BACKEND": os.environ.get("ITM_SUMO_BACKEND", "auto")}
        for name, gui in (("sumo", False), ("sumo_gui", True)):
            b = find_sumo_binary(gui)
            out[f"{name}_binary"] = b
        try:
            r = subprocess.run([out["sumo_binary"], "--version"], capture_output=True, text=True, timeout=30)
            out["sumo_version"] = (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else None
            out["sumo_version_exit_code"] = r.returncode
        except Exception as exc:  # noqa: BLE001
            out["sumo_version"] = f"échec : {exc}"
        from agents.common.sim_env import sumo_binary_status
        for name, gui in (("sumo", False), ("sumo_gui", True)):
            out[f"{name}_can_start"], out[f"{name}_status"] = sumo_binary_status(gui)
        ok, reason = libsumo_status()
        use, why = choose_backend(False, None)
        out.update({"libsumo_usable": ok, "libsumo_reason": reason, "backend_without_gui": "libsumo" if use else "traci",
                    "backend_reason": why, "backend_with_gui": "traci (sumo-gui)"})
        return out

    def available(s: str) -> bool:
        if s == "S3_rl_qlearning":
            return _default_qtable().exists()
        if s == "S2F_forecast_gap":
            return DEFAULT_MODEL.exists()
        return True

    @app.get("/api/health")
    def health():
        return {"ok": True, "simulation": mgr.state().get("status"), "auth": auth_obj is not None}

    @app.get("/api/config")
    def config():
        return {"scenarios": [{"id": k, "label": v} for k, v in SCENARIOS.items()],
                "strategies": [{"id": s, "label": results.STRATEGY_LABELS.get(s, s), "description": DESCRIPTIONS.get(s, ""),
                                "available": available(s)} for s in STRATEGIES],
                "detection_modes": list(DETECTION_MODES), "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls"}

    @app.get("/api/network")
    def get_network():
        return network()

    @app.post("/api/sim/start")
    def start(req: StartRequest):
        try:
            return mgr.start(**req.model_dump())
        except Busy as e:
            raise HTTPException(409, str(e))
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))

    @app.post("/api/sim/pause")
    def pause():
        try:
            return mgr.pause()
        except Busy as e:
            raise HTTPException(409, str(e))

    @app.post("/api/sim/resume")
    def resume():
        try:
            return mgr.resume()
        except Busy as e:
            raise HTTPException(409, str(e))

    @app.post("/api/sim/stop")
    def stop():
        try:
            return mgr.stop()
        except Busy as e:
            raise HTTPException(409, str(e))

    @app.get("/api/sim/state")
    def sim_state():
        return mgr.state()

    @app.get("/api/runs")
    def runs():
        return {"runs": results.list_runs()}

    @app.get("/api/runs/{run_id:path}/files/{name}")
    def run_file(run_id: str, name: str):
        try:
            f = results.run_file(run_id, name)
        except results.NotFound as e:
            raise HTTPException(404, str(e))
        return FileResponse(f, filename=f"{Path(run_id).name}_{name}")

    @app.get("/api/compare")
    def compare(a: str, b: str, scale: float = 5.0):
        try:
            return results.compare(a, b, scale)
        except results.NotFound as e:
            raise HTTPException(404, str(e))

    @app.get("/api/export/kpi_runs.csv")
    def export():
        return Response(results.export_csv(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=kpi_runs_export.csv"})

    @app.get("/api/reports")
    def reports():
        return {"reports": results.reports()}

    @app.get("/api/reports/{name:path}")
    def report(name: str):
        try:
            return {"name": name, "text": results.report_text(name)}
        except results.NotFound as e:
            raise HTTPException(404, str(e))

    @app.get("/api/data-sources")
    def data_sources():
        return results.data_sources()

    if FRONTEND.exists():
        app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
    else:
        @app.get("/")
        def no_frontend():
            return PlainTextResponse("Frontend not built: run `npm install` then `npm run build` in app/frontend.", 503)
    return app


# Authentication is ON for the real server. ITM_AUTH=off disables it (local development only: everybody is admin).
AUTH_ON = os.environ.get("ITM_AUTH", "on").strip().lower() not in ("off", "0", "false", "no")
app = create_app(auth=AUTH_ON)


def main(argv=None):
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true")
    a = p.parse_args(argv)
    if not a.no_browser:
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{a.host}:{a.port}/")).start()
    if not AUTH_ON:
        print("ATTENTION : authentification désactivée (ITM_AUTH=off) - n'utilisez ce mode qu'en local.")
    elif app.state.auth.users.count() == 0:
        print("Aucun compte n'existe encore. Créez le compte administrateur, puis rechargez la page de connexion :")
        print("    python -m app.backend.auth add-user --email VOTRE@ADRESSE --name \"Votre nom\" --role admin")
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
