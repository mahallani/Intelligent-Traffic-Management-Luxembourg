# Contrôle visuel du suivi de l'ambulance dans l'application web – Linux, pas Windows

- 22/10/2026, conteneur Linux, Chromium sans écran (Playwright), même code que le projet (agents, backend, interface construite).
- Réglages : S0, ×5, graine 1, vitesse Rapide, ambulance + priorité, case « Son de sirène » cochée.
- `captures.json` : heure simulée, statut de la simulation, statut de l'ambulance, texte « Sirène : … » affiché, erreurs console (aucune).
- Le texte « Sirène : en cours » / « silencieuse » prouve seulement la logique d'activation. Le son lui-même n'a PAS été écouté (navigateur sans écran ni haut-parleur).
- Rien de cela ne valide le fonctionnement sous Windows (caméra SUMO-GUI, affichage, son) : à vérifier sur le PC.
