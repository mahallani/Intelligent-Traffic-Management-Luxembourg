# APPLICATION_GUIDE – application de pilotage de la simulation

L'application pilote SUMO et affiche les résultats. Elle comprend deux parties :

| Partie | Technologie | Dossier |
|---|---|---|
| Backend | Python, FastAPI, TraCI/libsumo via `agents/orchestrator.py` | `app/backend/` |
| Frontend | Next.js 15 (React 19), exporté en pages statiques et servi par le backend | `app/frontend/` (sources), `app/frontend/out/` (version compilée) |

**Toutes les valeurs affichées sont simulées** (SUMO, réseau et demande LuST de 2015 environ). Aucune mesure réelle n'existe dans la zone des 4 feux. L'en-tête de chaque page le rappelle, et la page « Données » sépare les sources réelles des sources simulées.

## Démarrer (Windows)

```powershell
cd C:\Users\ASUS\Intelligent-Traffic-Management-Luxembourg
python -m pip install -r requirements.txt          # une fois : fastapi, uvicorn, httpx, pytest, numpy, traci, sumolib
powershell -ExecutionPolicy Bypass -File scripts\windows\run_app_windows.ps1
```

Le navigateur s'ouvre sur `http://127.0.0.1:8000`. Pour arrêter, faire Ctrl+C dans la fenêtre PowerShell.

- Le frontend compilé (`app/frontend/out`) est livré : **Node.js n'est pas nécessaire** pour utiliser l'application.
- Pour modifier le frontend : `cd app\frontend`, `npm install`, puis `npm run dev` (port 3000, avec le backend lancé sur le port 8000) ou `npm run build`.

## Pages

| Page | Ce qu'elle permet |
|---|---|
| Pilotage | Choisir le scénario, la stratégie (S0, S1, S2, S2F, S2b, S3), la demande, la graine, la vitesse d'affichage et la règle de détection ; transmettre ou non les prévisions à la décision ; ouvrir SUMO-GUI en parallèle. **Lancer, Pause, Reprendre, Arrêter.** Carte du réseau avec véhicules (plein : en mouvement ; anneau : arrêté) et 4 feux colorés selon leur état ; fiche de chaque carrefour (états de tous les mouvements, phase, file) ; indicateurs en direct ; courbes ; onglets Décisions des agents, Détections, Prévisions +5/+10/+15 min. |
| Résultats et comparaison | Comparer deux stratégies : moyenne ± écart-type sur les graines d'évaluation, écart en %, verdict « meilleur », « moins bon » ou « non significatif ». Liste de tous les runs (évaluation, application, démo), téléchargement des fichiers de chaque run, export CSV de tous les indicateurs. |
| Données | Sources réelles (CITA, PCH, GTFS) et simulées (LuST et runs), avec ce que chacune permet ; verdicts de préparation des données ; échec de la calibration. |
| Rapports | Lecture des rapports Markdown du projet. |

## API (backend)

