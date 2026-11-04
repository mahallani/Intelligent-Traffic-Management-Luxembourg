"""
Simulation environment shared by all agents: starts SUMO with the project's TraCI layer
(traci_layer.SumoConfig / SumoConnection) and exposes the static topology of the 4 signals.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from traci_layer import SumoConfig, SumoConnection  # noqa: E402

SCENARIO_DIR = PROJECT_ROOT / "sumo" / "lust_4_intersections"
SUMOCFG = SCENARIO_DIR / "kirchberg_4tls.sumocfg"
TLS_IDS = ["-28692", "-23354", "-20484", "-29958"]      # SW -> NE along Avenue J.F. Kennedy
BEGIN, END = 25200.0, 28800.0                             # 07:00 - 08:00
WARMUP_S = 300.0                                          # zone empty at 07:00: KPIs on queues ignore the first 300 s


def _ensure_sumo_home() -> None:
    """pip package eclipse-sumo does not set SUMO_HOME; the Windows installer does."""
    if os.environ.get("SUMO_HOME"):
        return
    try:
        import sumo  # type: ignore
        os.environ["SUMO_HOME"] = str(sumo.SUMO_HOME)
    except ImportError:
        pass


_LIBSUMO_STATUS: Optional[tuple[bool, str]] = None


def libsumo_status() -> tuple[bool, str]:
    """(usable, reason). On Windows the import is first tried in a SEPARATE Python process: a broken libsumo
    (e.g. 'DLL load failed while importing _libsumo', seen on the Windows PC on 13/10) must not partially load
    native DLLs nor change the environment (PROJ_LIB, DLL directories) of the application process at every run.
    The result is cached for the life of the process."""
    global _LIBSUMO_STATUS
    if _LIBSUMO_STATUS is not None:
        return _LIBSUMO_STATUS
    import importlib.util
    if importlib.util.find_spec("libsumo") is None:
        _LIBSUMO_STATUS = (False, "libsumo non installé")
    elif os.name == "nt":
        import subprocess
        try:
            r = subprocess.run([sys.executable, "-c", "import libsumo"], capture_output=True, text=True, timeout=120)
            msg = (r.stderr or r.stdout).strip().splitlines()
            _LIBSUMO_STATUS = (r.returncode == 0, "libsumo OK" if r.returncode == 0 else f"libsumo inutilisable : {msg[-1] if msg else r.returncode}")
        except Exception as exc:  # noqa: BLE001
            _LIBSUMO_STATUS = (False, f"libsumo inutilisable : {exc}")
    else:
        try:
            import libsumo  # type: ignore  # noqa: F401
            _LIBSUMO_STATUS = (True, "libsumo OK")
        except ImportError as exc:
            _LIBSUMO_STATUS = (False, f"libsumo inutilisable : {exc}")
    return _LIBSUMO_STATUS


_BINARY_OK: dict[bool, str] = {}


def sumo_binary_status(gui: bool) -> tuple[bool, str]:
    """Can sumo / sumo-gui start on this PC? Runs '<binary> --version' (exits at once, opens no window).
    A Windows loader failure (missing DLL...) shows here as an exit code. Only successes are cached, so a
    repaired installation is seen without restarting the application (2026-10-15)."""
    import subprocess
    from traci_layer.config import find_sumo_binary
    from traci_layer.launcher import describe_returncode
    if gui in _BINARY_OK:
        return True, _BINARY_OK[gui]
    b = find_sumo_binary(gui)
    name = "SUMO-GUI" if gui else "SUMO"
    try:
        r = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{name} ne peut pas démarrer ({b}) : {exc}"
    if r.returncode != 0:
        return False, f"{name} ne peut pas démarrer sur ce PC ({b}) : {describe_returncode(r.returncode)}"
    first = (r.stdout or r.stderr or "").strip().splitlines()
    _BINARY_OK[gui] = first[0] if first else b
    return True, _BINARY_OK[gui]


def choose_backend(gui: bool, use_libsumo: Optional[bool]) -> tuple[bool, str]:
    """libsumo (in-process) or TraCI (SUMO subprocess). Environment variable ITM_SUMO_BACKEND = auto | traci | libsumo."""
    if use_libsumo is not None:
        return bool(use_libsumo) and not gui, "imposé par l'appelant"
    wanted = os.environ.get("ITM_SUMO_BACKEND", "auto").strip().lower()
    if gui:
        return False, "SUMO-GUI : TraCI"
    if wanted == "traci":
        return False, "ITM_SUMO_BACKEND=traci"
    ok, reason = libsumo_status()
    if wanted == "libsumo" and not ok:
        raise RuntimeError(f"ITM_SUMO_BACKEND=libsumo mais {reason}")
    return ok, reason


@dataclass
class TLSInfo:
    """Static description of one signal, read from SUMO at start-up."""
    tls_id: str
    states: list[str]
    durations: list[float]
    in_lanes: list[str]
    out_lanes: list[str]
    green_phases: list[int] = field(default_factory=list)
    phase_links: dict[int, list[tuple[str, str]]] = field(default_factory=dict)

    @staticmethod
    def is_green(state: str) -> bool:
        return ("G" in state or "g" in state) and "y" not in state.lower()

    @classmethod
    def read(cls, api, tls_id: str) -> "TLSInfo":
        prog = api.trafficlight.getProgram(tls_id)
        logic = next(l for l in api.trafficlight.getAllProgramLogics(tls_id) if l.programID == prog)
        states = [p.state for p in logic.phases]
        durations = [float(p.duration) for p in logic.phases]
        links = api.trafficlight.getControlledLinks(tls_id)          # index -> [(in, out, via)]
        ins, outs = [], []
        for lk in links:
            for (i, o, _v) in lk:
                if i not in ins:
                    ins.append(i)
                if o not in outs:
                    outs.append(o)
        info = cls(tls_id, states, durations, ins, outs)
        for p, st in enumerate(states):
            if cls.is_green(st):
                info.green_phases.append(p)
                info.phase_links[p] = [(i, o) for idx, lk in enumerate(links) if st[idx] in "Gg" for (i, o, _v) in lk]
        return info


class SimEnv:
    """One SUMO run of the Kirchberg scenario."""

    def __init__(self, scale: float = 1.0, seed: int = 1, out_dir: Optional[Path] = None, gui: bool = False,
                 additional_files: Sequence[Path] = (), label: str = "kirchberg", end: float = END,
                 use_libsumo: Optional[bool] = None, gui_delay_ms: float = 0.0):
        _ensure_sumo_home()
        self.scale, self.seed, self.out_dir, self.end = scale, seed, out_dir, end
        extra = ["--scale", str(scale), "--duration-log.disable", "true", "--end", str(end)]
        if gui and gui_delay_ms:
            extra += ["--delay", str(gui_delay_ms)]      # slows sumo-gui down so a human can follow
        if out_dir is not None:
            extra += ["--tripinfo-output.write-unfinished", "true"]
        # in-process SUMO (same simulator, ~2x faster) when it really works and no GUI; otherwise TraCI
        use_libsumo, self.backend_reason = choose_backend(gui, use_libsumo)
        self.cfg = SumoConfig(sumocfg=SUMOCFG, gui=gui, seed=seed, output_dir=out_dir, emission_device=True,
                              additional_files=list(additional_files), extra_args=extra, label=label,
                              use_libsumo=use_libsumo)
        self.conn = SumoConnection(self.cfg)
        self.api = None
        self.tls: dict[str, TLSInfo] = {}

    def start(self):
        self.api = self.conn.start()
        try:
            self.tls = {t: TLSInfo.read(self.api, t) for t in TLS_IDS}
        except Exception:
            self.close()                 # never leave a SUMO process behind
            raise
        return self.api

    @property
    def time(self) -> float:
        return float(self.api.simulation.getTime())

    def step(self) -> float:
        self.api.simulationStep()
        return self.time

    def done(self) -> bool:
        return self.time >= self.end

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
