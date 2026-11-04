# Scénarios de démonstration (a) – résultats SIMULÉS (SUMO, demande LuST ×5)

## A. Congestion : S0 (temps fixe) contre S3 (agent RL), mêmes graines 61-65

| Indicateur | S0 | S3 | Différence S3 − S0 | IC 95 % | S3 meilleur sur |
|---|---|---|---|---|---|
| Temps de trajet moyen (s) | 134.94 | 122.74 | -12.20 (-9.0 %) | [-12.91 ; -11.49] | 5/5 |
| Attente moyenne (s) | 38.90 | 30.13 | -8.77 (-22.6 %) | [-10.02 ; -7.53] | 5/5 |
| File moyenne (véh.) | 40.44 | 32.81 | -7.63 (-18.9 %) | [-9.28 ; -5.99] | 5/5 |
| File maximale (véh.) | 105.20 | 95.40 | -9.80 (-9.3 %) | [-22.86 ; +3.26] | 4/5 |
| CO2 simulé (kg) | 1349.64 | 1268.03 | -81.61 (-6.0 %) | [-91.66 ; -71.56] | 5/5 |
| Véhicules arrivés | 3658.80 | 3688.40 | +29.60 (+0.8 %) | [+5.55 ; +53.65] | 4/5 |

Part des décisions de S3 prises par la règle de secours S2 : 43.7 %. Violations de sécurité (10 runs) : 0.

## B. Voie bloquée avant le Carrefour 4 (07:20-07:40), même graine avec et sans incident

| Stratégie | Graine | Détecté | Délai (s) | Alertes sur la voie | Fausses alertes ailleurs | Arrêtés Carrefour 4 pendant l'incident (sans → avec) | Trajet moyen (sans → avec, s) | Décisions de l'agent au Carrefour 4 pendant l'incident (sans → avec) |
|---|---|---|---|---|---|---|---|---|
| S0_fixed_time | 61 | oui | 86.0 | 6 | 0 | 21.2 → 50.6 | 136.83 → 148.21 | – (programme fixe) → – |
| S0_fixed_time | 62 | oui | 86.0 | 7 | 0 | 21.2 → 53.6 | 134.05 → 148.18 | – (programme fixe) → – |
| S0_fixed_time | 63 | oui | 86.0 | 8 | 0 | 20.4 → 55.7 | 134.31 → 149.15 | – (programme fixe) → – |
| S3_rl_qlearning | 61 | oui | 131.0 | 9 | 2 | 16.7 → 47.7 | 125.53 → 142.73 | 31 → 16 |
| S3_rl_qlearning | 62 | oui | 136.0 | 12 | 3 | 16.3 → 46.3 | 121.97 → 138.24 | 30 → 19 |
| S3_rl_qlearning | 63 | oui | 151.0 | 7 | 2 | 17.1 → 50.9 | 121.89 → 139.76 | 34 → 22 |

Aucune stratégie ne reçoit les alertes : S3 réagit seulement parce que ses observations (files) changent.

### Ambulance pendant l'incident (S3, graine 61)

| Priorité urgence | Trajet ambulance (s) | Attente ambulance (s) | Violations |
|---|---|---|---|
| sans | 345.0 | 202.0 | 0 |
| avec | 120.0 | 1.0 | 0 |

Source : fichiers kpis.json, alerts.csv, decisions.csv, queue_timeseries.csv des runs de demo_scenarios_v1.
