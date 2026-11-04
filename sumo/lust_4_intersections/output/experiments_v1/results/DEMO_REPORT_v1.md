# Démonstration fonctionnelle – rapport (v1, 2026-10-11)

Tous les chiffres viennent de simulations SUMO réellement exécutées dans ce dossier. Ce sont des **valeurs simulées** : demande LuST d'environ 2015, réseau LuST, aucune calibration sur données réelles.

## Mission 1 – SUMO fonctionnel

- **Recherche du scénario réduit :** absent du projet. `sumo\` ne contenait que `sumo\test` (2 arêtes, 0 feu). `data.zip` ne contient que des données (42 fichiers `data/raw`, `data/historical` et `data/processed`). Aucun autre `.sumocfg` hors LuST.
- **Installation :** le scénario de la phase 2 a été ajouté dans `sumo\lust_4_intersections\`, avec la couche `traci_layer\`, ses tests et sa documentation.
- **Reconstruction depuis ton LuST :** `lust.net.xml` est identique à celui ayant servi à construire le scénario (seules les fins de ligne Windows diffèrent). `build_scenario.py`, exécuté dans une copie, régénère un réseau identique (en-tête mis à part), des routes identiques (778 véhicules) et les mêmes 11 arrêts de bus.
- **Simulation :** SUMO 1.27.1 démarre, 778 véhicules circulent (752 arrivés en 1 h), 0 téléportation, 0 collision.
- **Feux et TraCI :** les 4 feux sont lus et commandés par TraCI (`setPhase`, `setPhaseDuration`, `setProgramLogic`…). Chaque feu est traversé : 154, 162, 322 et 400 véhicules.

## Mission 2 – Résultats mesurables

Comparaison détaillée : `RESULTS_v1.md`. Données : `kpi_runs_v1.csv`, `kpi_summary_v1.csv`, `kpi_vs_baseline_v1.csv`. Une série temporelle des files est disponible par run (`runs/*/queue_timeseries.csv`).

Demande ×5 (congestion), moyenne sur 3 graines, écart à la référence S0 :

| Stratégie | Trajet moyen | Attente moyenne | File moyenne | CO2 |
|---|---|---|---|---|
| S0 temps fixe LuST (référence) | 135,1 s | 38,8 s | 40,6 véh. | 1 348 kg |
| S1 feux actuated SUMO | −14,7 % | −40,2 % | −39,7 % | −9,1 % |
| S2 règle demande / creux (agent TraCI) | −10,9 % | −25,0 % | −23,8 % | −7,1 % |
| S2b max-pressure | +2,6 % | +10,4 % | +14,1 % | +1,3 % |
| S3 agent RL (Q-learning) | −9,7 % | −24,2 % | −21,7 % | −6,4 % |

À demande ×1 (trafic LuST), les gains sont du même ordre :
- trajet −10 à −12 % pour S1, S2 et S3 ;
- attente −55 à −58 % ;
- S2b reste moins bon que S0.

## Mission 3 – Architecture multi-agents

L'architecture est décrite dans `agents/README.md`. La boucle collecte → détection → prédiction → décision → intervention tourne sans intervention humaine.

- **Agent RL :**
  - **Entraînement :** 26 épisodes (graines 101 à 126). Trajet moyen pendant l'entraînement : 138 s à l'épisode 1, environ 120 à 129 s sur les épisodes 17 à 26.
  - **Décisions en évaluation :** il décide seul sur des graines non vues, sans exploration ni mise à jour.
  - **Résultat :** il bat le temps fixe, mais **pas** la règle S2 ni les feux actuated de SUMO.
  - **Part apprise :** sur les 1 999 états rencontrés, seuls 341 ont assez d'essais pour une décision apprise ; ailleurs, l'agent applique la règle S2.
- **Agent de détection (incidents simulés) :** une voie très ralentie (0,05 m/s) de 07:20 à 07:40.
  - À ×1 : 6 incidents détectés sur 6, délai moyen 292 s (151 à 381 s), 0 fausse alerte sans incident.
  - À ×5 : 6 sur 6 en 26 à 41 s, mais 15 à 16 fausses alertes par heure sans incident. En congestion forte, la règle ne distingue donc pas un incident d'une congestion récurrente.
- **Agent de prédiction (+60 s) :** erreur supérieure à la persistance partout. À ×5 en S0 : MAE 9,0 contre 7,1 véhicules ; à ×1 : 1,53 contre 1,28. Il n'est **pas utile** en l'état.

## Mission 4 – Données

Les agents n'utilisent que des données simulées. `agents/common/real_data.py` lit `data/reports/readiness_by_objective_v1.json` et **refuse** tout entraînement réel pour les objectifs A (incidents) et B (prévision), jugés non entraînables. Un test le vérifie.

Aucune observation réelle (capteur CITA ou poste PCH) n'existe dans la zone des 4 feux. La comparaison réel/simulé et la calibration sont donc impossibles pour l'instant.

## Limites

- La demande et le réseau sont ceux de LuST (vers 2015) : ni le tram T1 ni les plans de feux réels.
- 3 graines par stratégie seulement. Les paramètres de S2 et S2b ont été réglés sur la graine 50 ; les choix du RL ont été validés sur les graines 60 et 61.
- La congestion ×5 est un scénario artificiel (demande multipliée).
- Les émissions sortent du modèle HBEFA de SUMO.
