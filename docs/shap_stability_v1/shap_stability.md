# Sensibilité de l'explication SHAP à la pondération du fond – S3, 07:29:01, feu -29958 – SIMULÉ

- Décision : run `20261022_141518_S3_rl_qlearning_x1_seed1_ambulance_prio`, source « table apprise » ; Q(garder) = -4.650686, Q(passer) = -1.480660, Δ = 3.170026
- Fond : 36 états, **29 retenus** (mêmes états pour A et B), 7 exclus ; poids de visites retenu = 1688 ; 22 états retenus peu fiables

| Variable | Classe | A : poids = visites | B : poids uniforme | Écart absolu | Signe A / B | Rang A / B |
|---|---|---|---|---|---|---|
| véhicules arrêtés sur les voies au vert (*) | 0 | +0.000000 | +0.000000 | 0.000000 | 0 / 0 | 4 / 4 |
| véhicules arrêtés sur une autre phase | 6–10 | -0.447999 | +0.260435 | 0.708434 | - / + | 2 / 3 |
| véhicules en mouvement au vert | 0 | +0.520247 | +0.805710 | 0.285463 | + / + | 1 / 1 |
| durée du vert écoulée | ≤ 10 s | +0.202498 | +0.793159 | 0.590661 | + / + | 3 / 2 |

(*) constante dans le fond retenu : 0 par construction dans les deux méthodes, ce n'est pas la preuve d'une absence d'effet.

| | A : visites | B : uniforme |
|---|---|---|
| Valeur de référence | +2.895279 | +1.310722 |
| Somme des contributions | +0.274747 | +1.859304 |
| Référence + somme | +3.170026 | +3.170026 |
| Δ expliqué | +3.170026 | +3.170026 |
| Erreur d'additivité | 0.00e+00 | 0.00e+00 |
| Part pondérée d'évaluations peu fiables | 17.0 % | 51.3 % |

- Mêmes signes : False ; même classement : False ; écart maximal : 0.708434 (60.5 % de la somme des |contributions| de A)
- Contrôles : l'ensemble retenu reproduit exactement l'explication par défaut de `shap_qtable` ; additivité ≤ 1e-09 dans les deux méthodes : True

**Conclusion :** Sensible à la pondération : au moins un signe change et le classement des variables change (écart maximal 0.708434).

## Limites

- Only the weights of the SAME 29 retained states change; other backgrounds (other runs, other demand) are not tested.
- A variable that is constant in the retained background gets 0 in both methods by construction: this proves nothing about its effect.
- Many retained states are unreliable (fewer than 3 visits); uniform weights give them more influence than visit weights.
- SHAP describes the output of the table, not a causal effect on traffic. One decision only.
