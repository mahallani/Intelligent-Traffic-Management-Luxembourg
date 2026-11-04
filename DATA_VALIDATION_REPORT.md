# DATA_VALIDATION_REPORT – données réelles et simulation (2026-10-12)

Tous les chiffres sont recalculés depuis les fichiers du disque. Rapports détaillés antérieurs :
- `data/reports/DATA_READINESS_REPORT.md` ;
- `data/reports/source_inventory_v1.md` ;
- `data/reports/data_validation_v1.md` (73 contrôles sur 73).

## 1. Données effectivement disponibles

| Source | Nature | Période réelle | Volume utile | Fichiers nettoyés |
|---|---|---|---|---|
| CITA trafic (DATEX v2) | réelle | 3 instants : 07/10/2026 16:53 et 16:58 UTC, 10/10/2026 20:33 UTC | 492 lignes, 247 capteurs, max 2 mesures par capteur | `data/processed/cita_traffic/cita_traffic_reference_v1.csv` |
| CITA trafic (anciens collecteurs) | réelle, **attribution des capteurs fausse** | 07/10 → 09/10/2026 | 34 483 lignes, diagnostic seulement | `data/interim/cita/cita_traffic_legacy_diagnostic_v1.csv` |
| CITA événements | réelle | instantanés du 07/10 et du 10/10/2026 | 24 événements avec identifiants DATEX, 0 accident | `data/processed/cita_events/cita_events_v1.csv` |
| PCH comptages | réelle | 01/01 → 31/12/2025 (30/03 absent) | 272 postes, 815 739 journées-postes-sens-classes | `data/processed/pch/*_v1.*` |
| GTFS | réelle (horaire planifié) | 30/09 → 12/12/2026 | 28 993 courses, 2 805 arrêts | `data/processed/gtfs/*_v1.*` |
| LuST | **synthétique** (scénario de recherche, vers 2015) | journée type | réseau + demande | `LuSTScenario/` (non modifié) |
| Simulations du projet | **simulées** | — | 30 runs d'évaluation, 18 runs de détection, 26 épisodes RL | `sumo/lust_4_intersections/output/experiments_v1/` |

**Collecte CITA de 7 jours : non démarrée.** Le 12/10, aucun fichier `cita_traffic_sites_v2.csv` ni `cita_events_records_v2.csv` n'existe, et `data/reports/collection_logs/` est vide.

## 2. Séparation des données

- **Brutes**, jamais modifiées : `data/raw/`, `data/historical/`.
- **Nettoyées et préparées** : `data/interim/` (diagnostics, exports), `data/processed/` (jeux validés).
- **Observations réelles** : marquées `data_origin = real_*` dans chaque fichier préparé.
- **Simulées** : `data_origin = SIMULATED_sumo_lust_kirchberg_4tls`. Elles sont rangées sous `sumo/lust_4_intersections/output/` et `data/interim/simulation/`. Le validateur vérifie qu'aucun fichier réel ne contient de lignes simulées.

## 3. Compatibilité géographique (PCH) et calibration

- **Zone des 4 feux :** aucun poste PCH ni capteur CITA dans la zone. Le poste le plus proche (439, Neudorf, N1) est à 1,0 km du centre de la zone, hors du réseau réduit. **Aucune calibration locale n'est donc possible.**
- **Indicateur commun :** véhicules/heure sur une section, les deux sens confondus, de 07:00 à 08:00. Côté réel : PCH 2025, moyenne des mardis à jeudis, `DIRECTION 3` (deux sens), `VEHICULE U` (tous véhicules). Côté simulé : entrées par arête dans un run LuST de 07:00 à 08:30.
- **Appariement :** 19 postes de l'emprise LuST, avec l'arête la plus proche et sa voie inverse (moins de 6 m). Les arêtes LuST n'ont pas de nom de rue, donc l'appariement reste **à vérifier manuellement**. Script : `scripts/data_pipeline/compare_pch_lust_v1.py`. Résultats : `data/reports/pch_vs_lust_0700_0800_v1.csv` et `.json`.
- **Écarts avant calibration :**
  - GEH moyen 13,2 sur la moitié d'ajustement, 14,0 sur la moitié de test (GEH : écart usuel entre comptages simulés et réels ; < 5 est le seuil d'acceptation) ;
  - GEH < 5 pour 20 % et 11 % des postes ;
  - erreur relative moyenne (MAPE) d'environ 52 %.
