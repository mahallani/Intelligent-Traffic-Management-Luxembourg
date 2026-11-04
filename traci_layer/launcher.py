"""Robust launch of a SUMO process for TraCI (used instead of ``traci.start``) - added 2026-10-15.

Why: ``traci.start`` relaunches SUMO on a new port up to 60 times when the process dies at start-up
("Could not connect to TraCI server using port ... (TraCI server already finished). Retrying with
different port."), never shows SUMO's own error message (it only goes to the console) and finally
raises ``FatalTraCIError: Could not connect`` - about 60-80 s later, with an empty run folder.

Here:
* SUMO's stdout + stderr are written to a file (``<run>/sumo_process.log``) with the exact command line,
  so the initial error is kept even when the console is closed;
* a process that dies at start-up is NOT relaunched, except when its output shows a port conflict
  (at most ``max_launches`` launches in total);
* the error raised (:class:`SumoStartError`) contains the exit code (decoded for the usual Windows
  status codes: missing DLL, wrong DLL version, crash...) and the last lines written by SUMO;
* a SUMO that is still alive but never accepts the connection is killed (no orphan process).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

#: Windows NTSTATUS codes seen when an executable cannot start (exit code of the process).
WINDOWS_STATUS = {
    0xC0000135: ("STATUS_DLL_NOT_FOUND - une DLL nécessaire à SUMO est introuvable ; cas constaté le 15/10 : "
                 "sumo-gui.exe -> gdal.dll -> VCOMP140.DLL, à installer avec Microsoft Visual C++ Redistributable x64"),
    0xC0000139: "STATUS_ENTRYPOINT_NOT_FOUND - une DLL chargée n'a pas la bonne version (mélange de DLL SUMO)",
    0xC000007B: "STATUS_INVALID_IMAGE_FORMAT - DLL 32/64 bits incompatible",
    0xC0000142: "STATUS_DLL_INIT_FAILED - échec d'initialisation d'une DLL",
    0xC0000005: "STATUS_ACCESS_VIOLATION - plantage de SUMO",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN - arrêt critique de SUMO",
    0xC000013A: "STATUS_CONTROL_C_EXIT - SUMO interrompu (Ctrl+C / fermeture)",
}
PORT_ERROR_MARKERS = ("address already in use", "only one usage of each socket address", "unable to create listening socket",
                      "adresse de socket", "une seule utilisation")


class SumoStartError(RuntimeError):
    """SUMO could not be started or did not accept the TraCI connection."""

    def __init__(self, message: str, returncode: Optional[int] = None, output_tail: str = "",
                 command: Optional[Sequence[str]] = None, launches: int = 0, process_log: Optional[Path] = None):
        super().__init__(message)
        self.returncode, self.output_tail, self.command = returncode, output_tail, list(command or [])
        self.launches, self.process_log = launches, process_log

    def as_dict(self) -> dict:
        return {"error": str(self), "returncode": self.returncode, "returncode_meaning": describe_returncode(self.returncode),
                "launches": self.launches, "command": self.command, "sumo_output_tail": self.output_tail,
                "process_log": str(self.process_log) if self.process_log else None}


def describe_returncode(rc: Optional[int]) -> str:
    if rc is None:
        return "processus encore actif"
    u = rc & 0xFFFFFFFF
    if u in WINDOWS_STATUS:
        return f"code {rc} (0x{u:08X} : {WINDOWS_STATUS[u]})"
    if rc < 0:
        return f"arrêté par le signal {-rc}"
    if rc == 1:
        return "code 1 (erreur signalée par SUMO : voir ses messages ci-dessous)"
    return f"code {rc}"


def _tail(path: Path, n: int = 30) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def start_traci(cmd: Sequence[str], label: str, process_log: Optional[Path] = None, max_launches: int = 2,
                connect_retries: int = 60):
    """Start SUMO with ``cmd`` (+ ``--remote-port``) and return ``(connection, process)``.

    Raises :class:`SumoStartError` with SUMO's own messages when it cannot start.
    """
    import traci

    if traci.main.connection.has(label):
        raise SumoStartError(f"Une connexion TraCI nommée '{label}' est déjà active.")
    if process_log is None:
        fd, name = tempfile.mkstemp(prefix="sumo_process_", suffix=".log")
        os.close(fd)
        process_log = Path(name)
    process_log = Path(process_log)
    process_log.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for launch in range(1, max_launches + 1):
        port = traci.getFreeSocketPort()
        full = [str(c) for c in cmd] + ["--remote-port", str(port)]
        with open(process_log, "ab") as fh:
            fh.write((f"\n===== {datetime.now().isoformat(timespec='seconds')} launch {launch}/{max_launches} port {port}\n"
                      f"command: {subprocess.list2cmdline(full)}\n").encode("utf-8"))
            fh.flush()
            proc = subprocess.Popen(full, stdout=fh, stderr=subprocess.STDOUT)
        try:
            traci.init(port, numRetries=connect_retries, host="localhost", label=label, proc=proc, doSwitch=False)
            conn = traci.getConnection(label)
            with open(process_log, "ab") as fh:
                fh.write(f"connected on port {port}\n".encode("utf-8"))
            return conn, proc
        except Exception as exc:  # noqa: BLE001
            # Matched by NAME: once libsumo is imported it replaces traci.exceptions.TraCIException by its own
            # class while traci.main keeps raising the original one, and on Windows a second 'traci' copy
            # (SUMO_HOME/tools) can coexist with the pip one - an isinstance test would miss the error.
            if not (isinstance(exc, OSError) or type(exc).__name__ in ("TraCIException", "FatalTraCIError")):
                raise
            still_running = proc.poll() is None
            if still_running:                      # alive but never accepted the connection: no orphan
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            rc = proc.returncode
            tail = _tail(process_log)
            with open(process_log, "ab") as fh:
                fh.write(f"SUMO exit: {describe_returncode(rc)}; TraCI: {type(exc).__name__}: {exc}\n".encode("utf-8"))
            reason = ("SUMO ne répond pas sur le port TraCI (processus arrêté de force)" if still_running
                      else f"SUMO s'est arrêté au démarrage, {describe_returncode(rc)}")
            last_error = SumoStartError(
                f"{reason}. Dernières lignes de SUMO : {tail.splitlines()[-1] if tail.strip() else '(aucune sortie)'} "
                f"- journal complet : {process_log}", rc, tail, full, launch, process_log)
            if any(m in tail.lower() for m in PORT_ERROR_MARKERS) and launch < max_launches:
                continue                           # port conflict only: one new port
            raise last_error from exc
    raise last_error  # pragma: no cover


def stop_process(proc, timeout: float = 10.0) -> Optional[int]:
    """Wait for a SUMO process to end; kill it if it does not. Returns its exit code."""
    if proc is None:
        return None
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            return proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return None
