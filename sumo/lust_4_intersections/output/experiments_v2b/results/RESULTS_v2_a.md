# Comparaison des stratégies – experiments_v2b (a) – résultats SIMULÉS

Source : SUMO 1.27.1, demande LuST 07:00–08:00, réseau réduit Kirchberg 4 feux. **Aucune donnée réelle de trafic n'est utilisée par les contrôleurs ; aucun résultat ici n'est un résultat de trafic réel.**

Runs v2 complets : 96 (6 stratégies × échelles x1, x5 × graines 1–3 et 61–65).

## 1. Reproduction de v1 (graines 1–3)

36 / 36 runs identiques à v1 sur les 12 indicateurs (écart absolu max. 0.0). Runs v2 sans équivalent v1 : 0.

## 2. Résultats x1 – graines neuves 61–65 (jamais utilisées pour un choix de conception)

| Stratégie | Trajet (s) | Attente (s) | Temps perdu (s) | File moy. (véh.) | CO₂ (kg) | Arrivés |
|---|---|---|---|---|---|---|
| S0_fixed_time | 99.8 ± 0.3 | 18.9 | 29.8 | 4.46 | 208.7 | 752 |
| S1_actuated | 90.0 ± 0.3 | 8.2 | 19.8 | 1.97 | 200.8 | 753 |
| S2_demand_gap | 88.9 ± 0.7 | 8.3 | 18.7 | 1.83 | 195.2 | 752 |
| S2F_forecast_gap | 88.9 ± 0.7 | 8.3 | 18.7 | 1.83 | 195.2 | 752 |
| S2b_max_pressure | 105.6 ± 0.7 | 24.5 | 35.5 | 5.40 | 214.6 | 753 |
| S3_rl_qlearning | 88.9 ± 0.5 | 8.5 | 18.7 | 1.92 | 194.6 | 752 |

Différences appariées (B − A) sur le temps de trajet moyen, IC 95 % de Student sur 5 graines :

| A | B | Δ (s) | Δ % | IC 95 % | B meilleur sur | Significatif |
|---|---|---|---|---|---|---|
| S0_fixed_time | S1_actuated | -9.85 | -9.9 % | [-10.31 ; -9.39] | 5/5 | oui |
| S0_fixed_time | S2_demand_gap | -10.91 | -10.9 % | [-11.63 ; -10.20] | 5/5 | oui |
| S0_fixed_time | S2F_forecast_gap | -10.91 | -10.9 % | [-11.63 ; -10.20] | 5/5 | oui |
| S0_fixed_time | S2b_max_pressure | +5.84 | +5.8 % | [+5.18 ; +6.49] | 0/5 | oui |
| S0_fixed_time | S3_rl_qlearning | -10.93 | -10.9 % | [-11.19 ; -10.67] | 5/5 | oui |
| S1_actuated | S2_demand_gap | -1.06 | -1.2 % | [-1.74 ; -0.39] | 5/5 | oui |
| S1_actuated | S3_rl_qlearning | -1.08 | -1.2 % | [-1.72 ; -0.44] | 5/5 | oui |
| S2_demand_gap | S3_rl_qlearning | -0.02 | -0.0 % | [-0.68 ; +0.65] | 3/5 | non |
| S2_demand_gap | S2F_forecast_gap | +0.00 | +0.0 % | [+0.00 ; +0.00] | 0/5 | non |

## 2. Résultats x5 – graines neuves 61–65 (jamais utilisées pour un choix de conception)

| Stratégie | Trajet (s) | Attente (s) | Temps perdu (s) | File moy. (véh.) | CO₂ (kg) | Arrivés |
|---|---|---|---|---|---|---|
| S0_fixed_time | 134.9 ± 1.1 | 38.9 | 65.2 | 40.44 | 1349.6 | 3659 |
| S1_actuated | 113.4 ± 1.3 | 21.9 | 43.4 | 23.20 | 1218.6 | 3706 |
| S2_demand_gap | 120.7 ± 2.2 | 29.4 | 50.8 | 32.09 | 1256.2 | 3692 |
| S2F_forecast_gap | 119.4 ± 0.7 | 28.3 | 49.5 | 30.86 | 1248.6 | 3691 |
| S2b_max_pressure | 136.5 ± 2.7 | 41.0 | 66.8 | 44.02 | 1356.4 | 3657 |
| S3_rl_qlearning | 122.7 ± 1.6 | 30.1 | 52.9 | 32.81 | 1268.0 | 3688 |

Différences appariées (B − A) sur le temps de trajet moyen, IC 95 % de Student sur 5 graines :

| A | B | Δ (s) | Δ % | IC 95 % | B meilleur sur | Significatif |
|---|---|---|---|---|---|---|
| S0_fixed_time | S1_actuated | -21.54 | -16.0 % | [-24.32 ; -18.75] | 5/5 | oui |
| S0_fixed_time | S2_demand_gap | -14.29 | -10.6 % | [-16.90 ; -11.67] | 5/5 | oui |
| S0_fixed_time | S2F_forecast_gap | -15.53 | -11.5 % | [-17.52 ; -13.54] | 5/5 | oui |
| S0_fixed_time | S2b_max_pressure | +1.56 | +1.2 % | [-2.52 ; +5.64] | 1/5 | non |
| S0_fixed_time | S3_rl_qlearning | -12.20 | -9.0 % | [-12.91 ; -11.49] | 5/5 | oui |
| S1_actuated | S2_demand_gap | +7.25 | +6.4 % | [+4.02 ; +10.48] | 0/5 | oui |
| S1_actuated | S3_rl_qlearning | +9.33 | +8.2 % | [+6.10 ; +12.57] | 0/5 | oui |
| S2_demand_gap | S3_rl_qlearning | +2.08 | +1.7 % | [-1.13 ; +5.29] | 1/5 | non |
| S2_demand_gap | S2F_forecast_gap | -1.25 | -1.0 % | [-4.23 ; +1.74] | 4/5 | non |

## 3. Sécurité des feux (moniteur indépendant, tous les runs v2)

| Stratégie | Runs | Transitions vérifiées | Violations | Collisions | Téléportations | Repli RL |
|---|---|---|---|---|---|---|
| S0_fixed_time | 16 | 16528 | 0 | 0 | 0 |  |
| S1_actuated | 16 | 42475 | 0 | 0 | 0 |  |
| S2_demand_gap | 16 | 14846 | 0 | 0 | 0 |  |
| S2F_forecast_gap | 16 | 14871 | 0 | 0 | 0 |  |
| S2b_max_pressure | 16 | 11762 | 0 | 0 | 0 |  |
| S3_rl_qlearning | 16 | 17625 | 0 | 0 | 0 | 0.428 |

Règles vérifiées à chaque pas : état présent dans le programme du feu, pas de passage vert→rouge sans jaune, vert ≥ 5 s, jaune à sa durée programmée, vert ≤ 90 s. Les conflits de mouvements sont couverts par la règle « état présent dans le programme » : les contrôleurs ne fabriquent jamais d'état, ils ne choisissent que des phases du programme LuST (dont les états ont été conçus sans conflit).
