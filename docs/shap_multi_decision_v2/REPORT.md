# Étude SHAP multi-décision — stabilité selon le fond de référence

Données : **simulation SUMO** (SIMULATED_sumo_lust_kirchberg_4tls). Table Q gelée : `sumo/lust_4_intersections/output/experiments_v1/rl/qtable_v4_FROZEN_ep26_eval.json`. Rien n'a été simulé ni réentraîné ; les fichiers d'entrée sont inchangés (empreintes avant/après identiques).

Fonds : **A** visites (méthode actuelle) · **B** uniforme sur les mêmes états · **C** états fiables de A, pondérés par les visites (calculé si ≥ 5 états).

## 1. Données

| Run | Lignes | État enregistré | Décisions retenues |
|---|---|---|---|
| `20261012_180949_S3_rl_qlearning_x5_seed22` | 68 | non | 0 |
| `20261012_181128_S3_rl_qlearning_x5_seed22` | 68 | non | 0 |
| `20261022_141518_S3_rl_qlearning_x1_seed1_ambulance_prio` | 613 | oui | 259 |

259 décisions retenues sur 749 lignes ; 490 exclues :

| Code | Détail | Lignes |
|---|---|---|
| fallback_S2 | règle de secours S2 (situation trop peu vue) | 277 |
| run_without_logged_state | decisions.csv has no 'explanation' column | 136 |
| rule:max_green | sécurité : vert maximum atteint | 74 |
| fallback_S2 | règle de secours S2 (situation jamais vue) | 3 |

Unité d'analyse : **l'état distinct** (32 états pour 259 décisions).

## 2. Résultat principal (non pondéré : un état = une unité)

| Catégorie | États | Décisions (pondéré) |
|---|---|---|
| stable | 12 | 145 |
| partiellement stable | 3 | 14 |
| instable | 17 | 100 |
| non évaluable | 0 | 0 |

- États évaluables : 32 ; part stable ou partiellement stable : **46.9 %** (pondérée par les décisions : 61.4 %).
- Lecture fixée à l'avance (≥ 80 % plutôt robuste, < 50 % sensible) : **sensible**.
- États où C = A (tous les états retenus sont fiables, accord A–C non probant) : 2 (dont 2 classés stables).
- Parmi les états partiellement stables, 2 ont une inversion de signe **sur la variable principale elle-même** (même variable en tête, sens opposé) : le protocole les classe « partiellement stables », mais ce désaccord est sérieux (indicateur descriptif, non utilisé pour le classement).
- Profils d'accord : A≈B, C differs : 10, A≈C, B differs : 2, all agree : 12, all differ : 8.

| Paire | États | Avec inversion de signe | Distance de forme min / médiane / max | τ de Kendall défini | τ médian |
|---|---|---|---|---|---|
| A-B | 32 | 4 | 0.040 / 0.273 / 0.922 | 25 | 0.667 |
| A-C | 32 | 10 | 0.000 / 0.353 / 0.985 | 23 | 0.333 |
| B-C | 32 | 13 | 0.054 / 0.525 / 1.000 | 25 | 0.333 |

## 3. Par intersection (descriptif uniquement)

| Feu | États | Décisions | Stable | Partiel | Instable | Non évaluable | Part stable/partiel | C = A |
|---|---|---|---|---|---|---|---|---|
| -20484 | 13 | 97 | 3 | 2 | 8 | 0 | 38.5 % | 0 |
| -23354 | 9 | 71 | 3 | 1 | 5 | 0 | 44.4 % | 2 |
| -28692 | 4 | 41 | 3 | 0 | 1 | 0 | 75.0 % | 0 |
| -29958 | 6 | 50 | 3 | 0 | 3 | 0 | 50.0 % | 0 |

## 4. Détail par état

