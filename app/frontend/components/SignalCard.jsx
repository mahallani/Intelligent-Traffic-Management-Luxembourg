"use client";
const cls = (c) => (c === "G" || c === "g" ? "g" : c === "y" || c === "Y" ? "y" : c === "r" || c === "R" ? "r" : "o");

export default function SignalCard({ id, label, info }) {
  const state = info?.state || "";
  return (
    <div className="signal">
      <div className="name">{label}</div>
      <div className="hint">feu {id}</div>
      <div className="heads" aria-label={`État des ${state.length} mouvements : ${state || "inconnu"}`}>
        {state.split("").map((c, i) => <span key={i} className={`head ${cls(c)}`} />)}
      </div>
      <div style={{ fontSize: ".85rem" }}>
        Phase {info?.phase ?? "–"} depuis {info?.green_elapsed !== undefined ? Math.round(info.green_elapsed) : "–"} s
      </div>
      <div style={{ fontSize: ".85rem" }}>{info?.halting ?? "–"} véhicules arrêtés</div>
    </div>
  );
}
