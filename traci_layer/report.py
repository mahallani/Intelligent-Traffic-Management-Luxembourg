"""Human-readable console report of an observation / of scenario KPIs."""
from __future__ import annotations



LINE = "=" * 56


def _f(value, fmt: str = ".1f", unit: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        return f"{value:{fmt}}{(' ' + unit) if unit else ''}"
    except (TypeError, ValueError):
        return str(value)


def format_observation(obs: dict) -> str:
    meta, sim, veh = obs["meta"], obs["simulation"], obs["vehicles"]
    con, env, travel = obs.get("congestion", {}), obs["environment"], obs["travel"]
    out = [LINE, "LUXEMBOURG TRAFFIC OBSERVATION  (LuST / SUMO)", LINE,
           f"Scenario: {meta['scenario']}   Run: {meta['run_id']}",
           f"Simulation time: {meta['timestamp']:.0f} s  ({meta['clock']})", ""]
    out += ["Vehicles:",
            f"  Count:                 {veh['count']}  (pending insertion: {sim['pending_vehicles']})",
            f"  Average speed:         {_f(veh['average_speed_kmh'], unit='km/h')}",
            f"  Average waiting time:  {_f(veh['average_waiting_time_s'], unit='s')}",
            f"  Average time loss:     {_f(veh['average_time_loss_s'], unit='s')}",
            f"  Departed / arrived:    {sim['departed_total']} / {sim['arrived_total']}  (teleports: {sim['teleports_total']})",
            ""]
    out += ["Congestion:",
            f"  Occupancy (occupied edges): {_f(con.get('average_occupancy_pct'), unit='%')}",
            f"  Halting vehicles:      {con.get('halting_vehicles', 'n/a')}",
            f"  Queue length:          {_f(con.get('queue_length_m'), '.0f', 'm')}  [{con.get('queue_method', '-')}]",
            f"  Longest queue:         {_f(con.get('max_queue_length_m'), '.0f', 'm')}",
            f"  Congestion index:      {_f(con.get('network_congestion_index'), '.2f')}  ({con.get('level', 'n/a')})",
            f"  Congested edges:       {con.get('congested_edges', 'n/a')}"]
    edges = con.get("edges") or {}
    if edges.get("top_bottlenecks"):
        b = edges["top_bottlenecks"][0]
        out.append(f"  Worst bottleneck:      edge {b['edge_id']} {('(' + b['street_name'] + ')') if b.get('street_name') else ''}"
                   f" - {b['halting_number']} halting, {_f(b['mean_speed_kmh'], unit='km/h')}")
    out.append("")
    tr = travel["since_last_observation"]
    out += ["Travel:",
            f"  Trips completed (interval): {tr['completed_trips']}",
            f"  Average travel time:   {_f(tr['average_travel_time_s'], unit='s')}",
            f"  Vehicle-km travelled:  {_f(travel['vehicle_km_travelled'], '.0f', 'km')}", ""]
    out += ["Environment (since start of observation):",
            f"  CO2:   {_f(env['co2_total_kg'], '.1f', 'kg')}   ({_f(env['co2_g_per_s'], '.0f', 'g/s')} now)",
            f"  NOx:   {_f(env['nox_total_g'], '.1f', 'g')}",
            f"  Fuel:  {_f(env['fuel_total_kg'], '.1f', 'kg')}  (~{_f(env['fuel_total_l_indicative'], '.0f', 'L')})",
            f"  PMx:   {_f(env['pmx_total_g'], '.2f', 'g')}", ""]
    bus = obs.get("buses")
    if bus is not None:
        out += ["Buses:",
                f"  Count:                 {bus['count']}  ({bus['lines_active']} lines, {bus['at_stop_now']} at a stop)",
                f"  Average speed:         {_f(bus['average_speed_kmh'], unit='km/h')}",
                f"  Average delay (time loss): {_f(bus['average_delay_s'], unit='s')}",
                f"  Average dwell time:    {_f(bus['average_dwell_time_s'], unit='s')}",
                f"  Bunching events:       {bus['bunching_events_total']}", ""]
    em = obs.get("emergency")
    if em is not None:
        out += ["Emergency vehicles:",
                f"  Active / completed:    {em['active']} / {em['completed']}"]
        for v in em["vehicles"]:
            out.append(f"  {v['emergency_vehicle_id']}: {_f(v['speed_kmh'], unit='km/h')} on {v['edge_id']}, "
                       f"progress {_f((v['progress'] or 0) * 100, '.0f', '%')}, next TLS {v['next_tls_id']} ({v['next_tls_state']})")
        for r in em["completed_missions"]:
            out.append(f"  {r['vehicle_id']}: travel {_f(r['travel_time_s'], '.0f', 's')}, "
                       f"free-flow {_f(r['free_flow_time_s'], '.0f', 's')}, delay {_f(r['delay_s'], '.0f', 's')}")
        out.append("")
    tls = obs.get("traffic_lights")
    if tls is not None:
        out += ["Traffic Lights:",
                f"  Active signals:        {tls['active_signals']} / {tls['total_signals']}",
                f"  Programs in use:       {tls['programs_in_use']}",
                f"  Signals with a queue:  {tls['signals_with_queue']}"]
        if tls["most_loaded_signals"]:
            s = tls["most_loaded_signals"][0]
            out.append(f"  Most loaded:           {s['tls_id']} - {s['queued_vehicles']} veh, {_f(s['queue_length_m'], '.0f', 'm')}")
    out.append(LINE)
    return "\n".join(out)


def format_kpis(k) -> str:
    d = k.to_dict() if hasattr(k, "to_dict") else k
    rows = [LINE, f"SCENARIO KPIs - {d['scenario']} (run {d['run_id']})",
            f"Window: {d['start_time']:.0f} s -> {d['end_time']:.0f} s ({d['duration_s']:.0f} s)", LINE]
    groups = {
        "BO1 Waiting": ["total_waiting_time_s", "average_waiting_time_per_vehicle_s", "average_halting_vehicles"],
        "BO2 Congestion": ["network_mean_speed_kmh", "average_congestion_index", "average_congested_edges",
                           "average_total_queue_length_m", "max_lane_queue_length_m", "teleports",
                           "pending_vehicles_end"],
        "BO3 Travel": ["vehicles_observed", "completed_trips", "completed_trips_observed_from_departure",
                       "average_travel_time_s", "average_time_loss_s", "total_time_loss_in_window_s",
                       "vehicle_hours_travelled", "vehicle_km_travelled"],
        "BO4 Emergency": ["emergency_missions", "emergency_completed", "emergency_average_travel_time_s",
                          "emergency_average_delay_s"],
        "BO5 Environment": ["co2_kg", "nox_g", "fuel_kg", "pmx_g", "co2_g_per_km"],
        "Public transport": ["bus_trips_observed", "bus_average_delay_s", "bus_average_dwell_s",
                             "bus_bunching_events", "bus_headway_cv"],
    }
    for g, keys in groups.items():
        rows.append(g)
        for key in keys:
            v = d.get(key)
            rows.append(f"  {key:38s} {_f(v, '.2f') if isinstance(v, float) else v}")
    rows.append(LINE)
    return "\n".join(rows)
