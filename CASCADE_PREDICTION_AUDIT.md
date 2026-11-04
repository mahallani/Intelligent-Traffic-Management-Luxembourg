# CASCADE_PREDICTION_AUDIT – audit de la prédiction en cascade

Date : 2026-10-12. Audit fait **avant** toute modification de la partie prédiction.

Méthode :
- lecture des dossiers `agents/`, `scripts/`, `tests/`, `traci_layer/`, `sumo/lust_4_intersections/`, `docs/` et `data/reports/` ;
- recherche des termes `cascade`, `predict`, `forecast`, `horizon`, `propagat` et `t+5` ;
- exécution des tests existants.

## Verdict

| Élément | Verdict |
|---|---|
| Prédiction **en cascade** multi-horizon (+5/+10/+15 min) | **NOT IMPLEMENTED** |
| Agent de prédiction existant (horizon unique de 60 s) | **NOT INTEGRATED** : il calcule et se note, mais aucune décision ne l'utilise |
| Analyse de propagation de congestion (observation, pas prédiction) | **PARTIAL** : le code existe dans `traci_layer`, mais il n'est utilisé ni par les agents ni par les tests |

## Réponses aux 10 questions

1. **Une prédiction en cascade existe-t-elle ?** Non.
   - `agents/cascade/` est un dossier **vide** (créé le 2026-10-06, 0 fichier).
   - Aucune fonction ne chaîne des prédictions entre horizons ou entre intersections.

2. **Où se trouve ce qui existe ?**
   - `agents/prediction/prediction_agent.py`, classe `PredictionAgent` : méthodes `update(obs, tls_lanes)` et `scores()`.
   - `traci_layer/network.py`, classe `NetworkTopology` : méthodes `upstream()`, `downstream()` et `upstream_within(edge, depth)`. Le docstring indique « Used for congestion propagation (Cascade Agent) ».
   - `traci_layer/edge_data.py`, méthode `_propagated()` : elle compte les arêtes nouvellement congestionnées situées en amont d'une arête déjà congestionnée. C'est une **mesure du présent**, pas une prévision.
   - `docs/TRACI_LAYER.md`, lignes 19, 86 et 438 : un agent « Cascade » y est **décrit** comme consommateur de ces sorties, mais il n'est pas codé.
   - `scripts/data_pipeline/build_task_datasets_v1.py` : il prépare un panel de données réelles avec des cibles à +5, +10 et +15 min (`task_B_forecast_panel_v1.csv`). Ce sont **des colonnes cibles, pas un modèle**, et elles sont toutes vides : aucune paire (passé, futur) n'existe dans les données collectées.

3. **Quels indicateurs ?** `PredictionAgent` prévoit un seul indicateur : le **nombre de véhicules arrêtés sur les voies entrantes de chaque feu** (4 séries). Aucune prévision de vitesse, de densité, de congestion d'arête ou de propagation d'incident.

4. **Quels horizons ?** Un seul horizon : `horizon_s = 60` s, soit +1 min. Aucun horizon à +5, +10 ou +15 min dans le code des agents.

5. **De quelle nature ?** Une **règle simple** et non un modèle appris : tendance linéaire amortie (`damping = 0.5`) sur les 60 dernières secondes d'échantillons. Elle n'est ni multi-horizon, ni dépendante d'une prédiction précédente, ni composée de modèles indépendants.

6. **Données d'entraînement et d'inférence ?** Il n'y a aucun entraînement. L'inférence utilise les observations TraCI de la simulation en cours, échantillonnées toutes les 5 s par `CollectionAgent`.

7. **Données réelles ou simulées ?** **Simulées uniquement** (`data_origin = SIMULATED_sumo_lust_kirchberg_4tls`). Le garde `agents/common/real_data.py` bloque l'objectif réel B (prévision), jugé « NOT TRAINABLE » dans `data/reports/readiness_by_objective_v1.json`.

8. **Quels tests démontrent sa qualité ?**
   - `tests/test_agents.py::test_prediction_scores_against_persistence` (réexécuté le 2026-10-12 : **1 passed**). Ce test ne prouve qu'une chose : sur une série synthétique linéaire, la tendance bat la persistance.
   - Mesures réelles en simulation (`runs/*/kpis.json`, champ `prediction`) : le modèle est **moins bon que la persistance** dans les 10 configurations. Exemples : S0 ×5, MAE 9,0 contre 7,1 véhicules ; S0 ×1, MAE 1,53 contre 1,28.

9. **Est-elle connectée à la décision et aux feux ?** **Non.**
   - `agents/orchestrator.py` appelle `pred.update(obs, tls_lanes)` (ligne 92) puis `pred.scores()` pour le rapport.
   - `controller.decide(obs, env)` ne reçoit pas les prévisions : aucun contrôleur de `agents/decision/controllers.py` ne lit `last_forecast`.
   - `TLSActuator` non plus.

10. **Que faut-il développer ou connecter ?**
    - Une prévision multi-horizon (+5, +10, +15 min) des indicateurs utiles à la décision (véhicules arrêtés par approche, débit), avec une dépendance explicite entre horizons. La cascade proposée : chaque horizon utilise la prévision de l'horizon précédent comme entrée, plus l'état amont fourni par la topologie (`NetworkTopology.upstream`) pour la propagation entre intersections.
    - Une évaluation sans fuite (séparation chronologique, graines d'entraînement et de test distinctes) contre des baselines simples (persistance, moyenne historique au même instant), avec l'erreur par horizon.
    - L'enregistrement des prévisions, des valeurs observées et des erreurs.
    - La transmission des prévisions à la décision (entrée de `decide`) et un test qui le prouve.
    - Tout cela **en simulation** et étiqueté comme tel : les données réelles ne permettent pas d'entraîner l'objectif B.

## Tests exécutés pour cet audit

- `python -m pytest tests/test_agents.py -k prediction` (Linux, machine de ton PC) : 1 passed.
- Recherche dans le code : `grep -rn cascade|horizon|forecast|propagat` sur `agents`, `scripts`, `tests`, `traci_layer` et `sumo`. Aucun test ne couvre `_propagated` ni `upstream_within`.
