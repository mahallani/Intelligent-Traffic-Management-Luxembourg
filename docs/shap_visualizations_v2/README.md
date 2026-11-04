# Figures XAI (SHAP) — S3, feu -29958, 07:29:01

Générées par `python -m agents.xai.shap_figures` à partir de :
- `docs/shap_demo_v2/shap_result.json` (SHA-256 `758ce0c983975241…`)
- `docs/shap_stability_v2/shap_stability.json` (SHA-256 `2c341ace852df2c4…`)

Les valeurs ne sont pas recopiées à la main : elles sont lues dans ces fichiers, contrôlées
(cohérence des deux rapports, additivité, rangs), puis relues dans les graphiques avant l'export.
Les valeurs exactes tracées sont dans `figures_manifest.json`.

| Figure | Contenu |
|---|---|
| `fig1_shap_contributions_*` | contributions signées des 4 variables, méthode A (visites) à côté de la méthode B (uniforme) |
| `fig2_shap_ranking_*` | rang de chaque variable selon \|contribution\| dans chaque méthode |
| `fig3_shap_additivity_*` | valeur de référence + somme des contributions = Δ commun, pour chaque méthode |

Suffixe `_fr` / `_en` : langue des libellés. Formats PNG (200 dpi) et PDF (vectoriel).

À lire avec les limites du rapport de stabilité : une seule décision, 22 des 29 états
retenus ont des valeurs Q peu fiables, `file_servie` est constante dans le fond retenu
(contribution nulle par construction, ce qui ne prouve pas l'absence d'effet), et SHAP
décrit la sortie de la table Q, pas un effet causal sur le trafic.
Données : simulation SUMO (SIMULATED_sumo_lust_kirchberg_4tls).
