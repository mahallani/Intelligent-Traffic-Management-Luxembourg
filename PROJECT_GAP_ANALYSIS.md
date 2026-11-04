# PROJECT_GAP_ANALYSIS – état du projet

## Mise à jour du 12/10/2026 (soir), après les phases 4 à 7

Légende des preuves :
- « Linux » = machine Linux de ton PC (journal `data/reports/test_logs/linux_vm_pytest_20261012_184601.log`, 109/109) ;
- « Windows » = journal `validation_20261012_134608.log` (antérieur à ces travaux).

**Tous les résultats d'agents sont simulés.**

| # | Fonctionnalité | État | Preuve | Reste à faire | Priorité |
|---|---|---|---|---|---|
| 1 | Scénario SUMO Kirchberg 4 feux | Fonctionne | Linux : tests ; Windows : 12/12 | — | — |
| 2 | Couche TraCI | Fonctionne | Linux : tests | Module de propagation toujours inutilisé (la cascade suit `TLS_CHAIN`) | P3 |
| 3 | Agent de collecte | Fonctionne | `test_agents` | — | — |
| 4 | Agent de détection | **Fonctionne (simulé)** | Règle `discharge` : F1 0,991, 0,08 fausse alerte/h (graines 1–3) ; **confirmée** sur les graines 11–12 : F1 0,985, 0,12 FA/h | Valider sur d'autres types d'incident et d'autres lieux ; filtrer par la prévision n'apporte rien (F1 0,453) | P3 |
| 5 | Prédiction en cascade +5/+10/+15 | **Fonctionne (simulé)** | Hold-out (graines 401–402) : MAE 2,80 / 2,79 / 2,99 contre 3,49 / 3,44 / 3,41 pour la persistance ; reproduction identique | Pas mieux que la persistance à x1, ni en congestion à +15 min. Le profil fait mieux à x5. La cascade apporte peu par rapport au modèle direct. | P2 |
| 6 | Décision (S0–S3, S2F) | Fonctionne | v2b : 96 runs, graines neuves 61–65 ; S1 −16,0 %, S2 −10,6 %, S2F −11,5 %, S3 −9,0 % à x5 contre S0 | Aucun agent ne bat S1 à x5 ; S2F ≈ S2 | P2 |
| 7 | La prévision alimente la décision et peut être coupée | **Fonctionne** | `decisions_with_forecast` ; S2F sans prévision = S2 (test) | — | — |
| 8 | RL (S3) | Fonctionne, gain non démontré | 341/1 999 états fiables, 42,8 % de repli, ≈ S2 (n.s.) | Plus d'épisodes, états plus grossiers | P2 |
| 9 | Sécurité des feux | **Fonctionne** | Moniteur dans chaque run : 0 violation sur 96 runs ; 0 conflit prioritaire sur 48 phases ; 2 contrôles négatifs | — | — |
| 10 | Priorité urgence (module séparé) | **Fonctionne (simulé)** | Ambulance −11 % (S0), −29 % (S2), −1 % (S1), 0 violation ; bug de blocage trouvé et corrigé | Plus de graines pour un IC | P3 |
| 11 | Reroutage | Test de faisabilité seulement | `validate_scenario.py` | Non exposé dans l'application | P3 |
| 12 | Application (Next.js + FastAPI/TraCI) | **Fonctionne sous Linux** (API + HTTP réel) | 5 tests API ; session HTTP réelle : démarrer, pause, reprendre, arrêter, 409, exports, comparaison | **Rendu navigateur non observé ; Windows non testé** | **P1** |
| 13 | Évaluation reproductible | Fonctionne | 36/36 runs v1 = v2 ; 96/96 v2 = v2b | — | — |
| 14 | Données réelles CITA | Partiel | 492 lignes, 3 instants | **Collecte 7 jours non démarrée** | P1 (calendrier) |
| 15 | PCH, GTFS | Prêts, non utilisés par les agents | `DATA_VALIDATION_REPORT.md` | — | — |
| 16 | Calibration réel ↔ simulé | **Échec documenté** | GEH test 13,95 → 14,92 | Comparaison d'ordre de grandeur seulement | P3 |
| 17 | Tests Windows | **Non exécutés** | pytest absent le 12/10 13:46 | `pip install -r requirements.txt`, puis `validate_windows.ps1` (mis à jour) | **P1** |
| 18 | Démo graphique Windows | **Non observée** | — | Lancement par toi | **P1** |

**Défauts trouvés et corrigés le 12/10 :**
- actionneur appliquant le maintien de 3 600 s à un jaune après une libération d'urgence ;
- moniteur aveugle à un jaune qui ne finit pas ;
- chemin de run de l'application incompatible avec les dossiers temporaires des tests.

Détails dans `AGENT_EVALUATION_REPORT.md` §8.

---

## État au début de la finalisation (12/10 matin, conservé)

Ce constat repose sur l'inspection du disque et sur les tests et journaux existants. « Linux » désigne la machine Linux de ton PC, qui écrit directement dans le dossier du projet. « Windows » désigne ton Python 3.11.9 avec SUMO 1.27.1, d'après le journal `data/reports/windows_validation/validation_20261012_134608.log`.

### Matrice des fonctionnalités

