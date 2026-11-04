"use client";
// IA explicable (XAI) - dashboard (2026-11-04; previous versions: XaiClient.jsx.bak_20261103 / .bak_20261104).
// Data, unchanged since 2026-10-29: GET /api/health, /api/xai/runs, /api/xai/decisions[?run=], /api/xai/shap?index=[&run=].
// No value is computed or invented here: the SHAP numbers come from agents/xai/shap_qtable.py through the backend, and
// decisions refused by the backend (not admissible) never get SHAP values.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API } from "@/components/api";
import Icon from "@/components/icons";
import { useAuth } from "@/components/session";
import { parseRun, strategyName, strategyShort } from "@/components/traffic";
import { Card, Distribution, Hero, NotAdmissible, ObservedState, ORIGINS, QCompare, Ring, ShapChart, SimpleExplanation, Technical, Waterfall, num, origin } from "./XaiParts";
import s from "./xai.module.css";

const ACTIVE = ["starting", "running", "paused", "stopping"];
const STATUS_FR = { idle: "Aucune simulation", starting: "Démarrage", running: "En cours", paused: "En pause", stopping: "Arrêt en cours",
  finished: "Terminée", stopped: "Arrêtée", error: "Erreur", incomplete: "Incomplète" };

async function api(path) {
  let r;
  try {
    r = await fetch(`${API}${path}`, { cache: "no-store" });
  } catch {
    const e = new Error("serveur injoignable");
    e.network = true;
    throw e;
  }
  const body = await r.json().catch(() => ({}));
  if (r.status === 401 && typeof window !== "undefined") {
    window.location.assign(`/login/?expired=1&next=${encodeURIComponent(window.location.pathname)}`);
  }
  if (!r.ok) {
    const d = body.detail;
    const e = new Error(typeof d === "string" ? d : d?.message || `erreur HTTP ${r.status}`);
    e.status = r.status;
    e.code = typeof d === "object" ? d?.code : undefined;
    throw e;
  }
  return body;
}

function ShapSection({ d, shap, onRetry, view, isAdmin }) {
  if (!d.shap.eligible) {
    return view === "tech" ? <NotAdmissible d={d} /> : <div className={s.shapGrid}><NotAdmissible d={d} /><QCompare d={d} res={null} /></div>;
  }
  if (!shap || shap.state === "loading") {
    return <Card><p role="status" style={{ margin: 0 }}><span className={s.spinner} />Calcul exact des valeurs de Shapley par le moteur XAI…</p></Card>;
  }
  if (shap.state === "error") {
    return (
      <div className={`${s.notice} ${s.noticeError}`} role="alert">
        <Icon name="alert" size={18} />
        <div><strong>{shap.code === "verification_failed" ? "Vérification refusée : " : "Calcul impossible : "}</strong>{shap.message}
          {shap.code !== "not_eligible" && shap.code !== "verification_failed" && <> <button className={s.btn} type="button" onClick={onRetry}>Réessayer</button></>}</div>
      </div>);
  }
  const r = shap.data;
  const action = d.explanation?.action || "passer";
  if (view === "tech") return <Technical d={d} res={r} isAdmin={isAdmin} />;
  return (
    <>
      <div className={s.shapGrid}>
        <Card title="Facteurs qui ont influencé la décision" icon="xai"
          sub={`Contributions SHAP exactes à l'écart Δ = Q(passer) − Q(garder) = ${num(r.delta, 3)}, par rapport à la situation habituelle (${num(r.base_value, 3)})`}>
          <ShapChart res={r} action={action} />
          <p className={s.note} style={{ marginTop: ".9rem" }}>
            Additivité {r.additivity.ok ? "vérifiée" : "NON vérifiée"} : référence {num(r.base_value, 3)} + somme des contributions = {num(r.additivity.base_plus_sum, 3)} = Δ.
            {" "}Détails dans la vue technique.</p>
        </Card>
        <QCompare d={d} res={r} />
      </div>
      <div className={s.shapGrid}>
        <SimpleExplanation d={d} res={r} />
        <Card title="De la situation habituelle à cette décision" icon="forecast" sub="Chaque facteur déplace l'écart Δ ; la dernière ligne est l'écart réel de la table">
          <Waterfall res={r} />
        </Card>
      </div>
    </>
  );
}

