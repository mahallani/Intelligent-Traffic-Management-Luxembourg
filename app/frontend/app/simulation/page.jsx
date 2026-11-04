"use client";
// Simulation (2026-11-03): the former control page (page.jsx.bak_20261103) reorganised. Same API calls and parameters:
// POST /api/sim/start|pause|resume|stop with the same body as before; technical options only for administrators.
import { useEffect, useRef, useState } from "react";
import { fmt, getJSON, postJSON } from "@/components/api";
import { decisionText } from "@/components/data";
import Icon from "@/components/icons";
import NetworkMap from "@/components/NetworkMap";
import { useAuth, useSim } from "@/components/session";
import { ACTIVE, DEMAND, STATUS, STRATEGIES, junction, strategyName } from "@/components/traffic";
import { Badge, Card, Empty, Kpi, Notice, PageHeader, Progress, Segmented, Tabs } from "@/components/ui";

const INCIDENTS = [["none", "Aucun incident"], ["carrefour4", "Voie bloquée avant le Carrefour 4 (07:20–07:40)"],
  ["carrefour1", "Voie bloquée avant le Carrefour 1 (07:20–07:40)"]];

// Optional siren (2026-10-22): synthesised by THIS browser (Web Audio API), only while the ambulance is in the network.
function makeSiren() {
  const a = { ctx: null, osc: null, gain: null, timer: null };
  return {
    unlock() {
      const C = typeof window !== "undefined" ? (window.AudioContext || window.webkitAudioContext) : null;
      if (!C) return false;
      if (!a.ctx) a.ctx = new C();
      if (a.ctx.state === "suspended") a.ctx.resume();
      return true;
    },
    start() {
      if (!a.ctx || a.osc) return;
      a.osc = a.ctx.createOscillator();
      a.gain = a.ctx.createGain();
      a.osc.type = "triangle";
      a.gain.gain.value = 0.05;
      a.osc.connect(a.gain).connect(a.ctx.destination);
      let hi = false;
      const flip = () => { hi = !hi; a.osc.frequency.setValueAtTime(hi ? 880 : 660, a.ctx.currentTime); };
      flip();
      a.timer = setInterval(flip, 500);
      a.osc.start();
    },
    stop() {
      if (a.timer) clearInterval(a.timer);
      if (a.osc) { try { a.osc.stop(); } catch { /* already stopped */ } a.osc.disconnect(); }
      a.osc = null; a.timer = null;
    },
  };
}

function Switch({ checked, onChange, disabled, label, sub, id }) {
  return (
    <label className="switch" htmlFor={id}>
      <span className="switch-text">{label}{sub && <small>{sub}</small>}</span>
      <input id={id} type="checkbox" checked={checked} onChange={onChange} disabled={disabled} />
      <span className="track" aria-hidden="true" />
    </label>
  );
}

function AmbulanceBanner({ e }) {
  if (!e || e.status === "absente") return null;
  const txt = e.status === "en attente d'insertion" ? `Ambulance : départ demandé à ${e.requested_at}, en attente d'une place sur la voie d'entrée.`
    : e.status === "arrivée" ? `Ambulance arrivée à ${e.arrival} · trajet ${e.travel_s} s (départ ${e.depart}).`
      : `Ambulance en circulation depuis ${e.depart}${e.next ? ` · prochain carrefour : ${e.next.label} à ${e.next.dist_m} m, feu ${e.next.signal} pour elle` : " · sortie de l'avenue"}${e.speed_kmh != null ? ` · ${e.speed_kmh} km/h` : ""}.`;
  return <div className="amb-banner" role="status"><Icon name="ambulance" size={18} />{txt}</div>;
}

