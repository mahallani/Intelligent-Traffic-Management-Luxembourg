"use client";
// Prévisions IA (2026-11-03): forecasts of stopped vehicles per junction (+5/+10/+15 min) and their accuracy measured
// during the run against what really happened, next to a naive reference (nothing changes). From GET /api/sim/state.
import { fmt } from "@/components/api";
import Icon from "@/components/icons";
import { useSim } from "@/components/session";
import { STATUS, junction } from "@/components/traffic";
import { Badge, Card, Empty, PageHeader } from "@/components/ui";

const H = [["now", "Maintenant"], ["300", "+5 min"], ["600", "+10 min"], ["900", "+15 min"]];

function Bars({ f, max }) {
  return (
    <div className="fc-bars">
      {H.map(([k, l]) => {
        const v = f[k];
        return (
          <div key={k} className="fc-col">
            <div className="fc-track"><div className={`fc-bar ${k === "now" ? "now" : ""}`} style={{ height: `${Math.max(3, (100 * (v || 0)) / max)}%` }} /></div>
            <strong>{fmt(v)}</strong><small>{l}</small>
          </div>);
      })}
    </div>
  );
}

export default function Previsions() {
  const { state } = useSim();
  const status = state?.status || "idle";
  const fc = state?.forecasts || {};
  const sc = state?.prediction_scores;
  const checks = state?.prediction_checks || [];
  const entries = Object.entries(fc);
  const max = Math.max(1, ...entries.flatMap(([, f]) => H.map(([k]) => f[k] || 0)));

  return (
    <div className="stack">
      <PageHeader eyebrow="Anticipation" title="Prévisions IA"
        subtitle="Nombre de véhicules arrêtés attendu à chaque carrefour dans 5, 10 et 15 minutes, et précision mesurée en direct."
        actions={<Badge tone={STATUS[status]?.tone} dot>{STATUS[status]?.label}</Badge>} />

      {entries.length === 0 ? (
        <Card><Empty icon="forecast" title="Pas encore de prévision">
          {status === "idle" ? "Les prévisions sont produites pendant une simulation." : "Les premières prévisions arrivent après 6 minutes simulées (le modèle a besoin d'un historique)."}
        </Empty></Card>) : (
        <div className="grid g-4">
          {entries.map(([t, f]) => (
            <Card key={t} title={junction(t)} icon="signal" subtitle="Véhicules arrêtés prévus"><Bars f={f} max={max} /></Card>))}
        </div>)}

      <div className="grid g-2">
        <Card title="Précision mesurée pendant la simulation" icon="check"
          subtitle={sc ? `${sc.n_scored} prévisions comparées à la valeur réellement observée` : "Comparaison prévision / réalité"}>
          {!sc ? <Empty icon="clock" title="Pas encore de mesure">La précision est calculée quand l'heure visée par une prévision est atteinte.</Empty> : (
            <table>
              <thead><tr><th>Horizon</th><th className="num">Erreur moyenne du modèle</th><th className="num">Référence naïve</th><th>Face à la référence</th></tr></thead>
              <tbody>{[5, 10, 15].map((h) => {
                const m = sc[`mae_cascade_${h}min`], p = sc[`mae_persistence_${h}min`];
                const better = m != null && p != null ? m < p : null;
                return (
                  <tr key={h}><td className="cell-main">+{h} min</td><td className="num">{fmt(m, 2)} véh.</td><td className="num">{fmt(p, 2)} véh.</td>
                    <td>{better === null ? "–" : better ? <Badge tone="ok">Meilleur</Badge> : <Badge tone="warn">Pas meilleur</Badge>}</td></tr>);
              })}</tbody>
            </table>)}
          <p className="hint" style={{ marginTop: ".8rem" }}><Icon name="info" size={14} /> Référence naïve : supposer que rien ne change par rapport à maintenant. Un modèle utile doit faire une erreur plus faible.</p>
        </Card>
        <Card title="Dernières vérifications" icon="clock" subtitle="Prévision faite à une heure donnée, comparée à ce qui s'est passé">
          {checks.length === 0 ? <Empty icon="clock" title="Aucune vérification pour l'instant" /> : (
            <div className="table-wrap scroll">
              <table>
                <thead><tr><th>Faite à</th><th>Pour</th><th>Carrefour</th><th className="num">Prévu</th><th className="num">Observé</th><th className="num">Écart</th></tr></thead>
                <tbody>{checks.slice(0, 16).map((c, i) => (
                  <tr key={i}><td>{c.made}</td><td>{c.target} <span className="cell-sub">+{c.horizon_min} min</span></td><td>{junction(c.tls)}</td>
                    <td className="num">{fmt(c.forecast, 1)}</td><td className="num">{fmt(c.observed, 1)}</td>
                    <td className="num">{c.error > 0 ? "+" : ""}{fmt(c.error, 1)}</td></tr>))}</tbody>
              </table>
            </div>)}
        </Card>
      </div>
    </div>
  );
}
