"use client";
// Visual building blocks of the XAI dashboard (2026-11-04). Every number shown comes from the backend:
//   GET /api/xai/decisions  -> decision rows (+ explanation recorded by the agent at decision time, admissibility)
//   GET /api/xai/shap       -> exact SHAP result of agents/xai/shap_qtable.py (Q values of the frozen table, contributions,
//                              base value, additivity, background statistics)
// Nothing is estimated here: the texts only put these numbers into words; signs are never changed.
import Icon from "@/components/icons";
import s from "./xai.module.css";

export const QCLS = ["0", "1–2", "3–5", "6–10", "> 10"];
export const MCLS = ["0", "1–2", "3–5", "> 5"];
export const TCLS = ["≤ 10 s", "11–20 s", "21–40 s", "> 40 s"];
// Class bounds = agents/decision/controllers.py (Q_EDGES, M_EDGES, T_EDGES). file_autre = longest queue of ANOTHER phase.
export const VARS = {
  file_servie: { name: "Véhicules en attente sur la voie au vert", short: "En attente au vert", icon: "car", classes: QCLS },
  file_autre: { name: "Véhicules en attente sur les autres voies", short: "En attente ailleurs", icon: "timer", classes: QCLS,
    hint: "file la plus longue d'une autre phase" },
  en_mouvement: { name: "Véhicules en mouvement sur la voie au vert", short: "En mouvement au vert", icon: "route", classes: MCLS },
  "durée_vert": { name: "Durée actuelle du feu vert", short: "Durée du vert", icon: "clock", classes: TCLS },
};
export const VAR_ORDER = ["file_servie", "file_autre", "en_mouvement", "durée_vert"];
const ACTION_FR = { passer: "passer à la phase suivante", garder: "garder le vert" };

export const num = (v, d = 3) => (v === null || v === undefined || Number.isNaN(Number(v)) ? "–" :
  `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d })}`);
const plain = (v, d = 3) => (v === null || v === undefined ? "–" : Number(v).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d }));

// Who decided (from the recorded explanation; same categories as the backend admissibility rule).
export const ORIGINS = {
  table: { label: "Agent IA · table apprise", short: "Agent IA (table apprise)", color: "#2BC48A" },
  fallback: { label: "Agent IA · règle de secours S2", short: "Règle de secours", color: "#F59E0B" },
  safety: { label: "Règle de sécurité · vert maximum", short: "Sécurité (vert max.)", color: "#F2555A" },
  rule: { label: "Agent à règles / max-pressure", short: "Autre stratégie", color: "#9B87F5" },
  unknown: { label: "Sans explication enregistrée", short: "Non documentée", color: "#8EA3BD" },
};
export function origin(d) {
  const e = d.explanation || {};
  const src = String(e.source || "");
  if (d.reason === "max_green" || src.startsWith("sécurité")) return { key: "safety", text: "Règle de sécurité : vert maximum atteint" };
  if (src === "table apprise") return { key: "table", text: "table apprise" };
  if (src.startsWith("règle de secours")) return { key: "fallback", text: src };
  if (src) return { key: "rule", text: src };
  return { key: "unknown", text: d.reason === "agent_decision" ? "décision sans explication enregistrée" : d.reason };
}

export function Ring({ pct, size = 52, color = "#2BC48A" }) {
  const r = (size - 8) / 2, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct || 0));
  return (
    <svg className={s.ring} width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,.1)" strokeWidth="6" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${(p / 100) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  );
}

export function Card({ title, icon, sub, actions, className = "", children, ...rest }) {
  return (
    <section className={`${s.card} ${className}`} {...rest}>
      {(title || actions) && (
        <div className={s.cardHead}>
          <div className={s.cardTitle}>
            {icon && <span className={s.cardIcon}><Icon name={icon} size={17} /></span>}
            <div>{title && <h2>{title}</h2>}{sub && <p className={s.cardSub}>{sub}</p>}</div>
          </div>
          {actions}
        </div>)}
      {children}
    </section>
  );
}

