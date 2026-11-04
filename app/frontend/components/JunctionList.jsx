"use client";
import { Badge } from "./ui";
import { congestion, lampOf } from "./traffic";

export default function JunctionList({ net, state }) {
  const sig = state?.signals || {};
  const open = (state?.alerts || []).filter((a) => !a.end_clock);
  return (
    <div className="jn-list">
      {(net?.signals || []).map((t, i) => {
        const s = sig[t.id];
        const c = congestion(s?.halting);
        const alerts = open.filter((a) => a.tls === t.id).length;
        return (
          <div className="jn-row" key={t.id}>
            <span className="jn-num">{i + 1}</span>
            <div style={{ minWidth: 0 }}>
              <div className="jn-name">{t.label}</div>
              <div className="jn-meta">
                <span className="lamps" aria-label={`État des feux : ${s?.state || "inconnu"}`}>
                  {(s?.state || "").split("").map((ch, k) => <span key={k} className={`lamp ${lampOf(ch)}`} />)}
                  {!s && <span className="muted">feux inactifs</span>}
                </span>
                {s && <span>{s.halting} arrêté(s)</span>}
                {alerts > 0 && <Badge tone="bad">{alerts} alerte(s)</Badge>}
              </div>
            </div>
            <span className={`level tone-${c.tone}`}>{c.label}</span>
          </div>);
      })}
    </div>
  );
}

