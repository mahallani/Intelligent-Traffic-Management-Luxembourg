# Étude SHAP multi-décision — comment reproduire (Windows)

Module : `agents/xai/shap_multi_decision.py` · tests : `tests/test_xai_shap_multi_decision.py`.
Lecture seule : table Q gelée et `decisions.csv` des runs S3 existants. Aucune simulation, aucun entraînement.

Depuis la racine du projet (`C:\Users\ASUS\Intelligent-Traffic-Management-Luxembourg`) :

```
python -m pytest tests\test_xai_shap.py tests\test_xai_shap_stability.py tests\test_xai_shap_figures.py tests\test_xai_shap_multi_decision.py -v -ra
python -m agents.xai.shap_multi_decision --out docs\shap_multi_decision_v2
```

Le dossier de sortie ne doit pas exister (code de sortie 2 sinon) ; si un contrôle du protocole échoue,
rien n'est écrit (code 1). Contenu produit :

| Fichier | Contenu |
|---|---|
| `cases.csv` | chaque décision retenue et son état |
| `exclusions.csv` | chaque ligne exclue et son motif |
| `per_state.csv` / `per_state.json` | contributions des fonds A, B, C et mesures, par état distinct |
| `summary.json` | protocole, entrées (SHA-256), exclusions, agrégats |
| `REPORT.md` | rapport lisible |

Séparateur CSV : `;` (comme les journaux du projet), encodage UTF-8.
