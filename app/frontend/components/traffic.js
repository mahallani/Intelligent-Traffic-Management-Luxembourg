// Labels and small derivations shared by the pages (2026-11-03). Nothing here invents data: every function only
// renames or classifies a value received from the backend, with the rule written next to it.

export const STATUS = {
  idle: { label: "Aucune simulation", tone: "neutral" },
  starting: { label: "Démarrage…", tone: "info" },
  running: { label: "Simulation en cours", tone: "ok" },
  paused: { label: "En pause", tone: "warn" },
  stopping: { label: "Arrêt en cours…", tone: "warn" },
  finished: { label: "Simulation terminée", tone: "info" },
  stopped: { label: "Simulation arrêtée", tone: "neutral" },
  error: { label: "Erreur de simulation", tone: "bad" },
};
export const ACTIVE = ["starting", "running", "paused", "stopping"];

// Client-facing names of the signal-control strategies (the technical codes stay visible to administrators).
export const STRATEGIES = {
  S0_fixed_time: { name: "Plan de feux fixe", short: "Plan fixe", desc: "Programme de feux d'origine, aux durées fixes. Sert de référence." },
  S1_actuated: { name: "Feux adaptatifs standards", short: "Adaptatif", desc: "Le vert est prolongé tant que des véhicules sont détectés." },
  S2_demand_gap: { name: "Agent à règles (demande)", short: "Règles", desc: "Termine le vert quand les voies servies se vident et qu'une autre direction attend." },
  S2F_forecast_gap: { name: "Agent à règles + prévision", short: "Règles + prévision", desc: "Même principe, en tenant compte de la prévision de trafic à 5 minutes." },
  S2b_max_pressure: { name: "Agent max-pressure", short: "Max-pressure", desc: "Donne le vert à la direction où la pression de trafic est la plus forte." },
  S3_rl_qlearning: { name: "Agent IA (apprentissage par renforcement)", short: "Agent IA", desc: "Agent qui a appris quand terminer chaque vert. Ses décisions sont explicables (page IA explicable)." },
};
export const strategyName = (id) => STRATEGIES[id]?.name || id || "–";
export const strategyShort = (id) => STRATEGIES[id]?.short || id || "–";

export const DEMAND = { 1: "Normal", 2: "Soutenu", 3: "Dense", 4: "Très dense", 5: "Congestion", 6: "Saturation" };

// Alerts raised by the detection agent: type and a FIXED severity per type (not measured; shown as such in the UI).
export const ALERT_TYPES = {
  blocked: { label: "Voie bloquée", severity: "high", rule: "vert ≥ 20 s sur 90 s, ≥ 3 véhicules arrêtés à chaque relevé, aucun passage" },
  stalled: { label: "Véhicule immobilisé", severity: "medium", rule: "un véhicule arrêté depuis au moins 150 s" },
  congestion: { label: "Congestion", severity: "low", rule: "au moins 8 véhicules arrêtés pendant au moins 60 s" },
};
export const SEVERITY = { high: { label: "Élevée", tone: "bad" }, medium: { label: "Moyenne", tone: "warn" }, low: { label: "Modérée", tone: "info" } };
export const alertType = (rule) => ALERT_TYPES[rule] || { label: rule, severity: "low", rule: "" };

// Congestion level of a junction from its stopped vehicles. The upper threshold is the one of the detection agent
// (congestion = 8 stopped vehicles); "dense" from 3 vehicles.
export function congestion(halting) {
  if (halting === null || halting === undefined) return { label: "–", tone: "neutral", level: -1 };
  if (halting >= 8) return { label: "Saturé", tone: "bad", level: 2 };
  if (halting >= 3) return { label: "Dense", tone: "warn", level: 1 };
  return { label: "Fluide", tone: "ok", level: 0 };
}

// Signal state string (one character per controlled movement, SUMO convention).
export const lampOf = (c) => (c === "G" || c === "g" ? "green" : c === "y" || c === "Y" ? "amber" : c === "r" || c === "R" || c === "u" ? "red" : "off");
export function signalSummary(state = "") {
  const n = { green: 0, amber: 0, red: 0 };
  for (const c of state) { const l = lampOf(c); if (n[l] !== undefined) n[l] += 1; }
  return n;
}

export const hhmm = (sec) => {
  const s = Math.round(sec || 0);
  return `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
};

export function duration(sec) {
  if (sec === null || sec === undefined || Number.isNaN(sec)) return "–";
  const s = Math.round(sec);
  if (s < 60) return `${s} s`;
  return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
}

// Run folder names written by the backend: 20261022_141518_S3_rl_qlearning_x1_seed1[_incident_x][_ambulance[_prio]]
const RUN_RE = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_(S\w+?)_x([\d.]+)_seed(\d+)(.*)$/;
export function parseRun(name = "") {
  const base = name.split("/").pop();
  const m = RUN_RE.exec(base);
  if (!m) return { name: base, label: base };
  const [, y, mo, d, h, mi, , strategy, scale, seed, rest] = m;
  const date = `${d}/${mo}/${y} ${h}:${mi}`;
  const extras = [rest.includes("incident") && "incident", rest.includes("ambulance") && "ambulance"].filter(Boolean);
  return { name: base, date, strategy, scale: Number(scale), seed: Number(seed), extras,
    label: `${date} · ${strategyShort(strategy)} · demande ×${scale}${extras.length ? ` · ${extras.join(", ")}` : ""}` };
}

export const initials = (name = "") => name.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";

// Junction names (same order and labels as app/backend/network.py LABELS: south-west -> north-east along the avenue).
export const JUNCTIONS = { "-28692": "Carrefour 1", "-23354": "Carrefour 2", "-20484": "Carrefour 3", "-29958": "Carrefour 4" };
export const junction = (tls) => JUNCTIONS[tls] || tls;
