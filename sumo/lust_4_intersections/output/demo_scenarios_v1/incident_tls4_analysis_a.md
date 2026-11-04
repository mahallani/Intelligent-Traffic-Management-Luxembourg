# Scénario B – détail au Carrefour 4 (a) – SIMULÉ

Fenêtre : 07:20-07:40 (cible des prévisions dans la fenêtre). Phase 4 = vert de l'approche bloquée (-31070#4).

| Run | MAE modèle +5 / +10 / +15 | MAE persistance +5 / +10 / +15 | Arrêtés observés (moy., +5) | Phase 4 terminée par l'agent | Phase 4 terminée par le vert max | Alertes |
|---|---|---|---|---|---|---|
| S0_fixed_time_x5_seed61_no_incident | 8.8 / 9.18 / 9.98 | 10.91 / 11.08 / 9.04 | 21.12 | – | – | {} |
| S0_fixed_time_x5_seed61_incident | 32.42 / 32.85 / 37.05 | 14.74 / 23.08 / 32.97 | 49.07 | – | – | {"blocked@-31070#4_1": 1, "blocked@-31070#4_0": 2, "stalled@-31070#4_0": 3} |
| S0_fixed_time_x5_seed62_no_incident | 9.05 / 9.29 / 10.02 | 12.03 / 12.1 / 9.19 | 21.03 | – | – | {} |
| S0_fixed_time_x5_seed62_incident | 34.9 / 35.53 / 39.85 | 20.8 / 28.45 / 36.34 | 51.58 | – | – | {"blocked@-31070#4_1": 1, "blocked@-31070#4_0": 1, "stalled@-31070#4_0": 5} |
| S0_fixed_time_x5_seed63_no_incident | 8.53 / 8.85 / 9.37 | 10.77 / 11.51 / 8.92 | 20.17 | – | – | {} |
| S0_fixed_time_x5_seed63_incident | 37.06 / 37.64 / 42.03 | 16.16 / 27.4 / 38.49 | 53.7 | – | – | {"blocked@-31070#4_1": 1, "stalled@-31070#4_1": 1, "blocked@-31070#4_0": 1, "stalled@-31070#4_0": 5} |
| S3_rl_qlearning_x5_seed61_no_incident | 10.16 / 9.32 / 9.29 | 11.6 / 12.1 / 9.4 | 15.78 | 8 | 4 | {"blocked@--31070#6_0": 1} |
| S3_rl_qlearning_x5_seed61_incident | 29.96 / 31.51 / 36.46 | 25.1 / 25.7 / 34.51 | 45.13 | 1 | 9 | {"blocked@-31070#4_1": 1, "blocked@-31070#4_0": 2, "stalled@-31070#4_0": 6, "blocked@--31070#5_1": 2} |
| S3_rl_qlearning_x5_seed62_no_incident | 8.49 / 8.8 / 9.12 | 11.45 / 11.27 / 10.34 | 15.66 | 9 | 4 | {} |
| S3_rl_qlearning_x5_seed62_incident | 28.6 / 30.33 / 34.96 | 16.08 / 22.48 / 34.14 | 43.28 | 2 | 8 | {"blocked@-31070#4_1": 1, "stalled@-31070#4_1": 1, "blocked@-31070#4_0": 2, "stalled@-31070#4_0": 8, "blocked@--31070#5_1": 3} |
| S3_rl_qlearning_x5_seed63_no_incident | 8.4 / 8.93 / 9.89 | 9.53 / 11.16 / 11.2 | 16.41 | 11 | 2 | {"blocked@--31070#6_0": 1} |
| S3_rl_qlearning_x5_seed63_incident | 33.08 / 34.29 / 39.31 | 17.67 / 24.63 / 35.64 | 48.17 | 3 | 8 | {"stalled@-31070#4_1": 1, "blocked@-31070#4_0": 2, "blocked@--31070#6_0": 1, "stalled@-31070#4_0": 4, "blocked@--31070#5_1": 1} |

Source : predictions.csv, decisions.csv, alerts.csv des runs demo_scenarios_v1/B.