| État | Déc. | Retenus A / C | Catégorie | Variable principale A / B / C | Inversions de signe | Remarque |
|---|---|---|---|---|---|---|
| `-20484\|0\|0\|0\|0\|3` | 19 | 172 / 40 | instable | durée_vert / file_servie / durée_vert | B-C: en_mouvement |  |
| `-20484\|0\|0\|0\|1\|3` | 14 | 176 / 40 | instable | file_autre / file_autre / durée_vert | A-C: en_mouvement; B-C: en_mouvement |  |
| `-20484\|0\|1\|1\|0\|0` | 1 | 144 / 39 | instable | file_servie / en_mouvement / file_servie | A-B: durée_vert; B-C: durée_vert |  |
| `-20484\|1\|0\|1\|0\|0` | 22 | 62 / 17 | instable | file_autre / en_mouvement / file_autre | A-C: en_mouvement; B-C: en_mouvement | inversion sur la variable principale : en_mouvement |
| `-20484\|1\|0\|2\|0\|0` | 1 | 76 / 17 | instable | file_autre / en_mouvement / file_autre | A-C: en_mouvement; B-C: en_mouvement | inversion sur la variable principale : en_mouvement |
| `-20484\|2\|0\|0\|0\|0` | 9 | 56 / 12 | partiellement stable | en_mouvement / en_mouvement / en_mouvement | A-B: file_autre; A-C: en_mouvement; B-C: file_autre,en_mouvement | inversion sur la variable principale : en_mouvement; constante(s) : file_servie |
| `-20484\|2\|0\|0\|0\|1` | 1 | 52 / 12 | instable | en_mouvement / en_mouvement / file_autre | aucune | constante(s) : file_servie |
| `-20484\|2\|0\|1\|0\|0` | 16 | 94 / 28 | instable | file_servie / file_servie / en_mouvement | B-C: en_mouvement | inversion sur la variable principale : en_mouvement |
| `-20484\|2\|0\|2\|0\|0` | 1 | 108 / 30 | partiellement stable | file_servie / file_servie / file_servie | A-C: en_mouvement; B-C: en_mouvement |  |
| `-20484\|2\|1\|1\|0\|0` | 5 | 93 / 25 | stable | en_mouvement / en_mouvement / en_mouvement | aucune |  |
| `-20484\|2\|1\|1\|1\|0` | 3 | 87 / 25 | stable | en_mouvement / en_mouvement / en_mouvement | aucune |  |
| `-20484\|2\|1\|1\|1\|1` | 2 | 86 / 25 | stable | en_mouvement / en_mouvement / en_mouvement | aucune |  |
| `-20484\|2\|1\|2\|0\|0` | 3 | 141 / 30 | instable | file_autre / en_mouvement / durée_vert | aucune |  |
| `-23354\|0\|0\|0\|0\|2` | 21 | 16 / 15 | stable | durée_vert / durée_vert / durée_vert | aucune | constante(s) : file_autre, file_servie |
| `-23354\|0\|1\|1\|0\|1` | 2 | 32 / 15 | instable | en_mouvement / file_autre / durée_vert | aucune | constante(s) : file_servie |
| `-23354\|0\|1\|1\|1\|0` | 4 | 35 / 15 | partiellement stable | en_mouvement / en_mouvement / en_mouvement | A-C: en_mouvement,durée_vert; B-C: en_mouvement,durée_vert | inversion sur la variable principale : en_mouvement; constante(s) : file_servie |
| `-23354\|0\|1\|1\|1\|1` | 1 | 41 / 15 | instable | en_mouvement / file_autre / durée_vert | aucune | constante(s) : file_servie |
| `-23354\|0\|1\|2\|1\|3` | 2 | 70 / 24 | instable | en_mouvement / en_mouvement / file_autre | A-C: durée_vert; B-C: durée_vert |  |
| `-23354\|1\|0\|0\|0\|1` | 30 | 16 / 16 | stable | en_mouvement / en_mouvement / en_mouvement | aucune | C = A; constante(s) : file_autre, file_servie |
| `-23354\|1\|0\|0\|1\|3` | 8 | 16 / 16 | stable | en_mouvement / en_mouvement / en_mouvement | aucune | C = A; constante(s) : file_autre, file_servie |
| `-23354\|1\|1\|1\|0\|0` | 1 | 16 / 14 | instable | durée_vert / durée_vert / en_mouvement | aucune | constante(s) : file_autre, file_servie |
| `-23354\|1\|1\|1\|0\|1` | 2 | 16 / 14 | instable | en_mouvement / en_mouvement / durée_vert | aucune | constante(s) : file_autre, file_servie |
| `-28692\|0\|0\|1\|3\|1` | 2 | 199 / 26 | instable | file_autre / file_autre / durée_vert | A-C: file_servie; B-C: file_servie |  |
| `-28692\|3\|0\|1\|0\|0` | 29 | 31 / 11 | stable | file_autre / file_autre / file_autre | aucune |  |
| `-28692\|3\|0\|2\|0\|0` | 8 | 48 / 13 | stable | file_autre / file_autre / file_autre | aucune |  |
| `-28692\|3\|0\|3\|0\|0` | 2 | 58 / 13 | stable | file_autre / file_autre / file_autre | aucune |  |
| `-29958\|0\|0\|0\|0\|1` | 26 | 80 / 14 | stable | file_autre / file_autre / file_autre | aucune | constante(s) : file_servie |
| `-29958\|0\|0\|0\|0\|2` | 5 | 80 / 14 | stable | file_autre / file_autre / file_autre | aucune | constante(s) : file_servie |
| `-29958\|1\|0\|2\|0\|0` | 6 | 22 / 7 | stable | file_autre / file_autre / file_autre | aucune | constante(s) : file_servie |
| `-29958\|1\|0\|3\|0\|0` | 1 | 29 / 7 | instable | en_mouvement / en_mouvement / file_autre | A-B: file_autre; B-C: file_autre | inversion sur la variable principale : file_autre; constante(s) : file_servie |
| `-29958\|2\|0\|0\|0\|2` | 11 | 117 / 11 | instable | en_mouvement / en_mouvement / durée_vert | A-C: file_autre,durée_vert | inversion sur la variable principale : durée_vert; constante(s) : file_servie |
| `-29958\|2\|0\|1\|3\|2` | 1 | 222 / 34 | instable | file_servie / file_autre / file_servie | A-B: file_servie; A-C: durée_vert; B-C: file_servie,file_autre,durée_vert | inversion sur la variable principale : file_autre, file_servie |

