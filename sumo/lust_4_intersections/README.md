# Scénario réduit LuST : Kirchberg, 4 carrefours à feux

Sous-réseau du scénario **LuST** (Luxembourg SUMO Traffic) limité à **4 carrefours à feux consécutifs de l'avenue J.F. Kennedy à Kirchberg** (Luxembourg-Ville) et aux rues qui les entourent. Le trafic est le **trafic réel de LuST entre 07:00 et 08:00**, découpé à la zone.

- 4 feux : `-28692`, `-23354`, `-20484`, `-29958` (programmes LuST d'origine, vérifiés identiques)
- 73 arêtes (12,6 km de voies), 33 nœuds, 4 points d'entrée/sortie
- 778 véhicules (dont 19 bus de 5 lignes) entrent dans la zone entre 07:00 et 08:00 ; 11 arrêts de bus
- une heure simulée en **< 1 s** avec `sumo` (environ 10 s avec la collecte TraCI complète)

Rapport détaillé (identification de la zone, choix des 4 feux, résultats des tests) : **[RAPPORT.md](RAPPORT.md)**. Carte : `docs/kirchberg_4tls_map.png`.

LuST n'est **jamais modifié**. Ce dossier est autonome pour simuler (il n'a pas besoin de `LuSTScenario/`) ; seul le script de reconstruction utilise LuST.

---

## Prérequis

- SUMO 1.27.1 (installateur Windows, `SUMO_HOME` défini, `...\Sumo\bin` dans le `PATH`)
- Python 3.11 avec `traci`, `sumolib` (déjà installés) ; `pandas` et `pytest` pour les tests
- Pour les scripts Python : la couche `traci_layer/` du projet (racine du dépôt)

Si `sumo-gui` n'est pas dans le `PATH`, remplacer `sumo-gui` par `& "C:\Program Files (x86)\Eclipse\Sumo\bin\sumo-gui.exe"` dans les commandes ci-dessous.

---

## Commandes PowerShell

Depuis la racine du projet (`C:\Users\ASUS\Intelligent-Traffic-Management-Luxembourg`) :

```powershell
# 1) Ouvrir le scénario dans SUMO-GUI (07:00 -> 08:00, trafic réel LuST)
sumo-gui -c sumo\lust_4_intersections\kirchberg_4tls.sumocfg

# 2) Même chose avec une demande x5 (congestion)
sumo-gui -c sumo\lust_4_intersections\kirchberg_4tls.sumocfg --scale 5

# 3) Simulation sans interface (statistiques de fin de run)
sumo -c sumo\lust_4_intersections\kirchberg_4tls.sumocfg --duration-log.statistics true

# 4) Lancer avec TraCI + rapports de la couche d'observation (toutes les 15 min)
python sumo\lust_4_intersections\scripts\run_scenario.py
python sumo\lust_4_intersections\scripts\run_scenario.py --gui
python sumo\lust_4_intersections\scripts\run_scenario.py --scale 5 --ambulance-at 26400 --export

# 5) Tests rapides (pytest) puis validation complète (8 tests obligatoires + S0..S3), ~2 min
python -m pytest tests\test_kirchberg_scenario.py -v
python sumo\lust_4_intersections\scripts\validate_scenario.py

# 6) (optionnel) reconstruire le réseau et les routes depuis LuST
python sumo\lust_4_intersections\scripts\build_scenario.py
python sumo\lust_4_intersections\scripts\build_scenario.py --run-lust --state data\states\lust_0700.xml.gz   # ~7 min
```

