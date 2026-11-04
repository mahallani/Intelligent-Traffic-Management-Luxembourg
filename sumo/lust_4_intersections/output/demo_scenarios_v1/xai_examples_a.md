# Explications fidèles – B/S3_rl_qlearning_x5_seed61_incident, feu -29958, 07:20:00-07:26:40 (SIMULÉ)

Texte construit uniquement à partir de la colonne `explanation` de decisions.csv. Arrêtés au feu : queue_timeseries.csv. Avant/après = observation, pas un effet causal.

| Heure | Phase → | Vert (s) | Explication enregistrée | Arrêtés au feu t−10 s / t / t+30 s / t+60 s |
|---|---|---|---|---|
| 07:20:01 | 0 → 1 | 20 | Agent RL, table apprise. Observé : phase verte n°0, arrêtés côté vert 1-2, en attente ailleurs >10, en mouvement >5, vert depuis 11-20 s. Q(passer)=-12.26 > Q(garder)=-12.28 (écart 0.026 : quasi-égalité); visites garder/passer = [92, 13] | 17 / 24 / 17 / 19 |
| 07:20:11 | 2 → 3 | 5 | Agent RL, table apprise. Observé : phase verte n°1, arrêtés côté vert 0, en attente ailleurs >10, en mouvement 0, vert depuis <=10 s. Q(passer)=-11.57 > Q(garder)=-15.36 (écart 3.794); visites garder/passer = [106, 697] | 24 / 28 / 14 / 26 |
| 07:21:16 | 4 → 5 | 60 | Règle de sécurité : vert de 60 s = limite 60 s → passage forcé | 23 / 31 / 17 / 12 |
| 07:21:56 | 0 → 1 | 35 | Agent RL, table apprise. Observé : phase verte n°0, arrêtés côté vert 1-2, en attente ailleurs >10, en mouvement >5, vert depuis 21-40 s. Q(passer)=-10.84 > Q(garder)=-10.88 (écart 0.036 : quasi-égalité); visites garder/passer = [71, 13] | 17 / 12 / 19 / 24 |
| 07:22:21 | 2 → 3 | 20 | Règle de sécurité : vert de 20 s = limite 20 s → passage forcé | 13 / 18 / 24 / 27 |
| 07:23:26 | 4 → 5 | 60 | Règle de sécurité : vert de 60 s = limite 60 s → passage forcé | 27 / 24 / 21 / 32 |
| 07:24:31 | 0 → 1 | 60 | Règle de sécurité : vert de 60 s = limite 60 s → passage forcé | 31 / 38 / 51 / 45 |
| 07:24:46 | 2 → 3 | 10 | Agent RL, table apprise. Observé : phase verte n°1, arrêtés côté vert 0, en attente ailleurs >10, en mouvement 1-2, vert depuis <=10 s. Q(passer)=-11.61 > Q(garder)=-16.32 (écart 4.710); visites garder/passer = [59, 106] | 34 / 41 / 41 / 60 |
| 07:24:56 | 4 → 5 | 5 | Agent RL, table apprise. Observé : phase verte n°2, arrêtés côté vert >10, en attente ailleurs >10, en mouvement >5, vert depuis <=10 s. Q(passer)=-10.84 > Q(garder)=-13.00 (écart 2.162); visites garder/passer = [78, 100] | 41 / 52 / 44 / 66 |
| 07:25:26 | 0 → 1 | 25 | Agent RL, table apprise. Observé : phase verte n°0, arrêtés côté vert 1-2, en attente ailleurs >10, en mouvement >5, vert depuis 21-40 s. Q(passer)=-10.84 > Q(garder)=-10.88 (écart 0.036 : quasi-égalité); visites garder/passer = [71, 13] | 41 / 44 / 66 / 76 |
| 07:25:36 | 2 → 3 | 5 | Agent RL, table apprise. Observé : phase verte n°1, arrêtés côté vert 0, en attente ailleurs >10, en mouvement 0, vert depuis <=10 s. Q(passer)=-11.57 > Q(garder)=-15.36 (écart 3.794); visites garder/passer = [106, 697] | 44 / 52 / 74 / 73 |

Seuls les changements de phase sont journalisés : les décisions « garder » ne le sont pas.