export default function XaiClient() {
  const { can } = useAuth();
  const isAdmin = can("admin");
  const [conn, setConn] = useState("checking");
  const [runs, setRuns] = useState([]);
  const [run, setRun] = useState("");                 // "" = current simulation, otherwise a recorded run folder
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [sel, setSel] = useState(null);
  const [follow, setFollow] = useState(true);         // keep the most recent decision selected
  const [shaps, setShaps] = useState({});
  const [updated, setUpdated] = useState(null);
  const [view, setView] = useState("simple");
  const [q, setQ] = useState("");
  const [fTls, setFTls] = useState("");
  const [fOrigin, setFOrigin] = useState("");
  const [fAdm, setFAdm] = useState("all");
  const [order, setOrder] = useState("desc");
  const runKey = data ? (data.run || "") : "";
  const lastRun = useRef(null);

  const loadRuns = useCallback(() => api("/xai/runs").then((r) => setRuns(r.runs)).catch(() => {}), []);

  const refresh = useCallback(async () => {
    try {
      await api("/health");
      setConn("ok");
    } catch (e) {
      setConn("down");
      setErr(e);
      return;
    }
    try {
      const d = await api(`/xai/decisions${run ? `?run=${encodeURIComponent(run)}` : ""}`);
      setData(d);
      setErr(null);
      setUpdated(new Date().toLocaleTimeString("fr-FR"));
      if (lastRun.current !== `${run}|${d.run}`) {          // new run: empty selection, follow the latest decision
        lastRun.current = `${run}|${d.run}`;
        setSel(null);
        setFollow(true);
        setShaps({});
        loadRuns();
      }
    } catch (e) {
      setErr(e);
    }
  }, [run, loadRuns]);

  useEffect(() => { loadRuns(); }, [loadRuns]);
  useEffect(() => {
    refresh();
    const live = !run && data && ACTIVE.includes(data.status);
    const t = setInterval(refresh, run ? 15000 : live ? 2000 : 5000);
    return () => clearInterval(t);
  }, [refresh, run, data?.status]);   // eslint-disable-line react-hooks/exhaustive-deps

  const decisions = data?.decisions || [];
  useEffect(() => {                                       // "Dernière décision de l'agent"
    if (follow && decisions.length) setSel(decisions[decisions.length - 1].index);
  }, [follow, decisions.length]);   // eslint-disable-line react-hooks/exhaustive-deps

  const carrefours = useMemo(() => [...new Set(decisions.map((d) => d.carrefour))].sort(), [decisions]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = decisions.filter((d) => (!fTls || d.carrefour === fTls) && (!fOrigin || origin(d).key === fOrigin)
      && (fAdm === "all" || (fAdm === "yes") === d.shap.eligible)
      && (!needle || `${d.clock} ${d.carrefour} phase ${d.from_phase} ${d.to_phase} ${origin(d).text}`.toLowerCase().includes(needle)));
    return order === "desc" ? [...list].reverse() : list;
  }, [decisions, q, fTls, fOrigin, fAdm, order]);
  const current = sel === null ? null : decisions[sel] || null;
  const shapKey = current ? `${runKey}#${current.index}` : null;

  const computeShap = useCallback((d) => {
    const key = `${runKey}#${d.index}`;
    setShaps((m) => ({ ...m, [key]: { state: "loading" } }));
    const path = `/xai/shap?index=${d.index}${run ? `&run=${encodeURIComponent(run)}` : ""}`;
    api(path).then((r) => {
      if (r.index !== d.index || (run && r.decision.run !== run)) throw new Error("réponse incohérente avec la décision demandée");
      setShaps((m) => ({ ...m, [key]: { state: "ok", data: r } }));
    }).catch((e) => setShaps((m) => ({ ...m, [key]: { state: "error", message: e.message, code: e.code } })));
  }, [runKey, run]);

  useEffect(() => {
    if (current && current.shap.eligible && !shaps[shapKey]) computeShap(current);
  }, [current, shapKey, shaps, computeShap]);

  const status = run ? (data?.status || "–") : (data?.status || (conn === "ok" ? "idle" : "–"));
  const waiting = conn === "ok" && !run && data?.status === "idle";
  const count = data?.count ?? 0, eligible = data?.eligible ?? 0;
  const pct = count ? (100 * eligible) / count : 0;
  const shapRes = shaps[shapKey]?.state === "ok" ? shaps[shapKey].data : null;
  const pick = (i) => { setSel(i); setFollow(false); };

  return (
    <div className={s.dash}>
      <div className={s.head}>
        <div>
          <div className={s.eyebrow}>Intelligence artificielle</div>
          <h1>Explicabilité de l'IA (XAI)</h1>
          <p className={s.sub}>Pourquoi l'agent IA a-t-il changé de phase ? Chaque décision réelle de la simulation, ce que l'agent a observé,
            et l'explication exacte de son choix.</p>
        </div>
        <div className={s.headRight}>
          <span className={`${s.pill} ${conn === "ok" ? s.pillOk : conn === "down" ? s.pillBad : ""}`}>
            {conn === "ok" ? "Serveur connecté" : conn === "down" ? "Serveur injoignable" : "Connexion…"}</span>
          <div className={s.viewSwitch} role="tablist" aria-label="Niveau de lecture">
            <button type="button" role="tab" aria-selected={view === "simple"} onClick={() => setView("simple")}>Vue simplifiée</button>
            <button type="button" role="tab" aria-selected={view === "tech"} onClick={() => setView("tech")}>Vue technique</button>
          </div>
        </div>
      </div>

      <section className={s.card} style={{ marginBottom: "1rem" }}>
        <div className={s.toolbar}>
          <div>
            <label htmlFor="xai-run">Décisions affichées</label>
            <select id="xai-run" value={run} onChange={(e) => { setRun(e.target.value); setData(null); }}>
              <option value="">Simulation courante</option>
              {runs.map((r) => <option key={r.run} value={r.run}>{parseRun(r.run).label} — {r.decisions} décision(s){r.finished ? "" : " (incomplète)"}</option>)}
            </select>
          </div>
          <div className={s.headRight}>
            <span className={`${s.pill} ${ACTIVE.includes(status) ? s.pillOk : s.pillInfo}`}>{STATUS_FR[status] || status}</span>
            {updated && <span className={s.updated}>Mise à jour {updated}</span>}
          </div>
        </div>
        {conn === "down" && (
          <div className={`${s.notice} ${s.noticeError}`} role="alert"><Icon name="alert" size={18} />
            <div><strong>Serveur injoignable.</strong> La plateforme n'obtient aucune réponse du serveur. Cette page se mettra à jour seule dès son retour
              {isAdmin ? <> (démarrage depuis la racine du projet : <code>python -m app.backend.server</code>, réponse attendue de {API}).</> : " ; si le problème persiste, contactez l'administrateur."}</div>
          </div>)}
        {conn === "ok" && err && <div className={`${s.notice} ${s.noticeError}`} role="alert"><Icon name="alert" size={18} /><div><strong>Erreur du module d'explication :</strong> {err.message}</div></div>}
        {waiting && (
          <div className={`${s.notice} ${s.noticeInfo}`} role="status"><Icon name="info" size={18} />
            <div><strong>En attente d'une simulation.</strong> Lancez une simulation depuis la page Simulation : ses décisions apparaîtront ici pendant
              l'exécution et resteront consultables après la fin. Vous pouvez aussi ouvrir une simulation enregistrée dans la liste ci-dessus.</div></div>)}
        {data?.note && !waiting && <div className={`${s.notice} ${s.noticeInfo}`} role="status"><Icon name="info" size={18} /><div>{data.note}</div></div>}
        {!data && conn !== "down" && !err && <p role="status" style={{ margin: 0 }}><span className={s.spinner} />Chargement des décisions…</p>}
      </section>

      <div className={s.kpis} aria-live="polite">
        <div className={`${s.card} ${s.kpi} ${s.kCyan}`}>
          <div className={s.kpiTop}>Décisions de l'agent<span className={s.kpiIcon}><Icon name="signal" size={16} /></span></div>
          <div className={s.kpiValue}>{data ? count : "–"}</div>
          <div className={s.kpiSub}>changements de phase enregistrés dans cette simulation</div>
        </div>
        <div className={`${s.card} ${s.kpi} ${s.kGreen}`}>
          <div className={s.kpiTop}>Explicables par SHAP<span className={s.kpiIcon}><Icon name="check" size={16} /></span></div>
          <div className={s.kpiValue}>{data ? eligible : "–"}</div>
          <div className={s.kpiSub}>décisions prises par la table apprise de l'agent IA</div>
        </div>
        <div className={`${s.card} ${s.kpi} ${s.kOrange}`}>
          <div className={s.kpiTop}>Non admissibles<span className={s.kpiIcon}><Icon name="info" size={16} /></span></div>
          <div className={s.kpiValue}>{data ? count - eligible : "–"}</div>
          <div className={s.kpiSub}>règle de secours, sécurité ou autre stratégie : pas de SHAP</div>
        </div>
        <div className={`${s.card} ${s.kpi} ${s.kBlue}`}>
          <div className={s.kpiTop}>Part explicable<span className={s.kpiIcon}><Icon name="xai" size={16} /></span></div>
          <div className={s.kpiRow}><Ring pct={pct} color="#3D8BFD" /><div className={s.kpiValue}>{data && count ? `${Math.round(pct)} %` : "–"}</div></div>
          <div className={s.kpiSub}>des décisions de cette simulation</div>
        </div>
        <div className={`${s.card} ${s.kpi} ${s.kViolet}`}>
          <div className={s.kpiTop}>Stratégie<span className={s.kpiIcon}><Icon name="play" size={16} /></span></div>
          <div className={`${s.kpiValue} ${s.kpiValueSm}`}>{data?.strategy ? strategyShort(data.strategy) : "–"}</div>
          <div className={s.kpiSub}>{data?.strategy ? strategyName(data.strategy) : "aucune simulation"}{isAdmin && data?.run ? ` · ${data.run}` : ""}{isAdmin && data?.source ? ` · source : ${data.source}` : ""}</div>
        </div>
      </div>

      {data && count > 0 && (
        <div className={s.layout}>
          <Card title={`Décisions (${shown.length}${shown.length !== count ? ` sur ${count}` : ""})`} icon="report" sub="Cliquez une décision pour voir son explication"
            aria-label="Liste des décisions">
            <Distribution decisions={decisions} />
            <div className={s.filters} style={{ marginTop: ".8rem" }}>
              <div className={s.full}><label htmlFor="xai-q">Rechercher</label>
                <input id="xai-q" type="search" placeholder="heure, carrefour, phase…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
              <div><label htmlFor="xai-tls">Carrefour</label>
                <select id="xai-tls" value={fTls} onChange={(e) => setFTls(e.target.value)}>
                  <option value="">Tous</option>{carrefours.map((c) => <option key={c}>{c}</option>)}</select></div>
              <div><label htmlFor="xai-origin">Stratégie / règle</label>
                <select id="xai-origin" value={fOrigin} onChange={(e) => setFOrigin(e.target.value)}>
                  <option value="">Toutes</option>{Object.entries(ORIGINS).map(([k, o]) => <option key={k} value={k}>{o.short}</option>)}</select></div>
              <div><span style={{ fontSize: ".72rem", fontWeight: 650, display: "block", marginBottom: ".2rem", color: "var(--d-ink-2)" }}>Statut SHAP</span>
                <div className={s.seg} role="radiogroup" aria-label="Statut SHAP">
                  {[["all", "Tous"], ["yes", "SHAP"], ["no", "Non adm."]].map(([v, l]) => (
                    <button key={v} type="button" role="radio" aria-checked={fAdm === v} onClick={() => setFAdm(v)}>{l}</button>))}
                </div></div>
              <div><label htmlFor="xai-order">Ordre</label>
                <select id="xai-order" value={order} onChange={(e) => setOrder(e.target.value)}>
                  <option value="desc">Récentes d'abord</option><option value="asc">Anciennes d'abord</option></select></div>
            </div>
            <div className={s.listMeta}>
              <span>{follow ? "Suit la dernière décision" : "Sélection manuelle"}</span>
              {!follow && <button type="button" className={s.linkBtn} onClick={() => setFollow(true)}>Revenir à la dernière décision</button>}
            </div>
            <div className={s.list}>
              {shown.length === 0 && <div className={s.empty}><strong>Aucune décision</strong>ne correspond à ces filtres.</div>}
              {shown.map((d) => {
                const o = origin(d);
                return (
                  <button key={d.index} type="button" className={s.item} aria-pressed={sel === d.index} onClick={() => pick(d.index)}>
                    <span className={s.itemTime}>{d.clock}</span>
                    <span className={s.itemMain}><strong>{d.carrefour}</strong> · phase {d.from_phase} → {d.to_phase}
                      <span className={s.itemSub}><i className={s.sw} style={{ background: ORIGINS[o.key].color, marginRight: ".35rem" }} />{o.text}</span></span>
                    <span className={`${s.badge} ${d.shap.eligible ? s.badgeYes : s.badgeNo}`}>{d.shap.eligible ? "SHAP" : "non admissible"}</span>
                  </button>);
              })}
            </div>
          </Card>

          <div className={s.detail}>
            {!current && <Card><div className={s.empty}><strong>Sélectionnez une décision</strong>dans la liste pour voir son explication.</div></Card>}
            {current && (<>
              <Hero d={current} res={shapRes} isAdmin={isAdmin} />
              {view === "simple" && <ObservedState d={current} res={shapRes} />}
              <ShapSection d={current} shap={shaps[shapKey]} onRetry={() => computeShap(current)} view={view} isAdmin={isAdmin} />
              {view === "tech" && !current.shap.eligible && (
                <Card title="Explication enregistrée au moment de la décision" icon="report">
                  <dl className={s.facts}>{Object.entries(current.explanation || {}).map(([k, v]) => (
                    <span key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></span>))}</dl>
                </Card>)}
            </>)}
          </div>
        </div>)}

      <Card title="Limites de l'explication" icon="info" style={{ marginTop: "1rem" }}>
        <ul className={s.limits}>
          <li>SHAP n'est calculé que pour les décisions « passer » prises par la table apprise de l'agent IA (S3). Les décisions de la règle de secours,
            des règles de sécurité et des autres stratégies (S2, S2F, max-pressure) sont affichées avec leur explication enregistrée, sans valeurs SHAP.</li>
          <li>Le plan fixe et les feux adaptatifs standards (S0, S1) n'enregistrent aucune décision : leurs feux suivent le programme du simulateur.</li>
          <li>SHAP décrit la sortie de la table (Δ = Q(passer) − Q(garder)), pas un effet causal sur le trafic. Le résultat dépend du fond de référence
            (situations de la table pondérées par les visites) ; une partie des valeurs Q utilisées est peu fiable (part indiquée dans la vue technique).</li>
          <li>Les variables sont des classes (intervalles), pas des comptages exacts. Toutes les données viennent de la simulation.</li>
        </ul>
      </Card>
    </div>
  );
}
