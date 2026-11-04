# DATA READINESS REPORT – Luxembourg (v1, 2026-10-10)

Périmètre : Luxembourg uniquement. Toutes les valeurs ci-dessous ont été recalculées par les scripts cités et vérifiées par `validate_datasets.py` (73/73 contrôles réussis, `data_validation_v1.md`). Les valeurs « héritées » (non recalculées) sont signalées comme telles.

## 1. Verdict par objectif (critères mesurables : `readiness_by_objective_v1.md`)

| Objectif | Verdict | Mesure décisive | Seuil |
|---|---|---|---|
| A. Détection d'incidents | **NON ENTRAÎNABLE** | 4 événements non planifiés, 0 accident, 2 jours de trafic | ≥ 100 incidents (dont ≥ 30 accidents), ≥ 28 jours |
| B. Prévision +5/+10/+15 min | **NON ENTRAÎNABLE** | max. 2 observations par capteur, 0 paire (lag, cible) | ≥ 2 016 pas (7 jours) par capteur, ≥ 10 000 paires par horizon |
| C. SUMO / RL | **SIMULATION SEULEMENT** | 0 capteur CITA et 0 poste PCH dans la zone Kirchberg | ≥ 1 point d'observation réel dans la zone |
| D. KPI d'impact | **KPI SIMULÉS SEULEMENT** | aucune mesure réelle de temps de parcours, file ou attente | temps de parcours, vitesse, débit réels |

Aucun modèle n'est déclaré fiable : aucun entraînement n'a été lancé faute de données suffisantes.

## 2. Jeux de données produits (dimensions réelles)

| Fichier | Lignes × colonnes | Origine | Usage |
|---|---|---|---|
| `processed/cita_traffic/cita_traffic_reference_v1.csv` | 492 × 30 | réel CITA DATEX v2 (247 capteurs) | référence trafic |
| `interim/cita/cita_traffic_legacy_diagnostic_v1.csv` | 34 483 × 16 | anciens collecteurs | **diagnostic seulement** |
| `processed/cita_events/cita_events_record_versions_v1.csv` | 26 états | réel DATEX v3.6 | états (record × version) |
| `processed/cita_events/cita_events_v1.csv` | 24 × 29 | réel DATEX v3.6 | événements uniques (16 situations) |
| `interim/cita/cita_events_legacy_states_v1.csv` | 134 états / 64 événements | anciens CSV sans id | diagnostic + correspondance |
| `reports/cita_events_correspondence_v1.csv` | 64 | — | 18 exactes, 0 incertaine, 46 sans correspondance |
| `processed/pch/pch_posts_v1.csv` | 272 × 20 | réel PCH 2025 | postes, coordonnées |
| `processed/pch/pch_daily_counts_v1.csv.xz` | 815 739 × 37 | réel PCH 2025 | comptages horaires (format large) |
| `processed/pch/pch_hourly_counts_long_lust_bbox_v1.csv.xz` | 2 011 872 × 9 | réel PCH 2025 | 32 postes de l'emprise LuST (format long) |
| `processed/gtfs/gtfs_stop_times_prepared_v1.csv.xz` | 660 706 × 11 | horaire GTFS | temps en secondes, > 24 h conservés |
| `processed/gtfs/gtfs_stops_prepared_v1.csv` | 2 805 × 15 | horaire GTFS | appartenance aux zones |
| `processed/gtfs/gtfs_trips_prepared_v1.csv` | 28 993 × 19 | horaire GTFS | — |
| `processed/gtfs/gtfs_service_dates_v1.csv` | 6 950 × 3 | horaire GTFS | dates actives par service |
| `processed/gtfs/gtfs_kirchberg_zone_stop_times_v1.csv` | 8 356 × 20 | horaire GTFS | 11 arrêts, 4 684 courses, 18 lignes |
| `processed/tasks/task_A_event_label_inventory_v1.csv` | 24 × 16 | réel | inventaire des étiquettes |
| `processed/tasks/task_A_traffic_with_event_context_v1.csv` | 492 × 14 | réel | contexte, pas une étiquette d'incident |
| `processed/tasks/task_B_forecast_panel_v1.csv` | 492 × 26 | réel | panel, lags et cibles = vides (pas de pas consécutifs) |
| `processed/tasks/task_C_real_cita_observables_lust_bbox_v1.csv` | 123 × 12 | réel | 63 capteurs |
| `processed/tasks/task_C_real_pch_potential_demand_profiles_v1.csv` | 1 968 × 18 | réel | demande **potentielle**, compatibilité non vérifiée |
| `processed/tasks/task_C_SIMULATED_kpis_kirchberg_v1.csv` | 78 × 6 | **SIMULÉ** (SUMO, phase 2) | — |
| `processed/tasks/task_D_kpi_catalogue_v1.csv` | 9 × 6 | réel + simulé étiquetés | — |