## 5. Contrôles

- Additivité vérifiée pour chaque état et chaque fond (tolérance 1e-9).
- Fond A identique à l'explication par défaut de `shap_qtable` (écart ≤ 1e-12) pour chaque état.
- Fond B : exactement les états de A, poids 1. Fond C : exactement A restreint aux états fiables (recalculé indépendamment à partir du fond complet).
- Chaque ligne des journaux est soit retenue, soit exclue avec un motif.
- Empreintes SHA-256 et dates des fichiers d'entrée identiques avant et après.

Mesure descriptive ajoutée (non utilisée pour le classement) : `main_margin_*` dans `per_state.csv` = écart entre la 1re et la 2e |contribution|, rapporté à Σ|φ|. Une petite marge signale qu'un changement de variable principale peut venir d'une quasi-égalité.

## 6. Limites

- Un seul run exploitable (×1, graine 1, 07:00–08:00, priorité ambulance) ; la table a été entraînée à ×5.
- Seules les décisions « passer » de la table sont explicables (S2, règles et « garder » exclus) : l'échantillon favorise les états bien appris.
- Les états d'un même feu et d'une même phase partagent presque le même fond : ils ne sont pas indépendants. Aucun test statistique.
- Une contribution nulle d'une variable constante ne prouve rien sur son effet. Même dans C, des états hybrides peuvent être peu fiables.
- SHAP décrit la sortie de la table Q, pas un effet causal sur le trafic. Les seuils (5 %, 80 %, 50 %) sont des conventions fixées avant le calcul.
