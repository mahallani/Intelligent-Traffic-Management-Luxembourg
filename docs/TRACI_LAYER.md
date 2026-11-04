# Couche TraCI : observation et collecte de données (LuST Luxembourg)

Projet : *Intelligent Multi-Agent Traffic Management, Luxembourg*.
Environnement de référence : SUMO 1.27.1, Python 3.11, scénario LuST `dua.actuated.sumocfg`.

Toutes les affirmations marquées **(vérifié)** ont été contrôlées sur les fichiers LuST ou par exécution réelle. La plupart sont aussi verrouillées par un test automatique (`tests/test_lust_integration.py`), qui échouera si LuST ou SUMO change.

---

## 1. Compréhension du projet

**Objectif.** Système multi-agent qui, après un incident, observe le réseau, prédit son évolution, teste plusieurs stratégies de signalisation **dans SUMO**, compare les résultats et applique automatiquement la meilleure. Nous ne pilotons aucun feu réel : SUMO est notre environnement d'expérimentation.

Boucle : `OBSERVE → PREDICT → SIMULATE → DECIDE → ACT → OBSERVE AGAIN`

| Agent | Rôle | Ce qu'il reçoit de cette couche |
|---|---|---|
| Observation | Lit l'état du réseau, détecte l'incident | `TrafficDataCollector.observe()` (observations structurées) |
| Cascade | Analyse la propagation de la congestion | arêtes congestionnées, nouvelles, propagées, topologie amont |
| Prediction | Prévoit l'évolution | séries temporelles (JSONL/CSV/DataFrame) |
| Intervention | **Expérimente** S0…S4 | état sauvegardé, `TrafficLightActuator`, mêmes KPI par run |
| Decision | **Compare** et **choisit** | `ScenarioKPIs` + `KPI_DIRECTIONS` par scénario |

**Les 6 Business Objectives.** BO1 temps d'attente · BO2 congestion · BO3 temps de trajet · BO4 arrivée des véhicules d'urgence · BO5 impact environnemental · BO6 décision automatique pendant un incident (S0 Do Nothing, S1 Bus Priority, S2 Emergency Priority, S3 Traffic Light Optimization, S4 Combined).

**Rôle de SUMO.** Simulateur microscopique : il fait circuler les ~288 000 véhicules de la journée LuST et calcule vitesses, files, émissions, etc.
**Rôle de TraCI.** Interface Python de SUMO : *lire* l'état (getters, subscriptions) et *agir* (feux, routes, véhicules), pas à pas.

**Déjà réalisé (avant cette couche).** SUMO 1.27.1 + Python 3.11 + TraCI installés ; LuST cloné via `setup_lust.ps1` ; `traci/test_lust.py` (test de connexion, conservé tel quel).

**Ajouté maintenant.** Le package `traci_layer/` (couche de collecte complète), les tests, les scripts d'exécution, ce document.

**Reste à faire (hors de cette couche).** La logique des 5 agents : détection d'incident, modèle de prédiction, stratégies S1–S4, fonction de score du Decision Agent. Voir §11.

---

## 2. Démarrage rapide (Windows PowerShell, depuis la racine du projet)

```powershell
pip install -r requirements.txt          # traci/sumolib déjà installés ; ajoute pandas, pytest, libsumo
python -m pytest                          # 34 tests (~25 s), dont 7 sur le vrai LuST
python scripts\test_lust_observation.py   # 00:00 -> 00:05, un rapport toutes les 100 s, export
```

Heure de pointe (07:00) :

```powershell
# 1) créer une fois l'état SUMO de 07:00 (~3-8 min selon la machine)
python -m traci_layer --start-at 25200 --duration 0 --save-state data\states\lust_0700.xml.gz --no-export
# 2) observer 10 minutes à partir de cet état, avec une ambulance
python -m traci_layer --load-state data\states\lust_0700.xml.gz --duration 600 --interval 300 --details `
    --emergency-from=-31952#8 --emergency-to=--31272#3 --emergency-at 25230
# 3) même chose ~2x plus vite (sans GUI)
python -m traci_layer --load-state data\states\lust_0700.xml.gz --duration 600 --libsumo
```

Options : `python -m traci_layer --help` (`--gui`, `--libsumo`, `--lane-scope tls|all|none`, `--details`, `--scenario S2`…).

Extrait réel du rapport console (07:05, état S0) :

```
Vehicles:      Count 4005 (pending insertion: 94) · Average speed 43.0 km/h · Average waiting time 6.7 s
Congestion:    Occupancy 5.5 % · Halting 1219 · Queue length 6961 m [tls_lanes_vehicle_positions]
               Longest queue 82 m · Congestion index 0.40 (light) · Congested edges 276
Environment:   CO2 3944 kg · NOx 1563 g · Fuel 1278 kg (~1715 L) · PMx 423 g   (depuis 07:00)
Buses:         77 (32 lines, 12 at a stop) · 22.1 km/h · delay (time loss) 204 s · dwell 20.0 s
Emergency:     emergency_1: 74.3 km/h on -30528#2, progress 52 %, next TLS -24852 (r)
Traffic Lights: 201 / 201 active
```

---

## 3. Architecture

```
SUMO (LuST)
  │  TraCI sockets (sumo / sumo-gui)  ou  libsumo (in-process)
  ▼
