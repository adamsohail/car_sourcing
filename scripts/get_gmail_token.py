"""Obtient l'accès Gmail du compte dédié, une seule fois, et l'écrit dans un fichier.

1. Dans la console GCP : API et services > Identifiants > Créer un ID client OAuth > Application de bureau.
   Télécharger le JSON (client_secret.json).
2. Écran de consentement OAuth : type Externe, puis « Publier l'application » (état En production).
   En état Test, Google invalide l'accès au bout de 7 jours.
3. uv run python scripts/get_gmail_token.py client_secret.json token.json
   Se connecter avec le compte Gmail dédié, accepter l'avertissement « application non validée ».
4. scripts/set_secret.sh gmail-oauth-json token.json   puis supprimer token.json et client_secret.json.
"""

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage : get_gmail_token.py client_secret.json token.json")
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    Path(sys.argv[2]).write_text(creds.to_json())
    print(
        f"Accès Gmail enregistré dans {sys.argv[2]}. Envoyez-le dans Secret Manager puis supprimez le fichier."
    )
