"use client";
// Section technique (2026-11-03), administrators only (the backend refuses these routes to other roles).
// Internal information removed from the client pages lives here: data sources, internal reports, diagnostics,
// technical strategy descriptions. Former pages: donnees/page.jsx.bak_20261103, rapports/page.jsx.bak_20261103.
import { useEffect, useState } from "react";
import { getJSON } from "@/components/api";
import { Badge, Card, Notice, PageHeader, Spinner, Tabs } from "@/components/ui";

function Sources() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { getJSON("/data-sources").then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <Notice tone="bad">{err}</Notice>;
  if (!d) return <Spinner label="Chargement…" />;
  return (
    <div className="stack">
      <div className="grid g-2">
        {d.sources.map((s) => (
          <Card key={s.name} title={s.name} actions={<Badge tone={s.origin === "réelle" ? "info" : "sim"}>{s.origin}</Badge>}>
            <p>{s.description}</p><p className="hint">{s.period}</p><p className="small"><strong>Usage dans le projet :</strong> {s.use}</p>
          </Card>))}
      </div>
      {d.readiness && Object.keys(d.readiness).length > 0 && (
        <Card title="Ce que les données réelles permettent aujourd'hui">
          <table><thead><tr><th>Objectif</th><th>Verdict mesuré</th></tr></thead>
            <tbody>{Object.entries(d.readiness).map(([k, v]) => <tr key={k}><td>{v.label}</td><td>{v.verdict}</td></tr>)}</tbody></table>
          <p className="hint" style={{ marginTop: ".6rem" }}>Source : data/reports/readiness_by_objective_v1.json. Calibration PCH ↔ simulation : échec documenté (DATA_VALIDATION_REPORT.md).</p>
        </Card>)}
    </div>
  );
}

function Reports() {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState("");
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { getJSON("/reports").then((r) => { setList(r.reports); if (r.reports[0]) setSel(r.reports[0]); }).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { if (sel) getJSON(`/reports/${encodeURIComponent(sel)}`).then((r) => setText(r.text)).catch((e) => setErr(e.message)); }, [sel]);
  return (
    <div className="stack">
      {err && <Notice tone="bad">{err}</Notice>}
      <div className="field" style={{ maxWidth: 560 }}><label htmlFor="rp">Rapport interne</label>
        <select id="rp" value={sel} onChange={(e) => setSel(e.target.value)}>{list.map((r) => <option key={r}>{r}</option>)}</select></div>
      <div className="report">{text}</div>
    </div>
  );
}

function Diagnostics() {
  const [d, setD] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    getJSON("/diagnostics").then(setD).catch((e) => setErr(e.message));
    getJSON("/config").then(setCfg).catch(() => {});
  }, []);
  return (
    <div className="grid g-2">
      <Card title="Moteur de simulation">
        {err && <Notice tone="bad">{err}</Notice>}
        {!d && !err && <Spinner label="Interrogation de SUMO…" />}
        {d && <table><tbody>{Object.entries(d).map(([k, v]) => (
          <tr key={k}><td className="cell-main" style={{ whiteSpace: "nowrap" }}>{k}</td><td style={{ overflowWrap: "anywhere" }}><code>{String(v)}</code></td></tr>))}</tbody></table>}
      </Card>
      <Card title="Stratégies (description technique)">
        {cfg && <table><thead><tr><th>Code</th><th>Libellé</th><th>Description</th></tr></thead>
          <tbody>{cfg.strategies.map((s) => <tr key={s.id}><td><code>{s.id}</code>{!s.available && <Badge tone="warn">indisponible</Badge>}</td><td>{s.label}</td><td className="why">{s.description}</td></tr>)}</tbody></table>}
        {cfg && <p className="hint" style={{ marginTop: ".6rem" }}>Origine des données : <code>{cfg.data_origin}</code></p>}
      </Card>
    </div>
  );
}

export default function Technique() {
  const [tab, setTab] = useState("diag");
  return (
    <div className="stack">
      <PageHeader eyebrow="Administration" title="Section technique"
        subtitle="Informations internes de développement et de recherche, non affichées aux autres utilisateurs." actions={<Badge tone="warn">Administrateurs</Badge>} />
      <Tabs value={tab} onChange={setTab} label="Section technique" tabs={[["diag", "Diagnostic"], ["sources", "Sources de données"], ["reports", "Rapports internes"]]} />
      {tab === "diag" && <Diagnostics />}
      {tab === "sources" && <Sources />}
      {tab === "reports" && <Reports />}
    </div>
  );
}