SumoConnection ──► api  (mêmes fonctions dans les deux cas)
  ▼
TrafficDataCollector
  ├─ step()      à CHAQUE pas : départs/arrivées, temps de trajet, attente cumulée,
  │              émissions intégrées, débit par arête, arrêts de bus, véhicules d'urgence
  └─ observe()   toutes les N s (60 par défaut) : arêtes, voies, feux, bus, urgences
  ▼
Observation (dict JSON) ─► Observation Agent ─► Cascade ─► Prediction ─► Intervention ─► Decision
                                                                     │
                       ScenarioKPIs (mêmes KPI pour S0..S4) ◄────────┘
```

| Module | Contenu |
|---|---|
| `config.py` | `SumoConfig` (comment lancer SUMO), `CollectorConfig` (quoi collecter), chemins robustes |
| `connection.py` | `SumoConnection` : start/close, context manager, TraCI ou libsumo, labels multiples |
| `simulation.py` | `SimulationController` : pas, événements du pas, compteurs, **save/load state** (+ correctif SUMO) |
| `readers.py` | Lecture en masse optimisée (context subscriptions / getters libsumo), voir §10 |
| `vehicle_data.py` | Véhicules : flux par pas, trajets (`TripRecord`), résumé, table détaillée |
| `edge_data.py` | Arêtes : congestion, goulots, débit, propagation |
| `lane_data.py` | Voies (contrôlées par feux par défaut) : files d'attente calculées |
| `traffic_light_data.py` | Feux : état, phase, programme, temps restant, files par carrefour |
| `bus_data.py` | Bus : ligne, arrêts, temps d'arrêt, intervalle (headway), bunching |
| `emergency_data.py` | Urgences : création (`spawn_emergency_vehicle`), suivi, retard |
| `environmental_data.py` | Émissions instantanées et cumulées |
| `metrics.py` | **Toutes** les métriques dérivées (fonctions pures, testées) |
| `kpi.py` | `ScenarioKPIs`, `KPI_DIRECTIONS`, `compare_scenarios` (entrée du Decision Agent) |
| `actuators.py` | `TrafficLightActuator` : opérations TraCI sur les feux, journalisées |
| `network.py` | `NetworkTopology` : graphe amont/aval des arêtes (lu depuis `lust.net.xml`) |
| `export.py` | JSON, JSONL, CSV, DataFrame ; `RunExporter` |
| `report.py` | Rapport console |
| `__main__.py` | CLI `python -m traci_layer` |

**Pourquoi `traci_layer/` et pas du code dans `traci/` ?** Un dossier de projet nommé `traci` entre en collision avec la bibliothèque officielle `traci` dès qu'on y ajoute un `__init__.py` ou qu'on l'importe depuis la racine. `traci/test_lust.py` est conservé sans modification. **Ne pas ajouter de `__init__.py` dans `traci/`.**

---

## 4. Format des observations

Chaque appel à `observe()` renvoie un `dict` (sérialisable JSON) ; `schema_version = "1.0"`. Exemple complet réel : `docs/sample_output/last_observation.json`.

```text
{
  "schema_version": "1.0",
  "meta":        {network, scenario, run_id, timestamp (s), clock "07:10:00", step_length, observed_since},
  "simulation":  {running_vehicles, pending_vehicles, departed_total, arrived_total,
                  teleports_total, collisions_total, emergency_braking_total, ...},
  "vehicles":    {count, average_speed_kmh, average_waiting_time_s, average_time_loss_s,
                  halting_count, halting_ratio, total_waiting_time_s, by_class{...}},
  "congestion":  {average_occupancy_pct, halting_vehicles, queue_length_m, queue_method,
                  max_queue_length_m, queued_vehicles, network_congestion_index, level,
                  congested_edges,
                  edges{... top_bottlenecks[...], congested_edge_ids[...],
                        newly_congested_edges, recovered_edges, propagated_congestion_edges},
                  tls_lanes{... spillback_lanes}},
  "travel":      {since_last_observation{completed_trips, average_travel_time_s, p95, ...},
                  cumulative{...}, vehicle_km_travelled, vehicle_hours_travelled},
  "environment": {co2_g_per_s, nox_g_per_s, fuel_g_per_s, ..., co2_total_kg, nox_total_g,
                  fuel_total_kg, fuel_total_l_indicative, pmx_total_g, co2_g_per_km, by_class_total},
  "buses":       {count, lines_active, average_speed_kmh, average_delay_s, at_stop_now,
                  average_dwell_time_s, average_headway_s, headway_cv, bunching_events_total, by_line{...}},
  "emergency":   {active, completed, average_travel_time_s, average_delay_s,
                  vehicles[...position, lon/lat, next_tls...], completed_missions[...]},
  "traffic_lights": {total_signals, active_signals, programs_in_use, signals_with_queue,
                     average_remaining_s, most_loaded_signals[...]}
}
```

Tables détaillées (une ligne par objet, colonne `time`) : `collector.latest_tables` (dernière observation) ou, avec `include_details=True`, `collector.tables` (toutes) : `vehicles`, `edges`, `lanes`, `traffic_lights`, `buses`, `emergency`. Plus `collector.trips_table()` et `collector.buses.stop_events_table()`.

Unités : vitesses en **km/h** dans les sorties (m/s en interne), temps en s, distances en m, occupation en %, émissions instantanées en g/s et cumulées en g ou kg, carburant en **masse** (le volume en litres est indicatif, densité essence 0,745 kg/L supposée).

---

## 5. Matrice Business Objectives → données → API TraCI → agents

Légende **Source** : **D** = disponible directement via l'API TraCI · **C** = cette métrique doit être calculée · **CFG** = nécessite une configuration SUMO supplémentaire.
**Fréq.** : **P** = chaque pas (1 s) · **S** = à chaque observation (60 s par défaut).
Agents : Obs = Observation, Cas = Cascade, Pre = Prediction, Int = Intervention, Dec = Decision.

### BO1 : Temps d'attente

| Donnée | Niveau | API TraCI / méthode | Unité | Source | Fréq. | Agents |
|---|---|---|---|---|---|---|
| Temps d'attente courant | véhicule | `vehicle.getWaitingTime` | s | D | P | Obs |
| Temps d'attente total d'un trajet | véhicule | Σ dt quand `getWaitingTime() > 0` | s | C (écart ≤ 1 s avec tripinfo, testé) | P | Dec, Pre |
| Attente cumulée (fenêtre de 100 s) | véhicule | `vehicle.getAccumulatedWaitingTime` | s | D (limitée par `--waiting-time-memory`) | S | Obs |
| Véhicules à l'arrêt (< 0,1 m/s) | arête/voie | `edge/lane.getLastStepHaltingNumber` | véh | D | S | Obs, Cas |
| Attente cumulée sur une arête/voie | arête/voie | `edge/lane.getWaitingTime` | s | D | S | Cas |
| Moyenne, total, évolution | réseau | agrégation + historique des observations | s | C | S | Pre, Dec |

### BO2 : Congestion

| Donnée | Niveau | API TraCI / méthode | Unité | Source | Fréq. | Agents |
|---|---|---|---|---|---|---|
| Nombre de véhicules | réseau/arête/voie | `vehicle.getIDCount`, `edge/lane.getLastStepVehicleNumber` | véh | D | S | Obs |
| Vitesse moyenne | arête/voie | `edge/lane.getLastStepMeanSpeed` (*vide → renvoie la limite*) | m/s | D | S | Obs, Cas |
| Vitesse moyenne réseau | réseau | VKT / VHT (vitesse moyenne d'espace) | km/h | C | P | Dec |
| Occupation | arête/voie | `edge/lane.getLastStepOccupancy` (**fraction 0–1**, ×100) | % | D | S | Obs, Cas |
| Longueur de file | voie | positions/vitesses des véhicules de la voie (`queue_from_vehicles`) | m, véh | C | S | Obs, Cas, Int |
| Longueur de file (alternative) | voie | `lanearea.getJamLengthMeters` (détecteurs E2) | m | CFG (LuST n'a aucun E2) | – | – |
| Indice et niveau de congestion | arête/réseau | `1 − vitesse/limite`, seuils 0,3/0,5/0,75 | 0–1 | C | S | Obs, Cas, Dec |
| Goulots d'étranglement | arête | classement par véhicules arrêtés puis indice | – | C | S | Cas |
| Propagation | arête | nouvelles arêtes congestionnées en amont d'arêtes déjà congestionnées (`NetworkTopology`) | nb | C | S | Cas, Pre |
| Débit (throughput) | arête | sorties d'arête détectées par changement de `getRoadID` | véh/h | C | P | Pre |
| Débit (détecteurs LuST) | point | `inductionloop.getLastIntervalVehicleNumber` (3 146 boucles E1, période 1 800 s) | véh | D (non collecté par défaut) | – | Pre |
| Téléportations, véhicules en attente d'insertion | réseau | `simulation.getStartingTeleportIDList`, `simulation.getPendingVehicles`, `vehicle.getDepartDelay` | nb, s | D | P/S | Obs, Dec |

### BO3 : Temps de trajet

| Donnée | Niveau | API TraCI / méthode | Unité | Source | Fréq. | Agents |
|---|---|---|---|---|---|---|
| Temps de trajet par véhicule | véhicule | arrivée − départ (`simulation.getDepartedIDList` / `getArrivedIDList`) | s | C (**identique** à tripinfo, testé) | P | Pre, Dec |
| Heure de départ | véhicule | observée, ou `vehicle.getDeparture` | s | D | P | Pre |
| Temps de trajet moyen / total / p95 | réseau | agrégation des trajets terminés | s | C | S | Dec |
| Distance parcourue | véhicule | Σ vitesse·dt | m | C (±5 % de tripinfo) | P | Pre |
| Odomètre SUMO | véhicule | `vehicle.getDistance` (*peut devenir négatif, voir §9*) | m | D | S | – |
| Route utilisée | véhicule | `vehicle.getRoute`, `getRouteID` | arêtes | D | à la demande | Pre, Int |
| Temps perdu (time loss) | véhicule | `vehicle.getTimeLoss` | s | D | P | Dec |
| Temps de parcours d'une arête | arête | `edge.getTraveltime` (longueur/vitesse moyenne) | s | D (estimation) | S | Pre |
| Comparaison avant/après | scénario | mêmes KPI calculés depuis le même état sauvegardé | – | C | fin de run | Dec |

### BO4 : Véhicules d'urgence

| Donnée | Niveau | API TraCI / méthode | Unité | Source | Fréq. | Agents |
|---|---|---|---|---|---|---|
| Existence d'un véhicule d'urgence | – | **aucun dans LuST** → types `sumo/additional/emergency_vtypes.add.xml` + `spawn_emergency_vehicle` | – | CFG | – | Int |
| Identification | véhicule | `vehicle.getVehicleClass() == "emergency"` ou type configuré | – | D | départ | Obs |
| Position (x, y) / (lon, lat) | véhicule | `vehicle.getPosition`, `simulation.convertGeo` | m / ° | D | P | Obs |
| Arête, voie, vitesse, attente | véhicule | `getRoadID`, `getLaneID`, `getSpeed`, `getWaitingTime` | – | D | P | Obs, Int |
| Route | véhicule | `vehicle.getRoute` | arêtes | D | départ | Int |
| Départ / arrivée / temps de trajet | véhicule | listes `simulation` | s | C | P | Dec |
| Temps en libre circulation | véhicule | Σ longueur / vitesse idéale sur la route | s | C | départ | Dec |
| Retard | véhicule | temps de trajet − libre circulation ; aussi `getTimeLoss` (D) | s | C | arrivée | Dec |
| Nombre d'arrêts | véhicule | transitions vitesse < 0,1 m/s | nb | C | P | Dec |
| Prochain feu, distance, état | véhicule | `vehicle.getNextTLS` | id, m, état | D | S | **Int (S2)** |
| Sirène, couloir de secours | véhicule | `device.bluelight` (paramètre du vType) | – | CFG (inclus dans notre fichier) | – | Int |

### BO5 : Impact environnemental

| Donnée | Niveau | API TraCI / méthode | Unité | Source | Fréq. | Agents |
|---|---|---|---|---|---|---|
| CO2, CO, HC, PMx, NOx | véhicule | `vehicle.getCO2Emission` … `getNOxEmission` | mg/s | D (modèle HBEFA4 par défaut) | P | Obs |
| Carburant | véhicule | `vehicle.getFuelConsumption` | **mg/s** (masse) | D | P | Obs |
| Totaux cumulés (réseau, par trajet, par classe) | réseau | Σ taux·dt | g, kg | C (écart < 2 % avec le device emissions de SUMO, testé) | P | Dec |
| Intensité | réseau | CO2 cumulé / VKT | g/km | C | S | Dec |
| Émissions par arête | arête | `edge.getCO2Emission`, `getNOxEmission`, `getFuelConsumption` | mg/s | D | S | Cas |
| Électricité | véhicule | `vehicle.getElectricityConsumption` | Wh/s | D mais **aucun véhicule électrique** dans LuST | – | – |
| Bruit | véhicule | `vehicle.getNoiseEmission` | dBA | D (non collecté) | – | – |
| Flotte réaliste (diesel, Euro 6, VE) | type | `emissionClass` par vType | – | CFG | – | – |
| Émissions dans tripinfo | trajet | `--device.emissions.probability 1` (`SumoConfig(emission_device=True)`) | mg | CFG (optionnel) | fin | validation |

### BO6 : Décision pendant un incident

| Donnée | Niveau | Méthode | Source | Agents |
|---|---|---|---|---|
| Vecteur de KPI identique pour S0…S4 | scénario | `collector.kpis()` → `ScenarioKPIs.comparable()` | C | Int, Dec |
| Sens d'optimisation de chaque KPI | – | `KPI_DIRECTIONS` (min / max) | – | Dec |
| Tableau comparatif | scénarios | `compare_scenarios({...})` → DataFrame | C | Dec |
| Point de départ commun | simulation | `simulation.saveState` / `--load-state` (+ correctif §9) | D | Int |
| Actions sur les feux | feu | `TrafficLightActuator` (§7) | D | Int |

KPI comparés : `total_waiting_time_s`, `average_waiting_time_per_vehicle_s`, `average_halting_vehicles`, `network_mean_speed_kmh`, `average_congestion_index`, `average_congested_edges`, `average_total_queue_length_m` (somme des files des voies à feux, moyennée dans le temps), `max_lane_queue_length_m` (plus longue file d'une voie), `teleports`, `pending_vehicles_end`, `completed_trips`, `average_travel_time_s`, `total_time_loss_in_window_s`, `vehicle_hours_travelled`, `emergency_average_travel_time_s`, `emergency_average_delay_s`, `co2_kg`, `nox_g`, `fuel_kg`, `pmx_g`, `bus_average_delay_s`, `bus_bunching_events`, `bus_headway_cv`.

### Bus / transport public (Bus Headway Monitoring, Bus Priority)

| Donnée | API TraCI / méthode | Unité | Source | Fréq. | Agents |
|---|---|---|---|---|---|
| bus_id | id du véhicule de type `bus` | – | D | départ | Obs |
| line_id | **dérivé de l'id** (`AVL---_12_5` → `AVL---_12`) ; `vehicle.getLine()` renvoie `""` | – | C | départ | Obs |
| Position, arête, voie, vitesse, attente | getters `vehicle` | – | D | P/S | Obs, Int |
| À l'arrêt / quel arrêt | `vehicle.getStopState` (bits 1 et 16), `vehicle.getStops` | – | D | P | Obs |
| Temps d'arrêt (dwell) | départ − arrivée à l'arrêt | s | C (égal à SUMO stop-output, testé) | P | Pre |
| Retard | **pas d'horaire dans LuST** → `getTimeLoss` comme indicateur | s | C | S | Int, Dec |
| Retard vs horaire | `vehicle.getStopDelay` / `getStopArrivalDelay` | s | CFG (attributs `until` / `arrival`) | – | – |
| Headway observé | écart entre deux bus de la même ligne **et de la même séquence d'arrêts** au même arrêt | s | C | P | Obs, Pre |
| Headway planifié | médiane des écarts de départs prévus par séquence d'arrêts (76 séquences, toutes à 1 800 s) | s | C | init | Obs |
| Bunching | headway observé < 0,5 × planifié | bool | C | P | Obs, Int |
| Voyageurs aux arrêts | `busstop.getPersonCount` | pers. | D mais **0** (LuST ne simule pas les piétons) | – | – |

### Feux de circulation

| Donnée | API TraCI | Unité | Source | Fréq. | Agents |
|---|---|---|---|---|---|
| traffic_light_id | `trafficlight.getIDList` | – | D | init | tous |
| État courant | `getRedYellowGreenState` | chaîne rRgGyYoO | D | S | Obs, Int |
| Phase courante | `getPhase` | index | D | S | Int |
| Programme | `getProgram`, `getAllProgramLogics` | – | D | S / init | Int |
| Durée de phase | `getPhaseDuration` | s | D | S | Int |
| Temps restant | `getNextSwitch − getTime` | s | C | S | Int |
| Temps écoulé dans la phase | `getSpentDuration` | s | D | S | Int |
| Voies / liens contrôlés | `getControlledLanes`, `getControlledLinks` | – | D | init | Int |
| File par carrefour | Σ files des voies contrôlées | m, véh | C | S | Cas, Int |
| Durée de cycle | Σ durées des phases | s | C | init | Int |

---

## 6. Vérification technique de l'API (SUMO 1.27.1)

- Les ~160 fonctions TraCI utilisées ou citées ont été vérifiées par introspection de `traci` 1.27.1 : **aucune n'est manquante**.
- Les unités ont été vérifiées dans les docstrings TraCI **et** par mesure quand c'était ambigu :
  - **Occupation** : la docstring dit « % », mais SUMO 1.27.1 renvoie une **fraction** (vérifié : valeur = Σ longueurs des véhicules / longueur de voie). Nous la convertissons en %.
  - **Émissions et carburant** : mg/s pour le dernier pas.
  - **getNextSwitch** : temps de simulation **absolu**.
- Exactitude validée contre la vérité terrain de SUMO (`tests/test_synthetic.py`, réseau 3×3 à feux, 113 trajets) :

| Notre valeur | Référence SUMO | Écart |
|---|---|---|
| temps de trajet | tripinfo `duration` | 0 (exact) |
| attente totale | tripinfo `waitingTime` | ≤ 1 s |
| temps perdu | tripinfo `timeLoss` | ≤ 3 s |
| distance | tripinfo `routeLength` | ≤ 5 % |
| CO2, NOx, carburant | device emissions `*_abs` | < 2 % |
| arrivée/départ aux arrêts de bus, headway | `--stop-output` | ≤ 1 s |
| retard d'un véhicule d'urgence | tripinfo `timeLoss` | ≤ 5 s |
| tous les KPI | backend TraCI vs libsumo | identiques (aussi sur LuST) |

---

## 7. Analyse réelle de LuST (vérifiée)

Les fichiers joints au projet sont identiques (aux fins de ligne Windows près) à ceux du dépôt officiel `lcodeca/LuSTScenario`.

**Configuration `dua.actuated.sumocfg`.** Routes : `buslines.rou.xml`, `DUARoutes/local.{0,1,2}.rou.xml`, `transit.rou.xml`. Additionnels : `vtypes.add.xml`, `busstops.add.xml`, `e1detectors.add.xml`, `lust.poly.xml`. Pas de 1 s, `time-to-teleport` 600 s, rerouting dynamique pour 70 % des véhicules (période 300 s). Sorties : summary et tripinfo.

**Véhicules (288 250 sur 24 h).**

| Fichier | Véhicules | Types |
|---|---|---|
| `DUARoutes/local.0/1/2.rou.xml` | 72 000 + 72 000 + 71 526 | passenger1…5 (trafic local) |
| `transit.rou.xml` | 70 484 | passenger1…5 (trafic de transit) |
| `buslines.rou.xml` | 2 240 | bus |

Types (`vtypes.add.xml`) : distribution `private` de 6 types `passenger` (passenger1 40 %, 2a 20 %, 2b 20 %, 3 10 %, 4 5 %, 5 5 %) + `bus` (12 m, rerouting désactivé). **Aucun `emissionClass`** : SUMO 1.27.1 applique `HBEFA4/PC_petrol_Euro-4` (voitures) et `HBEFA4/UBus_Std_gt15-18t_Euro-VI_A-C` (bus).

**Bus.** 2 240 trajets, 38 lignes, 561 arrêts (`busStop`, chacun avec la liste des lignes). La ligne n'est encodée que dans l'id du véhicule. Les arrêts n'ont que `duration="20"` : **pas d'horaire**. Headway planifié : **1 800 s pour les 38 lignes** (départs toutes les 30 min dans chaque sens). **Aucune voie réservée aux bus** (aucune voie n'a d'attribut `allow`/`disallow`).

**Feux.** 203 jonctions `traffic_light` pilotées par **201 programmes**, tous `type="actuated"`, programID `"0"`, **sans `minDur`/`maxDur`** : SUMO fixe donc minDur = maxDur = duration, ce qui fait que les feux se comportent en **temps fixe** (confirmé par `getAllProgramLogics`). Phases : 116 programmes à 6 phases, 59 à 8, 20 à 4, quelques cas particuliers. `tll.static.xml` (non chargé par `dua.actuated`) contient des plans fixes alternatifs (programID `"1"`).
→ Il y a donc une vraie marge pour S3 (vrai actionnement, re-timing) et pour S1/S2 (préemption).

**Véhicules d'urgence.** **Aucun** dans LuST (aucune classe `emergency`, aucun type dédié). Représentation proposée et testée : `sumo/additional/emergency_vtypes.add.xml` (projet, LuST non modifié) :
- `emergency_bluelight` : vClass `emergency`, `device.bluelight` (couloir de secours), speedFactor 1,5 ;
- `emergency_plain` : vClass `emergency` sans device, pour une référence pessimiste.

Injection : `spawn_emergency_vehicle(api, EmergencyVehicleSpec(id, from_edge, to_edge, depart, type_id))` (route la plus rapide via `simulation.findRoute`). Mission de démonstration utilisée : `-31952#8 → --31272#3` (36 arêtes, ~4,9 km jonctions comprises) ; à 07:00 en S0 elle prend **441 s** contre 212 s en libre circulation (retard 229 s, cohérent avec le `timeLoss` de SUMO : 227 s), avec 9 arrêts.

