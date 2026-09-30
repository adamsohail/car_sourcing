#!/usr/bin/env bash
# Affiche l'identifiant des groupes où le bot a reçu un message.
# 1. Ajoutez le bot au groupe. 2. Écrivez « bonjour » dans le groupe. 3. Lancez ce script.
set -euo pipefail
read -r -s -p "Token du bot (BotFather) : " TOKEN; echo
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | python3 -c '
import json, sys
data = json.load(sys.stdin)
chats = {}
for update in data.get("result", []):
    for key in ("message", "my_chat_member"):
        if key in update:
            chat = update[key]["chat"]
            chats[chat["id"]] = chat.get("title", chat.get("first_name", ""))
if not chats:
    print("Aucun message reçu : écrivez dans le groupe puis relancez.")
for chat_id, title in chats.items():
    print(chat_id, title)
'
