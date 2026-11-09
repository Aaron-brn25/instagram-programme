# Publieur Instagram

Publie à l'heure prévue des Reels Instagram programmés à l'avance, par l'API officielle de Meta
(qui ne sait pas programmer Instagram elle-même). Tourne sur GitHub Actions toutes les 10 minutes.

- `file/<chaine>__<id>.json` : Reels en attente (heure en UTC, légende, noms des fichiers).
- Release `file` : vidéos et miniatures en attente, retirées une fois publiées.
- `journal.log` : chaque publication ; `echecs/` : Reels non publiés dans les 2 h (le passage échoue et GitHub prévient par e-mail).
- Secret `META_JETONS` : jetons de Page, jamais dans le dépôt.

Source : dépôt privé Tiktok, `moteur_commun/github_ig/` et `moteur_commun/meta_api.py`. Ne pas modifier ici :
corriger là-bas puis `meta.py deployer`.