**Réseau.** 5 779 arêtes (+13 248 internes), 8 622 voies, dont 1 512 contrôlées par des feux. Projection UTM 32 ; `simulation.convertGeo` donne des lon/lat (6,03–6,22° E, 49,55–49,65° N). Les rues ne sont pas nommées (`getStreetName` vide).

**Détecteurs.** 3 146 boucles E1 (période 1 800 s, fichiers `e1_*_output.xml`) ; **0 détecteur E2**.

**Polygones.** 13 567 bâtiments, 449 aménités, 180 parkings (`lust.poly.xml`, décoratif).

**Charge mesurée.** 07:00 : 3 835 véhicules en circulation ; 07:05 : 4 005. SUMO seul : ~34 ms par pas à 07:00 ; 00:00 → 08:30 en ~8 min sur la machine de test.

---

## 8. Disponible maintenant vs à configurer plus tard

**Disponible maintenant, sans rien changer à LuST :** tous les getters véhicules/arêtes/voies/feux/arrêts de bus ; émissions HBEFA4 ; temps de trajet, attente, temps perdu, distance, files, congestion, propagation, débit, bus (dwell, headway, bunching, retard approché), feux (état, phase, temps restant, files) ; véhicules d'urgence via notre fichier additionnel ; sauvegarde/rechargement d'état ; actionneurs de feux ; export JSON/CSV/DataFrame.

