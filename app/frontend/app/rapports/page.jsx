"use client";
// Rapports (2026-11-03): strategy comparison (GET /api/compare), simulation history (GET /api/runs), CSV export and
// print / PDF. The former page (internal Markdown reports) moved to the administrators' technical section
// (previous file: rapports/page.jsx.bak_20261103; results page: resultats/page.jsx.bak_20261103).
import { useEffect, useMemo, useState } from "react";
import { API, fmt, getJSON } from "@/components/api";
import Icon from "@/components/icons";
import { useAuth } from "@/components/session";
import { STRATEGIES, parseRun, strategyName } from "@/components/traffic";
import { Badge, Card, Empty, Notice, PageHeader, Spinner, Tabs } from "@/components/ui";

const MAIN = ["avg_travel_time_s", "avg_waiting_time_s", "avg_queue_veh", "co2_kg"];
const VERDICT = { meilleur: ["ok", "Meilleur"], "moins bon": ["bad", "Moins bon"], "non significatif": ["neutral", "Écart non significatif"] };

function CompareBars({ res }) {
  const rows = res.rows.filter((r) => MAIN.includes(r.kpi));
  return (
    <div className="grid g-4" style={{ gap: "1rem" }}>
      {rows.map((r) => {
        const max = Math.max(r.a_mean + r.a_std, r.b_mean + r.b_std, 1e-9);
        const v = VERDICT[r.verdict] || ["neutral", r.verdict];
        return (
          <div key={r.kpi} className="cmp">
            <div className="cmp-label">{r.label.replace(" simulé", "")}</div>
            {[["A", res.a.label, r.a_mean, r.a_std, "var(--deep)"], ["B", res.b.label, r.b_mean, r.b_std, "var(--electric)"]].map(([k, l, m, sd, c]) => (
              <div key={k} className="cmp-row">
                <span className="cmp-key" style={{ background: c }}>{k}</span>
                <div className="cmp-track"><div style={{ width: `${(100 * m) / max}%`, background: c }} /></div>
                <span className="cmp-val">{fmt(m, 1)}<small> ±{fmt(sd, 1)}</small></span>
              </div>))}
            <div className="row" style={{ justifyContent: "space-between", marginTop: ".35rem" }}>
              <Badge tone={v[0]}>B : {v[1]}</Badge>
              <span className="small muted">{r.pct === null ? "–" : `${r.pct > 0 ? "+" : ""}${fmt(r.pct)} %`}</span>
            </div>
          </div>);
      })}
    </div>
  );
}