| # | Fonctionnalité | État actuel | Preuve | Problème | Action requise | Priorité |
|---|---|---|---|---|---|---|
| 1 | Scénario SUMO Kirchberg (4 feux) | Fonctionne | Windows : 12/12 contrôles (73 arêtes, 33 nœuds, 778 véhicules) ; Linux : `test_kirchberg_scenario` | Réseau et demande LuST d'environ 2015 (sans tram T1) | Aucune (limite documentée) | — |
| 2 | Couche TraCI (`traci_layer/`) | Fonctionne | `test_synthetic`, `test_metrics`, `test_lust_integration` (Linux) | Le module de propagation (`edge_data._propagated`, `network.upstream_within`) n'est ni testé ni utilisé | Réutiliser la topologie dans la cascade et la tester | P2 |
| 3 | Agent de collecte | Fonctionne | `agents/observation/collection_agent.py` ; `test_agents` | Observation par voie seulement (pas par arête ni débit) | Ajouter le débit par approche (utile à la prédiction) | P2 |
| 4 | Agent de détection | Partiel | 6/6 incidents simulés détectés ; 0 fausse alerte/h à ×1, mais 15–16/h à ×5 (`detection_summary_x5.csv`) | Ne sépare pas incident et congestion récurrente ; pas de précision/rappel/F1 | Règle relative à un profil normal + métriques P/R/F1 sur incidents simulés | P1 |
| 5 | Agent de prédiction **en cascade** | **NOT IMPLEMENTED** | `CASCADE_PREDICTION_AUDIT.md` ; `agents/cascade/` vide | Horizon unique de 60 s, moins bon que la persistance, non relié à la décision | Cascade +5/+10/+15 min, baselines, erreurs par horizon, journal, transmission à la décision | **P1** |
| 6 | Agent de décision | Fonctionne | Résultats sur 3 graines (`RESULTS_v1.md`) : S1 −14,7 %, S2 −10,9 %, S3 −9,7 % de temps de trajet à ×5 | Le RL n'atteint pas S1 ni S2 ; aucune décision n'exploite de prévision | Revue du RL ; option « contrôleur informé par la prévision » ; garder S1/S2 comme référence | P1 |
| 7 | Agent d'intervention (feux) | Fonctionne | `test_actuator_keeps_order_yellow_min_and_max_green` | — | Test TraCI direct de transition sûre conservé | — |
| 8 | Reroutage | Test de faisabilité seulement | `validate_scenario.py` S2 (Windows : 80 routes changées, trajet 143,4 → 137,7 s) | Pas d'agent ni d'option dans l'application | L'exposer comme intervention simulée testée, sans le présenter comme agent abouti | P3 |
| 9 | Priorité véhicules d'urgence | Test de faisabilité seulement | `validate_scenario.py` S3 (Windows : ambulance 159 → 105 s, 1 préemption) | Préemption sans jaune (documenté dans le README du scénario) | Version sûre (jaune puis vert) testée séparément | P3 |
| 10 | Application de pilotage (frontend + backend) | **Absente** | `dashboard/` vide ; aucune API | Exigence du professeur non couverte | Backend Python (TraCI) + frontend Next.js relié, avec démarrer/pause/reprendre/arrêter, feux, KPI, comparaison, export CSV | **P1** |
| 11 | Évaluation reproductible | Fonctionne | `run_experiment.py`, `compare_strategies.py`, recontrôle à 0 écart | Exécutable en ligne de commande seulement | L'appeler depuis l'application | P2 |
| 12 | Données réelles CITA | Partiel | `cita_traffic_reference_v1.csv` : 492 lignes, 3 instants | Collecte de 7 jours **non démarrée** ; pas de série exploitable | Préparer l'exécution contrôlée (un seul collecteur) ; ne bloque pas l'application | P2 |
| 13 | PCH 2025 | Prêt (comptages) | `pch_preparation_v1.json` : sommes vérifiées, CRS vérifié | Aucun poste dans la zone des 4 feux (le plus proche à 1,0 km) | Comparaison d'ordre de grandeur seulement, sans calibration locale (voir `DATA_VALIDATION_REPORT.md`) | P2 |
| 14 | GTFS | Prêt | Clés étrangères OK ; 11 arrêts dans la zone | Arrêts GTFS ≠ arrêts LuST ; tram absent de LuST | Contrôle de compatibilité arrêt par arrêt | P3 |
| 15 | Calibration réel ↔ simulé | Impossible localement | Aucune mesure réelle dans la zone | — | Le documenter, et tester un écart sur un indicateur commun si un point existe | P3 |
| 16 | Tests Windows | Partiel | pytest **absent** sous Windows (journal du 12/10) | Les tests n'ont pas tourné sous Windows | Installer pytest (déjà dans `requirements.txt`) puis relancer | P1 |
| 17 | Démo graphique Windows | Non observée | Aucun journal de démo | — | Lancement par l'utilisateur + capture d'écran | P1 |

### Composants redondants ou inutiles

- `agents/cascade/` (vide) et `agents/prediction/` : une seule responsabilité. La cascade sera implémentée dans `agents/prediction/`, et `agents/cascade/` restera vide (non supprimé), avec un renvoi dans la documentation.
- `TrafficDataCollector` (traci_layer, observation riche, lente) et `CollectionAgent` (agents, observation légère pour le contrôle) se recouvrent. Les deux sont gardés : le premier sert à la validation et aux exports, le second à la boucle de contrôle.
- `sumo/test/` (réseau à 2 arêtes, 0 feu) et `traci/test_lust.py` : anciens essais, non utilisés, conservés.

### Boucle complète visée

```
SUMO ─TraCI─► collecte ─► détection ─► prédiction (cascade +5/+10/+15) ─► décision ─► intervention ─TraCI─► SUMO
                                   └────────────── journal (prévisions, erreurs, décisions, KPI) ─► application
```

Aujourd'hui, la prédiction est calculée mais **ne parvient pas** à la décision, et aucune application ne pilote la boucle.

### Ordre de travail retenu

1. Phase 3 : données (rapport, aucune calibration fictive).
2. Phase 4 : cascade (P1), détection (P1), revue du RL, sécurité des feux.
3. Phase 5 : application.
4. Phase 6 : tests.
5. Phase 7 : rapports.
