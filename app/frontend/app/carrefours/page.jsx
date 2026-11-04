"use client";
// Carrefours (2026-11-03): one sheet per junction from the live state (signals, stopped vehicles, stop time,
// alerts, forecasts, last agent decision). Congestion level: thresholds written in components/traffic.js.
import { fmt } from "@/components/api";
import { decisionText } from "@/components/data";
import Icon from "@/components/icons";
import LineChart from "@/components/LineChart";
import { useSim } from "@/components/session";
import { STATUS, alertType, congestion, lampOf, signalSummary } from "@/components/traffic";
import { Badge, Card, Notice, PageHeader } from "@/components/ui";

function Junction({ t, i, state }) {
  const s = state?.signals?.[t.id];
  const c = congestion(s?.halting);
  const sum = signalSummary(s?.state);
  const open = (state?.alerts || []).filter((a) => a.tls === t.id && !a.end_clock);
  const f = state?.forecasts?.[t.id];
  const last = (state?.decisions || []).find((d) => d.tls === t.id);
  const stopMin = state?.live?.stop_min_by_tls?.[t.id];
  const series = state?.series?.halting_by_tls?.[t.id] || [];
  return (
    <Card className="jn-card">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: ".9rem" }}>
        <div className="row" style={{ gap: ".75rem" }}>
          <span className="jn-num" style={{ width: 40, height: 40, fontSize: "1rem" }}>{i + 1}</span>
          <div><h2>{t.label}</h2><div className="muted small">Avenue J.F. Kennedy · feu n° {i + 1}</div></div>
        </div>
        <Badge tone={c.tone} dot>{c.label === "–" ? "Inactif" : c.label}</Badge>
      </div>

      <div className="grid g-2" style={{ gap: ".9rem", marginBottom: ".9rem" }}>
        <div>
          <div className="muted small">État des feux</div>
          <div className="lamps" style={{ margin: ".35rem 0" }} aria-label={`État des ${(s?.state || "").length} mouvements : ${s?.state || "inconnu"}`}>
            {(s?.state || "").split("").map((ch, k) => <span key={k} className={`lamp ${lampOf(ch)}`} style={{ width: 14, height: 14 }} />)}
            {!s && <span className="muted small">aucune simulation</span>}
          </div>
          {s && <div className="small">{sum.green} mouvement(s) au vert · {sum.amber} à l'orange · {sum.red} au rouge</div>}
        </div>
        <div>
          <div className="muted small">Phase en cours</div>
          <div style={{ fontWeight: 700, fontSize: "1.15rem" }}>{s ? `Phase ${s.phase}` : "–"}</div>
          {s && <div className="small">depuis {Math.round(s.green_elapsed)} s</div>}
        </div>
        <div>
          <div className="muted small">Véhicules arrêtés</div>
          <div style={{ fontWeight: 700, fontSize: "1.5rem" }}>{s ? s.halting : "–"}</div>
        </div>
        <div>
          <div className="muted small">Temps d'arrêt cumulé</div>
          <div style={{ fontWeight: 700, fontSize: "1.5rem" }}>{fmt(stopMin, 0)}{stopMin != null && <span className="kpi-unit">véh·min</span>}</div>
        </div>
      </div>

      <LineChart title="Véhicules arrêtés" unit="véh." x={(state?.series?.t || []).slice(-series.length)} series={[{ name: t.label, values: series, color: "#2478E5" }]}
        height={110} digits={0} empty="Courbe disponible pendant une simulation." />

      <div className="stack" style={{ marginTop: ".9rem" }}>
        {open.length > 0 ? open.map((a, k) => (
          <Notice key={k} tone="bad" title={`${alertType(a.rule).label} depuis ${a.clock}.`}>Jusqu'à {a.max_halting} véhicules arrêtés.</Notice>))
          : s && <div className="small muted"><Icon name="check" size={14} /> Aucun incident en cours.</div>}
        {f && <div className="small"><strong>Prévision</strong> : {fmt(f.now)} véhicules arrêtés maintenant → {fmt(f["300"])} dans 5 min, {fmt(f["900"])} dans 15 min.</div>}
        {last && <div className="small"><strong>Dernière décision</strong> ({last.clock}) : {decisionText(last).text}</div>}
      </div>
    </Card>
  );
}

export default function Carrefours() {
  const { state, net } = useSim();
  const status = state?.status || "idle";
  return (
    <div className="stack">
      <PageHeader eyebrow="Réseau" title="Carrefours"
        subtitle="Fiche de chaque carrefour à feux : état des feux, files d'attente, niveau de congestion, incidents et prévisions."
        actions={<Badge tone={STATUS[status]?.tone} dot>{STATUS[status]?.label}</Badge>} />
      {status === "idle" && <Notice tone="info" title="Aucune simulation en cours.">Les fiches se remplissent dès qu'une simulation démarre.</Notice>}
      <div className="grid g-2">
        {(net?.signals || []).map((t, i) => <Junction key={t.id} t={t} i={i} state={state} />)}
      </div>
      <p className="muted small"><Icon name="info" size={14} /> Niveau de congestion : fluide de 0 à 2 véhicules arrêtés, dense de 3 à 7, saturé à partir de 8 (seuil de congestion de l'agent de détection).
        Temps d'arrêt cumulé : somme, depuis 07:00, du temps passé à l'arrêt par les véhicules sur les voies de ce carrefour.</p>
    </div>
  );
}
