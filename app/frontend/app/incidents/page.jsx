"use client";
// Incidents et alertes (2026-11-03): alerts of the detection agent for the current simulation (GET /api/sim/state)
// or a past simulation launched from the application (GET /api/incidents?run=). Severity = fixed level per alert type.
import { useEffect, useMemo, useState } from "react";
import { fmt, getJSON } from "@/components/api";
import Icon from "@/components/icons";
import { useSim } from "@/components/session";
import { ALERT_TYPES, SEVERITY, STATUS, alertType, junction, parseRun } from "@/components/traffic";
import { Badge, Card, Empty, Kpi, Notice, PageHeader, Spinner } from "@/components/ui";

export default function Incidents() {
  const { state } = useSim();
  const [runs, setRuns] = useState([]);
  const [view, setView] = useState("");
  const [hist, setHist] = useState(null);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("all");

  useEffect(() => { getJSON("/incidents/runs").then((r) => setRuns(r.runs)).catch(() => {}); }, [state?.status]);
  useEffect(() => {
    if (!view) { setHist(null); return; }
    setHist("loading"); setErr("");
    getJSON(`/incidents?run=${encodeURIComponent(view)}`).then(setHist).catch((e) => { setErr(e.message); setHist(null); });
  }, [view]);

  const current = !view;
  const alerts = current ? state?.alerts || [] : hist && hist !== "loading" ? [...hist.alerts].reverse() : [];
  const incident = current ? state?.final_kpis?.incident || null : hist?.incident;
  const simIncident = current ? state?.incident : null;
  const emergency = current ? state?.final_kpis?.emergency : hist?.emergency;
  const shown = useMemo(() => alerts.filter((a) => filter === "all" || (filter === "open" ? !a.end_clock : a.end_clock)), [alerts, filter]);
  const open = alerts.filter((a) => !a.end_clock).length;
  const status = state?.status || "idle";

  return (
    <div className="stack">
      <PageHeader eyebrow="Sécurité du réseau" title="Incidents et alertes"
        subtitle="Alertes levées par l'agent de détection : type, localisation, heure, gravité et statut, pour la simulation en cours ou les simulations passées." />

      <div className="card" style={{ padding: ".9rem 1.2rem" }}>
        <div className="row" style={{ gap: "1rem" }}>
          <div className="field" style={{ margin: 0, flex: "1 1 22rem" }}>
            <label htmlFor="inc-run">Simulation affichée</label>
            <select id="inc-run" value={view} onChange={(e) => setView(e.target.value)}>
              <option value="">Simulation courante — {STATUS[status]?.label.toLowerCase()}</option>
              {runs.map((r) => <option key={r.run} value={r.run}>{parseRun(r.run).label} — {r.alerts} alerte(s)</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <span className="field-label">Statut</span>
            <div className="segmented" role="radiogroup" aria-label="Filtrer par statut">
              {[["all", "Toutes"], ["open", "En cours"], ["closed", "Résolues"]].map(([v, l]) => (
                <label key={v} className={`seg ${filter === v ? "on" : ""}`}><input type="radio" name="flt" checked={filter === v} onChange={() => setFilter(v)} />{l}</label>))}
            </div>
          </div>
        </div>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <Kpi icon="alert" tone={open ? "red" : "deep"} label="Alertes en cours" value={String(open)} />
        <Kpi icon="check" tone="green" label="Alertes résolues" value={String(alerts.length - open)} />
        <Kpi icon="alert" tone="orange" label="Voies bloquées" value={String(alerts.filter((a) => a.rule === "blocked").length)} />
        <Kpi icon="car" tone="blue" label="Véhicules immobilisés" value={String(alerts.filter((a) => a.rule === "stalled").length)} />
      </div>

      {(simIncident || incident) && (
        <Notice tone={incident ? (incident.detected ? "ok" : "warn") : "warn"} title="Incident simulé.">
          {simIncident ? `${simIncident.label}. ` : ""}
          {incident ? (incident.detected ? `Détecté par l'agent ${fmt(incident.detection_delay_s, 0)} s après son début.` : "Non détecté par l'agent.") : "Résultat de détection disponible à la fin de la simulation."}
        </Notice>)}
      {emergency && <Notice tone="sim" title="Ambulance.">{emergency.travel_time_s != null ? `Trajet de ${fmt(emergency.travel_time_s, 0)} s, dont ${fmt(emergency.waiting_time_s, 0)} s d'attente` : "Trajet non terminé"} (priorité {emergency.priority ? "activée" : "désactivée"}).</Notice>}
      {err && <Notice tone="bad">{err}</Notice>}

      <Card flush title="Journal des alertes" icon="report" subtitle={current ? "Simulation courante (40 dernières alertes)" : parseRun(view).label}>
        {hist === "loading" ? <div style={{ padding: "1.5rem" }}><Spinner label="Chargement…" /></div> : shown.length === 0 ? (
          <Empty icon="check" title="Aucune alerte">{current && status === "idle" ? "Lancez une simulation ou choisissez une simulation passée." : "Aucune alerte ne correspond à ce filtre."}</Empty>) : (
          <div className="table-wrap scroll" style={{ maxHeight: "34rem" }}>
            <table>
              <thead><tr><th>Type</th><th>Localisation</th><th>Levée à</th><th>Début</th><th>Fin</th><th>Gravité</th><th>Statut</th><th className="num">Arrêtés (max)</th></tr></thead>
              <tbody>{shown.map((a, i) => {
                const t = alertType(a.rule);
                const sev = SEVERITY[t.severity];
                return (
                  <tr key={i}>
                    <td><span className="cell-main">{t.label}</span><span className="cell-sub">{t.rule}</span></td>
                    <td>{a.carrefour || junction(a.tls)}<span className="cell-sub">voie d'approche</span></td>
                    <td>{a.clock}</td><td>{a.start_clock || "–"}</td><td>{a.end_clock || "–"}</td>
                    <td><Badge tone={sev.tone}>{sev.label}</Badge></td>
                    <td>{a.end_clock ? <Badge tone="neutral">Résolue</Badge> : <Badge tone="bad" dot>En cours</Badge>}</td>
                    <td className="num">{a.max_halting}</td>
                  </tr>);
              })}</tbody>
            </table>
          </div>)}
      </Card>

      <p className="muted small"><Icon name="info" size={14} /> Gravité attribuée selon le type d'alerte (règle fixe, non mesurée) :
        {Object.values(ALERT_TYPES).map((t) => ` ${t.label.toLowerCase()} = ${SEVERITY[t.severity].label.toLowerCase()}`).join(" ;")}.
        Une alerte « en cours » à la fin d'une simulation n'était pas encore close quand la simulation s'est terminée.</p>
    </div>
  );
}