## 3. Trafic CITA

- **Couverture temporelle :** 3 horodatages de mesure, à savoir 2026-10-07 16:53 et 16:58 UTC (archives XML) et 2026-10-10 20:33 UTC (collecte de validation). Chaque capteur a au plus 2 observations, séparées de 3 jours.
- **Couverture spatiale :** 7 routes (A1, A3, A4, A6, A7, A13, B40), soit 247 capteurs ; lat 49.471–49.815, lon 5.903–6.490.
- **Valeurs manquantes :** vitesse 5,89 % ; occupation 4,47 % ; débit 0 % ; coordonnées 6,3 % ; direction 11,99 %. Des capteurs de débit seul n'ont aucune localisation dans le XML, et rien n'a été inventé pour eux.
- **Drapeaux :** speed_above_130 (7), collection_ts_from_file_mtime (247), aucun conflit.
- **Unités :**
  - vitesse en km/h (convention DATEX ; l'unité n'est pas écrite par CITA) ;
  - occupation en % ;
  - débit en véh/h (`vehicleFlowRate`), période publiée 3 600 s ; l'ambiguïté entre heure glissante et taux horaire n'est pas résolue.
  - La colonne `vehicle_flow` n'existe pas dans le flux et **n'a pas été créée**.
- **Fuseaux horaires (preuves explicites) :**
  - Les mesures portent l'offset explicite `+02:00`.
  - La collecte v2 est en UTC explicite.
  - Les anciens CSV ont une heure de PC naïve. Preuve : la dernière heure naïve de chaque fichier comparée à la date de modification du fichier (UTC) donne un écart de **+1,00 h** sur les 5 fichiers.
  - Incertitude résiduelle : cette preuve suppose un offset constant et des dates de fichier non altérées par une copie.
- **Dédoublonnage :**
  - Clé : `sensor_id` + `measurement_timestamp`.
  - Répétition identique : on garde une ligne, `n_sightings` compte les copies et toutes les sources sont listées.
  - Contradiction : toutes les lignes sont gardées, avec le drapeau `conflict_same_key`.
  - Anciens fichiers : 104 933 et 2 034 répétitions identiques regroupées ; 9 contradictions de clé dans `cita_traffic_historical.csv`.

## 4. Événements CITA

- Les vrais identifiants DATEX (situation, record, version) proviennent du XML brut du 07/10 et de la collecte du 10/10. On obtient 24 événements, dont 15 vus aux deux dates.
- **Types** (xsi:type publié) : MaintenanceWorks 17, ConstructionWorks 3, EquipmentOrSystemFault 3, GeneralObstruction 1. **Aucun accident.** Aucun type n'a été déduit des commentaires (luxembourgeois, texte libre).
- **Fin d'événement :** elle n'est pas observable. CITA ne marque pas la fin ; l'événement disparaît du flux. `overall_end_time` est vide à 100 %.
- **Booléens :** valeurs true/false, valeurs inconnues gardées en NA, texte brut conservé.

## 5. PCH 2025

