"""
Connection to SUMO through TraCI (or libsumo).

The rest of the layer never imports ``traci`` directly: it receives an ``api`` object
exposing the usual TraCI domains (``api.vehicle``, ``api.edge``, ``api.trafficlight``...).
That object is either

* a ``traci.connection.Connection`` (socket, works with sumo and sumo-gui), or
* the ``libsumo`` module (in-process, much faster, no GUI).

Both expose exactly the same functions, so collectors and agents are independent of
the transport and several simulations can run side by side (one label each).

Example
-------
>>> from traci_layer import SumoConfig, SumoConnection
>>> with SumoConnection(SumoConfig()) as api:
...     api.simulationStep()
...     print(api.vehicle.getIDCount())
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .config import SumoConfig

log = logging.getLogger(__name__)


class SumoConnection:
    """Start / stop a SUMO instance and expose its TraCI API object."""

    def __init__(self, config: Optional[SumoConfig] = None):
        self.config = config or SumoConfig()
        self.api: Any = None
        self.backend: Optional[str] = None  # "traci" | "libsumo"
        self.process = None                 # SUMO subprocess (TraCI backend only)
        self.process_log = None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> Any:
        """Launch SUMO and return the API object."""
        if self.api is not None:
            return self.api
        cmd = self.config.build_command()
        log.info("Starting SUMO: %s", " ".join(cmd))

        if self.config.use_libsumo and not self.config.gui:
            try:
                import libsumo  # type: ignore

                libsumo.start(cmd)
                self.api, self.backend = libsumo, "libsumo"
                return self.api
            except ImportError:
                log.warning("libsumo not available - falling back to TraCI sockets")

        # TraCI: robust launcher (2026-10-15) - SUMO output kept in <output_dir>/sumo_process.log, no silent
        # 60-fold relaunch, clear SumoStartError with SUMO's own message and exit code.
        from pathlib import Path

        from .launcher import start_traci

        log_file = Path(self.config.output_dir) / "sumo_process.log" if self.config.output_dir else None
        self.api, self.process = start_traci(cmd, self.config.label, process_log=log_file)
        self.process_log = log_file
        self.backend = "traci"
        return self.api

    def close(self) -> None:
        """Close the simulation (safe to call twice)."""
        if self.api is None:
            return
        try:
            if self.backend == "traci":
                self.api.close(wait=False)   # the process is awaited below, with a timeout (never hangs)
            else:
                self.api.close()
        except Exception as exc:  # SUMO may already be gone (window closed...)
            log.debug("Ignoring error on close: %s", exc)
        finally:
            self.api = None
            if self.process is not None:
                from .launcher import stop_process

                stop_process(self.process)    # waits up to 10 s, then kills: no orphan SUMO process
                self.process = None

    # ------------------------------------------------------------- context manager
    def __enter__(self) -> Any:
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return self.api is not None
