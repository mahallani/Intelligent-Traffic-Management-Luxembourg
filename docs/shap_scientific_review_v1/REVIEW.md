# Revue scientifique finale — partie XAI (SHAP) du contrôleur S3

Projet *Intelligent Multi-Agent Traffic Management — Luxembourg* · revue du 29/10/2026
Données : **simulation SUMO** (`SIMULATED_sumo_lust_kirchberg_4tls`), aucune donnée réelle de trafic.
Aucun fichier existant n'a été modifié pour cette revue. Les calculs complémentaires sont en lecture seule
(`review_computations.py` → `review_computations.json`, dans ce dossier).

---

## 0. Résumé

1. Les 6 PNG de `docs/shap_visualizations_v2` (3 français, 3 anglais) ont été ouverts et relus : titres, axes,
   légendes et valeurs sont corrects et lisibles. Toutes les valeurs affichées correspondent aux deux rapports
   JSON sources (arrondi à 6 décimales). Aucun problème bloquant ; 8 remarques mineures sont listées (§ 2.4),
   **non corrigées**.
2. Le README et `figures_manifest.json` sont cohérents avec `shap_demo_v2/shap_result.json` et
   `shap_stability_v2/shap_stability.json` (empreintes SHA-256 identiques, valeurs égales au bit près).
3. Le changement de signe de `file_autre` est un **effet de référence** : la contribution SHAP mesure un écart
   par rapport au fond de référence. Ce fond est dominé par la classe « > 10 » avec les visites (76 %), et
   beaucoup moins en uniforme (28 %). La décomposition exacte le montre (§ 5).
4. La décision Q-learning **ne change pas** : elle vient des deux valeurs Q de l'état, que SHAP ne modifie pas.
   Les deux méthodes expliquent exactement le même Δ = +3,170026 (§ 6).
5. Les limites sont importantes : 22 des 29 états du fond sont peu fiables, le fond vient de l'entraînement (×5)
   alors que la décision vient d'un run ×1, et **une seule décision** est analysée. Le résultat positif de la
   méthode uniforme repose surtout sur des états peu fiables. Un plan de validation sur les 259 décisions
   apprises du run ×1 (32 états distincts) est proposé (§ 8).

---

## 1. Ce qui a été examiné

| Fichier | Comment | Empreinte SHA-256 (début) |
|---|---|---|
| `docs/shap_visualizations_v2/fig1_shap_contributions_fr.png` | image ouverte et lue | — |
| `docs/shap_visualizations_v2/fig2_shap_ranking_fr.png` | image ouverte et lue | — |
| `docs/shap_visualizations_v2/fig3_shap_additivity_fr.png` | image ouverte et lue | — |
| `docs/shap_visualizations_v2/fig{1,2,3}_*_en.png` | images ouvertes et lues | — |
| `docs/shap_visualizations_v2/fig{1,2,3}_*_fr.pdf` | rendus en image et comparés aux PNG ; polices vérifiées (`pdffonts`) | — |
| `docs/shap_visualizations_v2/README.md`, `figures_manifest.json` | lus et comparés aux sources par script | — |
| `docs/shap_demo_v2/shap_result.json` | source | `758ce0c983975241…` |
| `docs/shap_stability_v2/shap_stability.json` | source | `2c341ace852df2c4…` |
| table Q gelée `qtable_v4_FROZEN_ep26_eval.json` et `decisions.csv` des runs S3 | lus par `review_computations.py` | voir JSON |

Les PDF anglais n'ont **pas** été ouverts (seuls les PDF français l'ont été).
Remarque : la demande parlait de « 6 PNG français ». Le dossier contient **3 PNG français et 3 PNG anglais**,
plus 6 PDF ; les 6 PNG ont été examinés.

Les copies examinées ont été récupérées depuis le PC le 29/10/2026 ; le dossier `shap_visualizations_v2`
contient bien 14 fichiers (12 figures, le manifeste et le README).

---

## 2. Revue des figures

### 2.1 Figure 1 — contributions signées (A visites / B uniforme)

