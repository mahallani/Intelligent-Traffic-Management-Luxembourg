# Qualité des données CITA — diagnostic, nettoyage et correction du collecteur (10/10/2026)

Toutes les valeurs ci-dessous ont été produites par les scripts listés en fin de document et vérifiées par exécution.
Aucun fichier de `data/historical` ni de `data/raw` n'a été modifié.

## 1. Défauts trouvés dans la collecte

| Fichier | Script producteur | Défaut (vérifié) | Conséquence |
|---|---|---|---|
| `cita_traffic_historical_fixed.csv` | `collect_cita_fixed.py` (v1) | le « parent » de chaque mesure était la racine du document XML | **1 ligne par route et par horodatage** : position (code ALERT-C, coordonnées) du **premier** capteur de la route + vitesse/occupation/débit/sens du **dernier**. Prouvé en exécutant le code v1 inchangé sur les XML bruts (A4 : position de `A4.RH.12780`, valeurs de `A4.RH.3718`). |
| `cita_traffic_live.csv` | `collect_all_luxembourg.py` | chaque `basicData` lu isolément | lignes « vitesse » et lignes « débit » séparées, sans capteur ni heure de mesure : **inexploitable** |
| `cita_traffic_historical.csv` | `collect_cita.py` | 10 min de collecte, ni capteur ni vitesse | non intégré |
| `cita_events_*.csv` | `collect_cita.py`, `collect_all_luxembourg.py` | identifiants DATEX (`situation id`, `record id/version`) non collectés ; route/type vides en live | identité d'événement **reconstruite** |
| `prepare_cita.py` | — | `sep=";"` forcé | 4 fichiers sur 5 lus comme 1 colonne ; rapports `*_initial_report.json` et `*_combined.csv` de `data/interim` **faux** (non régénérés, non supprimés) |

## 2. Trafic — `data/processed/cita_traffic/cita_traffic_clean.csv`

- Source : `cita_traffic_historical_fixed.csv` (106 808 lignes, séparateur `;`).
- Clé (capteur, horodatage, sens) : **1 875 clés, 0 conflit de valeurs**. 104 933 lignes sont des répétitions **identiques** (relevé toutes les 60 s, mise à jour CITA toutes les 5 min) : regroupées, nombre conservé dans `n_polls` (somme = 106 808).
- **Aucune ligne exclue** (0 horodatage illisible). Anomalies **signalées, non supprimées** : 16 vitesses > 130 km/h, 2 vitesses nulles avec débit > 0 ; 0 occupation hors [0,100], 0 coordonnée hors Luxembourg, 0 débit négatif.
- Fuseaux : `timestamp_original` (texte, +02:00) et `collection_time_original` (horloge locale du PC, sans fuseau) **conservés** ; conversion UTC avec l'hypothèse UTC+1 pour la collecte, confirmée par le décalage mesure → collecte de 2,3 à 7,6 min.
- Colonnes : `vehicle_flow` (vide à 100 %, l'élément XML ne contient jamais de texte) **non reportée** dans `processed`, conservée dans `interim` ; `measurement_site` renommé `measurement_site_alertc` (ce n'est pas un identifiant de capteur).
- Chaque ligne porte `site_attribution_reliable = False`.

### Couverture — pourquoi ces données ne suffisent pas à entraîner un modèle fiable
- Période : 07/10 19:38 → 09/10 10:53 (heure du Luxembourg), soit 39 h ; **269 créneaux de 5 min sur 472 (57 %)**.
- Trous : 22:03 → 10:08 (725 min, nuit du 7 au 8), 18:53 → 23:38 le 8 (285 min), + 2 courts.
- **7 mesures par créneau sur ~247 capteurs disponibles = 2,8 % des mesures**, et **position non fiable**.
- Moins de 2 jours, aucun week-end, aucune journée complète.
- ⇒ Utilisable au mieux comme illustration grossière par route. **Pas** pour un modèle par capteur, spatial ou temporel fiable. Il faut une nouvelle collecte avec le collecteur corrigé.

## 3. Événements — `data/processed/cita_events/cita_events_clean.csv`
- 223 lignes historiques → 19 événements ; 36 402 lignes live → 64 événements, **115 états** (134 avant uniformisation de `True`/`true`).
- Sortie : **134 états** (19 historiques + 115 live) pour **64 événements** ; les versions distinctes sont conservées (`state_index`, `first_seen`, `last_seen`, `n_polls`).
- Correspondances (`data/reports/cita_events_matching.csv`) : 19 **exactes** (sur les 5 champs de la clé) ; 9 **incertaines** (mêmes heures de création et de début, positions différentes : probablement 2 enregistrements d'une même situation). Les incertaines ne servent jamais à compléter des valeurs.
- `road` complétée pour 22 états live **uniquement par correspondance exacte** (colonne `road_provenance`) ; route encore inconnue pour 93 états (69 %), type d'événement inconnu pour 94 %.
- `safety_message` : booléen (115 `True`) ; 19 manquants **restés manquants** (source historique sans cette colonne).
- `impact`, `comment`, `location_description` : vides à 100 %, conservées et documentées.

## 4. Collecteur corrigé — `collect_cita_fixed.py` (parser v2)
- Une ligne par `siteMeasurements` (capteur) : vrai identifiant (`B40.HR.18260`), heure de mesure, vitesse, occupation, débit, position, sens, codes ALERT-C, équipement.
- Tests `tests/test_collect_cita_fixed.py` sur les 7 XML bruts : **8/8 OK** — 247 capteurs par passage (contre 7), valeurs identiques à une lecture XML indépendante, capteurs partiels sans valeur inventée, pas de doublon après une nouvelle interrogation ou un redémarrage, refus d'écrire dans l'ancien fichier.
- Écrit dans un **nouveau** fichier : `data/historical/cita/traffic/cita_traffic_sites_v2.csv` (séparateur `;`). Ancienne version sauvegardée : `collect_cita_fixed.py.bak_20261010`.

### Commandes (PowerShell, racine du projet) — À LANCER SEULEMENT APRÈS VALIDATION
```powershell
python -m unittest tests.test_collect_cita_fixed -v        # tests hors ligne
python collect_cita_fixed.py --once                         # 1 passage réel, puis arrêt
python collect_cita_fixed.py --interval 300                 # collecte continue toutes les 5 min (CTRL+C)
```
Pour un jeu exploitable : au moins **7 jours complets** consécutifs (jours ouvrés + week-end), le PC restant allumé, sans mise en veille.

## 5. Scripts
| Script | Rôle | Écrit dans |
|---|---|---|
| `scripts/data_pipeline/diagnose_cita.py` | diagnostic (lecture seule) | `data/reports/cita_diagnostic.json` |
| `scripts/data_pipeline/prepare_cita.py --check-only` | contrôle de lecture des 5 CSV | rien |
| `scripts/data_pipeline/clean_cita_traffic.py` | nettoyage trafic | `data/interim/cita`, `data/processed/cita_traffic`, `data/reports` |
| `scripts/data_pipeline/clean_cita_events.py` | nettoyage événements | `data/interim/cita`, `data/processed/cita_events`, `data/reports` |
