#!/usr/bin/env bash
# Enregistre la valeur d'un secret sans qu'elle apparaisse à l'écran ni dans l'historique.
# Usage : scripts/set_secret.sh telegram-bot-token      (saisie masquée)
#         scripts/set_secret.sh gmail-oauth-json token.json
set -euo pipefail
NAME="${1:?nom du secret manquant : gmail-oauth-json, telegram-bot-token ou web-password}"
if [[ $# -ge 2 ]]; then
  gcloud secrets versions add "$NAME" --data-file="$2"
else
  read -r -s -p "Valeur de ${NAME} : " VALUE; echo
  printf '%s' "$VALUE" | gcloud secrets versions add "$NAME" --data-file=-
fi
echo "Secret ${NAME} mis à jour. Le job l'utilise dès son prochain run."
echo "Pour le service web : gcloud run services update car-sourcing-web --region <region> --update-labels=secrets=$(date +%s)"