- **Volume et période :** 272 postes, du 2025-01-01 au 2025-12-31. **Le 2025-03-30 (changement d'heure) est absent.** Il manque 0 valeur et il n'y a aucun doublon de clé.
- **Sémantique vérifiée :**
  - somme P00..P23 = SUM_TRAF sur 100 % des lignes ;
  - DIRECTION : 1 = D1→D2, 2 = D2→D1, 3 = deux sens, vérifié par le texte SENS sur tous les postes ;
  - DIRECTION 3 = 1 + 2 sur 99,90 % des lignes évaluables (792 exceptions, signalées) ;
  - VEHICULE : U = C + V sur 99,999 % des lignes (9 exceptions). U est donc le total. Le sens des lettres C et V n'est **pas documenté** : elles sont gardées comme codes.
- **Coordonnées :** LUREF (EPSG:2169), vérifié par conversion. Six localités repères tombent toutes à moins de 3 km de leur centre (Clemency 0,5 km, Remich 0,3 km…).
- **Zones :** aucun poste dans la zone Kirchberg à 4 feux ; le plus proche, Neudorf N1, est à 1,0 km. 32 postes sont dans l'emprise LuST, dont 23 avec des arêtes LuST candidates **non vérifiées**.
- Les comptages sont des véh/h et **ne sont jamais utilisés comme vitesses**.

## 6. GTFS

- **Intégrité :**
  - clés primaires uniques ;
  - 12 relations de clés étrangères contrôlées, 0 orphelin ;
  - 0 heure illisible et 0 retour en arrière dans une course ;
  - 9 046 passages après 24:00:00, conservés en secondes (≥ 86 400).
- **Période et fuseau :** du 2026-09-30 au 2026-12-12. Le fuseau déclaré est Europe/Berlin, qui a les mêmes offsets que le Luxembourg.
- **Arrêts hors du Luxembourg :** 44 arrêts sont transfrontaliers (Trier, Merzig…), ils sont signalés.
- **Lien transport public – route :** il repose uniquement sur les coordonnées des arrêts dans l'emprise de la zone SUMO. Il n'y a pas d'appariement aux arêtes. GTFS est un horaire planifié, pas une observation.
- **Ligne T1 (tram) :** elle dessert la zone Kirchberg, alors que le réseau LuST (~2015) n'a pas de tram. C'est une incohérence à traiter avant toute comparaison réel/simulé.

## 7. Pas de fusion forcée

CITA, PCH, GTFS et SUMO restent dans des fichiers séparés. Chaque ligne porte `data_origin` (`real_cita_*`, `real_pch_2025`, `real_gtfs_timetable`, `SIMULATED_sumo_*`). Le validateur vérifie que les fichiers réels ne contiennent ni données simulées ni anciennes données.

## 8. Données supplémentaires nécessaires

1. **Collecte CITA v2 continue** : minimum 7 jours (objectif B, minimal), 28 jours recommandés (saisonnalité hebdomadaire, objectif A). Le PC doit rester allumé et sans mise en veille.
2. **Étiquettes d'incidents** horodatées et géolocalisées : accidents et pannes. Le dossier `data/raw/accidents` est vide. La source est à identifier (Police grand-ducale, CITA, data.public.lu), avec disponibilité à vérifier.
3. **Observation réelle dans la zone Kirchberg** : compteurs de la Ville de Luxembourg, temps de parcours CITA (`historical/cita/travel_time` est vide), boucles des feux.
4. **Plans de feux réels** des 4 carrefours, et un **réseau à jour** (OSM 2026 avec le tram T1) pour remplacer ou compléter LuST 2015.
5. **Mesures météo** : `weather_static.xml` ne contient que la table des stations, sans valeurs.

## 9. Commande de collecte de 7 jours (NON lancée, à confirmer)

Lancer depuis la racine du projet, dans deux fenêtres PowerShell.

```powershell
# Trafic : un passage toutes les 150 s (2 par mesure de 5 min ; dédoublonnage par capteur + horodatage),
# arrêt automatique après 168 h
python collect_cita_fixed.py --interval 150 --max-hours 168 --raw-dir data\raw\cita\snapshots_v2
# Événements : un passage toutes les 300 s (date de disparition à ±5 min près)
python collect_cita_events_v2.py --interval 300 --max-hours 168 --raw-dir data\raw\cita_events\snapshots_v2
```

- **Fichiers de sortie :**
  - `data\historical\cita\traffic\cita_traffic_sites_v2.csv` ;
  - `data\historical\cita\events\cita_events_records_v2.csv` ;
  - `data\historical\cita\events\cita_events_sightings_v2.csv`.
- **Archives XML :** dans de nouveaux sous-dossiers, sans toucher aux fichiers existants. Prévoir environ 4,2 Go pour le trafic et 0,16 Go pour les événements. Variante légère : retirer `--raw-dir`, ce qui donne des CSV d'environ 160 Mo.
- **Arrêt :** automatique après 168 h, ou Ctrl+C pendant l'attente entre deux passages.
- **Reprise :** relancer la même commande ; les clés déjà écrites ne sont pas réécrites.

## 10. Problèmes restants

- **Trafic :** seulement 3 instants de mesure. Aucune série temporelle exploitable.
- **Événements :** 46 événements anciens n'ont aucune correspondance avec un identifiant réel (pas de snapshot XML à ces dates).
- **PCH :**
  - heure de référence supposée locale (non documentée) ;
  - 1 000 journées à zéro ;
  - 61 446 lignes avec 6 à 23 heures à zéro (capteur en panne probable, signalé et non supprimé).
- **Effets de bord antérieurs, conservés :**
  - `collect_cita_fixed.py.tmp_new` ;
  - les dossiers `__pycache__/` (racine et `tests/`) ;
  - l'export PCH partiel invalide ;
  - `.git/index.lock` (non touché).
- Le registre des statuts est `file_status_register_v1.csv` : 5 fichiers INVALIDES, 2 ANCIENS, 3 anciennes sources diagnostiques. Rien n'a été supprimé.
