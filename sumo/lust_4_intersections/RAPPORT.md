# Rapport : scénario LuST réduit à 4 carrefours à feux (Kirchberg)

Environnement de référence : SUMO 1.27.1, LuST (dépôt `lcodeca/LuSTScenario`, fichiers identiques à ceux du projet). Tous les résultats ci-dessous ont été **exécutés** (`scripts/validate_scenario.py`, `tests/test_kirchberg_scenario.py`). Rapport brut : `docs/validation_report.json`.

---

## 1. Kirchberg est-il identifiable dans LuST ?

**Oui, avec un niveau de confiance élevé.** Une limite : LuST ne contient **aucun nom de rue** (`getStreetName` est vide, les arêtes portent des identifiants numériques). L'identification repose donc sur trois indices indépendants, vérifiés dans `lust.net.xml` (projection UTM 32, conversion en lon/lat via `sumolib`) :

| Indice | Référence externe | Mesure dans LuST | Résultat |
|---|---|---|---|
| Pont Grande-Duchesse Charlotte | 49,61778 N, 6,13083 E, 355 m, 4 voies ([Wikipedia](https://en.wikipedia.org/wiki/Grand_Duchess_Charlotte_Bridge)) | arête `-30620`, type `highway.primary.bridge`, milieu à 49,61783 N, 6,13239 E | **à 112 m** |
| Avenue J.F. Kennedy | axe central de Kirchberg, ~3,5 km, du pont vers le NE ([Wikipedia](https://en.wikipedia.org/wiki/Kirchberg,_Luxembourg)) | depuis l'extrémité est du pont, route continue `31070#0…9` (2×2 voies, 2,5 km + pont 0,9 km), orientée SO→NE, 7 feux | géométrie conforme |
| Centre de Kirchberg | 49,627869 N, 6,153422 E ([Wikipedia](https://en.wikipedia.org/wiki/Kirchberg,_Luxembourg)) | feu `-29958` de cette route à **50 m** du centroïde | conforme |
| Jonction N51 / A1 au NE | la N51 (avenue Kennedy) rejoint l'A1 ([AARoads](https://wiki.aaroads.com/wiki/N51_(Luxembourg))) | 1,3 km après l'extrémité NE de la route : première bretelle autoroutière (49,6357 N, 6,1773 E) | conforme |

Conclusion : la route `31070` est l'avenue J.F. Kennedy, déduite de la géométrie et non lue dans un nom. Les 4 feux retenus sont sur cette avenue, au cœur de Kirchberg.

---

## 2. Choix des 4 carrefours

L'avenue porte 7 feux consécutifs (`-12, -14384, -28692, -23354, -20484, -29958, -13608, -11042`). J'ai comparé 4 fenêtres de 4 feux consécutifs avec des critères mesurés :

| Fenêtre | Feux | Exactement 4 feux dans la zone ? | Détours évitant l'avenue (paires de feux) / maillage | Trafic 07–08 h (véh. distincts) |
|---|---|---|---|---|
| A | -14384…-20484 | oui avec une marge de 150 m | 4 / 12 (31 arêtes fortement connexes) | 663 |
| **B (retenue)** | **-28692, -23354, -20484, -29958** | **oui avec une marge de 250 m** | **9 / 12 (59 arêtes fortement connexes)** | 544 |
| C | -23354…-13608 | non au-delà de 150 m (5e feu) | non calculé ; maillage quasi nul (4 arêtes fortement connexes à 150 m) | non mesuré |
| D | -20484…-11042 | non au-delà de 80 m (5e et 6e feux) | aucun possible (1 seule arête fortement connexe à 80 m) | 318 |

B est la seule fenêtre qui garde exactement 4 feux tout en incluant un maillage de rues secondaires. C'est ce maillage qui rend S2 (réorientation) possible.

### Les 4 intersections

| Feu (ID SUMO) | Coordonnées | Branches | Phases / cycle | Liens contrôlés | Rue transversale | Véhicules passés (×1, 07–08 h) |
|---|---|---|---|---|---|---|
| `-28692` | 49,62464 N ; 6,14538 E | 4 | 8 / 96 s | 14 | `30444` (tertiaire, bus) + `32010` (résidentielle) | 322 |
| `-23354` | 49,62568 N ; 6,14777 E | 3 (T, sortie seule) | 4 / 68 s | 6 | `32864` (sortie vers arrêt 645) | 162 |
| `-20484` | 49,62706 N ; 6,15105 E | 3 | 6 / 82 s | 8 | `31080` (résidentielle) | 154 |
| `-29958` | 49,62822 N ; 6,15385 E | 3 | 6 / 82 s | 8 | `30596` (secondaire) | 400 |

Distances entre feux : 194 m, 273 m, 229 m. Tous les programmes sont ceux de LuST : `type="actuated"`, programID `0`, phases et liens **identiques à l'original** (test T2).

---

## 3. Routes conservées et méthode d'extraction

**73 arêtes, 12,6 km de voies, 114 voies, 33 nœuds** (liste : `net/keep_edges.txt`).

| Type | Arêtes | Longueur |
|---|---|---|
| secondaire | 12 | 2,4 km |
| tertiaire (dont avenue) | 23 | 3,5 km |
| résidentielle | 38 | 6,6 km |

- **Voie principale** : avenue J.F. Kennedy, segments `31070#4` à `#8` dans les deux sens (1,3 km), 2 voies par sens.
- **Voies secondaires** : `30444`, `30730`, `30874`, `32010`, `32864`, `31080` (rues au sud et au nord) et la route secondaire `30596`/`31800`, qui forme une boucle au nord.
- **Frontière** : 4 nœuds d'entrée/sortie (`-14384`, `-13608` aux deux bouts de l'avenue ; `-14334`, `-14492`). Les feux voisins `-14384` et `-13608` sont devenus de simples nœuds d'extrémité (`--tls.unset`).

**Extraction** : `netconvert -s lust.net.xml --keep-edges.input-file keep_edges.txt --tls.unset=-14384,-13608 --remove-edges.isolated --keep-edges.components 1`. La liste d'arêtes = arêtes entièrement dans la boîte (marge 250 m) + **toutes** les branches des 4 feux (sinon netconvert régénère leurs programmes) + la boucle secondaire `30596#0/1`, `31800`. Cette boucle ramenait les trajets « déconnectés » de 315 à 22. Aucune route orpheline : une seule composante connexe.

**Routes (trafic réel).**
1. Run LuST complet 07:00→08:30 à partir de l'état de 07:00, avec `--vehroute-output.exit-times`.
2. Découpage par `cutRoutes.py` (outil SUMO).
3. Recalcul indépendant de l'heure réelle d'entrée de chaque véhicule dans la zone.
4. Conservation des entrées entre 07:00 et 08:00.

**Problème trouvé et corrigé :** `cutRoutes.py` perd les temps de sortie des véhicules re-routés (70 % des véhicules LuST ont le rerouting). Il retombe alors silencieusement sur l'heure de départ d'origine, parfois plusieurs dizaines de minutes trop tôt. `build_scenario.py` aplatit d'abord les routes (dernière route + ses temps) ; ensuite, la vérification indépendante ne trouve plus aucun écart (0 correction sur 778). Véhicules écartés : 199 dont l'entrée est inconnue (avant 07:00 ou après 08:30) et 471 hors fenêtre.

Entrées/sorties par la frontière : `departPos="base"`, `departSpeed="max"`, `arrivalPos="max"`.

---

## 4. Bus

**Conservés et valides.** Les 5 lignes LuST qui traversent la zone entre 07:00 et 08:00 sont `AVL---_7, _12, _13, _18, _25`, soit 19 bus (la ligne `CN_4` passe hors de cette heure). Les **11 arrêts LuST** de la zone sont conservés avec leurs positions d'origine :
- sur l'avenue : 260/261, 634/635, 454/455 ;
- sur les rues transversales : 171/172, 285/286, 645.

Test T6 : les 19 bus effectuent **54 arrêts**, desservent les 11 arrêts, avec un temps d'arrêt moyen de 20,0 s (la valeur LuST). Les événements détectés par la couche TraCI (54) sont identiques à la sortie `--stop-output` de SUMO (54).

---

## 5. Résultats des tests (exécutés, SUMO 1.27.1)

| Test | Résultat | Mesures |
|---|---|---|
| T1 le réseau se charge dans SUMO | **PASS** | 73 arêtes, 33 nœuds, aucune erreur |
| T2 nombre et identifiants des feux | **PASS** | exactement 4 : `-20484, -23354, -28692, -29958` ; programmes et liens identiques à LuST |
| T3 connexions et itinéraires | **PASS** | 778 routes, 0 lien rompu ; 11 arrêts sur des voies existantes |
| T4 démarrage et progression | **PASS** | 07:00→08:00, 778 insérés, 752 arrivés, 0 téléportation, 0 collision ; 9,6 s avec TraCI + collecte |
| T5 véhicules dans la zone | **PASS** | véhicules passés par chaque feu : 322 / 162 / 154 / 400 |
| T6 bus et arrêts | **PASS** | 19 bus, 5 lignes, 54 arrêts, 11 arrêts desservis |
| T7 lecture et contrôle des feux par TraCI | **PASS** | sur les 4 feux : lecture état/phase/programme/temps restant + `setPhase`, `setPhaseDuration`, `setRedYellowGreenState`, `setProgram`, `setProgramLogic` |
| T8 mesures | **PASS** | voir ci-dessous |
| Tests pytest du projet | **38 / 38 PASS** | dont 4 pour ce scénario |
| SUMO-GUI | chargé sans erreur (écran virtuel) | capture : `docs/sumo_gui_0710_scale5.png` |

**Mesures (trafic réel, ×1, 07:00–08:00)** : temps de parcours moyen dans la zone 99,8 s ; attente moyenne 19,0 s par véhicule (14 814 s au total) ; vitesse moyenne 35,6 km/h ; file totale moyenne aux feux 32,8 m, plus longue file d'une voie 37 m ; CO2 208 kg.

### Faisabilité des stratégies (demande ×5, ambulance à 07:20 sur l'avenue)

| Stratégie | Ce qui a été fait | Résultat mesuré |
|---|---|---|
| S0 aucune intervention | programmes LuST | parcours 134,9 s, attente 155 476 s, ambulance 159 s |
| S1 stratégie des feux | `setProgramLogic` : vert de l'avenue ×1,5 | effet réel mais faible (attente 155 129 s, files moyennes 245→206 m). Ce n'est qu'un exemple non optimisé |
| S2 réorientation | incident 07:15–07:35 (une voie fermée + 7 km/h) ; `rerouteTraveltime` | **80 itinéraires changés** sur 121 réévaluations ; attente 166 274 s sans réorientation → 157 601 s avec |
| S3 priorité urgence | `getNextTLS` + `setPhase` à 150 m | ambulance **159 s → 105 s** |

**Mise en garde sur S3 (vérifiée)** :
- Le saut de phase décale durablement le cycle du feu `-29958` (à 07:46 il est en phase 4 au lieu de 0 sans intervention), et une prolongation de vert décale `-20484`.
- La baisse d'attente générale observée en S3 (−7 %) vient donc en partie de ce décalage, pas de la priorité elle-même.
- La démonstration passe aussi au vert sans phase jaune.
- Une vraie stratégie S3 (agent RL) doit insérer le jaune et resynchroniser le cycle.

---

## 6. Limites

- **Trafic modéré à la demande réelle.** LuST génère 60–220 véh/h par sens sur l'avenue à la pointe : pas de congestion à ×1. Utiliser `--scale 5` à `6` pour la congestion (tableau dans le README).
- **Zone vide à 07:00** : les véhicules déjà présents dans la zone à 07:00 ne sont pas reproduits. Remplissage en ~2 min ; ignorer les 300 premières secondes.
- **Interactions aux frontières** : les remontées de file au-delà des 4 points d'entrée ne sont pas simulées. Un véhicule qui ne peut pas entrer attend (« bloqués à l'entrée »).
- **`-23354`** est un T avec une sortie seule (4 phases) : c'est le feu le moins riche des quatre, mais il fait partie de la seule séquence de 4 feux consécutifs qui offre des détours.
- **Nom de rue** : « avenue J.F. Kennedy » est une identification géométrique (§1), pas une donnée LuST.

---

## Sources

- [Kirchberg, Luxembourg (Wikipedia)](https://en.wikipedia.org/wiki/Kirchberg,_Luxembourg)
- [Grand Duchess Charlotte Bridge (Wikipedia)](https://en.wikipedia.org/wiki/Grand_Duchess_Charlotte_Bridge)
- [N51 (Luxembourg), AARoads](https://wiki.aaroads.com/wiki/N51_(Luxembourg))
- LuST : https://github.com/lcodeca/LuSTScenario