**Nécessite une configuration SUMO supplémentaire (si besoin) :**

| Besoin | Configuration |
|---|---|
| Retard bus vs horaire | ajouter `until`/`arrival` aux `<stop>` des bus (une copie projet de buslines) |
| Files « officielles » SUMO | détecteurs E2 (`laneAreaDetector`) aux approches des carrefours |
| Flotte réaliste (diesel, Euro 6, VE) | `emissionClass` par vType (fichier additionnel projet) |
| Voies bus pour S1 | `lane.setAllowed` via TraCI ou un réseau modifié |
| Vrais feux actionnés pour S3 | `trafficlight.setProgramLogic` avec `minDur`/`maxDur` + détecteurs, ou paramètres d'actionnement |
| Émissions par trajet dans tripinfo | `SumoConfig(emission_device=True)` |
| Voyageurs aux arrêts | demande piétonne (absente de LuST) |

---

## 9. Pièges découverts (tous vérifiés)

1. **Rechargement d'état impossible tel quel avec SUMO 1.27.1.** `saveState` écrit `state=""` pour chaque feu actionné, puis `--load-state` échoue (« Attribute 'state' in definition of tlLogic … is empty »). `SimulationController.save_state()` corrige automatiquement le fichier (`repair_state_file`) ; pour un état sauvé autrement, appeler `repair_state_file(chemin)`.
2. **Charger `tll.static.xml` active le programme `"1"` sur les 201 feux**, même après chargement d'un état. Le scénario S0 ne doit jamais charger ce fichier.
3. **`getLastStepOccupancy` renvoie une fraction**, pas un %.
4. **`getAccumulatedWaitingTime` ne couvre que les 100 dernières secondes** (`--waiting-time-memory`) : l'attente totale est intégrée par nous.
5. **`getDistance` peut devenir négatif** pour certains véhicules LuST (route modifiée par le rerouting) : la distance des trajets est intégrée (vitesse·dt).
6. **Une arête vide renvoie la vitesse limite comme vitesse moyenne** : les arêtes vides sont exclues des statistiques de congestion.
7. **Feux « actuated » en réalité fixes** (pas de `minDur`/`maxDur`).
8. **`vehicle.getLine()` est vide pour les bus LuST** ; **`getStopDelay` vaut −1** (pas d'horaire).
9. **Véhicules déjà présents au chargement d'un état** (85 % des trajets terminés dans une fenêtre de 10 min à 07:00) : leur temps de trajet SUMO est exact (`getDeparture`), mais leur histoire avant le début de l'observation est la même dans tous les scénarios et diluerait les écarts. Les KPI sont donc définis sur la fenêtre : `total_time_loss_in_window_s` = temps perdu accumulé pendant la fenêtre (tous véhicules) ; `average_travel_time_s` et `average_time_loss_s` = trajets observés depuis leur départ uniquement (`observed_from_departure`). Les moyennes sur tous les trajets terminés restent disponibles (`average_travel_time_all_completed_s`).
10. **Variantes de lignes de bus** : certaines lignes LuST ont deux variantes qui partent ensemble du même arrêt, et deux lignes différentes ont exactement la même séquence d'arrêts. Le headway et le bunching sont donc calculés par (ligne, séquence d'arrêts) ; sinon on obtient de fausses alertes de bunching (constaté lors de la revue).
11. **`average_travel_time_s` peut favoriser à tort une stratégie** qui empêche les longs trajets de se terminer dans la fenêtre. Le Decision Agent doit le lire avec `completed_trips`, `vehicle_hours_travelled` et `total_time_loss_in_window_s`, qui sont plus robustes.

