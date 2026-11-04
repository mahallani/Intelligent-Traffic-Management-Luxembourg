"use client";
// Vue d'ensemble (2026-11-03). The former control page moved to /simulation/ (previous file: page.jsx.bak_20261103).
// Values: live simulation state (GET /api/sim/state) or, when nothing ran since the server started, the last run
// launched from the application (GET /api/runs). Each card says which one it shows.
import Link from "next/link";
import { fmt } from "@/components/api";
import { useLastRun } from "@/components/data";
import Icon from "@/components/icons";
import LineChart from "@/components/LineChart";
import NetworkMap from "@/components/NetworkMap";
import { useAuth, useSim } from "@/components/session";
import { ACTIVE, STATUS, alertType, duration, junction, parseRun, strategyName } from "@/components/traffic";
import JunctionList from "@/components/JunctionList";
import { Badge, Card, Empty, Kpi, LinkButton, PageHeader, Progress } from "@/components/ui";

export default function Overview() {
  const { state, net } = useSim();
  const { can } = useAuth();
  const last = useLastRun();
  const status = state?.status || "idle";
  const hasRun = status !== "idle";
  const live = hasRun ? state.live || {} : {};
  const fin = state?.final_kpis;
  const s = state?.series || {};
  const openAlerts = (state?.alerts || []).filter((a) => !a.end_clock);
  const src = hasRun ? (ACTIVE.includes(status) ? "en direct" : "fin de la simulation") : last ? "dernière simulation" : "";
  const density = hasRun && net?.lane_km && live.vehicles !== undefined ? live.vehicles / net.lane_km : null;
  const travel = hasRun ? (fin?.avg_travel_time_s ?? live.avg_travel_time_s) : last?.avg_travel_time_s;
  const waiting = hasRun ? (fin?.avg_waiting_time_s ?? live.avg_waiting_s) : last?.avg_waiting_time_s;
  const co2 = hasRun ? (fin?.co2_kg ?? live.co2_kg) : last?.co2_kg;
  const loading = state === null || last === undefined;
  const lastInfo = last ? parseRun(last.name) : null;

  return (
    <div className="stack">
      <PageHeader eyebrow="Kirchberg · avenue J.F. Kennedy" title="Vue d'ensemble"
        subtitle="État du trafic et des quatre carrefours à feux, indicateurs clés et évolution de la simulation."
        actions={<>
          <Badge tone={STATUS[status]?.tone || "neutral"} dot>{STATUS[status]?.label}</Badge>
          {can("simulate") && <LinkButton href="/simulation/" icon="play" variant="primary">{ACTIVE.includes(status) ? "Suivre la simulation" : "Lancer une simulation"}</LinkButton>}
        </>} />

      {!hasRun && last && (
        <p className="muted small" style={{ marginTop: "-.4rem" }}>
          Aucune simulation en cours. Indicateurs de la dernière simulation : {lastInfo?.date || last.name} · {strategyName(last.strategy)} · demande ×{last.scale}.
        </p>)}

      <div className="kpis">
        <Kpi icon="route" tone="blue" label="Temps de trajet moyen" value={fmt(travel, 0)} unit="s" hint={travel != null ? `${duration(travel)} · ${src}` : "aucune donnée"} loading={loading} />
        <Kpi icon="timer" tone="orange" label="Attente moyenne" value={fmt(waiting, 0)} unit="s" hint={waiting != null ? `par véhicule · ${src}` : "aucune donnée"} loading={loading} />
        <Kpi icon="density" tone="deep" label="Densité du trafic" value={fmt(density, 1)} unit="véh/km" hint={density != null ? `véhicules / ${fmt(net?.lane_km, 1)} km de voies` : "pendant une simulation"} loading={loading} />
        <Kpi icon="car" tone="cyan" label="Véhicules dans le réseau" value={fmt(hasRun ? live.vehicles : null, 0)} hint={hasRun ? `${fmt(live.halting, 0)} arrêté(s) aux feux` : "pendant une simulation"} loading={loading} />
        <Kpi icon="leaf" tone="green" label="CO₂ émis" value={fmt(co2, 1)} unit="kg" hint={co2 != null ? `cumul · ${src}` : "aucune donnée"} loading={loading} />
        <Kpi icon="alert" tone={openAlerts.length ? "red" : "deep"} label="Incidents actifs" value={hasRun ? String(openAlerts.length) : "–"}
          hint={hasRun ? `${(state?.alerts || []).length} alerte(s) depuis 07:00` : "pendant une simulation"} loading={loading} />
      </div>

      <div className="grid g-main">
        <div className="stack">
          <NetworkMap net={net} state={state} title="Réseau surveillé" subtitle="4 carrefours à feux · avenue J.F. Kennedy" />
          {hasRun && <Progress value={state?.progress} />}
        </div>
        <div className="stack">
          <Card title="Carrefours" icon="signal" actions={<Link href="/carrefours/" className="small">Détails</Link>}>
            <JunctionList net={net} state={state} />
          </Card>
          <Card title="Alertes récentes" icon="alert" actions={<Link href="/incidents/" className="small">Tout voir</Link>}>
            {(state?.alerts || []).length === 0 ? <p className="muted small" style={{ margin: 0 }}>Aucune alerte{hasRun ? " depuis le début de la simulation." : "."}</p> : (
              <div className="feed">
                {state.alerts.slice(0, 4).map((a, i) => (
                  <div className="feed-item" key={i}>
                    <span className="feed-time">{a.clock}</span>
                    <div><strong>{alertType(a.rule).label}</strong> · {junction(a.tls)}
                      <div className="feed-sub">{a.end_clock ? `résolue à ${a.end_clock}` : "en cours"} · jusqu'à {a.max_halting} véhicules arrêtés</div></div>
                  </div>))}
              </div>)}
          </Card>
        </div>
      </div>

      <Card title="Évolution du trafic" icon="monitor" subtitle={hasRun ? `${STATUS[status]?.label} · ${strategyName(state.strategy)}` : undefined}>
        {(s.t || []).length < 2 ? (
          <Empty icon="monitor" title="Pas encore de courbes"
            action={can("simulate") ? <LinkButton href="/simulation/" icon="play" variant="primary">Lancer une simulation</LinkButton> : null}>
            Les courbes se remplissent pendant une simulation, à partir des mesures relevées toutes les 5 secondes.
          </Empty>) : (
          <div className="grid g-4">
            <LineChart title="Véhicules dans le réseau" unit="véh." x={s.t} series={[{ name: "véhicules", values: s.vehicles, color: "#2478E5" }]} digits={0} />
            <LineChart title="Vitesse moyenne" unit="km/h" x={s.t} series={[{ name: "vitesse", values: s.speed, color: "#26B6D4" }]} />
            <LineChart title="Attente moyenne" unit="s" x={s.t} series={[{ name: "attente", values: s.waiting || [], color: "#F59E0B" }]}
              empty="Courbe disponible pour les simulations lancées avec cette version." />
            <LineChart title="CO₂ cumulé" unit="kg" x={s.t} series={[{ name: "CO₂", values: s.co2 || [], color: "#22A06B" }]}
              empty="Courbe disponible pour les simulations lancées avec cette version." />
          </div>)}
      </Card>

      <p className="muted small"><Icon name="info" size={14} /> Toutes les valeurs proviennent de l'environnement de simulation de la plateforme ; elles ne sont pas des mesures du trafic réel.</p>
    </div>
  );
}