export default function Rapports() {
  const { can } = useAuth();
  const [tab, setTab] = useState("compare");
  const [cfg, setCfg] = useState(null);
  const [cmp, setCmp] = useState({ a: "S0_fixed_time", b: "S3_rl_qlearning", scale: 5 });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [runs, setRuns] = useState(null);
  const [src, setSrc] = useState("application");
  const [q, setQ] = useState("");

  useEffect(() => { getJSON("/config").then(setCfg).catch(() => {}); }, []);
  useEffect(() => { if (tab === "history" && runs === null) getJSON("/runs").then((r) => setRuns(r.runs)).catch((e) => { setErr(e.message); setRuns([]); }); }, [tab, runs]);

  const compare = async () => {
    setErr(""); setBusy(true);
    try { setRes(await getJSON(`/compare?a=${cmp.a}&b=${cmp.b}&scale=${cmp.scale}`)); } catch (e) {
      setErr(e.status === 404 ? "Aucune série d'évaluation disponible pour ces stratégies à ce niveau de trafic." : e.message); setRes(null);
    } finally { setBusy(false); }
  };
  useEffect(() => { compare(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const list = useMemo(() => (runs || []).filter((r) => (src === "all" || r.source === src || (src === "évaluation" && r.source === "démo"))
    && (!q || `${strategyName(r.strategy)} ${r.name}`.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => (a.name < b.name ? 1 : -1)), [runs, src, q]);
  const strategies = (cfg?.strategies || []).filter((s) => STRATEGIES[s.id]);
  const set = (k) => (e) => setCmp({ ...cmp, [k]: e.target.value });

  return (
    <div className="stack">
      <PageHeader eyebrow="Analyse" title="Rapports"
        subtitle="Comparaison des stratégies de gestion des feux, indicateurs de performance et historique des simulations."
        actions={<>
          <a className="btn" href={`${API}/export/kpi_runs.csv`}><Icon name="download" size={16} />Exporter (CSV)</a>
          <button className="btn btn-primary" type="button" onClick={() => window.print()}><Icon name="printer" size={16} />Imprimer / PDF</button>
        </>} />

      <div className="no-print"><Tabs value={tab} onChange={setTab} label="Rapports" tabs={[["compare", "Comparaison des stratégies"], ["history", "Historique des simulations"]]} /></div>
      {err && <Notice tone="bad">{err}</Notice>}

      {tab === "compare" && (<>
        <Card title="Comparer deux stratégies" icon="report" subtitle="Moyenne ± écart-type sur la série d'évaluation (mêmes conditions de trafic pour les deux stratégies)">
          <div className="row no-print" style={{ alignItems: "flex-end", gap: ".8rem" }}>
            {["a", "b"].map((k) => (
              <div className="field" key={k} style={{ margin: 0, flex: "1 1 16rem" }}><label htmlFor={`s${k}`}>Stratégie {k.toUpperCase()}</label>
                <select id={`s${k}`} value={cmp[k]} onChange={set(k)}>
                  {strategies.map((s) => <option key={s.id} value={s.id}>{STRATEGIES[s.id].name}</option>)}
                </select></div>))}
            <div className="field" style={{ margin: 0 }}><label htmlFor="cs">Trafic</label>
              <select id="cs" value={cmp.scale} onChange={set("scale")}><option value={1}>Normal (×1)</option><option value={5}>Congestion (×5)</option></select></div>
            <button className="btn btn-primary" type="button" onClick={compare} disabled={busy}>{busy ? <span className="spinner" /> : <Icon name="refresh" size={16} />}Comparer</button>
          </div>
        </Card>
        {busy && !res && <Spinner label="Calcul de la comparaison…" />}
        {res && (<>
          <Card title={`${strategyName(res.a.id)} (A) face à ${strategyName(res.b.id)} (B)`} icon="forecast"
            subtitle={`Trafic ×${res.scale} · ${res.a.n} simulations par stratégie · plus bas = meilleur, sauf « véhicules arrivés »`}>
            <CompareBars res={res} />
          </Card>
          <Card flush title="Tous les indicateurs" icon="report">
            <div className="table-wrap">
              <table>
                <thead><tr><th>Indicateur</th><th className="num">A · {STRATEGIES[res.a.id]?.short}</th><th className="num">B · {STRATEGIES[res.b.id]?.short}</th><th className="num">Écart B / A</th><th>Lecture</th></tr></thead>
                <tbody>{res.rows.map((r) => {
                  const v = VERDICT[r.verdict] || ["neutral", r.verdict];
                  return (
                    <tr key={r.kpi}><td className="cell-main">{r.label.replace(" simulé", "")}</td>
                      <td className="num">{fmt(r.a_mean, 2)} ± {fmt(r.a_std, 2)}</td><td className="num">{fmt(r.b_mean, 2)} ± {fmt(r.b_std, 2)}</td>
                      <td className="num">{r.pct === null ? "–" : `${r.pct > 0 ? "+" : ""}${fmt(r.pct)} %`}</td><td><Badge tone={v[0]}>{v[1]}</Badge></td></tr>);
                })}</tbody>
              </table>
            </div>
            <p className="hint" style={{ padding: ".8rem 1.2rem 1rem", margin: 0 }}>« Écart non significatif » : la différence est inférieure à deux écarts-types entre simulations. Toutes les valeurs sont issues de l'environnement de simulation.</p>
          </Card>
        </>)}
      </>)}

      {tab === "history" && (
        <Card flush title="Historique des simulations" icon="clock" subtitle={runs ? `${list.length} simulation(s) affichée(s)` : ""}
          actions={<div className="row no-print">
            <select aria-label="Origine des simulations" value={src} onChange={(e) => setSrc(e.target.value)} style={{ width: "auto" }}>
              <option value="application">Lancées depuis la plateforme</option><option value="évaluation">Série d'évaluation</option><option value="all">Toutes</option>
            </select>
            <input aria-label="Rechercher" placeholder="Rechercher une stratégie…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: "14rem" }} />
          </div>}>
          {runs === null ? <div style={{ padding: "1.5rem" }}><Spinner label="Chargement…" /></div> : list.length === 0 ? <Empty icon="clock" title="Aucune simulation" /> : (
            <div className="table-wrap scroll" style={{ maxHeight: "36rem" }}>
              <table>
                <thead><tr><th>Simulation</th><th>Stratégie</th><th className="num">Trafic</th><th className="num">Trajet (s)</th><th className="num">Attente (s)</th>
                  <th className="num">File (véh.)</th><th className="num">CO₂ (kg)</th>{can("admin") && <th>Fichiers</th>}</tr></thead>
                <tbody>{list.map((r) => {
                  const p = parseRun(r.name);
                  return (
                    <tr key={r.id}>
                      <td><span className="cell-main">{p.date || "Série d'évaluation"}</span><span className="cell-sub">graine {r.seed}{r.stopped_early ? " · arrêtée avant la fin" : ""}{p.extras?.length ? ` · ${p.extras.join(", ")}` : ""}</span></td>
                      <td>{strategyName(r.strategy)}</td><td className="num">×{fmt(r.scale)}</td>
                      <td className="num">{fmt(r.avg_travel_time_s)}</td><td className="num">{fmt(r.avg_waiting_time_s)}</td>
                      <td className="num">{fmt(r.avg_queue_veh)}</td><td className="num">{fmt(r.co2_kg)}</td>
                      {can("admin") && <td>{r.files.map((f) => <a key={f} href={`${API}/runs/${encodeURIComponent(r.id)}/files/${f}`} style={{ marginRight: ".5rem" }}>{f.replace(/\.(csv|json)$/, "")}</a>)}</td>}
                    </tr>);
                })}</tbody>
              </table>
            </div>)}
        </Card>)}
    </div>
  );
}
