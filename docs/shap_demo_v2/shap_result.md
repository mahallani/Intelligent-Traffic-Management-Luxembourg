# Explication SHAP exacte – décision réelle de S3 (07:29:01, feu -29958) – SIMULÉ

- Modèle expliqué : tabular Q-learning (S3), frozen table (`qtable_v4_FROZEN_ep26_eval.json`)
- Sortie expliquée : delta = Q(passer) - Q(garder)  (> 0: the table prefers to change the phase)
- Méthode : exact interventional Shapley values (2^4 coalitions per background state, no sampling); signal and green phase fixed; background = states of the same signal and phase in the table, weighted by visits
- Décision : run `20261022_141518_S3_rl_qlearning_x1_seed1_ambulance_prio`, source « table apprise », phase 2 → 3
- Q(garder) = -4.650686, Q(passer) = -1.480660 (journal : -4.651 / -1.481), visites [10, 79]

| Variable | Classe observée | Contribution SHAP à Δ |
|---|---|---|
| véhicules arrêtés sur les voies au vert | 0 | +0.000000 (*) |
| véhicules arrêtés sur une autre phase | 6–10 | -0.447999 |
| véhicules en mouvement au vert | 0 | +0.520247 |
| durée du vert écoulée | ≤ 10 s | +0.202498 |

(*) Variable constante dans le fond retenu : contribution nulle par construction, ce n'est PAS la preuve que la variable est sans effet.

- Valeur de référence (Δ moyen du fond retenu) : +2.895279
- Somme des contributions : +0.274747
- Référence + somme = +3.170026 ; Δ = +3.170026 ; écart = 0.00e+00 (tolérance 1e-09)
- Fond : 36 états, 29 retenus, 7 exclus (état mélangé absent de la table) ; 22 états retenus peu fiables ; 238/464 évaluations peu fiables (17.0 % en poids)

## Limites

- SHAP describes how the variables moved the OUTPUT OF THE TABLE (delta), not a causal effect on traffic.
- Background = training distribution of the table (demand x5); the explained decision comes from a x1 run.
- Variables are classes (bins), not exact vehicle counts.
- A variable that is constant in the retained background gets 0 by construction (see 'warning').
- Some table values used in the calculation are unreliable (fewer than 3 visits): their share is reported.
- Only decisions taken by the learned table can be explained this way (not the fallback rule S2, not safety rules, not 'keep' decisions, which are not logged).
