# AGENT_EVALUATION_REPORT – évaluation des agents (2026-10-12)

**Provenance.** Tous les résultats de ce rapport sont **simulés** : SUMO 1.27.1, réseau et demande LuST (scénario de recherche d'environ 2015), réseau réduit Kirchberg, avenue J.F. Kennedy, 4 feux (`-28692`, `-23354`, `-20484`, `-29958`), 07:00–08:00. Aucun agent n'a été entraîné ni évalué sur des données réelles : il n'existe aucune mesure réelle dans la zone des 4 feux (voir `DATA_VALIDATION_REPORT.md`). Les incidents et l'ambulance sont **simulés**. Aucun résultat ici n'est un résultat de trafic réel.

Chaque chiffre renvoie à un fichier du disque. Tous les runs sont reproductibles (même graine → mêmes résultats, vérifié ci-dessous).

## 1. Boucle multi-agents réellement exécutée

```
SUMO ─TraCI/libsumo─► collecte (5 s) ─► détection ─► prédiction en cascade (+5/+10/+15 min)
                                                         │ (option use_forecast)
                                                         ▼
            moniteur de sécurité ◄─ intervention (TLSActuator) ◄─ décision (S0…S3)
                     ▲                    ▲
                     └── priorité urgence (module séparé, optionnel)
```

Code : `agents/orchestrator.py::run_episode`. Chaque run écrit `queue_timeseries.csv`, `alerts.csv`, `predictions.csv`, `decisions.csv` et `kpis.json`.

| Lien | Vérifié par |
|---|---|
| La prévision est calculée pendant le run et journalisée | `predictions.csv` (origine, cible, horizon, prévision, observé, erreur, persistance) ; `tests/test_cascade.py` |
| La décision consomme réellement la prévision (S2F) | `kpis.json → controller.decisions_with_forecast` (ex. 2 229 / 2 474 décisions, x5 graine 61) ; `forecasts_passed_to_decision` |
| On peut la couper | `--no-forecast` / case de l'application : S2F devient **identique** à S2 (test `test_forecast_switch_off_gives_exactly_S2`) |
| Le moniteur de sécurité tourne dans **chaque** run | `kpis.json → safety` (patch `patches/p1_safety_emergency.py`, sauvegardes `.bak_20261012c`) |

## 2. Collecte

`agents/observation/collection_agent.py` : par voie entrante, véhicules, arrêtés, attente maximale, voies en vert, départs à la ligne d'arrêt, toutes les 5 s. Testée par `tests/test_agents.py`. Pas d'évaluation chiffrée séparée : c'est un capteur simulé exact.

## 3. Détection d'incidents

**Vérité terrain simulée :** vitesse d'une voie limitée à 0,05 m/s de 07:20 à 07:40 sur l'une de 2 approches chargées (`-31070#4_1`, `--31070#8_1`), contrôle S0, demande x1/x3/x5. Une alerte est vraie si elle porte sur l'arête de l'incident entre son début et sa fin + 60 s. Script : `scripts/simulation/evaluate_detection_v2.py`. Résumé : `output/experiments_v1/detection_v2/detection_v2_summary_v3.csv`.

| Variante | Graines | Runs | Rappel | Précision | F1 | Fausses alertes/h | Délai moyen |
|---|---|---|---|---|---|---|---|
| `rules` (≥ 8 arrêtés pendant 60 s ; véhicule arrêté ≥ 150 s) | 1–3 | 27 | 1,00 | 0,298 | 0,459 | 6,46 | 189 s |
| `gated` (même règle, filtrée par la prévision : déclenche seulement si l'observé dépasse de ≥ 5 la prévision faite 5 min plus tôt) | 1–3 | 27 | 1,00 | 0,293 | 0,453 | 6,83 | 189 s |
| `discharge` (voie bloquée : ≥ 20 s de vert sur 90 s, ≥ 3 arrêtés à chaque relevé, aucun départ) | 1–3 | 27 | 1,00 | 0,982 | **0,991** | **0,08** | 190 s |
| `rules` – confirmation | **11–12 (jamais utilisées)** | 18 | 1,00 | 0,322 | 0,488 | 6,24 | 185 s |
| `discharge` – confirmation | **11–12 (jamais utilisées)** | 18 | 1,00 | 0,970 | **0,985** | **0,12** | 188 s |

Par demande (graines 11–12, `discharge`) : x1 F1 1,00, 0 FA/h, délai 296 s ; x3 F1 1,00, 0 FA/h, 174 s ; x5 F1 0,962, 0,36 FA/h, 96 s.

**Conclusions.**
- La règle `discharge` est retenue (mode par défaut de l'application). Elle est confirmée sur des graines neuves.
- **Détection filtrée par la prévision** (`gated`) : **aucun gain** (F1 0,453 contre 0,459). À x5, la congestion récurrente dépasse aussi la prévision ; le filtre ne sépare pas incident et congestion. Résultat négatif conservé.
- Limites : 2 lieux d'incident, une seule fenêtre horaire, un seul type d'incident (voie ralentie), contrôle S0 seulement. Délai long à faible demande (≈ 5 min à x1), car la règle attend 3 véhicules arrêtés.

## 4. Prédiction en cascade (+5, +10, +15 min)

**Cible :** moyenne des véhicules arrêtés par feu sur la minute qui finit à t+h. **Modèle :** régression ridge, transformation log1p choisie sur la validation ; chaque étage reçoit les prédictions hors-échantillon de l'étage précédent (`agents/prediction/cascade.py`). Baselines : persistance (valeur actuelle) et profil historique (moyenne par feu, demande et heure, sur l'entraînement).

**Reproduction :** réentraînement complet → `cascade_model_v2repro.json` **identique** à `cascade_model_v2.json`.

**Jeux de données** (`scripts/simulation/generate_prediction_data.py`) : entraînement graines 201–203, test 301–302, hold-out **401–402 jamais utilisées** (36 épisodes, S0/S1/S2, x1–x6, 5 616 prévisions par horizon). Intervalle de confiance : bootstrap apparié par épisode.

Erreur absolue moyenne (véhicules arrêtés), hold-out (`prediction/cascade_metrics_holdout_v1.csv`) :

| Groupe | Horizon | Cascade | Persistance | Profil | Cascade vs persistance | Cascade vs profil |
|---|---|---|---|---|---|---|
| Tout | +5 | 2,80 | 3,49 | 4,14 | meilleure | meilleure |
| Tout | +10 | 2,79 | 3,44 | 4,22 | meilleure | meilleure |
| Tout | +15 | 2,99 | 3,41 | 4,61 | meilleure | meilleure |
| x1 | +5/+10/+15 | 0,54/0,52/0,49 | 0,59/0,55/0,54 | ≈ 5,0 | **non significatif** | meilleure |
| x4 | +5/+10/+15 | 2,80/2,75/2,88 | 3,78/3,65/3,45 | 2,41/2,45/2,63 | meilleure | non significatif (profil plus bas) |
| x5 | +5/+10/+15 | 4,22/4,19/4,57 | 5,35/5,20/5,25 | **3,47/3,51/3,96** | meilleure | **moins bonne (significatif)** |
| x6 | +5/+10/+15 | 6,07/6,19/6,81 | 7,43/7,55/7,35 | 6,79/7,09/7,69 | meilleure | non significatif |
| Congestionné | +5 | 7,75 | 9,96 | 8,54 | meilleure | non significatif |
| Congestionné | +10 | 7,53 | 9,93 | 8,88 | meilleure | non significatif |
| Congestionné | +15 | 8,90 | 9,36 | 10,09 | **non significatif** | non significatif |
| Contrôleur S1 (jamais vu à l'entraînement) | +5 | 2,26 | 2,85 | 3,86 | meilleure | meilleure |

Cascade et modèle direct (un modèle par horizon sans étage précédent) sont presque égaux (2,80/2,79/2,99 contre 2,80/2,80/3,02) : **l'apport de la cascade elle-même est faible**. La prévision est utile surtout par rapport à la persistance. À forte demande (x4–x5), le profil historique fait aussi bien ou mieux.

**En ligne** (pendant les runs, prévisions notées après coup) : par exemple S3 x5 graine 61, MAE +5 min 6,15 contre 8,38 pour la persistance (`kpis.json → prediction`).

## 5. Décision : stratégies S0 à S3

| Code | Stratégie | Nature |
|---|---|---|
| S0 | Temps fixe LuST | référence |
| S1 | Feux actuated SUMO (`tls_actuated_v1.add.xml`) | référence adaptative standard |
| S2 | Règle demande/creux (vert prolongé tant que la file servie existe, fin dès qu'un creux apparaît) | règle, réglée sur la graine 50 |
| S2F | S2 + prévision en cascade (prolonge si la file prévue monte) | utilise la prédiction |
| S2b | Max-pressure | résultat négatif conservé |
| S3 | Q-learning tabulaire par feu (voir §6) | apprentissage par renforcement |

**Protocole v2** (`scripts/simulation/analyze_strategies_v2.py`, dossier `output/experiments_v2b/`) : 6 stratégies × x1 et x5 × graines 1–3 (déjà utilisées en v1) et **61–65 (jamais utilisées pour un choix de conception)** = 96 runs. Comparaison appariée par graine (même demande), intervalle de Student à 95 % sur 5 graines.

**Reproductibilité :** les 36 runs des graines 1–3 sont **identiques** à v1 sur 12 indicateurs ; après les corrections du 12/10 (§8), les 96 runs v2b sont identiques aux 96 runs v2.

Temps de trajet moyen, graines neuves 61–65 (`experiments_v2b/results/RESULTS_v2_b.md`) :

| Stratégie | x1 (s) | Δ vs S0 | x5 (s) | Δ vs S0 | Attente x5 (s) | CO₂ x5 (kg) |
|---|---|---|---|---|---|---|
| S0 temps fixe | 99,8 | — | 134,9 | — | 38,9 | 1 349,6 |
| S1 actuated | 90,0 | −9,9 % | **113,4** | **−16,0 %** | 21,9 | 1 218,6 |
| S2 demande/creux | **88,9** | −10,9 % | 120,7 | −10,6 % | 29,4 | 1 256,2 |
| S2F + prévision | 88,9 | −10,9 % | 119,4 | −11,5 % | 28,3 | 1 248,6 |
| S2b max-pressure | 105,6 | **+5,8 %** | 136,5 | +1,2 % (n.s.) | 41,0 | 1 356,4 |
| S3 Q-learning | 88,9 | −10,9 % | 122,7 | −9,0 % | 30,1 | 1 268,0 |

Comparaisons appariées (5 graines neuves) :

| Comparaison | x1 | x5 |
|---|---|---|
| S1, S2, S2F, S3 contre S0 | toutes meilleures, 5/5 graines | toutes meilleures, 5/5 graines |
| S2 contre S1 | S2 meilleure (−1,1 s, 5/5) | **S1 meilleure** (+7,3 s pour S2, 0/5) |
| S3 contre S1 | S3 meilleure (−1,1 s, 5/5) | **S1 meilleure** (+9,3 s pour S3, 0/5) |
| S3 contre S2 | non significatif (−0,02 s) | non significatif (+2,1 s, IC [−1,1 ; +5,3]) |
| S2F contre S2 | **identique** (la prévision ne franchit jamais le seuil à x1) | non significatif (−1,3 s, IC [−4,2 ; +1,7], 4/5) |

**Conclusions.**
- Les stratégies adaptatives réduisent le temps de trajet de 9 à 16 % par rapport au temps fixe, en simulation.
- La meilleure stratégie à forte demande est **S1, le contrôleur actuated standard de SUMO**. Aucun de nos agents ne le bat à x5.
- **Utiliser la prévision dans la décision n'apporte pas de gain démontré** (S2F ≈ S2).
- Le RL (S3) n'est pas meilleur que la règle S2 qui lui sert de repli.

## 6. Revue de l'agent RL (S3)

| Élément | Valeur |
|---|---|
| Type | Q-learning tabulaire indépendant par feu, approximation semi-markovienne (une transition = d'un point de décision au suivant) |
| État | (phase verte, arrêtés sur les voies servies, max. d'arrêtés sur une autre phase, véhicules en mouvement servis, durée du vert), discrétisés |
| Actions | GARDER le vert / PASSER à la phase suivante (toujours par le jaune, via l'actionneur) |
| Récompense | −(somme des arrêtés sur toutes les voies entrantes du feu, relevés de 5 s entre deux décisions) / 10, actualisation γ^(nombre de relevés) |
| Entraînement | 26 épisodes, graines 101–126, x5, ε = 0,02 en fin d'entraînement (`rl/training_log_v4.csv`) ; versions v1 à v4 conservées |
| Table gelée | `rl/qtable_v4_FROZEN_ep26_eval.json` : 1 999 états vus, **341 états « fiables »** (les deux actions essayées ≥ 3 fois et valeurs différentes) |
| En évaluation | 0 mise à jour, 0 exploration (table gelée) ; **42,8 % des décisions viennent du repli S2** (états jamais vus ou peu visités) |
| Sécurité | les décisions passent par l'actionneur (ordre des phases, jaune, vert min 5 s, max min(60 s, 2 × programmé)) ; 0 violation (§7) |

**Verdict honnête :** l'agent RL décide de façon autonome dans 57 % des cas et s'appuie sur une règle pour le reste. Ses performances sont celles de cette règle (différence non significative). Cela ne démontre pas que l'apprentissage apporte un gain. À noter : la docstring de `QLearningController` mentionne encore un repli « durée programmée LuST », alors que le repli par défaut est la règle S2 (`fallback="demand_gap"`) ; c'est à corriger dans la documentation du code.

**Le RL et la priorité urgence sont séparés** : la priorité est un module d'intervention distinct (`agents/intervention/emergency_priority.py`), désactivé par défaut et évalué à part (§7.3). Le RL n'a jamais été entraîné avec une ambulance.

## 7. Sécurité des feux et véhicules d'urgence

### 7.1 Moniteur de sécurité

`agents/intervention/safety_monitor.py` ne fait que lire l'état des feux à chaque pas. Il vérifie :
- l'état affiché fait partie du programme ;
- aucun passage vert → rouge sans jaune ;
- vert ≥ 5 s ;
- jaune et tout-rouge à leur durée programmée, avec un dépassement signalé **dès qu'il se produit** (correction du 12/10) ;
- vert ≤ 90 s.

| Stratégie | Runs v2b | Transitions vérifiées | Violations | Collisions | Téléportations |
|---|---|---|---|---|---|
| S0 | 16 | 16 528 | 0 | 0 | 0 |
| S1 | 16 | 42 475 | 0 | 0 | 0 |
| S2 | 16 | 14 846 | 0 | 0 | 0 |
| S2F | 16 | 14 871 | 0 | 0 | 0 |
| S2b | 16 | 11 762 | 0 | 0 | 0 |
| S3 | 16 | 17 625 | 0 | 0 | 0 |

**Contrôles négatifs** (le moniteur doit signaler une faute provoquée exprès) :
- `test_monitor_detects_an_unsafe_jump` (vert → rouge sans jaune) : signalé ;
- `test_monitor_detects_a_stuck_yellow` (jaune maintenu 600 s) : signalé.

### 7.2 Conflits de mouvements

`scripts/simulation/check_signal_conflicts_v1.py` vérifie chaque phase des programmes LuST et actuated (8 programmes, 48 phases) avec la matrice de conflits de SUMO (`lane.getFoes`).

Résultat : **0 conflit prioritaire** (deux mouvements « G » qui se croisent). Les paires « G »/« g » (le mouvement « g » cède le passage, par exemple un tourne-à-gauche) sont autorisées et comptées.

Contrôle négatif : un état « tout vert » donnerait 58 paires en conflit, donc la vérification est sensible. Fichiers : `output/safety/signal_conflicts_v1.csv` et `.md`.

Les contrôleurs ne fabriquent jamais d'état de feu : ils choisissent seulement de garder ou de terminer une phase verte du programme.

### 7.3 Priorité véhicules d'urgence (module séparé)

Ce module fonctionne en simulation seulement :
- il détecte une ambulance (vClass emergency) à 150 m ou moins d'un feu ;
- il termine le vert en cours après 5 s minimum, toujours par son jaune ;
- il donne ensuite le vert de son mouvement, maintenu 30 s au plus ;
- il rend enfin la main au contrôleur par le jaune suivant.

Évaluation : ambulance insérée à 07:20, x5, graines 1–5, avec et sans priorité. Script `scripts/simulation/evaluate_emergency.py --folder emergency_v2`, résultats `output/experiments_v1/emergency_v2/emergency_summary_v2.csv`.

| Stratégie | Trajet ambulance sans → avec priorité | Attente ambulance | Attente moyenne des autres véhicules | Violations |
|---|---|---|---|---|
| S0 | 204,6 → 182,2 s (−11 %) | 86,8 → 31,6 s | 39,7 → 37,0 s | 0 |
| S1 | 150,8 → 149,4 s (−1 %) | 23,2 → 13,8 s | 22,4 → 21,8 s | 0 |
| S2 | 211,0 → 149,8 s (−29 %) | 72,6 → 19,2 s | 30,5 → 29,1 s | 0 |

L'effet varie d'une graine à l'autre. Sous S0, les graines 2 et 4 sont un peu plus lentes avec priorité (180 → 185 s, 184 → 189 s). Sous S1, déjà rapide sans priorité, 3 graines sur 5 sont plus lentes (de +5 à +11 s). Sous S2, l’ambulance est plus rapide sur les 5 graines (de −1 à −127 s). Cinq graines ne suffisent pas pour un intervalle de confiance serré : le gain n'est net que sous S0 et S2.

## 8. Défauts trouvés et corrigés pendant cette vérification (12/10)

| Défaut | Effet | Correction | Preuve |
|---|---|---|---|
| Après la libération d'un feu par la priorité urgence, l'actionneur appliquait son maintien de 3 600 s à la phase **jaune** qui venait d'être posée : il agissait sur la phase observée avant le changement. | Sous S2 avec priorité, le feu restait jaune jusqu'à la fin et le réseau se bloquait : 1 561 arrivées au lieu de 3 706, file moyenne de 218 véhicules. Première évaluation urgence (S2) invalide. | `tls_actuator.py` : l'actionneur ignore un feu dont la phase a changé depuis l'observation (sauvegarde `.bak_20261012d`). Sans ambulance, rien d'autre ne change les phases : les 96 runs v2b sont identiques à v2. | `test_signals_stay_controlled_after_emergency_release` échoue sur l'ancien code et passe sur le nouveau. Ancien dossier conservé, marqué remplacé (`emergency/README_SUPERSEDED.md`, registre `file_status_register_v1.csv`). |
| Le moniteur ne contrôlait la durée d'un jaune qu'à sa **fin** : un jaune qui ne finit jamais n'était pas signalé. | Le défaut ci-dessus est passé inaperçu (0 violation affichée). | `safety_monitor.py` : signalement du dépassement pendant qu'il se produit, nouvelle règle tout-rouge (sauvegarde `.bak_20261012d`). | `test_monitor_detects_a_stuck_yellow` échoue sur l'ancien code et passe sur le nouveau. Section sécurité de `RESULTS_v2_a.md` remplacée par `experiments_v2b/results/RESULTS_v2_b.md`. |
| Le test d'urgence initial ne vérifiait que la sécurité et le type des actions. | Il n'a pas détecté le blocage. | Ajout d'une vérification « chaque feu reçoit encore des décisions après le passage » et « file ≤ 1,5 × la référence ». | — |

## 9. Ce qui n'est pas affirmé

- Aucun gain sur le trafic réel du Kirchberg : aucune donnée réelle n'a servi, et la calibration avec les comptages PCH a **échoué** (`DATA_VALIDATION_REPORT.md` §3).
- La prévision n'améliore pas démontrablement la décision (S2F ≈ S2).
- Le RL ne dépasse ni S1 ni sa règle de repli.
- La détection n'est validée que sur un type d'incident simulé et deux lieux.
- La priorité urgence n'est pas une préemption réelle des feux.

## 10. Tests correspondants

Machine Linux de ton PC, 12/10 : **109 tests réussis sur 109** (277 sous-tests). Journal : `data/reports/test_logs/linux_vm_pytest_20261012_184601.log`.

Les tests propres à ce rapport sont :
- `tests/test_cascade.py` (6) ;
- `tests/test_safety_emergency.py` (11) ;
- `tests/test_agents.py`.

Sous Windows, ces tests **n'ont pas encore été exécutés** (pytest absent au dernier passage) : voir `FINAL_DEMO_REPORT.md`.
