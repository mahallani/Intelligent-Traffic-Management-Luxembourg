# FINAL_DEMO_REPORT – ce qui a réellement été exécuté (2026-10-12)

Ce rapport sépare strictement trois choses :
- ce qui a tourné sur la **machine Linux de ton PC** (Cowork, Python 3.10, SUMO 1.27.1 via pip, libsumo) ;
- ce qui a tourné sous **Windows** (ton Python 3.11.9, SUMO 1.27.1) ;
- ce qui **n'a pas encore été observé**.

Rien n'est déclaré « fonctionne sous Windows » sans journal Windows.

## 1. Synthèse

| Élément | Linux (ton PC) | Windows | Démo graphique |
|---|---|---|---|
| Scénario SUMO Kirchberg, 4 feux | ✅ tests | ✅ 12/12 contrôles (`validation_20261012_134608.log`) | — |
| TraCI | ✅ | ✅ démarrage rapide OK (même journal) | — |
| Suite de tests complète | ✅ **109/109** (`test_logs/linux_vm_pytest_20261012_184601.log`) | ❌ **non exécutée** : pytest absent au passage du 12/10 13:46 | — |
| Backend de l'application (API, démarrage/arrêt de SUMO, exports) | ✅ tests + session HTTP réelle (§3) | ❌ non exécuté | — |
| Frontend Next.js (pages servies, scripts chargés) | ✅ pages et scripts servis en HTTP 200 (§3) | ❌ non exécuté | ❌ **non observé dans un navigateur** |
| Démo SUMO-GUI | — | ❌ non lancée | ❌ **non observée** |
| Collecte CITA 7 jours | — | ❌ **non démarrée** | — |

## 2. Tests exécutés sous Linux (12/10)

Commande : `python3 -m pytest -p no:cacheprovider -v`, depuis la racine du projet.

Résultat : **109 réussis, 0 échec, 277 sous-tests réussis, 58 s.**

| Fichier | Ce qu'il couvre |
|---|---|
| `tests/test_app_api.py` (5) | API, run court complet, pause/reprise/arrêt, refus d'une 2e simulation (409), erreurs, comparaison et rapports |
| `tests/test_safety_emergency.py` (11) | sécurité de chaque stratégie y compris le RL, priorité urgence, 2 contrôles négatifs, non-régression du blocage après urgence |
| `tests/test_cascade.py` (6) | causalité des variables, cibles, étages de la cascade, sauvegarde/chargement, journal en ligne, prévision coupée = S2 |
| `tests/test_agents.py` | agents, ordre des phases, jaune, vert min/max |
| `tests/test_kirchberg_scenario.py`, `test_lust_integration.py`, `test_metrics.py`, `test_synthetic.py` | scénario, intégration LuST, métriques |
| `tests/test_collect_cita_*.py`, `test_collectors_resilience.py`, `test_single_instance.py`, `test_data_quality.py` | collecteurs CITA, verrou d'instance unique, qualité des données |

Chaque nouveau test de non-régression a d'abord été exécuté sur l'ancien code, où il **échoue**, puis sur le code corrigé, où il **réussit** (`AGENT_EVALUATION_REPORT.md` §8).

## 3. Application testée en HTTP réel (Linux, sans navigateur)

Un serveur uvicorn réel a été lancé, puis interrogé par HTTP. Journaux : `data/reports/test_logs/linux_vm_app_http_e2e_20261012_180904.log` et `linux_vm_app_http_stop_*.log`.

