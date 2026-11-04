"""Ambulance tracking (2026-10-22) - OBSERVATION + DRAWING ONLY.

Follows the simulated vehicle 'ambulance' (inserted by agents/orchestrator.py when emergency_at is set):
status (waiting for insertion / running / arrived), next signal of the 4 (Carrefour 1..4) with distance and
signal state, position, and time-stamped events (departure, approach of each signal, priority request/serve/release
read from the EmergencyPriorityAgent log, signal passed, arrival).

What it may CHANGE, all purely visual (no effect on vehicle dynamics, signals or outputs):
  - vehicle colour (vehicle.setColor) - applied in every run, GUI or not, so GUI and non-GUI runs stay identical;
  - in sumo-gui only: ONE ring that follows the vehicle (vehicle.highlight, created once) whose colour alternates
    magenta / blue every `blink_s` seconds (polygon.setColor) like a beacon, and camera tracking + zoom while the
    vehicle is in the network (gui.trackVehicle / gui.setZoom); afterwards the ring is removed and the original zoom
    and offset are restored.
Note (checked with sumo-gui 1.27.1): the 'emergency' shape is drawn with SUMO's own ambulance livery (white/green,
blue light) when zoomed in, so the vehicle colour mainly shows in simplified drawing; the ring is what makes it easy
to spot.
GUI commands that fail are recorded in `gui_errors` and never stop the simulation.
It never calls a trafficlight setter and never changes speed, lane, route or type."""
from __future__ import annotations

TLS_LABELS = {"-28692": "Carrefour 1", "-23354": "Carrefour 2", "-20484": "Carrefour 3", "-29958": "Carrefour 4"}
COLOR = (255, 0, 255, 255)           # fluorescent magenta: no LuST vehicle type uses it
BEACON = (0, 90, 255, 255)           # blue phase of the ring (sumo-gui only)
SIGNAL_WORD = {"G": "vert", "g": "vert (cédez)", "y": "jaune", "Y": "jaune", "r": "rouge", "R": "rouge",
               "u": "rouge-jaune", "o": "éteint", "O": "éteint", "s": "stop"}
PRIORITY_WORD = {"request": "demande de priorité", "serve": "vert accordé à l'ambulance", "release": "fin de la priorité"}


