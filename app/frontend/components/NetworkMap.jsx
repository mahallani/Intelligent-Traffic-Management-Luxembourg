"use client";
// Traffic map of the simulated network (2026-11-03; previous version: NetworkMap.jsx.bak_20261103).
// Everything comes from the backend: lane geometry and stop lines from the SUMO network (GET /api/network), signal
// states, vehicle positions, alerts, simulated incident and ambulance from GET /api/sim/state. Nothing is decorative.
//   stop line of each approach = colour of the signal characters that control it (green / amber / red)
//   vehicles: filled cyan = moving, white = stopped
//   alert in progress: approach lane outlined in orange; simulated incident (while active): red dashed lane
import { useMemo } from "react";

const W = 1000;
const LAMP = { green: "#22A06B", amber: "#F59E0B", red: "#E5484D", off: "#5B6B80" };

function stopColour(state, links) {
  if (!state) return LAMP.off;
  const cs = links.map((i) => state[i]).filter(Boolean);
  if (cs.some((c) => c === "G" || c === "g")) return LAMP.green;
  if (cs.some((c) => c === "y" || c === "Y")) return LAMP.amber;
  if (cs.length) return LAMP.red;
  return LAMP.off;
}

const inWindow = (clock, inc) => !!inc && !!clock && clock >= inc.start && clock < inc.end;