| Élément | Constat |
|---|---|
| Titre | « Contributions SHAP exactes à Δ = Q(passer) − Q(garder) = +3.170026 » : précis, la grandeur expliquée est nommée. |
| Sous-titre | Contrôleur, feu, heure, décision et provenance (« données simulées SUMO ») indiqués. |
| Axes | Même échelle (−1,0 à 1,0) dans les deux panneaux : la comparaison visuelle est honnête. Unité : « unités de valeur Q ». Ligne verticale à 0 bien visible. |
| Légende | Bleu = pousse vers « passer », rouge = pousse vers « garder ». Le signe est aussi écrit sur chaque valeur, donc la couleur n'est pas seule porteuse du sens. |
| Valeurs | A : 0 ; −0.447999 ; +0.520247 ; +0.202498. B : 0 ; +0.260435 ; +0.805710 ; +0.793159. Valeurs de référence : +2.895279 et +1.310722. **Toutes conformes au JSON.** |
| Notes | `file_servie` est marquée « 0 (constante) », avec la phrase « ne prouve pas l'absence d'effet ». Mention « 22 des 29 états retenus… peu fiables ». « (signe inversé) » est signalé sous `file_autre` dans le panneau B. |

### 2.2 Figure 2 — classement par |contribution|

| Élément | Constat |
|---|---|
| Titre | « Classement des variables selon \|contribution SHAP\| » : correct. |
| Lecture | Rangs 1 à 4 à gauche ; colonnes A et B ; valeurs signées affichées à côté de chaque nom. |
| Valeurs | Rangs A : en_mouvement 1, file_autre 2, durée_vert 3, file_servie 4. Rangs B : 1, 3, 2, 4. **Conformes au JSON.** |
| Notes | Croisement file_autre / durée_vert bien visible ; `file_servie` en pointillé gris avec astérisque et note explicite. |

### 2.3 Figure 3 — additivité

| Élément | Constat |
|---|---|
| Titre | « Additivité : valeur de référence + somme des contributions = Δ » : correct. |
| Axes | Axe vertical commun aux deux panneaux, partant de 0 (pas d'exagération visuelle). Unité : « unités de valeur Q ». |
| Valeurs | A : 2.895279 + 0.274747 = 3.170026. B : 1.310722 + 1.859304 = 3.170026. Erreur d'additivité 0 (tolérance 1e-09). **Conformes au JSON.** |
| Notes | La ligne tiretée Δ commun est expliquée en pied de figure. |

Les versions anglaises ont le même contenu et les mêmes valeurs ; les traductions sont correctes.

### 2.4 Problèmes signalés (non corrigés)

Aucun problème n'est bloquant. Ils peuvent être traités dans une version `shap_visualizations_v3`, si vous le décidez.

| # | Gravité | Problème | Proposition |
|---|---|---|---|
| P1 | moyenne | La note « 22 des 29 états retenus ont des valeurs Q peu fiables **(moins de 3 visites)** » est imprécise. La règle réelle (`QTable.reliable`) est : *une des deux actions essayée moins de 3 fois, ou valeurs Q égales*. Exemple : l'état [0,0,0,0] a 80 visites, mais « passer » n'y a été essayé qu'une fois ([79, 1]). Ici les 22 cas viennent tous de « moins de 3 essais d'une action » (vérifié), donc la phrase n'est pas fausse, mais elle peut être lue comme « moins de 3 visites au total ». La même formulation figure dans les limites de `shap_qtable.py`. | Écrire « une des deux actions essayée moins de 3 fois ». |
| P2 | moyenne | Les figures ne disent pas que **l'état expliqué lui-même est fiable** (visites 10 / 79, valeurs Q différentes). Un lecteur peut croire que la décision est peu fiable. | L'ajouter dans la légende du rapport. |
| P3 | moyenne | Les figures ne disent pas que le fond vient de la distribution d'entraînement (demande ×5), alors que la décision vient d'un run ×1. | L'ajouter dans la légende du rapport. |
| P4 | faible | « Valeur de référence » n'est pas définie sur la figure (c'est la moyenne pondérée de Δ sur le fond). | Une phrase dans la légende. |
| P5 | faible | « unités de valeur Q » : une valeur Q est un retour actualisé attendu, sans unité physique. | Préciser « unités de la récompense actualisée (sans unité physique) ». |
| P6 | faible | `durée_vert = ≤ 10 s` se lit mal (« = ≤ »). | Écrire `durée_vert : ≤ 10 s`. |
| P7 | faible | Dans les figures françaises, le séparateur décimal est le point, comme dans les JSON. C'est acceptable, mais incohérent avec un texte en français qui utilise la virgule. | Garder le point pour la traçabilité, ou le signaler dans la légende. |
| P8 | faible | 6 décimales suggèrent une précision que les valeurs peu fiables ne justifient pas. | Pour la soutenance : 2 décimales, avec les valeurs exactes en annexe. |