export default function Simulation() {
  const { state, net, setState, refresh } = useSim();
  const { can } = useAuth();
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({ scenario: "kirchberg_4tls", strategy: "S0_fixed_time", scale: 1, seed: 1, delay_ms: 20,
    gui: false, use_forecast: true, detection_mode: "discharge", incident: "none", ambulance: false, ambulance_priority: true });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [tab, setTab] = useState("decisions");
  const [advanced, setAdvanced] = useState(false);
  const siren = useRef(null);
  const [sirenOn, setSirenOn] = useState(false);
  const [sirenMsg, setSirenMsg] = useState("");

  useEffect(() => { getJSON("/config").then(setCfg).catch((e) => setErr(e.message)); }, []);
  // While a simulation is active, the form shows ITS parameters (read-only), not the defaults.
  const runKey = state && ACTIVE.includes(state.status) ? state.run_id : null;
  useEffect(() => {
    if (!runKey || !state) return;
    setForm((f) => ({ ...f, scenario: state.scenario || f.scenario, strategy: state.strategy || f.strategy, scale: state.scale ?? f.scale,
      seed: state.seed ?? f.seed, delay_ms: state.delay_ms ?? f.delay_ms, gui: !!state.gui, use_forecast: state.use_forecast ?? f.use_forecast,
      detection_mode: state.detection_mode || f.detection_mode, incident: state.incident?.id || "none", ambulance: !!state.ambulance,
      ambulance_priority: state.ambulance ? !!state.ambulance.priority : f.ambulance_priority }));
  }, [runKey]);   // eslint-disable-line react-hooks/exhaustive-deps

  const status = state?.status || "idle";
  const active = ACTIVE.includes(status);
  const allowed = can("simulate");
  const isAdmin = can("admin");
  const locked = active || !allowed;
  const ambLive = state?.emergency_live;
  const sirenPlaying = sirenOn && status === "running" && ambLive?.status === "en circulation";
  useEffect(() => { if (siren.current) { if (sirenPlaying) siren.current.start(); else siren.current.stop(); } }, [sirenPlaying]);
  useEffect(() => () => siren.current?.stop(), []);
  const toggleSiren = (e) => {
    const on = e.target.checked;
    if (on) {
      if (!siren.current) siren.current = makeSiren();
      if (!siren.current.unlock()) { setSirenMsg("Ce navigateur ne permet pas de jouer le son."); return; }
      setSirenMsg("");
    }
    setSirenOn(on);
  };

  const act = async (path, label, body) => {
    setErr(""); setBusy(label);
    try { setState(await postJSON(path, body)); } catch (e) { setErr(e.message); } finally { setBusy(""); refresh(); }
  };
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const setE = (k) => (e) => set(k)(e.target.type === "checkbox" ? e.target.checked : e.target.value);
  const start = () => act("/sim/start", "start", { ...form, scale: Number(form.scale), seed: Number(form.seed), delay_ms: Number(form.delay_ms) });
  const live = state?.live || {};
  const fin = state?.final_kpis;
  const st = STATUS[status] || STATUS.idle;
  const strategies = (cfg?.strategies || []).filter((x) => STRATEGIES[x.id]);

  return (
    <div className="stack">
      <PageHeader eyebrow="Pilotage" title="Simulation"
        subtitle="Configurez un scénario de trafic, choisissez la stratégie de gestion des feux et suivez les résultats en direct."
        actions={<Badge tone={st.tone} dot>{st.label}</Badge>} />

      {!allowed && <Notice tone="info" title="Consultation seule.">Votre rôle permet de suivre les simulations, pas de les lancer. Contactez un opérateur ou un administrateur.</Notice>}

      <div className="grid g-side">
        <Card title="Configuration" icon="settings" as="section" aria-label="Configuration de la simulation">
          <div className="field"><label htmlFor="sc">Scénario</label>
            <select id="sc" value={form.scenario} onChange={setE("scenario")} disabled={locked}>
              {(cfg?.scenarios || []).map((x) => <option key={x.id} value={x.id}>Kirchberg – avenue J.F. Kennedy, 4 carrefours (07:00–08:00)</option>)}
            </select></div>

          <div className="field"><label htmlFor="st">Stratégie de gestion des feux</label>
            <select id="st" value={form.strategy} onChange={setE("strategy")} disabled={locked}>
              {strategies.map((x) => <option key={x.id} value={x.id} disabled={!x.available}>{STRATEGIES[x.id].name}{x.available ? "" : " (indisponible)"}{isAdmin ? ` · ${x.id.split("_")[0]}` : ""}</option>)}
            </select>
            <span className="hint">{STRATEGIES[form.strategy]?.desc}</span></div>

          <div className="field"><span className="field-label">Intensité du trafic</span>
            <Segmented name="scale" label="Intensité du trafic" cols={3} value={form.scale} onChange={set("scale")} disabled={locked}
              options={[1, 2, 3, 4, 5, 6].map((x) => [x, `×${x}`, DEMAND[x]])} /></div>

          <div>
            <div className="field"><label htmlFor="sd">Graine aléatoire</label>
              <input id="sd" type="number" min="1" value={form.seed} onChange={setE("seed")} disabled={locked} />
              <span className="hint">Même graine = même trafic.</span></div>
            <div className="field"><label htmlFor="dl">Vitesse d'affichage</label>
              <select id="dl" value={form.delay_ms} onChange={setE("delay_ms")} disabled={locked}>
                <option value={0}>Maximale</option>
                <option value={20}>Rapide (1 h ≈ 1 min 30)</option>
                <option value={100}>Lente (1 h ≈ 6 min)</option>
              </select></div>
          </div>

          <fieldset className="field" style={{ marginBottom: ".4rem" }}>
            <legend className="field-label" style={{ marginBottom: ".35rem" }}>Événements simulés</legend>
            <div className="field" style={{ marginBottom: ".4rem" }}><label htmlFor="inc" className="sr-only">Incident</label>
              <select id="inc" value={form.incident} onChange={setE("incident")} disabled={locked}>
                {INCIDENTS.map(([id, l]) => <option key={id} value={id}>{l}</option>)}
              </select></div>
            <Switch id="amb" label="Ambulance sur l'avenue à 07:20" checked={form.ambulance} onChange={setE("ambulance")} disabled={locked} />
            {form.ambulance && <Switch id="ambp" label="Priorité aux véhicules d'urgence" sub="Les feux s'adaptent à l'approche de l'ambulance" checked={form.ambulance_priority} onChange={setE("ambulance_priority")} disabled={locked} />}
            <Switch id="siren" label="Son de sirène" sub="Dans ce navigateur, pendant le trajet de l'ambulance" checked={sirenOn} onChange={toggleSiren} />
            {sirenMsg && <p className="error">{sirenMsg}</p>}
          </fieldset>

          {isAdmin && (
            <div style={{ borderTop: "1px solid var(--line)", paddingTop: ".7rem", marginTop: ".4rem" }}>
              <button type="button" className="link-btn" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}>
                <Icon name={advanced ? "chevronDown" : "chevronRight"} size={15} /> Options avancées (administrateur)
              </button>
              {advanced && (
                <div style={{ marginTop: ".7rem" }}>
                  <div className="field"><label htmlFor="dr">Règle de détection d'incident</label>
                    <select id="dr" value={form.detection_mode} onChange={setE("detection_mode")} disabled={locked}>
                      <option value="discharge">Voie bloquée (recommandée)</option>
                      <option value="rules">Seuils de file (v1)</option>
                      <option value="gated">Seuils filtrés par la prévision</option>
                    </select></div>
                  <Switch id="fc" label="Transmettre les prévisions à la décision" sub="Utilisé par l'agent à règles + prévision" checked={form.use_forecast} onChange={setE("use_forecast")} disabled={locked} />
                  <Switch id="gui" label="Ouvrir aussi SUMO-GUI" sub="Sur le PC qui exécute le serveur" checked={form.gui} onChange={setE("gui")} disabled={locked} />
                </div>)}
            </div>)}

          <div className="row" style={{ marginTop: "1rem" }}>
            <button className="btn btn-primary" type="button" disabled={locked || !!busy} onClick={start}>
              {busy === "start" ? <span className="spinner" aria-hidden="true" /> : <Icon name="start" size={16} />}Démarrer
            </button>
            <button className="btn" type="button" disabled={!allowed || status !== "running" || !!busy} onClick={() => act("/sim/pause", "pause")}><Icon name="pause" size={16} />Pause</button>
            <button className="btn" type="button" disabled={!allowed || status !== "paused" || !!busy} onClick={() => act("/sim/resume", "resume")}><Icon name="start" size={16} />Reprendre</button>
            <button className="btn btn-danger" type="button" disabled={!allowed || !active || !!busy} onClick={() => act("/sim/stop", "stop")}>
              {busy === "stop" ? <span className="spinner" aria-hidden="true" /> : <Icon name="stop" size={16} />}Arrêter</button>
          </div>
          {(err || state?.error) && <div style={{ marginTop: ".9rem" }}><Notice tone="bad" title="Erreur.">{err || state.error}</Notice></div>}
          {isAdmin && state?.run_dir && <p className="hint" style={{ marginTop: ".7rem", overflowWrap: "anywhere" }}>Dossier des résultats : <code>{state.run_dir}</code></p>}
        </Card>

        <div className="stack">
          <div className="kpis kpis-5">
            <Kpi icon="car" tone="cyan" label="Véhicules" value={fmt(live.vehicles, 0)} hint={`${fmt(live.halting, 0)} arrêté(s)`} />
            <Kpi icon="monitor" tone="blue" label="Vitesse moyenne" value={fmt(live.mean_speed_kmh)} unit="km/h" />
            <Kpi icon="route" tone="deep" label="Trajet moyen" value={fmt(live.avg_travel_time_s, 0)} unit="s" hint={`${fmt(live.arrived, 0)} véhicules arrivés`} />
            <Kpi icon="timer" tone="orange" label="Attente moyenne" value={fmt(live.avg_waiting_s, 0)} unit="s" />
            <Kpi icon="leaf" tone="green" label="CO₂ émis" value={fmt(live.co2_kg)} unit="kg" />
          </div>
          {(state?.incident || state?.ambulance) && (
            <div className="row badges-wrap">
              {state.incident && <Badge tone="bad">Incident simulé : {state.incident.label}</Badge>}
              {state.ambulance && <Badge tone="sim">Ambulance à {state.ambulance.at} · priorité {state.ambulance.priority ? "activée" : "désactivée"}</Badge>}
            </div>)}
          <AmbulanceBanner e={ambLive} />
          <NetworkMap net={net} state={state} title={status === "idle" ? "Aperçu du réseau" : strategyName(state?.strategy)}
            subtitle={status === "idle" ? "Lancez une simulation pour voir le trafic" : `Demande ×${state?.scale} · graine ${state?.seed}`} />
          {status !== "idle" && <Progress value={state?.progress} />}

          {fin && (
            <Card title="Bilan de la simulation" icon="check" subtitle="Indicateurs finaux calculés sur l'ensemble des trajets">
              <div className="grid g-4" style={{ gap: ".9rem" }}>
                {[["Trajet moyen", fmt(fin.avg_travel_time_s, 1), "s"], ["Attente moyenne", fmt(fin.avg_waiting_time_s, 1), "s"],
                  ["File moyenne", fmt(fin.avg_queue_veh, 1), "véh."], ["CO₂", fmt(fin.co2_kg, 1), "kg"]].map(([l, v, u]) => (
                  <div key={l}><div className="muted small">{l}</div><div style={{ fontWeight: 700, fontSize: "1.3rem" }}>{v}<span className="kpi-unit">{u}</span></div></div>))}
              </div>
              <div className="stack" style={{ marginTop: ".9rem" }}>
                {fin.safety && <Notice tone={fin.safety.total_violations === 0 ? "ok" : "bad"} title="Sécurité des feux :">
                  {fmt(fin.safety.transitions_checked, 0)} changements vérifiés (jaune obligatoire, vert de {fmt(fin.safety.limits?.min_green_s, 0)} à {fmt(fin.safety.limits?.max_green_s, 0)} s) —{" "}
                  {fin.safety.total_violations === 0 ? "aucune anomalie." : `${fin.safety.total_violations} anomalie(s).`}</Notice>}
                {fin.incident && <Notice tone={fin.incident.detected ? "ok" : "warn"} title="Incident simulé :">
                  {fin.incident.detected ? `détecté ${fmt(fin.incident.detection_delay_s, 0)} s après son début.` : "non détecté."}</Notice>}
                {fin.emergency && <Notice tone="sim" title="Ambulance :">
                  {fin.emergency.travel_time_s != null ? `trajet ${fmt(fin.emergency.travel_time_s, 0)} s, dont ${fmt(fin.emergency.waiting_time_s, 0)} s d'attente` : "trajet non terminé"} (priorité {fin.emergency.priority ? "activée" : "désactivée"}).</Notice>}
              </div>
            </Card>)}

          <Card flush>
            <div style={{ padding: "0 1.2rem" }}>
              <Tabs value={tab} onChange={setTab} label="Journal de la simulation"
                tabs={[["decisions", "Décisions des agents", (state?.decisions || []).length || undefined], ...(state?.ambulance ? [["ambulance", "Ambulance"]] : [])]} />
            </div>
            <div style={{ padding: "0 1.2rem 1.1rem" }}>
              {tab === "decisions" && ((state?.decisions || []).length === 0 ? (
                <Empty icon="signal" title="Aucune décision">
                  {status === "idle" ? "Les changements de phase décidés par les agents apparaîtront ici." : "Avec le plan fixe ou les feux adaptatifs standards, les phases suivent le programme des feux : aucun agent ne décide."}
                </Empty>) : (
                <div className="feed scroll">
                  {state.decisions.map((d, i) => {
                    const t = decisionText(d);
                    return (
                      <div className="feed-item" key={i}>
                        <span className="feed-time">{d.clock}</span>
                        <div><div className="row" style={{ gap: ".4rem" }}><strong>{junction(d.tls)}</strong><span className="muted">phase {d.from_phase} → {d.to_phase} · {d.green_duration_s} s de vert</span></div>
                          <div className="feed-sub"><Badge tone={t.xai ? "info" : "neutral"}>{t.who}</Badge> {t.text}</div></div>
                      </div>);
                  })}
                </div>))}
              {tab === "ambulance" && (
                (ambLive?.events || []).length === 0 ? <Empty icon="ambulance" title="Pas encore d'événement">L'ambulance entre dans le réseau à 07:20:00.</Empty> : (
                  <div className="table-wrap scroll">
                    <table>
                      <thead><tr><th>Heure</th><th>Événement</th><th>Carrefour</th><th>Détail</th></tr></thead>
                      <tbody>{ambLive.events.map((ev, i) => (
                        <tr key={i}><td>{ev.clock}</td><td className="cell-main">{ev.event}</td><td>{ev.carrefour || "–"}</td><td className="why">{ev.detail}</td></tr>))}</tbody>
                    </table>
                  </div>))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
