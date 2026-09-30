"""Contenu des alertes Telegram et encodage des boutons (callback_data ≤ 64 octets)."""

from __future__ import annotations

import html
import re
from typing import Any

from car_sourcing.domain.config import Config
from car_sourcing.domain.models import AlertLevel, Evaluation, FeedbackStatus, Listing, Reliability, Source

_SOURCE_CODES = {Source.LEBONCOIN: "l", Source.LACENTRALE: "c", Source.MANUEL: "m"}
_STATUS_CODES = {
    FeedbackStatus.INTERESSANT: "i",
    FeedbackStatus.PAS_INTERESSANT: "p",
    FeedbackStatus.ACHETE: "a",
}
BUTTONS = [
    (FeedbackStatus.INTERESSANT, "👍 Intéressant"),
    (FeedbackStatus.PAS_INTERESSANT, "👎 Pas intéressant"),
    (FeedbackStatus.ACHETE, "🔑 Acheté"),
]
PRICE_PROMPT_RE = re.compile(r"réf\. (leboncoin|lacentrale|manuel):(\S+)")
RELIABILITY_LABEL = {
    Reliability.FIABLE: "fiable",
    Reliability.MOYENNE: "moyenne",
    Reliability.FAIBLE: "peu fiable",
}


def eur(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    n = round(value)
    body = f"{abs(n):,}".replace(",", "\u00a0") + "\u00a0€"
    if signed:
        return ("+" if n > 0 else "−" if n < 0 else "") + body
    return ("−" if n < 0 else "") + body


def km(value: float | None) -> str:
    return "—" if value is None else f"{round(value):,}".replace(",", "\u00a0") + "\u00a0km"


def encode_callback(status: FeedbackStatus, source: Source, listing_id: str) -> str:
    return f"fb|{_STATUS_CODES[status]}|{_SOURCE_CODES[source]}|{listing_id}"


def decode_callback(data: str) -> tuple[FeedbackStatus, Source, str] | None:
    parts = data.split("|", 3)
    if len(parts) != 4 or parts[0] != "fb":
        return None
    status = next((s for s, c in _STATUS_CODES.items() if c == parts[1]), None)
    source = next((s for s, c in _SOURCE_CODES.items() if c == parts[2]), None)
    if status is None or source is None or not parts[3]:
        return None
    return status, source, parts[3]


def alert_keyboard(listing: Listing, selected: FeedbackStatus | None, public_url: str = "") -> dict[str, Any]:
    row = [
        {
            "text": ("✓ " if status == selected else "") + label,
            "callback_data": encode_callback(status, listing.source, listing.listing_id),
        }
        for status, label in BUTTONS
    ]
    links = [{"text": "Voir l'annonce", "url": listing.url}]
    if public_url:
        links.append({"text": "Ouvrir la fiche", "url": f"{public_url.rstrip('/')}/#/annonce/{listing.key}"})
    return {"inline_keyboard": [row[:2], row[2:], links]}


def format_alert(listing: Listing, ev: Evaluation, config: Config) -> str:
    e = html.escape
    head = (
        "◆ <b>ALERTE PRIORITAIRE</b>"
        if ev.alert_level is AlertLevel.PRIORITAIRE
        else "<b>Nouvelle opportunité</b>"
    )
    name = e(
        " ".join(p for p in (listing.brand, listing.model, listing.version) if p)
        or listing.title
        or "Annonce"
    )
    lines = [
        head,
        f"<b>{name}</b>" + (f" ({listing.year})" if listing.year else ""),
        f"Prix : <b>{eur(listing.price_eur)}</b>",
        f"{km(listing.mileage_km)}, soit {km(ev.km_per_year)} par an",
    ]
    where = e(" ".join(p for p in (listing.city, listing.postal_code) if p) or "Lieu inconnu")
    lines.append(
        f"{where}, à {km(ev.distance_km)}" if ev.distance_km is not None else f"{where}, distance inconnue"
    )
    reliability = RELIABILITY_LABEL.get(ev.reliability, "") if ev.reliability else ""
    lines.append(f"Cote : {eur(ev.market_price_eur)} sur {ev.comparables_count} comparables, {reliability}")
    lines.append(f"Marge estimée : <b>{eur(ev.margin_eur, signed=True)}</b>")
    if ev.reliability is Reliability.FAIBLE:
        lines.append("⚠️ Cote peu fiable : vérifiez le prix du marché avant d'appeler.")
    if listing.enrichment_status.value == "detail_indisponible":
        lines.append("⚠️ Page de l'annonce illisible : description et mots-clés non vérifiés.")
    return "\n".join(lines)


def price_prompt(listing_key: str, name: str) -> str:
    return f"Prix payé pour {html.escape(name)} ? Répondez à ce message avec le montant, par exemple 7800.\nréf. {listing_key}"