Remarque sur le manifeste (pas une erreur) : `figures_manifest.json` n'enregistre ni la date de génération ni la
version de Matplotlib. Les valeurs restent traçables par les empreintes des sources.

---

## 3. Cohérence du README et du manifeste avec les rapports sources

Vérification faite par script (comparaison exacte des nombres, pas seulement à 6 décimales) :

| Contrôle | Résultat |
|---|---|
| SHA-256 des deux sources dans le manifeste = SHA-256 réels des fichiers | OK |
| Contributions A du manifeste = `shap_stability_v2` (`shap_visits`) = `shap_demo_v2` (`shap`) | OK (égalité exacte) |
| Contributions B du manifeste = `shap_stability_v2` (`shap_uniform`) | OK |
| Rangs, classes, drapeaux « constante » | OK |
| Valeurs de référence, sommes des contributions, Δ, erreurs d'additivité | OK |
| Décision (feu −29958, 26941,0 s, 07:29:01) | OK |
| Liste des 12 figures du manifeste = fichiers présents dans le dossier | OK |
| README : préfixes SHA-256, « 22 des 29 », provenance des données | OK |

Seule remarque : la formulation « peu fiables » du README hérite du point P1.

---

## 4. Interprétation scientifique prudente

### Figure 1 — contributions

- **Observé** : avec les visites, `en_mouvement` (+0,52) et `durée_vert` (+0,20) poussent vers « passer », et `file_autre` (−0,45) freine. En uniforme, les trois poussent vers « passer » (+0,81 ; +0,79 ; +0,26). `file_servie` vaut 0 dans les deux méthodes.
- **Hypothèse** : « aucun véhicule en mouvement au vert » est le facteur le plus constant en faveur du changement de phase. Il est au rang 1 dans les deux méthodes, avec le même signe. C'est cohérent avec l'idée qu'un vert inutilisé incite la table à passer, mais cela reste une lecture de la table, pas une preuve causale.
- **Limite** : la contribution nulle de `file_servie` vient de la construction : la variable vaut toujours 0 dans le fond retenu. On ne peut rien conclure sur son effet.

### Figure 2 — classement

- **Observé** : le premier rang (`en_mouvement`) est stable. Les rangs 2 et 3 s'échangent, et `file_autre` change de signe.
- **Hypothèse** : seule la conclusion « en_mouvement est le facteur principal » est robuste au choix de pondération **pour cette décision**.
- **Limite** : le classement par |φ| ne tient pas compte de l'incertitude des valeurs Q ; avec des écarts de cet ordre, les rangs 2 et 3 ne doivent pas être sur-interprétés.

### Figure 3 — additivité

- **Observé** : les deux méthodes reconstituent exactement le même Δ (erreur 0). La valeur de référence passe de 2,90 (visites) à 1,31 (uniforme), et la somme des contributions de 0,27 à 1,86.
- **Interprétation** : avec les visites, Δ de cette décision n'est que légèrement au-dessus du Δ moyen de ce feu et de cette phase (+0,27 sur 3,17). La table est donc *déjà* globalement favorable au changement de phase dans ce contexte, et l'état précis n'ajoute qu'un petit écart. En uniforme, la référence est plus basse, donc l'écart « à expliquer » est plus grand.
- **Limite** : l'additivité est une propriété mathématique de la méthode. Elle prouve que le calcul est exact, **pas** que l'explication est juste ou utile.

---

## 5. Pourquoi `file_autre` change de signe

### 5.1 Principe

Une contribution SHAP répond à la question : *« par rapport aux situations de référence, que change le fait
que file_autre vaille 6–10 ? »*. Si la référence contient surtout des situations où `file_autre` est **plus
grand**, la valeur 6–10 paraît « faible » ; si elle contient surtout des situations où il est **plus petit**,
6–10 paraît « élevé ». Le signe dépend donc de la référence, pas seulement de la table.