---

## 10. Performance

Mesures à 07:00 (~3 900 véhicules), SUMO seul ≈ 34 ms par pas :

| Approche | Coût |
|---|---|
| Subscription TraCI par véhicule, 16 variables | +182 ms par pas |
| Context subscription TraCI, 11 variables | +100 ms par pas |
| Context subscription TraCI, 6 variables | +69 ms par pas |
| Getters libsumo, 11 variables | +29 ms par pas |
| Subscription permanente des 5 779 arêtes | +136 ms par pas (et 11 s d'initialisation) |
| Lecture ponctuelle de toutes les arêtes (context subscription « one-shot ») | 0,45 s par observation |

D'où le choix : 10 variables par pas seulement (ce qui doit être intégré), tout le reste lu en masse au moment de l'observation.
Résultat sur 10 min de pointe avec collecte complète : **TraCI 102 s, libsumo 51 s** (KPI identiques).

Recommandations :
- runs S0…S4 automatiques : `SumoConfig(use_libsumo=True)` (`pip install libsumo==1.27.1`, roue Windows cp311 disponible) ;
- démonstrations : TraCI + `gui=True` ;
- plus rapide encore : `CollectorConfig(light_step_vars=True)` (CO/HC/PMx non intégrés), `lane_scope=None`, `snapshot_interval` plus grand ;
- plusieurs scénarios en parallèle : un **processus** par scénario (libsumo = une simulation par processus), `output_dir` distinct.

---

## 11. Intégration avec les 5 agents (recommandations)

```python
from traci_layer import (SumoConfig, SumoConnection, CollectorConfig, TrafficDataCollector,
                         TrafficLightActuator, EmergencyVehicleSpec, spawn_emergency_vehicle,
                         RunExporter, compare_scenarios, EMERGENCY_VTYPES_FILE)

# --- Observation Agent : surveillance continue
with SumoConnection(SumoConfig(additional_files=[EMERGENCY_VTYPES_FILE])) as api:
    col = TrafficDataCollector(api, CollectorConfig(snapshot_interval=60))
    for obs in col.run(duration=3600):
        if detect_incident(obs):                                  # logique de l'agent
            col.sim.save_state("data/states/incident.xml.gz")     # point de départ commun
            break

# --- Intervention Agent : un run par stratégie depuis le même état
def run(strategy, name):
    with SumoConnection(SumoConfig(load_state="data/states/incident.xml.gz", use_libsumo=True,
                                   additional_files=[EMERGENCY_VTYPES_FILE], label=name)) as api:
        spawn_emergency_vehicle(api, EmergencyVehicleSpec("amb_1", "-31952#8", "--31272#3"))
        act = TrafficLightActuator(api)
        col = TrafficDataCollector(api, scenario=name)
        for _ in col.run(duration=900, on_step=lambda c: strategy.step(c, act)):
            pass
        return col.kpis()

# --- Decision Agent
results = {name: run(s, name) for name, s in strategies.items()}   # S0..S4
table = compare_scenarios(results)    # DataFrame + colonne "direction" (min/max)
```

Gabarit exécutable : `scripts/example_compare_scenarios.py`. Démonstration réelle, à partir de l'état de 07:00 sur 15 min, avec la même ambulance (`docs/sample_output/kpi_comparison.csv`) :

| KPI | S0 (LuST tel quel) | Plans fixes `tll.static.xml` |
|---|---|---|
| Attente totale (s) | 731 683 | 790 823 |
| Trajets terminés | 5 090 | 4 904 |
| Temps perdu pendant la fenêtre (s) | 1 226 186 | 1 315 067 |
| Ambulance : temps de trajet (s) | 441 | 496 |
| CO2 (kg) | 11 953 | 12 007 |

*(Le second scénario n'est pas notre S3 : c'est un plan alternatif existant, utilisé uniquement pour tester le mécanisme de comparaison.)*

Recommandations par agent :
- **Observation** : possède la connexion et le collecteur ; publie `observations.jsonl` (un objet JSON par ligne, lisible en continu). Déclencheurs d'incident possibles : saut de `congestion.halting_vehicles`, `newly_congested_edges`, `teleports_total`, `spillback_lanes`.
- **Cascade** : `congestion.edges.congested_edge_ids`, `newly_congested_edges`, `propagated_congestion_edges`, `collector.latest_tables["edges"|"lanes"]`, `collector.topology.upstream_within(edge, depth)`.
- **Prediction** : `observations_to_dataframe()` pour les séries réseau ; `edges.csv` / `lanes.csv` (avec `--details`) pour des variables par arête (occupation, vitesse, arrêts, débit). Fenêtres glissantes de 1 à 5 observations.
- **Intervention** : toujours repartir de l'état sauvegardé ; même graine, même mission d'urgence, même durée ; agir via `TrafficLightActuator` (journal `actuator.log` pour la traçabilité) ; `on_step` pour les stratégies réactives (ex. S2 : `getNextTLS` de l'ambulance, puis `extend_green` ou `set_phase`).
- **Decision** : s'appuyer d'abord sur les KPI de fenêtre (`total_time_loss_in_window_s`, `vehicle_hours_travelled`, `total_waiting_time_s`, `completed_trips`) ; normaliser chaque KPI par rapport à S0 (gain relatif), pondérer par BO, imposer des contraintes (ex. ne jamais dégrader le temps de l'ambulance, pas de hausse des téléportations), puis choisir. La couche fournit les données et le sens d'optimisation ; la fonction de score appartient au Decision Agent.

---

## 12. Tests

```powershell
python -m pytest            # tout (≈ 25 s)
python -m pytest tests\test_metrics.py          # unitaires, sans SUMO
python -m pytest tests\test_synthetic.py        # validation contre tripinfo / stop-output / libsumo
python -m pytest tests\test_lust_integration.py # vrai LuST (ignoré si LuSTScenario absent)
```

| Fichier | Vérifie |
|---|---|
| `test_metrics.py` | métriques dérivées (congestion, files, headway, bunching, conversions) |
| `test_synthetic.py` | exactitude vs SUMO (trajets, attente, distance, émissions, arrêts de bus, retard d'urgence), actionneurs de feux (dont « extend_green ne raccourcit jamais »), sauvegarde/rechargement d'état, bus déjà en route au démarrage, fenêtres sans double comptage, export, équivalence TraCI/libsumo, preset léger |
| `test_lust_integration.py` | faits LuST de ce document (dont les 76 séquences de bus), collecte réelle, correctif de l'état sur les 201 feux |

---

## Fichiers ajoutés au projet

```
traci_layer/                     package (20 modules, voir §3)
tests/                           conftest + 3 fichiers de tests (34 tests)
scripts/test_lust_observation.py test réel LuST avec rapport + export
scripts/example_compare_scenarios.py   gabarit S0..S4 -> Decision
sumo/additional/emergency_vtypes.add.xml   types de véhicules d'urgence
docs/TRACI_LAYER.md              ce document
docs/sample_output/              exemples réels (observation, KPI, comparaison)
requirements.txt, pytest.ini
traci/test_lust.py               inchangé
```

À ajouter au `.gitignore` : `data/observations/` et `data/states/` (sorties générées, régénérables).