def hms(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


class AmbulanceTracker:
    def __init__(self, env, veh_id: str = "ambulance", gui: bool = False, priority_agent=None,
                 approach_m: float = 150.0, zoom: float = 800.0, blink_s: float = 1.0, ring_m: float = 25.0):
        self.env, self.vid, self.gui, self.prio = env, veh_id, bool(gui), priority_agent
        self.approach_m, self.zoom, self.blink_s, self.ring_m = approach_m, zoom, blink_s, ring_m
        self._ring = None
        self._ring_on = False
        self.status = "absente"            # absente -> en attente d'insertion -> en circulation -> arrivée
        self.requested_at = self.depart = self.arrival = None
        self.next = None                   # {"tls", "label", "dist_m", "signal"}
        self.pos = self.edge = self.speed_kmh = None
        self.events: list[dict] = []
        self.gui_errors: list[str] = []
        self._approached: set[str] = set()
        self._last_tls = None
        self._prio_seen = 0
        self._view = None
        self._saved_view = None
        self._last_blink = None

    # ---------------------------------------------------------------- helpers
    def _event(self, t: float, kind: str, tls=None, detail: str = ""):
        self.events.append({"time_s": float(t), "clock": hms(t), "event": kind, "tls": tls or "",
                            "carrefour": TLS_LABELS.get(tls, "") if tls else "", "detail": detail})

    def _gui(self, what: str, fn):
        if not self.gui:
            return None
        try:
            return fn(self.env.api)
        except Exception as e:     # drawing only: never stop the simulation for it
            self.gui_errors.append(f"{what}: {type(e).__name__}: {e}")
            return None

    # ---------------------------------------------------------------- lifecycle
    def inserted(self, t: float):
        """Call right after vehicle.add(...)."""
        self.requested_at, self.status = float(t), "en attente d'insertion"
        try:
            self.env.api.vehicle.setColor(self.vid, COLOR)       # visual only
        except Exception as e:
            self.gui_errors.append(f"setColor: {type(e).__name__}: {e}")
        self._event(t, "insertion demandée", None, "ambulance ajoutée en début d'avenue (--31070#8)")

    def _start_view(self):
        def go(api):
            views = list(api.gui.getIDList())
            self._view = views[0] if views else "View #0"
            self._saved_view = (api.gui.getZoom(self._view), api.gui.getOffset(self._view))
            api.gui.trackVehicle(self._view, self.vid)
            api.gui.setZoom(self._view, self.zoom)
        self._gui("suivi caméra", go)

        def ring(api):
            before = set(api.polygon.getIDList())
            api.vehicle.highlight(self.vid, COLOR, self.ring_m)      # permanent ring following the vehicle
            self._ring = next(iter(set(api.polygon.getIDList()) - before), None)
        self._gui("anneau", ring)

    def _stop_view(self):
        def back(api):
            if self._view is None:
                return
            if self._ring is not None and self._ring in api.polygon.getIDList():
                api.polygon.remove(self._ring)
            api.gui.trackVehicle(self._view, "")
            if self._saved_view:
                api.gui.setZoom(self._view, self._saved_view[0])
                api.gui.setOffset(self._view, *self._saved_view[1])
        self._gui("fin du suivi caméra", back)

    def step(self, obs):
        api, t = self.env.api, obs.time
        if self.status == "en attente d'insertion":
            if self.vid not in api.simulation.getDepartedIDList():
                return
            # SUMO time after a step = end of the step; the vehicle left at its departure time (tripinfo 'depart')
            self.status, self.depart = "en circulation", float(api.vehicle.getDeparture(self.vid))
            self._event(self.depart, "départ", None, f"entrée dans le réseau sur {api.vehicle.getLaneID(self.vid)}")
            self._start_view()
        if self.status != "en circulation":
            return
        if self.vid in api.simulation.getArrivedIDList():
            self._priority_events()
            self._last_tls = None
            self.status, self.arrival = "arrivée", float(t) - float(api.simulation.getDeltaT())   # = tripinfo 'arrival'
            self.next = None
            self._event(self.arrival, "sortie du réseau", None, f"trajet {self.arrival - self.depart:.0f} s depuis le départ")
            self._stop_view()
            return
        x, y = api.vehicle.getPosition(self.vid)
        self.pos = [round(x, 1), round(y, 1)]
        self.edge = api.vehicle.getRoadID(self.vid)
        self.speed_kmh = round(3.6 * api.vehicle.getSpeed(self.vid), 1)
        nxt = next(((tls, dist, state) for tls, _i, dist, state in api.vehicle.getNextTLS(self.vid) if tls in TLS_LABELS), None)
        tls_now = nxt[0] if nxt else None
        if self._last_tls is not None and tls_now != self._last_tls:
            self._event(t, "carrefour franchi", self._last_tls)
        self._last_tls = tls_now
        if nxt:
            tls, dist, state = nxt
            self.next = {"tls": tls, "label": TLS_LABELS[tls], "dist_m": round(dist), "signal": SIGNAL_WORD.get(state, state)}
            if dist <= self.approach_m and tls not in self._approached:
                self._approached.add(tls)
                self._event(t, "approche", tls, f"{dist:.0f} m, feu {SIGNAL_WORD.get(state, state)} pour l'ambulance")
        else:
            self.next = None
        self._priority_events()
        if self.gui and self._ring is not None and (self._last_blink is None or t - self._last_blink >= self.blink_s):
            self._last_blink, self._ring_on = t, not self._ring_on
            self._gui("gyrophare", lambda a: a.polygon.setColor(self._ring, BEACON if self._ring_on else COLOR))

    def _priority_events(self):
        log = getattr(self.prio, "log", None) if self.prio is not None else None
        if not log:
            return
        for e in log[self._prio_seen:]:
            if e.get("vehicle") != self.vid:
                continue
            a = e.get("action")
            detail = (f"phase {e.get('from_phase')} → phase cible {e.get('target_phase')}" if a in ("request", "serve")
                      else f"vert tenu {e.get('held_s')} s" if a == "release" else "")
            self._event(e["time"], PRIORITY_WORD.get(a, a), e.get("tls"), detail)
        self._prio_seen = len(log)

    def finish(self, t: float):
        """End of run (or stop): close the camera tracking if the vehicle is still in the network."""
        if self.status == "en circulation":
            self._stop_view()

    def as_state(self) -> dict:
        return {"status": self.status, "requested_at": hms(self.requested_at) if self.requested_at is not None else None,
                "depart": hms(self.depart) if self.depart is not None else None,
                "arrival": hms(self.arrival) if self.arrival is not None else None,
                "travel_s": round(self.arrival - self.depart) if self.arrival is not None else None,
                "next": self.next, "pos": self.pos, "edge": self.edge, "speed_kmh": self.speed_kmh,
                "events": list(reversed(self.events[-30:])), "gui": self.gui, "gui_errors": self.gui_errors[-5:]}
