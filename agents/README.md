# Agents – Kirchberg, 4 feux (SUMO / TraCI)

Couche multi-agents du projet. Elle pilote le scénario réduit `sumo/lust_4_intersections` : 4 feux de l'avenue J.F. Kennedy, issus de LuST.

**Tout ce qui sort de ces agents est SIMULÉ** : `data_origin = SIMULATED_sumo_lust_kirchberg_4tls`. Rien n'est mélangé aux données réelles (CITA, PCH, GTFS) de `data/processed`.

## Boucle d'exécution (sans intervention humaine)

À chaque pas de simulation (1 s), `agents/orchestrator.py` :

```
SUMO ─TraCI─► collecte ─► détection ─► prédiction ─► décision ─► intervention ─TraCI─► SUMO
```

| Agent | Fichier | Rôle | Statut |
|---|---|---|---|
| Collecte | `observation/collection_agent.py` | Lit les phases des feux (à chaque pas). Toutes les 5 s, relève sur chaque voie entrante et sortante les véhicules arrêtés, les véhicules présents, la longueur de file et le plus long arrêt continu. | opérationnel |
| Détection | `detection/detection_agent.py` | Deux règles à seuils documentés : « congestion » (≥ 8 véhicules arrêtés pendant ≥ 60 s) et « véhicule bloqué » (un véhicule arrêté ≥ 150 s, durée supérieure au plus long cycle normal, 96 s). | opérationnel, évalué sur incidents simulés |
| Prédiction | `prediction/prediction_agent.py` | Prévoit à +60 s le nombre de véhicules arrêtés par feu (tendance linéaire amortie), avec un score continu contre la persistance. | opérationnel, mais **moins bon que la persistance** |
| Décision | `decision/controllers.py` | Quatre décideurs. S0 : temps fixe LuST. S2 : demande / creux (règle). S2b : max-pressure. S3 : Q-learning (RL). | opérationnel |
| Intervention | `intervention/tls_actuator.py` | Applique « garder » ou « passer à la phase suivante ». L'ordre des phases et les jaunes de LuST sont conservés. Vert minimal 5 s ; vert maximal = min(60 s, 2 × durée programmée). | opérationnel, testé |
| Garde données réelles | `common/real_data.py` | Refuse tout entraînement sur données réelles pour un objectif jugé non entraînable : A (incidents) et B (prévision), d'après `data/reports/readiness_by_objective_v1.json`. | opérationnel |

S1 (feux « actuated » de SUMO) utilise les mêmes phases et les mêmes jaunes. Le programme est dans `sumo/lust_4_intersections/additional/tls_actuated_v1.add.xml`, généré par `scripts/simulation/make_actuated_programs.py`.

### Agent RL (S3)

- **Algorithme :** Q-learning tabulaire, une table par feu.
- **État :** phase verte ; véhicules arrêtés et en mouvement sur les voies servies ; file maximale d'une autre phase ; temps de vert écoulé (le tout discrétisé).
- **Actions :** garder ou passer à la phase suivante.
- **Récompense (semi-markovienne) :** −(somme des véhicules arrêtés entre deux décisions)/10.
- **Décision par défaut :** dans un état insuffisamment appris (moins de 3 essais de chaque action), l'agent applique la règle S2.
- **Entraînement :** 26 épisodes à demande ×5 (graines 101–126).
- **Évaluation :** graines 1–3, jamais vues à l'entraînement, avec la table figée `qtable_v4_FROZEN_ep26_eval.json`.
- **Historique :** les versions v1 à v3 (échecs documentés dans `scripts/simulation/train_rl.py`) sont conservées.

## Commandes (PowerShell, racine du projet)

```powershell
pip install -r requirements.txt            # traci, sumolib (libsumo optionnel : 2-3x plus rapide, mêmes résultats)
python -m pytest tests\test_agents.py tests\test_kirchberg_scenario.py -v

# démonstration visuelle : l'agent RL pilote les 4 feux dans sumo-gui
python scripts\simulation\run_experiment.py --strategy S3_rl_qlearning --scale 5 --seeds 1 --tag demo --gui

# reproduire l'évaluation (dossier experiments_v2 : rien n'est écrasé)
foreach ($s in "S0_fixed_time","S1_actuated","S2_demand_gap","S2b_max_pressure","S3_rl_qlearning") {
  python scripts\simulation\run_experiment.py --strategy $s --scale 5 --seeds 1 2 3 --tag v2 }
python scripts\simulation\evaluate_detection.py --scale 1 --seeds 1 2 3
python scripts\simulation\train_rl.py --episodes 5            # poursuit l'entraînement (qtable_v4.json)

python scripts\simulation\compare_strategies.py --experiments v2 --tag v2   # tableaux CSV + RESULTS_v2.md
```