- **Essai de calibration simple :** un facteur global de demande (1,242) ajusté sur 10 postes et testé sur les 9 autres.
  - Sur les postes de test, le GEH moyen passe de 13,95 à 14,92 et la MAPE de 51,7 % à 63,6 % : c'est **pire**.
  - Les écarts sont locaux (rapports réel/simulé de 0,31 à 3,6) et ne se corrigent pas par un facteur global.
  - **La calibration est un échec documenté** : elle n'est pas appliquée au scénario.
- **Usage des comptages :** les données PCH sont toujours traitées comme des comptages (véh/h), jamais comme des vitesses ou des temps de trajet.

## 4. Compatibilité GTFS ↔ réseau SUMO

Script `scripts/data_pipeline/compare_gtfs_sumo_v1.py`, résultats `data/reports/gtfs_vs_sumo_kirchberg_v1b.*`. Le premier passage (v1) avait deux erreurs de détection, corrigées ; v1 est marqué remplacé dans le registre.

- **Arrêts :** 18 arrêts GTFS dans la zone (plus 200 m de marge). Chacun a une voie SUMO à moins de 15 m, mais seulement **3** ont un arrêt LuST à moins de 50 m.
- **Lignes :** les lignes LuST du scénario sont 7, 12, 13, 18 et 25. GTFS 2026 dessert la zone avec 18 lignes. 3 lignes ont un numéro en commun (12, 18, 25), mais la correspondance des itinéraires n'est pas vérifiée.
- **Tram T1 :** il dessert la zone, mais le réseau SUMO n'a **aucune** voie réservée au tram.
- **Conclusion :** GTFS n'est pas fusionné au scénario. Il est utilisable pour une future demande de bus mise à jour, au prix d'un travail de réseau (ajout du tram).

## 5. Collecteur CITA : exécution contrôlée

- Les deux collecteurs prennent désormais un **verrou exclusif** (`<fichier>.lock`, module `single_instance.py`). Un second lancement sur le même fichier est refusé (test `tests/test_single_instance.py`). Le verrou est libéré par le système à la fin du processus, même après un plantage.
- **Commandes** (deux fenêtres PowerShell, 168 h, sans archivage XML) : voir `data/reports/DATA_READINESS_REPORT.md` §9 et le message de lancement du 10/10. Chaque collecteur écrit un journal dans `data/reports/collection_logs/`.
- Le développement de l'application ne dépend pas de cette collecte.

## 6. Mise à jour du 12/10/2026 (soir)

- **Aucune nouvelle donnée réelle.** La collecte CITA de 7 jours n'est toujours pas démarrée : `data/reports/collection_logs/` est vide. Aucun fichier de `data/raw/` ni de `data/historical/` n'a été modifié.
- **Agents : simulation uniquement.** Les agents (détection, prédiction en cascade, décision, RL, priorité urgence) ont été entraînés et évalués **uniquement sur des runs SUMO**. Les incidents et l'ambulance sont simulés. Chaque sortie porte `data_origin = SIMULATED_sumo_lust_kirchberg_4tls`.
- **Nouvelles sorties simulées :**
  - `sumo/lust_4_intersections/output/experiments_v2/`, `experiments_v2b/` (96 runs chacun) ;
  - `experiments_v1/emergency_v2/` ;
  - `experiments_v1/detection_v2/*_confirm_seeds11_12/` ;
  - `output/safety/` (programmes de feux) ;
  - `output/app_runs/` (runs lancés depuis l'application).
- **Provenance dans l'application** : la page « Données » sépare les sources réelles (CITA, PCH, GTFS) des sources simulées (LuST, runs). Chaque page porte la mention « simulé », et aucune valeur réelle n'est affichée comme sortie d'un contrôleur.
- **Registre** `data/reports/file_status_register_v1.csv` : 2 lignes « remplacé » ajoutées.
  - Évaluation urgence S2 de `experiments_v1/emergency/`, invalidée par un bug d'actionneur.
  - Section sécurité de `experiments_v2/results/RESULTS_v2_a.md`, produite avec un moniteur incomplet.
  - Les deux sont conservées, rien n'est supprimé.
- **La calibration reste un échec documenté** (§3) : les résultats de simulation ne sont pas transposables au trafic réel du Kirchberg.
