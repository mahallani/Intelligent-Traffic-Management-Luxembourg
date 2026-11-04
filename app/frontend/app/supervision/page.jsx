"use client";
// Supervision du trafic (2026-11-03): live map, connection / simulation indicators, junctions, alerts, agent decisions.
// Data: GET /api/sim/state (shared polling) and GET /api/network. Nothing else.
import Link from "next/link";
import { fmt } from "@/components/api";
import { decisionText } from "@/components/data";
import Icon from "@/components/icons";
import JunctionList from "@/components/JunctionList";
import LineChart from "@/components/LineChart";
import NetworkMap from "@/components/NetworkMap";
import { useAuth, useSim } from "@/components/session";
import { ACTIVE, STATUS, alertType, junction, strategyName } from "@/components/traffic";
import { Badge, Card, Empty, LinkButton, PageHeader, Progress } from "@/components/ui";

const SERIES_COLORS = ["#2478E5", "#26B6D4", "#6E56CF", "#F59E0B"];

function Tile({ icon, label, value, tone }) {
  return (
    <div className={`status-tile st-${tone}`}>
      <span className="st-icon"><Icon name={icon} size={19} /></span>
      <div style={{ minWidth: 0 }}><div className="st-label">{label}</div><div className="st-value">{value}</div></div>
    </div>
  );
}

