"""Adaptateurs fins vers Gmail, le web et le géocodeur. Non testés unitairement (smoke test)."""

from __future__ import annotations

import base64
import json
import logging
import random
import time
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from car_sourcing.adapters.ports import RawEmail
from car_sourcing.settings import Settings, log

logger = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailSource:
    """Lit les emails d'alerte non traités ; le label `traite` garantit l'idempotence."""

    def __init__(self, settings: Settings) -> None:
        if settings.gmail_oauth_json is None:
            raise RuntimeError("GMAIL_OAUTH_JSON manquant")
        info = json.loads(settings.gmail_oauth_json.get_secret_value())
        creds = Credentials.from_authorized_user_info(info, GMAIL_SCOPES)  # type: ignore[no-untyped-call]
        self._api: Any = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self._query = settings.gmail_query
        self._labels = {
            "done": self._label_id(settings.gmail_label_done),
            "error": self._label_id(settings.gmail_label_error),
        }

    def _label_id(self, name: str) -> str:
        labels = self._api.users().labels().list(userId="me").execute().get("labels", [])
        for label in labels:
            if label["name"] == name:
                return str(label["id"])
        created = self._api.users().labels().create(userId="me", body={"name": name}).execute()
        return str(created["id"])

    def list_unprocessed(self, limit: int) -> list[RawEmail]:
        resp = self._api.users().messages().list(userId="me", q=self._query, maxResults=limit).execute()
        out: list[RawEmail] = []
        for ref in reversed(resp.get("messages", [])):  # du plus ancien au plus récent
            msg = self._api.users().messages().get(userId="me", id=ref["id"], format="raw").execute()
            raw = base64.urlsafe_b64decode(msg["raw"].encode())
            headers = raw.split(b"\r\n\r\n", 1)[0].decode("utf-8", "replace")
            sender = _header(headers, "From")
            subject = _header(headers, "Subject")
            received = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=UTC)
            out.append(RawEmail(ref["id"], sender, subject, received, raw))
        return out

    def _label(self, message_id: str, key: str) -> None:
        self._api.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [self._labels[key]]}
        ).execute()

    def mark_processed(self, message_id: str) -> None:
        self._label(message_id, "done")

    def mark_failed(self, message_id: str) -> None:
        self._label(message_id, "error")

    def latest_alert_email_at(self) -> datetime | None:
        resp = (
            self._api.users()
            .messages()
            .list(userId="me", q="from:leboncoin.fr OR from:lacentrale.fr", maxResults=1)
            .execute()
        )
        refs = resp.get("messages", [])
        if not refs:
            return None
        msg = self._api.users().messages().get(userId="me", id=refs[0]["id"], format="minimal").execute()
        return datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=UTC)


def _header(headers: str, name: str) -> str:
    for line in headers.split("\r\n"):
        if line.lower().startswith(name.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""


class PoliteFetcher:
    """Requêtes espacées de 3 à 6 secondes, user-agent de navigateur courant, jamais d'exception."""

    def __init__(self, settings: Settings, sleep: Any = time.sleep) -> None:
        self._client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "fr-FR,fr;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=settings.http_timeout_s,
            follow_redirects=True,
        )
        self._min, self._max = settings.http_min_delay_s, settings.http_max_delay_s
        self._sleep = sleep
        self._last = 0.0

    def _wait(self) -> None:
        delay = random.uniform(self._min, self._max)  # noqa: S311 - espacement, pas de sécurité
        remaining = self._last + delay - time.monotonic()
        if remaining > 0:
            self._sleep(remaining)
        self._last = time.monotonic()

    def fetch(self, url: str) -> str | None:
        self._wait()
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            log(logger, logging.WARNING, "page inaccessible", url=url, error=str(exc))
            return None
        if resp.status_code != 200:
            log(logger, logging.WARNING, "page inaccessible", url=url, status=resp.status_code)
            return None
        return resp.text

    def resolve_redirect(self, url: str) -> str | None:
        self._wait()
        try:
            resp = self._client.head(url)
            if resp.status_code >= 400:
                resp = self._client.get(url)
        except httpx.HTTPError:
            return None
        return str(resp.url)


class GeocodeCache(Protocol):
    def get_geocode(self, postal_code: str, city: str) -> tuple[float, float] | None: ...
    def put_geocode(self, postal_code: str, city: str, lat: float, lon: float) -> None: ...


class IgnGeocoder:
    """Géocodeur de la Géoplateforme IGN (successeur de l'API Adresse), avec cache en table."""

    URL = "https://data.geopf.fr/geocodage/search"

    def __init__(self, cache: GeocodeCache, timeout: float = 10.0) -> None:
        self._cache = cache
        self._memory: dict[tuple[str, str], tuple[float, float] | None] = {}
        self._client = httpx.Client(timeout=timeout, headers={"User-Agent": "car-sourcing/0.1"})

    def geocode(self, postal_code: str | None, city: str | None) -> tuple[float, float] | None:
        cp, name = (postal_code or "").strip(), (city or "").strip()
        if not cp and not name:
            return None
        key = (cp, name.lower())
        if key in self._memory:
            return self._memory[key]
        cached = self._cache.get_geocode(cp, name.lower())
        if cached:
            self._memory[key] = cached
            return cached
        params = {"q": name or cp, "type": "municipality", "limit": "1", "index": "address"}
        if cp:
            params["postcode"] = cp
        try:
            resp = self._client.get(self.URL, params=params)
            resp.raise_for_status()
            features = resp.json().get("features", [])
        except (httpx.HTTPError, ValueError) as exc:
            log(logger, logging.WARNING, "géocodage impossible", postal_code=cp, city=name, error=str(exc))
            return None
        if not features and name and cp:  # ville mal orthographiée : repli sur le code postal
            return self.geocode(cp, None)
        if not features:
            self._memory[key] = None
            return None
        lon, lat = features[0]["geometry"]["coordinates"]
        result = (float(lat), float(lon))
        self._cache.put_geocode(cp, name.lower(), *result)
        self._memory[key] = result
        return result
