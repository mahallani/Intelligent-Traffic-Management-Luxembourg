# Captures de l'application – scénario B (SIMULÉ)

- Produites le 22/10/2026 par `scripts/demo/capture_app_screens_v1.py --tag v2`, Chromium sans écran, **conteneur Linux** (SUMO 1.27.1). Pas sous Windows.
- Scénario : S3 (agent RL), demande ×5, graine 61, voie bloquée avant le Carrefour 4 (07:20–07:40), ambulance à 07:20 avec priorité.
- `captures.json` : heure simulée, statut et run de chaque image. Tables défilantes affichées en entier pour la capture (contenu inchangé).
- `run_files/` : sorties du run capturé (`app_runs/20261022_011301_S3_rl_qlearning_x5_seed61_incident_carrefour4_ambulance_prio` dans le conteneur).
- Indicateurs finaux identiques au run équivalent dans la VM Linux (`output/demo_scenarios_v1/B/S3_rl_qlearning_x5_seed61_incident_ambulance_prio`) : trajet 139,87 s ; incident détecté en 131 s ; ambulance 120 s, 1 s d'attente ; 0 violation.
- `session.webm` : enregistrement de toute la session (≈ 2 min), utilisable comme base de vidéo.