export default function Supervision() {
  const { state, net, conn, updated } = useSim();
  const { can } = useAuth();
  const status = state?.status || "idle";
  const st = STATUS[status] || STATUS.idle;
  const live = state?.live || {};
  const s = state?.series || {};
  const byTls = s.halting_by_tls || {};
  const alerts = state?.alerts || [];
  const open = alerts.filter((a) => !a.end_clock);
  const decisions = state?.decisions || [];
  const simTone = { running: "ok", paused: "warn", stopping: "warn", starting: "info", finished: "info", stopped: "neutral", error: "bad", idle: "neutral" }[status];

  return (
    <div className="stack">
      <PageHeader eyebrow="Temps réel" title="Supervision du trafic"
        subtitle="Carte des carrefours, état des feux, véhicules, alertes et décisions des agents, actualisés chaque seconde pendant une simulation."
        actions={can("simulate") && !ACTIVE.includes(status) ? <LinkButton href="/simulation/" icon="play" variant="primary">Lancer une simulation</LinkButton> : null} />

      <div className="statusbar">
        <Tile icon="server" label="Serveur de la plateforme" tone={conn === "ok" ? "ok" : conn === "down" ? "bad" : "neutral"}
          value={conn === "ok" ? "Connecté" : conn === "down" ? "Injoignable" : "Vérification…"} />
        <Tile icon="play" label="Simulation" tone={simTone} value={status === "error" ? "Erreur de simulation" : st.label} />
        <Tile icon="clock" label="Heure simulée" tone="info" value={status === "idle" ? "–" : `${state?.clock} · ${Math.round(100 * (state?.progress || 0))} %`} />
        <Tile icon="signal" label="Pilotage des feux" tone="info" value={status === "idle" ? "–" : strategyName(state?.strategy)} />
      </div>
      {status === "error" && <Card><p className="error" role="alert" style={{ margin: 0 }}>La simulation s'est arrêtée sur une erreur. Consultez la page Simulation pour le détail.</p></Card>}

      <div className="grid g-main">
        <div className="stack">
          <NetworkMap net={net} state={state} title="Carte en direct" subtitle={updated ? `Mise à jour ${new Date(updated).toLocaleTimeString("fr-FR")}` : ""} />
          {ACTIVE.includes(status) && <Progress value={state?.progress} />}
        </div>
        <div className="stack">
          <Card title="Indicateurs en direct" icon="monitor">
            <div className="grid g-2" style={{ gap: ".9rem" }}>
              {[["Véhicules", fmt(live.vehicles, 0), ""], ["Arrêtés aux feux", fmt(live.halting, 0), ""], ["Vitesse moyenne", fmt(live.mean_speed_kmh), "km/h"],
                ["Attente moyenne", fmt(live.avg_waiting_s, 0), "s"], ["Trajet moyen", fmt(live.avg_travel_time_s, 0), "s"], ["CO₂ cumulé", fmt(live.co2_kg), "kg"]].map(([l, v, u]) => (
                <div key={l}><div className="muted small">{l}</div><div style={{ fontWeight: 700, fontSize: "1.25rem" }}>{v}{u && v !== "–" && <span className="kpi-unit">{u}</span>}</div></div>))}
            </div>
          </Card>
          <Card title="Carrefours" icon="signal" actions={<Link className="small" href="/carrefours/">Détails</Link>}>
            <JunctionList net={net} state={state} />
          </Card>
        </div>
      </div>

      <div className="grid g-2">
        <Card title="Alertes" icon="alert" subtitle={`${open.length} en cours · ${alerts.length} depuis le début`} actions={<Link className="small" href="/incidents/">Historique</Link>}>
          {alerts.length === 0 ? <Empty icon="check" title="Aucune alerte">Les alertes de l'agent de détection apparaissent ici dès qu'elles sont levées.</Empty> : (
            <div className="feed scroll" style={{ maxHeight: "20rem" }}>
              {alerts.map((a, i) => (
                <div className="feed-item" key={i}>
                  <span className="feed-time">{a.clock}</span>
                  <div><div className="row" style={{ gap: ".4rem" }}><strong>{alertType(a.rule).label}</strong><span className="muted">· {junction(a.tls)}</span>
                    {a.end_clock ? <Badge tone="neutral">Résolue {a.end_clock}</Badge> : <Badge tone="bad" dot>En cours</Badge>}</div>
                  <div className="feed-sub">Jusqu'à {a.max_halting} véhicules arrêtés{state?.incident && a.lane.split("_")[0] === state.incident.lane.split("_")[0] ? " · voie de l'incident simulé" : ""}</div></div>
                </div>))}
            </div>)}
        </Card>
        <Card title="Décisions des agents" icon="xai" subtitle="Chaque changement de phase, avec ce que l'agent a observé" actions={<Link className="small" href="/xai/">Explications</Link>}>
          {decisions.length === 0 ? (
            <Empty icon="signal" title="Aucune décision">
              {status === "idle" ? "Les décisions apparaissent pendant une simulation." : "Avec le plan fixe ou les feux adaptatifs standards, les changements de phase suivent le programme des feux : aucun agent ne décide."}
            </Empty>) : (
            <div className="feed scroll" style={{ maxHeight: "20rem" }}>
              {decisions.map((d, i) => {
                const t = decisionText(d);
                return (
                  <div className="feed-item" key={i}>
                    <span className="feed-time">{d.clock}</span>
                    <div><div className="row" style={{ gap: ".4rem" }}><strong>{junction(d.tls)}</strong><span className="muted">phase {d.from_phase} → {d.to_phase} · {d.green_duration_s} s de vert</span></div>
                      <div className="feed-sub"><Badge tone={t.xai ? "info" : "neutral"}>{t.who}</Badge> {t.text}</div></div>
                  </div>);
              })}
            </div>)}
        </Card>
      </div>

      <Card title="Véhicules arrêtés par carrefour" icon="signal" subtitle="Relevés toutes les 5 secondes">
        <LineChart title="Véhicules arrêtés" unit="véh." x={s.t || []} digits={0}
          series={(net?.signals || []).map((t, i) => ({ name: t.label, values: byTls[t.id] || [], color: SERIES_COLORS[i] }))}
          empty={status === "idle" ? "Lancez une simulation pour suivre les files d'attente." : "Courbe disponible pour les simulations lancées avec cette version."} height={190} />
      </Card>
    </div>
  );
}
