"""
Environmental data (BO5).

What TraCI provides directly (no extra SUMO configuration needed)
-----------------------------------------------------------------
Per vehicle, rate of the LAST step, in **mg/s**:
``vehicle.getCO2Emission``, ``getCOEmission``, ``getHCEmission``, ``getPMxEmission``,
``getNOxEmission``, ``getFuelConsumption`` (mass, mg/s), plus ``getNoiseEmission`` (dBA)
and ``getElectricityConsumption`` (Wh/s, only for electric vehicles - none in LuST).
The same getters exist per edge / lane (sum over the vehicles on it).

Which model is used in LuST?
----------------------------
LuST's ``vtypes.add.xml`` does not set ``emissionClass``. SUMO 1.27.1 then applies its
defaults (verified with ``vehicle.getEmissionClass``):

* passenger cars -> ``HBEFA4/PC_petrol_Euro-4``
* buses          -> ``HBEFA4/UBus_Std_gt15-18t_Euro-VI_A-C``

So emissions are available "out of the box", but every car is a Euro-4 petrol car.
A realistic Luxembourg fleet mix (diesel share, Euro-6, EV...) would need an
``emissionClass`` per vType -> "Cette métrique nécessite une configuration SUMO
supplémentaire" (only if absolute values matter; for comparing S0..S4 the default
is consistent across scenarios).

Derived values (calculated here)
--------------------------------
* network instantaneous rate = sum over running vehicles (g/s)
* cumulated mass = sum(rate * dt) (g / kg)
* intensity = cumulated CO2 / vehicle-km travelled (g/km)
* fuel volume = mass / density (indicative only, petrol density assumed)
"""
from __future__ import annotations

from collections import defaultdict

from . import metrics as m
from .vehicle_data import POLLUTANTS


class EnvironmentAccumulator:
    """Integrates network emissions step by step."""

    def __init__(self) -> None:
        self.rate_mg_s: dict[str, float] = {p: 0.0 for p in POLLUTANTS}
        self.cumulated_mg: dict[str, float] = {p: 0.0 for p in POLLUTANTS}
        self.cumulated_by_class_mg: dict[str, dict[str, float]] = defaultdict(lambda: {p: 0.0 for p in POLLUTANTS})

    def update(self, rate_by_class: dict[str, list[float]], dt: float) -> None:
        """``rate_by_class[vclass]`` = summed rates (mg/s) in POLLUTANTS order (from VehicleTracker)."""
        rate = {p: 0.0 for p in POLLUTANTS}
        for vclass, values in rate_by_class.items():
            cls = self.cumulated_by_class_mg[vclass]
            for p, r in zip(POLLUTANTS, values):
                rate[p] += r
                cls[p] += r * dt
        for p in POLLUTANTS:
            self.cumulated_mg[p] += rate[p] * dt
        self.rate_mg_s = rate

    def summary(self, vehicle_km: float) -> dict:
        r, c = self.rate_mg_s, self.cumulated_mg
        fuel_kg = c["fuel"] * m.MG_TO_KG
        return {
            # instantaneous network rates
            "co2_g_per_s": r["co2"] * m.MG_TO_G,
            "nox_g_per_s": r["nox"] * m.MG_TO_G,
            "fuel_g_per_s": r["fuel"] * m.MG_TO_G,
            "co_g_per_s": r["co"] * m.MG_TO_G,
            "hc_g_per_s": r["hc"] * m.MG_TO_G,
            "pmx_g_per_s": r["pmx"] * m.MG_TO_G,
            # cumulated since collector start
            "co2_total_kg": c["co2"] * m.MG_TO_KG,
            "nox_total_g": c["nox"] * m.MG_TO_G,
            "fuel_total_kg": fuel_kg,
            "fuel_total_l_indicative": fuel_kg / m.PETROL_DENSITY_KG_PER_L,
            "co_total_g": c["co"] * m.MG_TO_G,
            "hc_total_g": c["hc"] * m.MG_TO_G,
            "pmx_total_g": c["pmx"] * m.MG_TO_G,
            "co2_g_per_km": (c["co2"] * m.MG_TO_G / vehicle_km) if vehicle_km > 0 else None,
            "by_class_total": {
                vc: {"co2_kg": d["co2"] * m.MG_TO_KG, "nox_g": d["nox"] * m.MG_TO_G, "fuel_kg": d["fuel"] * m.MG_TO_KG}
                for vc, d in sorted(self.cumulated_by_class_mg.items())
            },
        }