Constaté :
- Les 4 pages (`/`, `/resultats/`, `/donnees/`, `/rapports/`) et les scripts `_next/static/*.js` répondent en 200.
- `POST /api/sim/start` (S2F, x3, graine 21) renvoie 200. Une deuxième demande pendant le run renvoie **409**.
- En cours de run, `/api/sim/state` donne l'heure simulée (07:42:46), l'état des 4 feux (par exemple `GGGgrrrGGGgrrr`) et 85 véhicules positionnés.
- **Pause** : l'heure simulée reste figée (27 821 s avant et après 2 s d'attente). **Reprise** : le run continue (40 décisions, prévisions pour les 4 feux).
- CO₂ en direct : 664,6 kg ; valeur finale SUMO : 663,5 kg (écart 0,2 %).
- Les 5 fichiers du run (kpis, file d'attente, décisions, alertes, prévisions) sont téléchargeables. L'export CSV renvoie 44 runs, et la comparaison S0/S1 à x5 répond.
- **Arrêt en cours de run** (S3 RL, x5, délai 20 ms) : statut « stopped » à 07:08, `stopped_early = true`, 0 violation de sécurité. Le run partiel apparaît dans la liste.
- Le serveur s'arrête proprement.

**Non vérifié :** l'affichage dans un navigateur (carte, couleurs des feux, graphiques, boutons). Le rendu n'a pas été observé par une personne ni capturé à l'écran.

## 4. Ce que tu dois lancer sous Windows (PowerShell, à la racine du projet)

```powershell
cd C:\Users\ASUS\Intelligent-Traffic-Management-Luxembourg
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\windows\validate_windows.ps1
```

`requirements.txt` a été mis à jour (sauvegarde `requirements.txt.bak_20261012`) : il ajoute `numpy`, `fastapi`, `uvicorn` et `httpx`.

`validate_windows.ps1` (sauvegarde `.bak_20261012`) lance maintenant :
- la suite pytest complète ;
- les tests de l'application, de la sécurité et de la cascade en mode détaillé ;
- un **démarrage et arrêt HTTP réel du serveur** ;
- la validation du scénario.

Le journal est écrit dans `data\reports\windows_validation\validation_<date>.log`.

Ensuite, pour l'application :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\run_app_windows.ps1
```

Le navigateur s'ouvre sur http://127.0.0.1:8000. Lance par exemple S1 puis S3 à x5 (graine 61) depuis « Pilotage ». Vérifie que les 4 carrefours changent de couleur et que les onglets Décisions et Prévisions se remplissent. Compare ensuite S0 et S1 dans « Résultats ».

Pour la démo SUMO-GUI : `powershell -ExecutionPolicy Bypass -File scripts\windows\run_demo_windows.ps1`, ou la case « SUMO-GUI » de l'application.

Après ces lancements, envoie-moi le chemin du journal (ou laisse-le dans le dossier) : je mettrai ce rapport à jour à partir du journal réel. Si tu m'y autorises, je peux aussi prendre une capture d'écran de l'application ouverte.

## 5. Problèmes connus et solutions réalisables en deux mois

| Problème | Cause | Solution proposée | Effort |
|---|---|---|---|
| Aucun test Windows de l'application | pytest et fastapi absents du Python Windows | Les commandes du §4 | 15 min |
| Rendu navigateur non vérifié | aucun lancement observé | Lancement par toi, puis capture d'écran | 15 min |
| Collecte CITA 7 jours jamais démarrée | non lancée (commandes prêtes) | La lancer dès que le PC peut rester allumé 7 jours ; deux fenêtres, un collecteur chacune, verrou d'instance unique | 7 jours de calendrier |
| Calibration réel/simulé impossible | aucun poste réel dans la zone ; le facteur global testé aggrave l'écart | Documenté ; piste : capteurs CITA de la N11/A1 voisins, après la collecte de 7 jours, en comparaison d'ordre de grandeur seulement | 1–2 semaines |
| Le RL ne dépasse pas S1 | 341 états fiables sur 1 999 ; 43 % de repli ; 26 épisodes | Plus d'épisodes (≈ 200, ≈ 1 h de calcul avec libsumo) avec des états plus grossiers, puis réévaluation sur les graines 61–65 | 1 semaine |
| La prévision n'aide pas la décision | prévision proche de la persistance à faible demande ; le profil fait mieux à x5 | Combiner cascade et profil ; tester la prévision pour anticiper les incidents plutôt que pour la durée des verts | 1–2 semaines |
| Ancienne évaluation urgence (S2) invalide | bug d'actionneur, corrigé | Déjà refaite (`emergency_v2`) | fait |

## 6. Fichiers produits ou modifiés aujourd'hui (rien n'a été supprimé)

| Fichier | Statut |
|---|---|
| `app/` (backend FastAPI, frontend Next.js compilé dans `out/`) | **nouveau**. Ancienne compilation conservée dans `out_build_20261012a/`. `page.jsx.bak_20261012` et `page.jsx.prev` sont deux copies de la version précédente. |
| `agents/intervention/safety_monitor.py`, `emergency_priority.py` | nouveaux |
| `agents/intervention/tls_actuator.py`, `agents/orchestrator.py`, `scripts/simulation/run_experiment.py` | modifiés (sauvegardes `.bak_20261012c` et `.bak_20261012d`) |
| `app/backend/sim_manager.py` | modifié après installation pour afficher le bilan de sécurité (`.bak_20261012`) |
| `scripts/simulation/evaluate_emergency.py`, `analyze_strategies_v2.py`, `check_signal_conflicts_v1.py` | nouveaux (les deux premiers modifiés ensuite, avec sauvegardes `.bak_20261012d`) |
| `tests/test_app_api.py`, `test_cascade.py`, `test_safety_emergency.py` | nouveaux (`test_safety_emergency.py.bak_20261012d` avant l'ajout des tests de non-régression) |
| `requirements.txt`, `scripts/windows/validate_windows.ps1` | modifiés (sauvegardes `.bak_20261012`) |
| `scripts/windows/run_app_windows.ps1`, `APPLICATION_GUIDE.md`, `AGENT_EVALUATION_REPORT.md`, `FINAL_DEMO_REPORT.md` | nouveaux |
| `PROJECT_GAP_ANALYSIS.md`, `DATA_VALIDATION_REPORT.md` | mis à jour (sauvegardes `.bak_20261012`) |
| `output/experiments_v2/`, `experiments_v2b/`, `experiments_v1/emergency_v2/`, `detection_v2/*_confirm_seeds11_12/`, `output/safety/`, `output/app_runs/` | nouveaux résultats |
| `data/reports/test_logs/` | journaux de tests Linux |
| `data/reports/file_status_register_v1.csv` | 2 lignes « remplacé » ajoutées (sauvegarde `.bak_20261012d`) |
| `_transfer/*.tar.gz` | archives ayant servi à installer l'application |
| Dossiers `*_INCOMPLETE_1` | runs interrompus par la limite de durée d'une commande, conservés et refaits |

## 7. Mise à jour du 15/10/2026

### 7.1 Tests Windows réellement exécutés le 13/10

Source : `data/reports/windows_validation/validation_20261013_115527.log`, lancé par toi (Python 3.11.9, SUMO 1.27.1).

| Étape | Résultat |
|---|---|
| Suite pytest complète | **108 réussis, 1 échec** : `test_libsumo_gives_identical_results`, `ImportError: DLL load failed while importing _libsumo` |
| Tests application, sécurité, cascade (détail) | **32/32** |
| Démarrage et arrêt HTTP réels du serveur | OK |
| Validation du scénario | 12/12 |
| Run de l'application (13/10 12:04, S0 x1, TraCI) | terminé, KPI écrits |
| Run du 13/10 12:06 | SUMO tué à 07:26:58 (backend fermé pendant le run), aucun KPI écrit |

Le §1 de ce rapport, qui indiquait les tests Windows comme non exécutés, date du 12/10 : il est dépassé sur ce point.

### 7.2 Incident du 15/10 : « Could not connect to TraCI server … (TraCI server already finished) »

**Constats** (dossiers de run et code) :
- les runs de 20:41:32 et 20:42:53 ont des dossiers **vides**, sans `sumo.log` : SUMO est mort avant d'ouvrir son journal ;
- 81 s séparent les deux runs, ce qui correspond aux 60 relances de `traci.start` ;
- ta console ne montre aucun message `Error:` de SUMO ;
- aucun fichier du projet n'a changé entre le 13/10 (run réussi) et le 15/10 ;
- un run lancé à 21:04:14 est lui aussi vide, sans `sumo_process.log` : ton backend tournait encore avec l'ancien code, à relancer.

**Ce qui est démontré**, en reproduction sous Linux avec l'ancien code : un SUMO qui meurt au démarrage provoque 61 lancements en 60 s, un dossier vide et une erreur trompeuse dans l'interface.

**Ce qui n'est pas encore démontré : la raison exacte de l'arrêt de SUMO sur ton PC.** L'absence de message dans la console indique soit sumo-gui (programme fenêtré : ses messages ne vont pas à la console, et son journal n'est ouvert qu'après sa fenêtre), soit un échec de chargement de DLL. Ce PC a déjà des DLL SUMO de versions mélangées (échec de libsumo). Le diagnostic `diagnose_sumo_launch.py` donnera le code de sortie et les messages.

**Défauts corrigés** (sauvegardes `.bak_20261015`) :

| Fichier | Correction |
|---|---|
| `traci_layer/launcher.py` (nouveau), `traci_layer/connection.py` | Lancement de SUMO unique, ou deux lancements en cas de conflit de port. Sortie de SUMO dans `sumo_process.log`. `SumoStartError` avec code de sortie décodé. SUMO bloqué tué. Fermeture avec délai maximal, puis arrêt forcé. Exceptions TraCI reconnues même avec plusieurs copies de `traci` ou avec libsumo chargé (sinon l'erreur échappait au traitement). |
| `agents/common/sim_env.py` | Test de libsumo une seule fois, dans un processus séparé sous Windows, puis TraCI. Variable `ITM_SUMO_BACKEND`. SUMO fermé si l'initialisation échoue. |
| `agents/orchestrator.py` | `env.start()` placé dans le bloc protégé : SUMO est toujours fermé. |
| `app/backend/sim_manager.py` | Erreur détaillée dans l'interface et dans `app_error.json`. `shutdown()` pour un arrêt propre. |
| `app/backend/server.py` | Arrêt propre de la simulation à la fermeture du backend. Nouvel endpoint `/api/diagnostics`. |
| `scripts/windows/diagnose_sumo_launch.py` (nouveau), `validate_windows.ps1` | Diagnostic du lancement et tests de lancement forcés en TraCI. |
| `tests/test_sumo_launch.py` (nouveau) | 5 tests : SUMO qui meurt au démarrage, arrêt silencieux avec code de sortie, erreur affichée puis reprise, **simulation complète 07:00–08:00 en TraCI avec KPI**, pause/reprise puis arrêt sans processus SUMO restant. |

**Tests réellement exécutés le 15/10** (machine Linux de ton PC, SUMO 1.27.1) :
- suite complète : **114/114** (`test_logs/linux_vm_pytest_20261015_195855.log`) ;
- tests application, lancement, sécurité et cascade **forcés en TraCI** : 27/27 (`linux_vm_pytest_traci_*.log`) ;
- session HTTP en TraCI avec arrêt du backend pendant un run (`linux_vm_app_http_traci_*.log`) ;
- le test de reproduction échoue sur l'ancien code (60 s) et réussit sur le nouveau.

Le rapport `windows_validation/sumo_launch_diag_20261015_200545.log` a été produit **sous Linux** (chemins `/sessions/...`) : ce n'est pas un résultat Windows. Son échec sumo-gui (« unable to open display ») est normal sur une machine sans écran.

**Sous Windows le 15/10 : aucun test exécuté par moi.** Les commandes sont au §4, avec en plus `python scripts\windows\diagnose_sumo_launch.py`.

### 7.3 Cause identifiée (15/10, 21:08–21:14, journaux Windows)

**Sources** : `windows_validation/sumo_launch_diag_20261015_210809.log`, `sumo_launch_diag_20261015_211138.log`, `validation_20261015_210823.log`, et analyse des tables d'import de `C:\Program Files (x86)\Eclipse\Sumo\bin` (lecture seule, aucun fichier SUMO modifié).

**Constats :**
- `sumo.exe` démarre et fonctionne avec la commande exacte de l'application (connexion TraCI, 30 s simulées, « TraCI requested termination »).
- `sumo-gui.exe` s'arrête immédiatement avec le code **0xC0000135 (STATUS_DLL_NOT_FOUND)**, sans aucun message et sans `sumo.log`.
- `netgenerate.exe` s'arrête avec le **même code** : les 18 tests de `test_synthetic.py` sont en erreur le 15/10, alors qu'ils passaient le 13/10.
- Chaîne de dépendances : `sumo-gui.exe`, `netgenerate.exe` et `netconvert.exe` chargent `gdal.dll`, qui charge **`VCOMP140.DLL`**. Ce runtime OpenMP de Microsoft Visual C++ n'est **pas fourni par SUMO** : son `bin` contient `msvcp140*` et `vcruntime140*`, mais pas `vcomp140.dll`. Il vient de Windows, par le « Microsoft Visual C++ Redistributable x64 ».
- `sumo.exe` ne charge pas GDAL, ce qui explique qu'il fonctionne.
- Aucun fichier du dossier `bin` de SUMO n'a changé depuis l'installation (25/06/2026). Le 13/10, `netgenerate` fonctionnait. **La DLL a donc disparu du système entre le 13/10 et le 15/10.** L'erreur libsumo est passée de « procédure introuvable » (13/10) à « module introuvable » (15/10).

**Conclusion.** Les avertissements « TraCI server already finished » du 15/10 venaient de lancements **avec SUMO-GUI**. sumo-gui ne peut plus démarrer sur ce PC faute de `vcomp140.dll`. La simulation sans SUMO-GUI fonctionne.

**Vérification à faire :** `Test-Path C:\Windows\System32\vcomp140.dll` doit répondre `False` avant réparation.

**Réparation** (action de l'utilisateur, hors projet) :
1. Installer « Microsoft Visual C++ Redistributable 2015–2022 x64 » depuis Microsoft (`https://aka.ms/vs/17/release/vc_redist.x64.exe`), ou choisir « Réparer » s'il est déjà listé dans les applications installées.
2. Relancer le diagnostic.

**Protection ajoutée dans l'application :**
- Une demande avec SUMO-GUI est refusée **immédiatement** (HTTP 400), avec la raison et le conseil de décocher SUMO-GUI. Aucun dossier de run vide n'est créé.
- La vérification (`sumo-gui --version`, sans fenêtre) est mémorisée seulement si elle réussit : une installation réparée est prise en compte sans redémarrer.
- `/api/diagnostics` indique si `sumo` et `sumo-gui` peuvent démarrer.
- Test : `test_gui_start_refused_clearly_when_sumo_gui_cannot_start`.

**Résultats Windows du 15/10** (journal `validation_20261015_210823.log`, exécuté par toi) :

| Étape | Résultat |
|---|---|
| TraCI, démarrage rapide (sans GUI) | OK |
| Diagnostic de lancement | `sumo` OK ; `sumo-gui` en échec (0xC0000135) |
| Tests de lancement et de l'application forcés en TraCI | **10/10** |
| Tests application, sécurité et cascade (détail) | **32/32** |
| Démarrage et arrêt HTTP réels du serveur | OK |
| Suite complète | **18 erreurs** dans `test_synthetic.py` (netgenerate, même DLL manquante) ; voir le journal pour le reste |
| Validation du scénario | en cours au moment de la lecture (T1–T3 réussis) |

Ces Windows 10/10 ne couvrent pas encore le test `test_gui_start_refused…`, ajouté après ton lancement.