### 5.2 Ce que fait la table le long de `file_autre` (autres variables fixées à l'état expliqué)

| file_autre | Δ = Q(passer) − Q(garder) | visites garder / passer | fiable ? |
|---|---|---|---|
| 0 | +0,074424 | 79 / 1 | non |
| 1–2 | −0,359475 | 1 / 43 | non |
| 3–5 | +0,198613 | 11 / 56 | oui |
| **6–10 (état expliqué)** | **+3,170026** | 10 / 79 | oui |
| > 10 | +3,793980 | 106 / 697 | oui |

Sur les états **fiables**, Δ augmente avec `file_autre` (0,20 → 3,17 → 3,79). Autrement dit, plus il y a de
véhicules arrêtés sur l'autre phase, plus la table veut changer. 6–10 est nettement au-dessus de 3–5, mais un
peu en dessous de « > 10 ». Ce tableau n'est qu'une coupe (les trois autres variables sont fixées) ; SHAP fait
la moyenne sur d'autres combinaisons.

### 5.3 Décomposition exacte de la contribution de `file_autre`

La valeur SHAP exacte est une moyenne pondérée de contributions calculées avec **un seul** état de fond à la
fois. On peut donc la découper selon la classe de `file_autre` dans le fond. La reconstruction reproduit les
deux valeurs publiées à 1e-12 près.

| Classe de file_autre dans le fond | États (dont fiables) | Poids A (visites) | Poids B (uniforme) | Part de φ en A | Part de φ en B |
|---|---|---|---|---|---|
| 0 | 3 (0) | 7,2 % | 10,3 % | +0,174912 | +0,237766 |
| 1–2 | 5 (0) | 3,3 % | 17,2 % | +0,103687 | +0,381087 |
| 3–5 | 5 (1) | 5,2 % | 17,2 % | +0,135244 | +0,293220 |
| 6–10 | 8 (1) | 7,9 % | 27,6 % | 0 | 0 |
| > 10 | 8 (5) | **76,4 %** | **27,6 %** | **−0,861842** | **−0,651638** |
| **Total** | 29 (7) | 100 % | 100 % | **−0,447999** | **+0,260435** |

**Lecture** :
- Les situations de fond « > 10 » tirent la contribution vers le négatif dans les deux méthodes, car 6–10 est *moins* que la référence.
- Les situations « 0 à 5 » la tirent vers le positif, car 6–10 est *plus* que la référence.
- Avec les visites, « > 10 » pèse 76 % et l'emporte : le signe est négatif. En uniforme, « 0 à 5 » pèse 45 % contre 28 % pour « > 10 » : le signe devient positif.

**Point de prudence important** : aucune des 8 situations de fond des classes 0 et 1–2 n'est fiable.
Découpage selon la fiabilité :

| Partie du fond | Part de φ(file_autre) en A | Part en B |
|---|---|---|
| 7 états fiables | −0,564012 | −0,138506 |
| 22 états peu fiables | +0,116013 | +0,398941 |

En uniforme, le signe positif vient **des états peu fiables**. Le résultat de la méthode B est donc fragile, et
la pondération par visites, qui suit ce que l'agent a réellement rencontré, reste la référence la plus défendable.
Ce n'est pas pour autant une « vérité » : c'est un choix de fond.

---

## 6. Pourquoi la décision Q-learning ne change pas

1. La décision a été prise **pendant la simulation** par le contrôleur, à partir des deux valeurs Q de l'état
   `-29958|1|0|3|0|0` : Q(garder) = −4,650686, Q(passer) = −1,480660, donc Δ = +3,170026 > 0. L'état est de
   confiance (10 et 79 essais, valeurs différentes), donc l'action est « passer ».
2. SHAP est calculé **après coup**, sur la table gelée, sans rien y modifier. Les deux méthodes lisent les
   mêmes valeurs Q ; seule la pondération des situations de référence change.
3. Les deux explications additionnent exactement au même Δ (figure 3). Ce qui change, c'est la question posée :
   « pourquoi Δ est-il différent du Δ moyen **de cette référence** ? ». Avec deux références différentes, on
   obtient deux réponses différentes au même fait.
4. Une contribution négative ne veut pas dire « cette variable a poussé l'agent à garder la phase ». Elle veut
   dire « par rapport à la référence, cette valeur rend Δ un peu moins grand ». Ici Δ reste très positif.