| Méthode et chemin | Rôle |
|---|---|
| `GET /api/health` | État du serveur et de la simulation |
| `GET /api/config` | Scénarios, stratégies (avec disponibilité : S3 exige la Q-table, S2F le modèle de cascade), règles de détection |
| `GET /api/network` | Géométrie du réseau réduit (voies, 4 feux) |
| `POST /api/sim/start` | Paramètres : `scenario`, `strategy`, `scale` (0,1–10), `seed`, `delay_ms`, `gui`, `use_forecast`, `detection_mode`. Renvoie **409** si une simulation est déjà active, **400 ou 422** pour un paramètre invalide. |
| `POST /api/sim/pause`, `/resume`, `/stop` | Contrôle du processus. 409 si l'état ne le permet pas. L'arrêt ferme SUMO proprement et écrit les sorties partielles (`stopped_early = true`). |
| `GET /api/sim/state` | État en direct : statut, heure simulée, feux, véhicules, indicateurs, séries, décisions, alertes, prévisions, erreur éventuelle |
| `GET /api/runs` | Runs enregistrés avec leurs indicateurs |
| `GET /api/runs/{id}/files/{nom}` | `kpis.json`, `queue_timeseries.csv`, `decisions.csv`, `alerts.csv` ou `predictions.csv` |
| `GET /api/compare?a=&b=&scale=` | Comparaison de deux stratégies (runs d'évaluation) |
| `GET /api/export/kpi_runs.csv` | Export CSV de tous les runs |
| `GET /api/reports`, `GET /api/reports/{nom}` | Rapports |
| `GET /api/data-sources` | Sources réelles ou simulées et verdicts |

## Règles de fonctionnement

- **Une seule simulation à la fois**, dans un thread du backend. Une deuxième demande reçoit 409 : pas de SUMO ni de port TraCI concurrents.
- Sans SUMO-GUI, la simulation tourne dans le processus via libsumo s'il est installé, sinon via TraCI. Avec SUMO-GUI, TraCI passe par un port propre au run.
- **Pause** : la boucle de simulation s'arrête entre deux pas.
- **Arrêt** : la boucle sort, SUMO est fermé, et `tripinfo.xml`, `kpis.json` et les CSV sont écrits.
- **Fermeture du backend** (Ctrl+C) : SUMO est arrêté avec le processus. Le run en cours n'a alors pas de `kpis.json`, et les scripts le renomment `_INCOMPLETE_n` au prochain lancement.
- **Sorties de l'application** : un nouveau dossier par run, `sumo/lust_4_intersections/output/app_runs/<date>_<stratégie>_x<demande>_seed<graine>/`, jamais écrasé.
- **Indicateurs en direct** : ce sont des approximations, calculées toutes les 5 s simulées. Les valeurs finales exactes viennent de `tripinfo` (SUMO) et sont visibles dans la page Résultats.

## Tests

`tests/test_app_api.py` couvre l'API, le lancement et l'arrêt de SUMO, la pause et la reprise, le refus d'une deuxième simulation, les erreurs, l'export et la lecture des résultats.

```powershell
python -m pytest tests\test_app_api.py -v
```

**État au 12/10/2026 :**
- **Linux** (machine Linux de ton PC) : 5/5 tests de l'API réussis, plus une session HTTP réelle (démarrer, refus 409, pause, reprise, arrêt en cours de run, fichiers, export, comparaison). Journaux dans `data/reports/test_logs/`.
- **Windows** : pas encore exécuté.
- **Navigateur** : rendu pas encore observé.

Détails dans `FINAL_DEMO_REPORT.md`.

## Bilan de sécurité affiché

À la fin d'un run, la page Pilotage affiche le bilan du moniteur de sécurité : nombre de transitions vérifiées et violations (jaune obligatoire, vert min. 5 s et max. 90 s, états du programme). Il apparaît aussi dans `kpis.json → safety`.

## Dépannage : « Could not connect to TraCI server … (TraCI server already finished) » (15/10/2026)

**Ce que signifie ce message.** SUMO s'est arrêté au démarrage. Avant la correction du 15/10 :
- `traci.start` le relançait jusqu'à 60 fois sur un nouveau port, pendant environ 80 s ;
- le message d'erreur de SUMO n'était conservé nulle part ;
- l'interface n'affichait que `FatalTraCIError: Could not connect`, avec un dossier de run vide.

**Depuis la correction** (`traci_layer/launcher.py`) :
- SUMO n'est lancé qu'**une fois**, et une deuxième fois seulement en cas de conflit de port ;
- sa sortie complète et la ligne de commande exacte sont écrites dans `<dossier du run>/sumo_process.log` ;
- l'erreur est affichée dans l'interface et enregistrée dans `<dossier du run>/app_error.json`, avec le code de sortie décodé (DLL introuvable, DLL de mauvaise version, plantage…) ;
- aucun processus SUMO ne reste ouvert ;
- `Ctrl+C` sur le backend arrête proprement la simulation en cours : `kpis.json` est écrit avec `stopped_early = true`.

**Diagnostic** : `python scripts\windows\diagnose_sumo_launch.py`. Il lance SUMO exactement comme l'application, sans puis avec SUMO-GUI. Le rapport est écrit dans `data\reports\windows_validation\sumo_launch_diag_<date>.log`.

L'adresse `http://127.0.0.1:8000/api/diagnostics` indique :
- le binaire SUMO utilisé et sa version ;
- si libsumo fonctionne ;
- le moteur choisi (libsumo ou TraCI) et pourquoi.

**libsumo sous Windows** : sur ce PC, `import libsumo` échoue (`DLL load failed … procédure spécifiée introuvable`, journal du 13/10). L'application le détecte une fois, dans un processus séparé, et utilise alors TraCI. Pour forcer TraCI : `$env:ITM_SUMO_BACKEND = "traci"`.

**Important** : après une mise à jour du code, arrête le backend (`Ctrl+C`) et relance `run_app_windows.ps1`. Un backend déjà lancé garde l'ancien code.

**Cause constatée sur ce PC le 15/10.** `sumo-gui.exe` (ainsi que `netgenerate` et `netconvert`) charge `gdal.dll`, qui a besoin de `VCOMP140.DLL`. Cette DLL n'est pas fournie par SUMO et manquait dans Windows : erreur 0xC0000135.
- Réparation : installer « Microsoft Visual C++ Redistributable 2015–2022 x64 » (`https://aka.ms/vs/17/release/vc_redist.x64.exe`).
- En attendant, lancer les simulations **sans** SUMO-GUI. Ce mode fonctionne, et l'application refuse désormais clairement SUMO-GUI tant qu'il ne peut pas démarrer.

