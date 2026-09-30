# Fixtures de test

Chaque fixture est un couple `nom.html` (ou `nom.eml`) + `nom.expected.json`. Les tests parcourent
automatiquement tous les couples présents dans `emails/<source>/` et `pages/<source>/`.

**Les fichiers `synthetique_*` sont provisoires** : ils imitent la structure supposée des emails et des pages,
sans garantie. Ils doivent être complétés par de vrais emails d'alerte et de vraies pages, anonymisés
(prénoms, téléphones, emails du vendeur remplacés), avant la mise en production.

Ajouter une fixture réelle :

1. Email : dans Gmail, « Afficher l'original » puis « Télécharger l'original » ; déposer le `.eml` dans
   `emails/leboncoin/` ou `emails/lacentrale/`.
2. Page : ouvrir l'annonce dans le navigateur, « Enregistrer sous » au format HTML (page seule) ; déposer
   le fichier dans `pages/<source>/`.
3. Lancer `uv run python scripts/make_fixture_expectation.py <fichier>` pour générer le `.expected.json`,
   le relire et corriger à la main ce qui est faux : c'est la référence.