Formulation proposée pour le rapport :
> *Le changement de signe de la contribution de `file_autre` ne traduit pas un changement de décision, mais un
> changement de point de comparaison : la valeur 6–10 est inférieure à la situation de référence la plus
> fréquente (> 10) et supérieure aux situations rares (0–5).*

---

## 7. Limites

**États peu fiables (22 sur 29)**
- Les 22 états sont peu fiables parce qu'une des deux actions y a été essayée moins de 3 fois (aucun cas de valeurs Q égales). Exemples parmi les plus lourds : [0,0,0,0] (79 / 1), [0,1,0,0] (1 / 43), [0,4,2,1] (39 / 1), [0,4,3,0] (22 / 0).
- Ils pèsent 18,9 % du poids en A, mais 75,9 % en B. Pour les évaluations hybrides (464 au total, dont 238 peu fiables), la part pondérée peu fiable est de 17,0 % en A et de 51,3 % en B.
- Les valeurs peu fiables sont utilisées telles quelles : rien n'est inventé ni remplacé, mais elles rendent les contributions incertaines, surtout en B.

**Choix du fond de référence**
- Le fond est formé des états de la table pour le même feu et la même phase verte. Il reflète la distribution d'entraînement (demande ×5, graines 101–126), alors que la décision expliquée vient d'un run à demande ×1 : les situations typiques peuvent différer.
- 7 des 36 états du fond sont exclus (poids 15 sur 1703), parce que certains états hybrides n'existent pas dans la table. Cette exclusion est faible, mais elle n'est pas neutre.
- Le SHAP interventionnel combine des valeurs de l'état expliqué et du fond. Il crée des situations hybrides qui n'ont pas toujours été observées, et 238 des 464 évaluations sont peu fiables.
- Seules deux pondérations ont été testées : visites et uniforme.

**Une seule décision**
- Un feu, un instant, un état. On ne peut pas généraliser le classement des variables ni la sensibilité observée.
- Le run ×1 contient 259 décisions apprises vérifiables, mais seulement **32 états distincts**. Comme un même état donne exactement la même explication, l'échantillon effectif est de 32 et non de 259.

**Autres limites**
- Les variables sont des classes (intervalles), pas des comptages exacts.
- SHAP décrit la **sortie de la table Q**, pas un effet causal sur le trafic, et ne dit rien de la qualité de la politique.
- Le partage des interactions entre variables suit la règle de Shapley (partage égal). C'est une convention, pas une propriété du trafic.
- Toutes les données sont simulées (SUMO, scénario LuST Kirchberg).

---

## 8. Plan de validation sur plusieurs décisions réelles (proposition, non exécutée)

**Contraintes respectées** : pas de SUMO, pas de réentraînement, pas de modification des contrôleurs, de la
table Q, de `shap_qtable.py` ni de `shap_stability.py`. Lecture seule des fichiers existants.

### 8.1 Données disponibles (pré-vérification faite en lecture seule)

| Run S3 | Lignes | Colonne `explanation` | Utilisable |
|---|---|---|---|
| `20261012_180949_S3_rl_qlearning_x5_seed22` | 68 | non | **non** (état non journalisé) |
| `20261012_181128_S3_rl_qlearning_x5_seed22` | 68 | non | **non** |
| `20261022_141518_S3_rl_qlearning_x1_seed1_ambulance_prio` | 613 | oui | oui |

Dans le run ×1 :
- 259 décisions sont prises par la table apprise et **vérifiées** : leurs valeurs Q et leurs visites journalisées correspondent à la table gelée.
- Les autres lignes sont 277 + 3 décisions de la règle de secours S2 (non explicables par la table) et 74 changements forcés par le vert maximal.
- Les 259 décisions apprises correspondent à **32 états distincts** et se répartissent par feu ainsi : −20484 : 97, −23354 : 71, −29958 : 50, −28692 : 41.

Les explications de ces décisions **n'ont pas été calculées** dans cette revue.

### 8.2 Protocole (à figer avant d'exécuter)

