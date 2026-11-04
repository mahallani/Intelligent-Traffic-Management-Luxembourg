# Démo XAI – décisions réelles au Carrefour 4 (SIMULÉ)

Run : `app_runs/20261022_141518_S3_rl_qlearning_x1_seed1_ambulance_prio` – S3_rl_qlearning, demande ×1, graine 1, backend traci.

| | Heure | Source | Observé | Raison enregistrée | Action |
|---|---|---|---|---|---|
| A | 07:28:41 | Agent RL – table apprise | Arrêtés sur la voie au vert : 0; En mouvement au vert : > 5; Attente sur une autre phase : 1–2; Vert depuis : 21–40 s | Table apprise : « passer » coûte moins (quasi-égalité) Situation déjà vue 40 fois (garder) / 9 fois (passer) Q(garder)=-0.664, Q(passer)=-0.616. | phase 4 → 5 |
| B | 07:28:51 | Règle de secours S2 | Arrêtés sur la voie au vert : 0; En mouvement au vert : 0; Attente sur une autre phase : 3; Vert depuis : ≤ 10 s | Table non fiable ici (vue 2 / 26 fois, minimum 3) → règle S2 : ≤ 1 arrêté, ≤ 2 en mouvement, attente ailleurs Q(garder)=-0.159, Q(passer)=-3.703. | phase 0 → 1 |
| C | 07:29:01 | Agent RL – table apprise | Arrêtés sur la voie au vert : 0; En mouvement au vert : 0; Attente sur une autre phase : 6–10; Vert depuis : ≤ 10 s | Table apprise : « passer » coûte moins (préférence nette) Situation déjà vue 10 fois (garder) / 79 fois (passer) Q(garder)=-4.651, Q(passer)=-1.481. | phase 2 → 3 |

Contrôle de fidélité sur tout le run : 613 décisions journalisées, 0 sans explication, 259 table apprise, 280 règle de secours, 74 sécurité, 0 incohérence(s).

Q = somme actualisée estimée de –(véhicules arrêtés sur toutes les entrées du feu)/10 par relevé de 5 s : plus proche de 0 = moins d'attente prévue.
Limites : seuls les changements de phase sont journalisés (pas les décisions « garder ») ; l'agent RL voit des classes, pas les nombres exacts ; les courbes avant/après sont des observations, pas un effet causal ; aucune explication pour le modèle de prévision.
