// Page XAI dynamique (2026-10-29) : décisions réelles du run courant ou d'un run enregistré, et explication SHAP exacte
// calculée à la demande par le backend (agents/xai/shap_qtable.py). Aucun graphique pré-calculé n'est affiché ici.
import XaiClient from "./XaiClient";

export const metadata = {
  title: "ITM Luxembourg – Explicabilité de l'IA",
  description: "Décisions réelles des agents et explication SHAP exacte des décisions de la table Q-learning S3 (données simulées).",
};

export default function Xai() {
  return <XaiClient />;
}