1. **Liste des cas.** Extraire les 259 décisions, les regrouper par état distinct (feu, phase, état), garder le nombre de décisions par état, et journaliser chaque exclusion avec sa raison.
2. **Méthodes, pour chaque état distinct :**
   - A : pondération par visites (méthode actuelle).
   - B : pondération uniforme (mêmes états retenus).
   - C : fond restreint aux états **fiables** (nouvelle variante), seulement si au moins 5 états sont retenus ; sinon, noter « non calculable ».
   - D : stabilité de A par rééchantillonnage du fond (bootstrap : 200 tirages, probabilité proportionnelle aux visites, graine fixée), pour obtenir un taux de stabilité du signe par variable.
3. **Mesures, pour chaque état :**
   - signe de chaque variable informative ;
   - variable de rang 1 ;
   - corrélation de rangs (Kendall) entre méthodes ;
   - écart maximal relatif à Σ|φ_A| ;
   - nombre d'états retenus et exclus ;
   - part peu fiable ;
   - variables constantes.
4. **Critère fixé à l'avance.** Une explication est « stable » si toutes les variables non constantes et non négligeables (|φ| ≥ 5 % de Σ|φ_A|) gardent le même signe en A, B et C, et si la variable de rang 1 est la même. Le seuil de 5 % est une convention, à justifier dans le rapport.
5. **Contrôle de cohérence locale.** Pour chaque variable, comparer le signe de φ_A au sens de variation de Δ entre l'état expliqué et les états voisins **fiables** (même méthode que le tableau du § 5.2). Signaler les désaccords.
6. **Agrégation descriptive.** Calculer la proportion d'états stables, sans pondération et pondérée par le nombre de décisions, par feu et au total. Pas de test statistique ni de p-valeur : les décisions viennent d'un seul run et d'une seule graine, donc elles ne sont pas indépendantes.
7. **Contrôles à chaque calcul.**
   - Additivité (tolérance 1e-9).
   - Valeurs journalisées égales à la table.
   - Empreintes et dates des fichiers d'entrée inchangées.
   - Résultats écrits dans un nouveau dossier (par exemple `docs/shap_multi_decision_v1`), jamais écrasé.
8. **Rapport.**
   - Tableaux par feu, liste des cas instables avec leur cause probable (part peu fiable, fond réduit, variable constante).
   - Tous les résultats sont publiés, y compris défavorables.
   - Les conclusions sont limitées au run ×1 et à la table gelée.
9. **Mise en œuvre.** Un nouveau module (par exemple `agents/xai/shap_multi_decision.py`), testé d'abord sur des tables artificielles à résultat connu, réutilisant `exact_shapley_delta`, `compare_weightings`, `check_learned_decision` et `verify_logged_values` sans les modifier. À faire seulement après votre accord.

### 8.3 Ce que ce plan ne pourra pas dire

- Si les explications restent valables pour d'autres demandes, d'autres graines ou d'autres scénarios (il faudrait de nouveaux runs SUMO).
- Si les décisions de la table sont *bonnes* pour le trafic : c'est une question de performance, pas d'explicabilité.
- Rien sur les décisions de la règle de secours S2 ni sur les décisions « garder », qui ne sont pas journalisées.

---

## 9. Conclusion de la revue

- Les figures sont **correctes et fidèles aux données** ; 8 remarques mineures de présentation sont listées sans avoir été corrigées.
- Le calcul SHAP est **exact** (additivité vérifiée), et la méthode A reproduit l'explication publiée.
- L'explication de **cette** décision est **sensible à la pondération** du fond. Seul le rôle principal de `en_mouvement` est stable. Cette sensibilité est un **résultat à interpréter**, pas une erreur du modèle : elle vient du choix de la référence, et en uniforme elle est amplifiée par des états peu fiables.
- Recommandation : garder la pondération par visites comme méthode principale, présenter la méthode uniforme comme analyse de sensibilité, et ne pas généraliser avant la validation multi-décisions du § 8.

---

## 10. Reproduction

Depuis la racine du projet :
```
python docs\shap_scientific_review_v1\review_computations.py docs\shap_scientific_review_v1\review_computations_rerun.json
```
Le script refuse d'écraser un fichier existant, d'où le nom `_rerun`. Il recalcule la décomposition du § 5, la
coupe du § 5.2, les causes de non-fiabilité du § 7 et le décompte du § 8.1. Il vérifie que les fichiers
d'entrée ne sont pas modifiés. Dans le conteneur de revue, la seconde exécution a donné un fichier identique
octet par octet au premier.
