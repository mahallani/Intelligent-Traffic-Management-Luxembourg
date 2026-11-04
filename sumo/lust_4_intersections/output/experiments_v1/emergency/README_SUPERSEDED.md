# Dossier remplacé (2026-10-12)

Les runs `S2_demand_gap_*_priority` de ce dossier et `emergency_summary_v1.csv` ont été produits avec un bug :
après la libération d'un feu par le module de priorité urgence, l'actionneur appliquait son maintien de 3600 s
à la phase jaune qui venait d'être posée (phase observée périmée). Le feu restait jaune jusqu'à la fin et le réseau
se bloquait (1 561 arrivées au lieu de 3 706). Les runs S0 et S1 ne sont pas concernés (actionneur inactif) et sont
identiques dans la nouvelle évaluation.

Résultats valides : `../emergency_v2/emergency_summary_v2.csv` (code corrigé, test de non-régression
`tests/test_safety_emergency.py::test_signals_stay_controlled_after_emergency_release`).
Aucun fichier de ce dossier n'a été supprimé ni modifié.
