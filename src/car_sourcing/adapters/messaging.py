"""Google Sheets (configuration métier) et Telegram (alertes et boutons de retour)."""

from __future__ import annotations

import logging
from typing import Any

import google.auth
import httpx
from googleapiclient.discovery import build

from car_sourcing.adapters.ports import SentAlert
from car_sourcing.alerts_format import alert_keyboard, format_alert
from car_sourcing.domain.config import Config, parse_sheet
from car_sourcing.domain.models import Evaluation, Listing
from car_sourcing.settings import Settings, log

logger = logging.getLogger(__name__)
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class SheetConfigSource:
    """Lit les onglets `parametres` et `mots_cles_exclusion` avec le compte de service (lecture seule)."""

    def __init__(self, settings: Settings) -> None:
        creds, _ = google.auth.default(scopes=SHEETS_SCOPES)
        self._api: Any = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self._sheet_id = settings.sheet_id

    def rows(self) -> tuple[list[list[str]], list[list[str]]]:
        resp = (
            self._api.spreadsheets()
            .values()
            .batchGet(
                spreadsheetId=self._sheet_id,
                ranges=["parametres!A:B", "mots_cles_exclusion!A:A"],
                valueRenderOption="FORMATTED_VALUE",
            )
            .execute()
        )
        ranges = resp.get("valueRanges", [])
        params = ranges[0].get("values", []) if ranges else []
        keywords = ranges[1].get("values", []) if len(ranges) > 1 else []
        return params, keywords

    def load(self) -> Config:
        params, keywords = self.rows()
        return parse_sheet(params, keywords)


class TelegramNotifier:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if settings.telegram_bot_token is None:
            raise RuntimeError("TELEGRAM_BOT_TOKEN manquant")
        self._base = f"https://api.telegram.org/bot{settings.telegram_bot_token.get_secret_value()}"
        self._chat = settings.telegram_chat_id
        self._public_url = settings.public_base_url
        self._http = client or httpx.Client(timeout=20)

    def call(self, method: str, **payload: Any) -> dict[str, Any]:
        resp = self._http.post(f"{self._base}/{method}", json=payload)
        data: dict[str, Any] = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} : {data.get('description')}")
        return data

    def send_alert(self, listing: Listing, evaluation: Evaluation, config: Config) -> SentAlert:
        text = format_alert(listing, evaluation, config)
        markup = alert_keyboard(listing, None, self._public_url)
        if listing.photo_url:
            try:
                res = self.call(
                    "sendPhoto",
                    chat_id=self._chat,
                    photo=listing.photo_url,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                return SentAlert(res["result"]["message_id"])
            except (RuntimeError, httpx.HTTPError) as exc:  # photo refusée : on envoie le texte seul
                log(
                    logger, logging.WARNING, "photo refusée par Telegram", listing=listing.key, error=str(exc)
                )
        res = self.call(
            "sendMessage",
            chat_id=self._chat,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
            link_preview_options={"is_disabled": True},
        )
        return SentAlert(res["result"]["message_id"])

    def send_technical(self, text: str) -> None:
        self.call("sendMessage", chat_id=self._chat, text=f"⚙️ Alerte technique\n{text}")
