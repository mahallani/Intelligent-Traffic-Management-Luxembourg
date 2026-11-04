"use client";
// Small data helpers shared by pages (2026-11-03).
import { useEffect, useState } from "react";
import { getJSON } from "./api";

// Latest run launched from the application (GET /api/runs, source "application"), used when no simulation is active.
export function useLastRun() {
  const [run, setRun] = useState(undefined);
  useEffect(() => {
    getJSON("/runs").then((r) => {
      const app = (r.runs || []).filter((x) => x.source === "application").sort((a, b) => (a.name < b.name ? 1 : -1));
      setRun(app[0] || null);
    }).catch(() => setRun(null));
  }, []);
  return run;
}

const QCLS = ["0", "1–2", "3–5", "6–10", "plus de 10"];
const MCLS = ["aucun", "1–2", "3–5", "plus de 5"];
const TCLS = ["≤ 10 s", "11–20 s", "21–40 s", "> 40 s"];

// Plain-language text of a phase change, built ONLY from what the agent recorded at decision time.
export function decisionText(d) {
  const e = d.explain || d.explanation;
  const act = e?.action === "garder" ? "garde le vert" : "passe à la phase suivante";
  if (d.reason === "max_green") return { who: "Sécurité", text: `Durée de vert maximale atteinte${e?.vert_s ? ` (${e.vert_s} s)` : ""} : changement imposé.` };
  if (!e) return { who: "Agent", text: "Changement de phase décidé par l'agent." };
  const s2 = (r) => r ? `${r["arrêtés_vert"]} arrêté(s) et ${r["en_mouvement_vert"]} en mouvement au vert, ${r["attente_autre_phase"]} en attente ailleurs` : "";
  if (e.source === "table apprise") {
    const s = e.situation || {};
    return { who: "Agent IA", xai: true, text: `${QCLS[+s.file_servie] ?? s.file_servie} arrêté(s) au vert, ${QCLS[+s.file_autre] ?? s.file_autre} en attente ailleurs, ` +
      `${MCLS[+s.en_mouvement] ?? s.en_mouvement} en mouvement, vert ${TCLS[+s["durée_vert"]] ?? s["durée_vert"]} → ${act}.` };
  }
  if (e.source?.startsWith("règle de secours")) return { who: "Agent IA (règle de secours)", text: `Situation peu connue de l'agent : règle simple appliquée. ${s2(e["règle_S2"])} → ${act}.` };
  if (e.source === "règle S2") return { who: "Agent à règles", text: `${s2(e)} → ${act}.` };
  if (e.source === "règle S2F") return { who: "Agent à règles + prévision", text: `${s2(e)} ; prévision à 5 min : ${e["prévision_5min"] ?? "–"} → ${act}.` };
  if (e.source === "max-pressure") return { who: "Agent max-pressure", text: `Pression ${e.pression_phase_actuelle} ici contre ${e.pression_autre_phase} ailleurs → ${act}.` };
  return { who: "Agent", text: e.source || "Changement de phase." };
}
