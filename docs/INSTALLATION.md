# Installation pas à pas

Comptez environ deux heures la première fois. Chaque étape se termine par une vérification.
Les commandes sont à lancer depuis la racine du dépôt, sur un poste avec `gcloud`, `terraform` (1.6 ou plus),
`uv` et `git` installés.

## 1. Le dépôt GitHub

Créez un repo vide (privé), puis :

```bash
git remote add origin git@github.com:<compte>/car-sourcing.git
git push -u origin main
```

La CI se lance : lint, typage, tests, image Docker et vérification Terraform doivent passer au vert.

## 2. Le projet GCP

1. Créez un projet dans la console GCP et activez la facturation.
2. Connectez-vous avec un compte **Owner** du projet :

```bash
gcloud auth login
gcloud auth application-default login
```

## 3. Le Google Sheet de configuration

1. Dans Google Drive : Nouveau > Importer, choisissez `templates/configuration_sourcing.xlsx`,
   puis ouvrez-le avec Google Sheets (Fichier > Enregistrer au format Google Sheets).
2. Renseignez au minimum `base_code_postal`, et confirmez `taux_frais_pct` et `cout_transport_eur_km`.
3. Notez l'identifiant du Sheet : dans l'URL, la partie entre `/d/` et `/edit`.

Tant que la base est vide, le run est bloqué et une alerte technique l'explique : c'est voulu.

## 4. Le bot Telegram

1. Dans Telegram, écrivez à **@BotFather** : `/newbot`, puis gardez le token affiché (il ne doit être collé nulle part
   ailleurs qu'à l'étape 6).
2. Créez un groupe, ajoutez-y votre collaborateur et le bot, puis écrivez `/start` dans le groupe.
3. Récupérez l'identifiant du groupe (il commence en général par `-100`) :

```bash
scripts/telegram_chat_id.sh
```

Faites-le avant l'étape 8 : une fois le webhook enregistré, cette méthode ne fonctionne plus.

## 5. L'infrastructure

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars   # puis complétez les 5 valeurs
scripts/bootstrap.sh <project_id> europe-west1
```

Le script crée le bucket d'état Terraform, puis toute l'infrastructure. À la fin, il affiche :

- `runtime_service_account` : partagez le Google Sheet **en lecture** avec cette adresse (bouton Partager) ;
- `service_url` : l'adresse de l'interface ;
- `workload_identity_provider` et `deployer_service_account` : pour l'étape 7.

Vérification : relancez `terraform -chdir=infra plan`, il doit annoncer « No changes ».

Si le projet appartient à une organisation Google Workspace, la règle « partage restreint au domaine » peut
refuser l'accès public au service web. Le webhook Telegram en a besoin : demandez une exception pour ce projet.

## 6. Les secrets

Trois secrets sont à saisir ; les deux autres (secret du webhook, clé de session) sont générés par Terraform.

```bash
scripts/set_secret.sh telegram-bot-token     # collez le token BotFather (saisie masquée)
scripts/set_secret.sh web-password           # choisissez le mot de passe de l'interface
```

Accès Gmail du compte dédié, à faire une seule fois :

1. Console GCP > API et services > **Écran de consentement OAuth** : type Externe, puis **Publier l'application**
   (état « En production »). En état « Test », Google coupe l'accès au bout de 7 jours.
2. API et services > Identifiants > Créer des identifiants > **ID client OAuth** > Application de bureau.
   Téléchargez le fichier JSON sous le nom `client_secret.json`.
3. Lancez le script, connectez-vous avec le **compte Gmail dédié** et acceptez l'avertissement
   « application non validée » (c'est votre propre application) :

```bash
uv run python scripts/get_gmail_token.py client_secret.json token.json
scripts/set_secret.sh gmail-oauth-json token.json
rm token.json client_secret.json
```

## 7. Le déploiement automatique

Dans GitHub : Settings > Secrets and variables > Actions > **Variables**, créez :

| Variable | Valeur |
| --- | --- |
| `GCP_PROJECT` | identifiant du projet |
| `GCP_REGION` | `europe-west1` |
| `WIF_PROVIDER` | sortie `workload_identity_provider` |
| `DEPLOYER_SA` | sortie `deployer_service_account` |

Relancez le workflow « Déploiement » (onglet Actions) ou poussez sur `main`. Il construit l'image, la publie
et met à jour le job et le service. Vérification : `service_url` affiche l'écran de connexion.

## 8. Le webhook Telegram

```bash
export TELEGRAM_BOT_TOKEN="$(gcloud secrets versions access latest --secret=telegram-bot-token)"
export TELEGRAM_WEBHOOK_SECRET="$(gcloud secrets versions access latest --secret=telegram-webhook-secret)"
uv run car-sourcing set-webhook "$(terraform -chdir=infra output -raw service_url)"
```

La réponse doit contenir `"ok": true`.

## 9. Vérifications

Les commandes suivantes s'exécutent dans GCP, avec les vrais secrets :

```bash
REGION=europe-west1
gcloud run jobs execute car-sourcing-ingest --region $REGION --args=smoke --wait       # 5 lignes « OK »
gcloud run jobs execute car-sourcing-ingest --region $REGION --args=test-alert --wait  # une alerte arrive
gcloud run jobs execute car-sourcing-ingest --region $REGION --wait                    # un vrai run
```

Correspondance avec les critères de validation du plan :

| Étape | Vérification |
| --- | --- |
| 4. Infrastructure | second `terraform plan` vide ; `BQ_TEST_PROJECT=<projet> BQ_TEST_DATASET=car_sourcing_test uv run pytest -m bigquery` vert |
| 5. Pipeline | après un run, des lignes dans `listings` et `evaluations`, les emails portent le label `traite` ; un second run n'ajoute aucun doublon |
| 6. Telegram | `test-alert` envoie une alerte ; chaque bouton crée une ligne dans `feedback` et coche le bouton |
| 7. Production | 24 h de runs sans erreur dans Cloud Logging ; chaque alerte technique déclenchée une fois (par exemple en vidant temporairement `base_code_postal` dans le Sheet) |

## 10. Valider les parsers sur de vrais emails

Les exemples fournis dans `tests/fixtures` sont synthétiques. Dès que les premières alertes arrivent :

1. Dans Gmail, ouvrez un email d'alerte, menu ⋮ > **Télécharger le message** (fichier `.eml`), et déposez-le dans
   `tests/fixtures/emails/leboncoin/` ou `.../lacentrale/`.
2. Ouvrez une annonce de cet email dans le navigateur, Fichier > **Enregistrer sous** (HTML, page seule), et
   déposez-la dans `tests/fixtures/pages/<source>/`.
3. `uv run python scripts/make_fixture_expectation.py <fichier>` génère le résultat attendu : relisez-le et
   corrigez-le à la main.
4. `uv run pytest tests/unit/test_parsers.py` : tout doit passer. Sinon, c'est le parser qu'il faut adapter.

Anonymisez les fichiers (prénom, téléphone et email du vendeur) avant de les versionner.