export function Distribution({ decisions }) {
  const n = { table: 0, fallback: 0, safety: 0, rule: 0, unknown: 0 };
  for (const d of decisions) n[origin(d).key] += 1;
  const total = decisions.length || 1;
  const keys = Object.keys(n).filter((k) => n[k] > 0);
  return (
    <div>
      <div className={s.dist} role="img" aria-label={`Répartition : ${keys.map((k) => `${ORIGINS[k].short} ${n[k]}`).join(", ")}`}>
        {keys.map((k) => <span key={k} style={{ width: `${(100 * n[k]) / total}%`, background: ORIGINS[k].color }} />)}
      </div>
      <div className={s.distLegend}>
        {keys.map((k) => <span key={k}><i className={s.sw} style={{ background: ORIGINS[k].color }} />{ORIGINS[k].short} · {n[k]}</span>)}
      </div>
    </div>
  );
}

function Gauge({ classes, idx }) {
  return (
    <div>
      <div className={s.gauge} style={{ gridTemplateColumns: `repeat(${classes.length}, 1fr)` }} aria-hidden="true">
        {classes.map((c, i) => <span key={c} className={i <= idx ? s.on : ""} />)}
      </div>
      <div className={s.gaugeLabels}><span>{classes[0]}</span><span>{classes[classes.length - 1]}</span></div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ hero (B)
export function Hero({ d, res, isAdmin }) {
  const o = origin(d);
  const e = d.explanation || {};
  const action = e.action || (d.to_phase !== d.from_phase ? "passer" : "garder");
  const lc = res?.logged_check;
  const qg = lc ? lc.q_garder_table : e.q_garder, qp = lc ? lc.q_passer_table : e.q_passer;
  const tableChoice = qg !== null && qg !== undefined && qp !== null && qp !== undefined ? (qp > qg ? "passer" : qp < qg ? "garder" : null) : null;
  const ruleBox = o.key !== "table";
  let because = null;
  if (o.key === "table" && tableChoice === action) {
    because = <>L'agent a choisi de <strong>{ACTION_FR[action]}</strong> parce que, dans sa table apprise, la valeur de « {action} » (<strong>{plain(action === "passer" ? qp : qg)}</strong>)
      était supérieure à celle de « {action === "passer" ? "garder" : "passer"} » (<strong>{plain(action === "passer" ? qg : qp)}</strong>).</>;
  } else if (o.key === "fallback") {
    because = <>La table de l'agent ne connaissait pas assez cette situation : une <strong>règle de secours simple</strong> a décidé de {ACTION_FR[action]}. Les valeurs de la table n'ont pas été utilisées.</>;
  } else if (o.key === "safety") {
    because = <>Le feu était vert depuis <strong>{e.vert_s ?? d.green_duration_s} s</strong>, la durée maximale autorisée{e.limite_s ? ` (${e.limite_s} s)` : ""} : la <strong>règle de sécurité</strong> a imposé le changement de phase.</>;
  } else if (o.key === "rule") {
    because = <>Décision prise par la règle « {e.source} » de la stratégie, pas par une table apprise.</>;
  }
  return (
    <Card className={s.hero} aria-label="Décision sélectionnée">
      <div className={s.heroTop}>
        <div>
          <div className={s.eyebrow}>Pourquoi l'IA a-t-elle pris cette décision ?</div>
          <h2 className={s.heroTitle}>Décision du {d.carrefour} à {d.clock}</h2>
          <div className={s.heroMeta}>
            <span className={s.chip}><Icon name="signal" size={14} />{ORIGINS[o.key].label}</span>
            <span className={s.chip}><Icon name="clock" size={14} />vert pendant {d.green_duration_s} s</span>
            {isAdmin && <span className={s.chip}>feu {d.tls}</span>}
          </div>
        </div>
        <span className={`${s.badge} ${d.shap.eligible ? s.badgeYes : s.badgeNo}`} style={{ fontSize: ".78rem", padding: ".25rem .7rem" }}>
          {d.shap.eligible ? "Explicable par SHAP" : "Non admissible au SHAP"}</span>
      </div>
      <div className={s.flow}>
        <div className={s.flowBox}><div className={s.flowLabel}>Phase actuelle</div><div className={s.flowValue}>Phase {d.from_phase}</div>
          <div className={s.flowSub}>au vert depuis {d.green_duration_s} s</div></div>
        <div className={s.flowArrow}><Icon name="chevronRight" size={26} /></div>
        <div className={`${s.flowBox} ${ruleBox ? s.flowRule : s.flowAction}`}>
          <div className={s.flowLabel}>{ruleBox ? "Règle appliquée" : "Décision de l'agent"}</div>
          <div className={s.flowValue} style={{ fontSize: "1.1rem" }}>{action === "passer" ? "Passer au vert suivant" : "Garder le vert"}</div>
          <div className={s.flowSub}>{ORIGINS[o.key].short}</div></div>
        <div className={s.flowArrow}><Icon name="chevronRight" size={26} /></div>
        <div className={s.flowBox}><div className={s.flowLabel}>Nouvelle phase</div><div className={s.flowValue}>Phase {d.to_phase}</div>
          <div className={s.flowSub}>{d.to_phase % 2 === 1 ? "orange de transition, puis vert suivant" : "phase suivante du cycle"}</div></div>
      </div>
      {because && <p className={s.because}>{because}</p>}
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------ observed state (C)
export function ObservedState({ d, res }) {
  const e = d.explanation || {};
  const sit = e.situation;
  const contrib = Object.fromEntries((res?.contributions || []).map((c) => [c.variable, c]));
  if (!sit && !e["règle_S2"] && !(e.vert_s !== undefined)) {
    return <Card title="État du trafic observé" icon="monitor"><p className="hint" style={{ margin: 0 }}>Aucune observation enregistrée pour cette décision.</p></Card>;
  }
  const s2 = e["règle_S2"] || (e.source === "règle S2" || e.source === "règle S2F" ? e : null);
  return (
    <Card title="État du trafic observé" icon="monitor" sub="Ce que l'agent a vu au moment de décider (enregistré à cet instant)">
      {sit && (
        <div className={s.tiles}>
          {VAR_ORDER.map((v) => {
            const meta = VARS[v];
            const idx = Number(sit[v]);
            const bg = contrib[v]?.background_classes_retained;
            let usual = null;
            if (bg) {
              const total = Object.values(bg).reduce((a, b) => a + b, 0) || 1;
              const top = Object.entries(bg).sort((a, b) => b[1] - a[1])[0];
              usual = `Situations comparables : le plus souvent « ${meta.classes[+top[0]] ?? top[0]} » (${Math.round((100 * top[1]) / total)} % du poids).`;
            }
            return (
              <div className={s.tile} key={v}>
                <div className={s.tileLabel}><Icon name={meta.icon} size={15} />{meta.name}</div>
                <div className={s.tileValue}>{meta.classes[idx] ?? sit[v]}</div>
                <Gauge classes={meta.classes} idx={idx} />
                {meta.hint && <div className={s.usual}>{meta.hint}</div>}
                {usual && <div className={s.usual}>{usual}</div>}
              </div>);
          })}
        </div>)}
      <div className={s.extra}>
        {sit && <span className={s.chip}>{+sit.phase_verte === 0 ? "1re" : `${+sit.phase_verte + 1}e`} phase verte du cycle</span>}
        {e.visites_garder_passer && <span className={s.chip}>Expérience : {e.visites_garder_passer[0]} essais « garder », {e.visites_garder_passer[1]} « passer »</span>}
        {e.vert_s !== undefined && <span className={s.chip}>Vert : {e.vert_s} s sur {e.limite_s} s autorisées</span>}
      </div>
      {s2 && (
        <div className={s.tiles} style={{ marginTop: ".7rem" }}>
          <div className={s.tile}><div className={s.tileLabel}><Icon name="car" size={15} />Arrêtés au vert (compte exact)</div><div className={s.tileValue}>{s2["arrêtés_vert"]}</div></div>
          <div className={s.tile}><div className={s.tileLabel}><Icon name="route" size={15} />En mouvement au vert</div><div className={s.tileValue}>{s2["en_mouvement_vert"]}</div></div>
          <div className={s.tile}><div className={s.tileLabel}><Icon name="timer" size={15} />En attente ailleurs (plus longue file)</div><div className={s.tileValue}>{s2["attente_autre_phase"]}</div></div>
          {s2.seuils && <div className={s.tile}><div className={s.tileLabel}><Icon name="info" size={15} />Seuils de la règle</div>
            <div className={s.tileValue} style={{ fontSize: "1rem" }}>≤ {s2.seuils[0]} arrêté · ≤ {s2.seuils[1]} en mouvement</div></div>}
        </div>)}
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------ Q comparison (F)
export function QCompare({ d, res }) {
  const e = d.explanation || {};
  const lc = res?.logged_check;
  const qg = lc ? lc.q_garder_table : e.q_garder, qp = lc ? lc.q_passer_table : e.q_passer;
  if (qg === null || qg === undefined || qp === null || qp === undefined) {
    return <Card title="Comparaison des actions possibles" icon="layers"><p className="hint" style={{ margin: 0 }}>
      Pas de valeurs Q pour cette décision {e.source?.includes("jamais vue") ? "(situation jamais vue pendant l'entraînement)" : ""}.</p></Card>;
  }
  const action = e.action || "passer";
  const ruled = origin(d).key !== "table";
  const visits = e.visites_garder_passer || lc?.visits_garder_passer || [];
  const lo = Math.min(qg, qp, 0), hi = Math.max(qg, qp, 0), span = hi - lo || 1;
  const x = (v) => `${(100 * (v - lo)) / span}%`;
  const delta = qp - qg;
  const card = (name, q, n, key) => (
    <div className={`${s.qCard} ${!ruled && action === key ? s.qChosen : ""}`}>
      {!ruled && action === key && <span className={s.qTag}>choisie</span>}
      <div className={s.qName}>{name}</div>
      <div className={s.qValue}>{plain(q)}</div>
      <div className={s.qVisits}>{n !== undefined ? `essayée ${n} fois à l'entraînement dans cette situation` : ""}</div>
    </div>);
  return (
    <Card title="Comparaison des actions possibles" icon="layers" sub={lc ? "Valeurs de la table gelée de l'agent (vérifiées contre le journal)" : "Valeurs enregistrées dans le journal de décision"}>
      <div className={s.qGrid}>
        {card("Garder la phase actuelle", qg, visits[0], "garder")}
        {card("Passer à la phase suivante", qp, visits[1], "passer")}
      </div>
      <div className={s.qBar} role="img" aria-label={`Garder ${plain(qg)}, passer ${plain(qp)}`}>
        {lo < 0 && hi > 0 && <span className={s.qZero} style={{ left: x(0) }} />}
        <span className={s.qGap} style={{ left: x(Math.min(qg, qp)), width: `${(100 * Math.abs(delta)) / span}%` }} />
        <span className={s.qMark} style={{ left: x(qg), background: "#F59E0B" }} />
        <span className={s.qMark} style={{ left: x(qp), background: "#3D8BFD" }} />
        <span className={s.qMarkLbl} style={{ left: x(qg) }}>garder</span>
        <span className={s.qMarkLbl} style={{ left: x(qp) }}>passer</span>
      </div>
      <div className={s.gapLine}>
        <span>Écart Δ = Q(passer) − Q(garder) : <strong>{num(delta, lc ? 6 : 3)}</strong></span>
        <span>{delta > 0 ? "la table préfère « passer »" : delta < 0 ? "la table préfère « garder »" : "égalité"}</span>
      </div>
      {ruled && <p className={s.note} style={{ marginTop: ".6rem" }}>
        Ces valeurs n'ont pas décidé : la situation était trop peu connue de la table (au moins une action essayée moins de 3 fois), ou une règle a imposé le changement.</p>}
      {!ruled && visits.length === 2 && <p className={s.note} style={{ marginTop: ".6rem" }}>
        Règle de confiance : la table n'est utilisée que si chaque action a été essayée au moins 3 fois dans cette situation ({visits[0]} et {visits[1]} ici).</p>}
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------ SHAP chart (D)
export function ShapChart({ res, action }) {
  // Bars proportional to the |SHAP| values returned by the API. A positive value raises delta = Q(passer) - Q(garder),
  // i.e. favours "passer"; it favours the chosen action when the chosen action is "passer".
  const rows = VAR_ORDER.map((v) => res.contributions.find((c) => c.variable === v)).filter(Boolean);
  const max = Math.max(...rows.map((c) => Math.abs(c.shap)), 1e-12);
  const sign = action === "garder" ? -1 : 1;
  return (
    <figure style={{ margin: 0 }}>
      <div className={s.legend}>
        <span><i className={`${s.sw} ${sign > 0 ? s.pos : s.neg}`} />valeur positive : pousse vers « passer »{sign > 0 ? " (favorise l'action choisie)" : ""}</span>
        <span><i className={`${s.sw} ${sign > 0 ? s.neg : s.pos}`} />valeur négative : pousse vers « garder »{sign > 0 ? " (s'oppose à l'action choisie)" : ""}</span>
      </div>
      <div className={s.bars} role="img"
        aria-label={`Contributions SHAP : ${res.contributions.map((c) => `${c.variable} ${num(c.shap, 6)}`).join(", ")}`}>
        <div className={s.axisCaption}><span />
          <span className={s.captionMid}><span>← vers « garder »</span><span>0</span><span>vers « passer » →</span></span><span /></div>
        {rows.map((c) => {
          const zero = Math.abs(c.shap) < 1e-12, pos = c.shap > 0, w = `${(Math.abs(c.shap) / max) * 48}%`;
          return (
            <div className={s.barRow} key={c.variable}>
              <div className={s.barLabel}><strong>{VARS[c.variable]?.name || c.variable}</strong><span>observé : {c.class} · {c.variable}</span></div>
              <div className={s.barTrack}>
                <span className={s.axis} />
                {zero ? <span className={s.zeroDot} title="contribution nulle" />
                  : <span className={`${s.bar} ${pos ? s.pos : s.neg}`} style={pos ? { left: "50%", width: w } : { right: "50%", width: w }} />}
              </div>
              <div className={`${s.barValue} ${zero ? s.valZero : pos ? s.valPos : s.valNeg}`}>{zero ? "0" : num(c.shap, 3)}</div>
            </div>);
        })}
      </div>
    </figure>
  );
}

// ------------------------------------------------------------------------------------------------ waterfall
export function Waterfall({ res }) {
  // base value -> + each contribution -> delta (base + sum = delta, checked by the engine)
  const rows = VAR_ORDER.map((v) => res.contributions.find((c) => c.variable === v)).filter(Boolean);
  let acc = res.base_value;
  const steps = rows.map((c) => { const a = acc; acc += c.shap; return { c, from: a, to: acc }; });
  const pts = [0, res.base_value, res.delta, ...steps.flatMap((t) => [t.from, t.to])];
  const lo = Math.min(...pts), hi = Math.max(...pts), span = hi - lo || 1;
  const pct = (v) => (100 * (v - lo)) / span;
  const seg = (a, b, cls, style) => <span className={`${s.wfSeg} ${cls}`} style={{ left: `${pct(Math.min(a, b))}%`, width: `${Math.max(0.6, pct(Math.max(a, b)) - pct(Math.min(a, b)))}%`, ...style }} />;
  const zero = lo < 0 && hi > 0 ? <span className={s.wfZero} style={{ left: `${pct(0)}%` }} /> : null;
  return (
    <div className={s.wf} role="img" aria-label={`Valeur de référence ${num(res.base_value, 6)}, Δ ${num(res.delta, 6)}`}>
      <div className={s.wfRow}><span className={s.wfName}>Situation habituelle (référence)</span>
        <div className={s.wfTrack}>{zero}{seg(0, res.base_value, s.wfTotal)}</div><span className={s.wfVal}>{num(res.base_value, 3)}</span></div>
      {steps.map(({ c, from, to }) => (
        <div className={s.wfRow} key={c.variable}><span className={s.wfName}>{VARS[c.variable]?.short || c.variable}</span>
          <div className={s.wfTrack}>{zero}{seg(from, to, c.shap >= 0 ? s.pos : s.neg, Math.abs(c.shap) < 1e-12 ? { opacity: .35 } : undefined)}</div>
          <span className={`${s.wfVal} ${Math.abs(c.shap) < 1e-12 ? s.valZero : c.shap > 0 ? s.valPos : s.valNeg}`}>{num(c.shap, 3)}</span></div>))}
      <div className={s.wfRow}><span className={s.wfName}><strong>Cette décision (Δ)</strong></span>
        <div className={s.wfTrack}>{zero}{seg(0, res.delta, s.wfTotal)}</div><span className={s.wfVal}>{num(res.delta, 3)}</span></div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ plain language (E)
export function SimpleExplanation({ d, res }) {
  const e = d.explanation || {};
  const action = e.action || "passer";
  const lc = res.logged_check;
  const delta = res.delta, base = res.base_value, sum = delta - base;
  const rows = VAR_ORDER.map((v) => res.contributions.find((c) => c.variable === v)).filter(Boolean)
    .sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap));
  const nz = rows.filter((c) => Math.abs(c.shap) >= 1e-12);
  const favours = (c) => (action === "garder" ? -c.shap : c.shap) > 0;
  const pref = (v) => (v > 0 ? "« passer »" : "« garder »");
  return (
    <Card className={s.simple} title="Explication simplifiée" icon="xai" sub="Construite à partir des valeurs de cette décision, sans texte inventé">
      <p>L'agent a décidé de <strong>{ACTION_FR[action]}</strong>. Dans sa table apprise, « passer » valait <strong>{plain(lc.q_passer_table)}</strong> et
        « garder » <strong>{plain(lc.q_garder_table)}</strong> : écart de <strong>{num(delta, 3)}</strong> en faveur de {pref(delta)}.</p>
      <p>Dans les situations comparables de ce carrefour (même phase verte), l'écart habituel est de <strong>{num(base, 3)}</strong>, en faveur de {pref(base)}.
        {" "}{Math.abs(sum) < 1e-12 ? "La situation observée n'a rien changé à cet écart."
          : sum < 0 ? <>La situation observée a <strong>réduit</strong> cet écart de {plain(Math.abs(sum))}{(base > 0) === (delta > 0) ? ", sans inverser la préférence de la table." : ", au point d'inverser la préférence de la table."}</>
            : <>La situation observée a <strong>augmenté</strong> cet écart de {plain(sum)}.</>}</p>
      {nz.length > 0 && <>
        <p style={{ marginBottom: ".2rem" }}><strong>Principaux facteurs</strong> (du plus au moins influent) :</p>
        <ul className={s.factorList}>
          {nz.map((c) => (
            <li key={c.variable}>
              <Icon name={favours(c) ? "check" : "alert"} size={16} className={favours(c) ? s.arrowUp : s.arrowDown} />
              <span>{VARS[c.variable]?.name} : <strong>{c.class}</strong> — {favours(c) ? "favorise" : "s'oppose à"} l'action choisie</span>
              <span className={c.shap > 0 ? s.valPos : s.valNeg} style={{ fontWeight: 700 }}>{num(c.shap, 3)}</span>
            </li>))}
        </ul></>}
      {rows.some((c) => Math.abs(c.shap) < 1e-12) && <p className={s.note}>
        {rows.filter((c) => Math.abs(c.shap) < 1e-12).map((c) => VARS[c.variable]?.short).join(", ")} : contribution nulle, car cette variable avait la même valeur
        dans toutes les situations de comparaison ; cela ne prouve pas qu'elle n'a pas d'effet.</p>}
      <p className={s.note} style={{ marginTop: ".5rem" }}>Ces valeurs décrivent le raisonnement de la table de l'agent par rapport à des situations comparables.
        Elles ne mesurent pas l'effet de la décision sur le trafic.</p>
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------ not admissible (G)
const RULE_TEXT = {
  fallback: "Quand la table de l'agent ne connaît pas assez une situation (une action essayée moins de 3 fois), une règle simple prend le relais : "
    + "terminer le vert quand la voie au vert est presque vide et qu'un véhicule attend ailleurs.",
  safety: "Un feu vert ne peut pas dépasser une durée maximale (2 fois la durée prévue, 60 s au plus) : le changement est alors imposé, quoi que préfère l'agent.",
  rule: "Cette stratégie décide avec une règle explicite (seuils, prévision ou pression du trafic), lisible directement : il n'y a pas de modèle appris à expliquer.",
  unknown: "Cette simulation n'a pas enregistré ce que l'agent observait au moment de décider.",
};
export function NotAdmissible({ d }) {
  const o = origin(d);
  const e = d.explanation || {};
  return (
    <Card className={s.na} role="status">
      <span className={s.naBadge}><Icon name="info" size={14} />Décision non admissible au SHAP</span>
      <p style={{ margin: ".7rem 0 .3rem", color: "#fff", fontWeight: 650 }}>Pas d'explication SHAP pour cette décision.</p>
      <p style={{ margin: 0 }}>Cette décision a été prise par {o.key === "safety" ? "une règle de sécurité" : o.key === "fallback" ? "la règle de secours de l'agent" : "une règle de la stratégie"} et
        non par la table Q-learning : SHAP n'est donc pas calculé, aucune valeur n'est inventée.</p>
      <dl className={s.facts}>
        <dt>Règle responsable</dt><dd>{ORIGINS[o.key].label}{e.source && o.key !== "safety" ? ` (${e.source})` : ""}</dd>
        <dt>Motif</dt><dd>{d.shap.reason}</dd>
        <dt>Comment fonctionne la règle</dt><dd>{RULE_TEXT[o.key]}</dd>
        {e.source === "max-pressure" && <><dt>Pressions</dt><dd>{e.pression_phase_actuelle} ici contre {e.pression_autre_phase} ailleurs (marge {e.marge})</dd></>}
        {e.source === "règle S2F" && <><dt>Prévision</dt><dd>{e["prévision_5min"] ?? "–"} à 5 min contre {e["prévision_maintenant"] ?? "–"} maintenant</dd></>}
      </dl>
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------ technical view
export function Technical({ d, res, isAdmin }) {
  const b = res.background;
  const lc = res.logged_check;
  const consts = res.contributions.filter((c) => c.warning).map((c) => c.variable);
  return (
    <div className={s.detail}>
      <Card title="Valeurs exactes" icon="report" sub="Grandeur expliquée : Δ = Q(passer) − Q(garder) de la table gelée (Δ > 0 : la table préfère changer de phase)">
        <div className="table-wrap">
          <table className={s.techTable}>
            <thead><tr><th>Variable</th><th>Signification</th><th>Classe observée</th><th className="num">Contribution SHAP</th></tr></thead>
            <tbody>
              {res.contributions.map((c) => (
                <tr key={c.variable}><td><code>{c.variable}</code></td><td>{VARS[c.variable]?.name}</td><td>{c.class}</td><td className="num">{num(c.shap, 6)}</td></tr>))}
              <tr><td colSpan={3}>Valeur de référence (moyenne de Δ sur le fond)</td><td className="num">{num(res.base_value, 6)}</td></tr>
              <tr><td colSpan={3}><strong>Valeur de référence + somme des contributions</strong></td><td className="num"><strong>{num(res.additivity.base_plus_sum, 6)}</strong></td></tr>
              <tr><td colSpan={3}>Δ = Q(passer) − Q(garder) de la table</td><td className="num">{num(res.delta, 6)}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="hint" style={{ marginTop: ".7rem" }}>
          Additivité {res.additivity.ok ? "vérifiée" : "NON vérifiée"} (écart {res.additivity.abs_error.toExponential(1)}, tolérance {res.additivity.tolerance}).
          {" "}Méthode : valeurs de Shapley interventionnelles exactes (2⁴ = 16 coalitions par situation de fond, sans échantillonnage) ;
          fond = situations du même feu et de la même phase verte présentes dans la table, pondérées par les visites.</p>
      </Card>
      <div className={s.two}>
        <Card title="Contrôle des valeurs Q" icon="check">
          <dl className={s.facts}>
            <dt>Q(garder) journal / table</dt><dd>{lc.q_garder_logged} / {lc.q_garder_table.toFixed(6)}</dd>
            <dt>Q(passer) journal / table</dt><dd>{lc.q_passer_logged} / {lc.q_passer_table.toFixed(6)}</dd>
            <dt>Essais garder / passer</dt><dd>{lc.visits_garder_passer?.join(" / ")}</dd>
            <dt>Concordance</dt><dd>{lc.ok ? "oui (écart dû à l'arrondi du journal)" : "non"}</dd>
            <dt>État (clé)</dt><dd><code>{res.state.key}</code></dd>
            {isAdmin && <><dt>Table</dt><dd><code>{res.model.file}</code></dd></>}
          </dl>
        </Card>
        <Card title="Fond de référence" icon="layers" sub="Situations de comparaison : même feu, même phase verte, pondérées par les visites">
          <dl className={s.facts}>
            <dt>Situations retenues</dt><dd>{b.states_retained} sur {b.states_total} ({b.states_excluded_missing_hybrid} exclues : état hybride absent de la table)</dd>
            <dt>Peu fiables</dt><dd>{b.states_retained_unreliable} situations ; {(100 * b.weighted_share_unreliable_evaluations).toFixed(1)} % des évaluations pondérées</dd>
            <dt>Évaluations hybrides</dt><dd>{b.hybrid_evaluations} (dont {b.hybrid_evaluations_unreliable} peu fiables)</dd>
          </dl>
          {consts.length > 0 && <div className={`${s.notice} ${s.noticeWarn}`} style={{ marginTop: ".7rem" }}>
            {consts.join(", ")} : constante dans le fond retenu, contribution nulle par construction — cela ne prouve pas l'absence d'effet.</div>}
        </Card>
      </div>
      <Card title="Distribution du fond par variable" icon="layers" sub="Poids des situations de comparaison pour chaque classe ; en cyan, la classe observée">
        <div className={s.two}>
          {VAR_ORDER.map((v) => {
            const c = res.contributions.find((x) => x.variable === v);
            if (!c) return null;
            const bg = c.background_classes_retained || {};
            const total = Object.values(bg).reduce((a, x) => a + x, 0) || 1;
            return (
              <div key={v}>
                <h3 style={{ fontSize: ".84rem" }}>{VARS[v].name}</h3>
                <div className={s.bgDist}>
                  {VARS[v].classes.map((label, i) => (
                    <div className={s.bgRow} key={label}><span>{label}</span>
                      <span className={s.bgTrack}><span className={`${s.bgFill} ${i === c.class_index ? s.bgFillOn : ""}`} style={{ width: `${(100 * (bg[String(i)] || 0)) / total}%`, display: "block" }} /></span>
                      <span>{Math.round((100 * (bg[String(i)] || 0)) / total)} %</span></div>))}
                </div>
              </div>);
          })}
        </div>
      </Card>
      <Card title="Explication enregistrée au moment de la décision" icon="report">
        <dl className={s.facts}>
          {Object.entries(d.explanation || {}).map(([k, v]) => (
            <span key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></span>))}
        </dl>
      </Card>
    </div>
  );
}
