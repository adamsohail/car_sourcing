# Sourcing auto

Repère, parmi les alertes email Leboncoin et La Centrale, les voitures qui dégagent au moins 1 000 € de marge
nette estimée, et les envoie sur Telegram avec trois boutons : Intéressant, Pas intéressant, Acheté.
Une interface web montre les mêmes opportunités, le détail du calcul et le suivi des achats.

Installation : **[docs/INSTALLATION.md](docs/INSTALLATION.md)**.

## Fonctionnement

Toutes les 10 minutes, un job Cloud Run :

1. lit les emails d'alerte non traités du compte Gmail dédié ;
2. extrait les annonces et ignore celles déjà vues (sauf changement de prix) ;
3. ouvre la page de chaque nouvelle annonce, avec 3 à 6 secondes entre deux requêtes. Si la page est
   inaccessible, l'annonce est évaluée avec les seules données de l'email et marquée « détail indisponible » ;
4. applique les filtres du Google Sheet, calcule la cote (médiane des comparables) et la marge ;
5. enregistre tout dans BigQuery, alerte sur Telegram, puis pose le label `traite` sur l'email.

Toutes les annonces sont conservées, filtrées ou non : elles forment la cote de marché.
Un service Cloud Run reçoit les clics Telegram et sert l'interface, protégée par mot de passe.

## Régler l'outil

Tout se règle dans le **Google Sheet**, sans code : onglet `parametres` (seuils, frais, transport, base) et onglet
`mots_cles_exclusion` (un mot-clé par ligne). Les changements sont pris en compte au run suivant. Une valeur
invalide suspend les alertes et envoie une alerte technique qui nomme le champ en cause.

Après 2 à 4 semaines, la page **Suivi** de l'interface aide à ajuster les seuils : entonnoir des annonces, motifs
d'exclusion et remise réellement obtenue à l'achat, à comparer avec la décote de revente.

## Alertes techniques (Telegram, au plus une toutes les 6 h par type)

| Message | Que faire |
| --- | --- |
| Google Sheet invalide | Corriger la valeur indiquée dans le Sheet. |
| Échecs de parsing au-delà de 20 % | Un site a changé le format de ses emails ou pages : ajouter l'email en fixture (voir l'installation, étape 10) et adapter le parser. Les emails illisibles portent le label `erreur_parsing`. |
| Aucun email depuis 24 h | Vérifier que les alertes Leboncoin et La Centrale sont actives et arrivent sur le compte dédié. |
| Run en échec | Lire l'erreur dans Cloud Logging (ressource « Cloud Run Job », `car-sourcing-ingest`). |

## Commandes

```bash
make install          # dépendances et hooks pre-commit
make check            # lint, typage, tests
uv run car-sourcing demo            # interface avec des annonces simulées, mot de passe « demo »
uv run car-sourcing run             # un run d'ingestion (avec un fichier .env, DRY_RUN=true conseillé)
uv run car-sourcing smoke           # vérifie BigQuery, Sheet, Gmail, géocodage et Telegram
uv run car-sourcing test-alert      # envoie une alerte de test
python web/build.py                 # reconstruit l'interface après modification de web/
```

Dans GCP, les mêmes commandes passent par le job : `gcloud run jobs execute car-sourcing-ingest --args=smoke --wait`.

## Structure

```
src/car_sourcing/
  domain/        règles pures : configuration, filtres, cote, marge, niveaux (testées à 94 %)
  parsers/       emails et pages Leboncoin et La Centrale
  adapters/      Gmail, HTTP, BigQuery, Sheets, Telegram, géocodage IGN
  pipeline.py    orchestration d'un run et supervision
  web/           service web : webhook Telegram, API, interface (static/index.html)
  demo.py        données simulées pour `car-sourcing demo`
web/             sources de l'interface, assemblées par web/build.py
sql/             schémas des tables, vues et requête des comparables (versionnés)
infra/           Terraform
tests/           tests unitaires, fixtures, test SQL BigQuery (-m bigquery)
```

## Choix à connaître

- Le géocodage utilise le service de la Géoplateforme IGN : l'ancienne URL de l'API Adresse a été
  décommissionnée fin janvier 2026.
- Les annonces exclues pour un mot-clé (épave, moteur HS…) ne servent pas de comparables, pour ne pas tirer la
  cote vers le bas. Les annonces de professionnels, elles, sont incluses.
- La cote affichée dans une alerte est celle du moment de l'évaluation. La fiche de l'interface montre aussi le
  marché actuel, qui évolue avec les nouvelles annonces.
- Le calcul de la marge est isolé par régime fiscal (`MARGIN_CALCULATORS` dans `domain/rules.py`) : le régime
  professionnel avec TVA sur marge s'y ajoutera sans toucher au reste.

## Coûts attendus

Cloud Run, Scheduler, Secret Manager et BigQuery restent dans les quotas gratuits ou à quelques euros par mois à
ce volume. Le poste principal est BigQuery : chaque requête facture au minimum 10 Mo lus, soit quelques Go par
mois, bien en dessous du To gratuit.