export default function NetworkMap({ net, state, compact = false, title, subtitle, showLegend = true, height }) {
  const geo = useMemo(() => {
    if (!net) return null;
    const [x0, y0, x1, y1] = net.bbox;
    const s = W / (x1 - x0);
    const H = Math.round((y1 - y0) * s) + 60;
    const px = (x) => (x - x0) * s;
    const py = (y) => (y1 - y) * s + 30;
    const pts = (shape) => shape.map(([x, y]) => `${px(x).toFixed(1)},${py(y).toFixed(1)}`).join(" ");
    return { s, H, px, py, lanes: net.lanes.map((l) => ({ id: l.id, d: pts(l.shape), mid: l.shape[Math.floor(l.shape.length / 2)] })),
      stops: (net.stop_lines || []).map((t) => ({ ...t, d: pts(t.shape) })) };
  }, [net]);

  const signals = state?.signals || {};
  const vehicles = state?.vehicles || [];
  const alertLanes = new Set((state?.alerts || []).filter((a) => !a.end_clock).map((a) => a.lane));
  const inc = state?.incident;
  const incActive = inWindow(state?.clock, inc);
  const amb = state?.emergency_live?.status === "en circulation" ? state.emergency_live.pos : null;
  const laneW = geo ? Math.max(2.4, 3.2 * geo.s) : 3;

  return (
    <div className="map-card">
      {(title || state?.clock) && (
        <div className="map-top">
          {title && <div className="map-title">{title}{subtitle && <small>{subtitle}</small>}</div>}
          {state && state.status !== "idle" && state.clock && (
            <div className="map-clock">{state.clock}<small>heure simulée</small></div>)}
        </div>)}
      {!geo ? (
        <div style={{ aspectRatio: "2.4", position: "relative" }}><div className="map-empty">Chargement de la carte…</div></div>
      ) : (
        <svg className="map-svg" viewBox={`0 0 ${W} ${geo.H}`} style={height ? { maxHeight: height } : undefined} role="img"
          aria-label={`Carte du réseau : 4 carrefours, ${vehicles.length} véhicules affichés, ${alertLanes.size} alerte(s) en cours`}>
          <defs>
            <pattern id="map-grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M40 0H0V40" fill="none" stroke="#14243A" strokeWidth="1" />
            </pattern>
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4" /></filter>
          </defs>
          <rect width={W} height={geo.H} fill="url(#map-grid)" />
          <g fill="none" strokeLinecap="round" strokeLinejoin="round">
            {geo.lanes.map((l) => <polyline key={`c${l.id}`} points={l.d} stroke="#0A1422" strokeWidth={laneW + 3} />)}
            {geo.lanes.map((l) => <polyline key={l.id} points={l.d} stroke="#2B3F5C" strokeWidth={laneW} />)}
            {geo.lanes.filter((l) => alertLanes.has(l.id)).map((l) => (
              <polyline key={`a${l.id}`} points={l.d} stroke="#F59E0B" strokeWidth={laneW + 6} strokeOpacity=".55" filter="url(#glow)" />))}
            {incActive && geo.lanes.filter((l) => l.id === inc.lane).map((l) => (
              <polyline key={`i${l.id}`} points={l.d} stroke="#E5484D" strokeWidth={laneW + 1} strokeDasharray="7 6" />))}
            {geo.stops.map((t) => (
              <polyline key={`s${t.lane}`} points={t.d} stroke={stopColour(signals[t.tls]?.state, t.links)} strokeWidth={laneW + 1.5} />))}
          </g>
          {!compact && vehicles.map(([x, y, stopped], i) => (
            <circle key={i} cx={geo.px(x)} cy={geo.py(y)} r={3.4} fill={stopped ? "#F3F6FA" : "#26B6D4"}
              stroke={stopped ? "#0A1422" : "#0E5F70"} strokeWidth={1} />))}
          {compact && vehicles.map(([x, y, stopped], i) => (
            <circle key={i} cx={geo.px(x)} cy={geo.py(y)} r={3} fill={stopped ? "#F3F6FA" : "#26B6D4"} />))}
          {incActive && (() => {
            const l = net.lanes.find((ln) => ln.id === inc.lane);
            if (!l) return null;
            const [x, y] = l.shape[Math.floor(l.shape.length / 2)];
            return (
              <g transform={`translate(${geo.px(x)},${geo.py(y) - 22})`}>
                <title>{`Incident simulé : ${inc.label}`}</title>
                <path d="M0 -13 L13 10 H-13 Z" fill="#E5484D" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
                <path d="M0 -4 V3 M0 6.5 V6.6" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
              </g>);
          })()}
          {amb && (
            <g transform={`translate(${geo.px(amb[0])},${geo.py(amb[1])})`}>
              <title>Ambulance</title>
              <circle className="amb-ring" r={16} fill="none" stroke="#C218C2" strokeWidth={3} />
              <circle r={7} fill="#C218C2" stroke="#fff" strokeWidth={2} />
            </g>)}
          {net.signals.map((t, i) => {
            const st = signals[t.id];
            const halting = st?.halting;
            const x = geo.px(t.x), y = geo.py(t.y);
            return (
              <g key={t.id} transform={`translate(${x},${y})`}>
                <title>{`${t.label}${halting !== undefined ? ` · ${halting} véhicule(s) arrêté(s)` : ""}`}</title>
                <circle r={15} fill="#101D2E" stroke="#2478E5" strokeWidth={2.5} />
                <text y={5} textAnchor="middle" fontSize="14" fontWeight="700" fill="#fff">{i + 1}</text>
                {!compact && (
                  <g transform="translate(0,-28)">
                    <rect x={-48} y={-14} width={96} height={22} rx={6} fill="rgba(16,29,46,.88)" stroke="rgba(255,255,255,.12)" />
                    <text y={1.5} textAnchor="middle" fontSize="12.5" fontWeight="600" fill="#DCE6F2">{t.label}</text>
                  </g>)}
              </g>);
          })}
        </svg>
      )}
      {showLegend && (
        <div className="map-legend">
          <span><i className="lg-bar" style={{ background: LAMP.green }} />Feu vert</span>
          <span><i className="lg-bar" style={{ background: LAMP.amber }} />Orange</span>
          <span><i className="lg-bar" style={{ background: LAMP.red }} />Rouge</span>
          <span><i className="lg" style={{ background: "#26B6D4" }} />Véhicule en mouvement</span>
          <span><i className="lg" style={{ background: "#F3F6FA" }} />Véhicule arrêté</span>
          <span><i className="lg-bar" style={{ background: "#F59E0B", opacity: .7 }} />Alerte en cours</span>
          {inc && <span><i className="lg-bar" style={{ background: "#E5484D" }} />Incident simulé</span>}
          {state?.ambulance && <span><i className="lg" style={{ background: "#C218C2" }} />Ambulance</span>}
        </div>)}
    </div>
  );
}