La validation écrit `output\validation_report.json` et `.md`. La version de référence exécutée est dans `docs\`.

---

## Contenu du dossier

```
lust_4_intersections/
├── kirchberg_4tls.sumocfg            configuration (chemins relatifs, 07:00-08:00)
├── kirchberg.gui.xml                 vue SUMO-GUI cadrée sur la zone
├── net/
│   ├── kirchberg_4tls.net.xml        sous-réseau extrait de lust.net.xml (netconvert)
│   ├── keep_edges.txt                les 73 arêtes conservées
│   └── tls_reference_from_lust.json  programmes d'origine des 4 feux (contrôle)
├── routes/kirchberg_0700_0800.rou.xml  778 trajets LuST réels découpés (07:00-08:00)
├── additional/
│   ├── vtypes.add.xml                types de véhicules LuST (copie, licence MIT)
│   ├── busstops_kirchberg.add.xml    les 11 arrêts LuST de la zone
│   └── emergency_vtypes.add.xml      ambulances (projet ; LuST n'en a pas)
├── scripts/
│   ├── build_scenario.py             reconstruction complète depuis LuST
│   ├── run_scenario.py               lancement TraCI + rapports + export
│   ├── validate_scenario.py          tests obligatoires + faisabilité S0..S3
│   └── plot_network.py               carte annotée
├── build_cache/vehroutes_0700_0830.xml.gz   trajets LuST complets enregistrés (pour reconstruire sans relancer LuST)
├── docs/                             carte, capture SUMO-GUI, rapport de validation de référence
└── output/                           sorties des runs (ignoré par Git sauf .gitignore)
```

**Dépendances minimales pour simuler :** `net/`, `routes/`, `additional/`, `output/` (le dossier doit exister) et le `.sumocfg`.
**Pour reconstruire :** `LuSTScenario/scenario/lust.net.xml`, `busstops.add.xml`, `vtypes.add.xml`, plus le cache ou un état LuST de 07:00 (`python -m traci_layer --start-at 25200 --duration 0 --save-state data\states\lust_0700.xml.gz --no-export`).

---

## Régler la demande (congestion)

La demande de base (×1) est le trafic LuST réel : fluide, environ 19 s d'attente par véhicule. Pour étudier la congestion, utiliser l'option SUMO `--scale` (ou `run_scenario.py --scale`). Mesures sur 07:00–08:00 :

| Échelle | Véhicules | Attente moy. (s) | Temps perdu moy. (s) | Véh. arrêtés max | Bloqués à l'entrée (max) | Téléport. |
|---|---|---|---|---|---|---|
| ×1 (réel) | 778 | 19,0 | 29,9 | 14 | 1 | 0 |
| ×2 | 1 555 | 21,0 | 34,7 | 32 | 9 | 0 |
| ×3 | 2 332 | 23,2 | 39,5 | 49 | 21 | 0 |
| ×4 | 3 105 | 28,7 | 48,8 | 76 | 33 | 0 |
| **×5** | 3 875 | 38,0 | 63,6 | 109 | 68 | 0 |
| **×6** | 4 567 | 53,8 | 87,4 | 154 | 127 | 0 |
| ×8 | 5 321 / 6 224 | 99,6 | 152,8 | 324 | 653 | 2 |

Recommandation :
- **×1** pour la référence réaliste ;
- **×5 à ×6** pour étudier congestion et stratégies ;
- **×8** sature le réseau (des véhicules ne peuvent plus entrer).

La graine SUMO est fixe : un même réglage donne exactement le même résultat.

---

## Utilisation par les agents

| Rôle | Ce que fournit le scénario |
|---|---|
| Agent de collecte | `traci_layer.TrafficDataCollector` fonctionne tel quel (voir `run_scenario.py`) |
| Agent incidents / anomalies | incident simulable : fermeture de voie (`lane.setDisallowed`), ralentissement (`lane.setMaxSpeed`), exemple dans `validate_scenario.py` |
| Agent prédiction / propagation | 4 feux sur 1,3 km d'avenue, rues parallèles : files et propagation mesurables par voie |
| Agent RL | actions : phase et durée des 4 feux (`setPhase`, `setPhaseDuration`, `setProgramLogic`) ; épisode d'1 h en < 1 s avec SUMO seul |
| SUMO + TraCI | environnement de simulation et d'évaluation (pas un agent) |

Stratégies testées (preuve de faisabilité, pas d'optimisation) dans `validate_scenario.py` :
- **S0** : programmes LuST d'origine ;
- **S1** : plan de feux modifié via `setProgramLogic` ;
- **S2** : incident sur l'avenue + réorientation par `rerouteTraveltime` (des itinéraires alternatifs existent) ;
- **S3** : préemption pour une ambulance via `getNextTLS` + `setPhase`.

Points d'attention pour la suite :
- La préemption de démonstration change de phase **sans phase jaune**, et décale **durablement** le cycle du feu concerné (vérifié). Une vraie stratégie S3 doit insérer le jaune et resynchroniser le cycle, sinon une partie de l'effet mesuré vient du décalage, pas de la priorité.
- La zone est vide à 07:00 et se remplit en environ 2 min (trajet moyen de 100 s) : ignorer les 300 premières secondes dans les KPI.
- Les feux LuST sont déclarés « actuated » sans `minDur`/`maxDur` : ils fonctionnent en temps fixe (même comportement que dans LuST complet).
