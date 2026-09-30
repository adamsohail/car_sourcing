"""Structures communes aux parsers d'emails et de pages.

Règle : un parser qui échoue lève une erreur typée ; il ne renvoie jamais une annonce
partielle en silence. Les champs absents restent à None et l'évaluation les signale.
"""

from __future__ import annotations

import email
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from typing import Any
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

from car_sourcing.domain.models import Source


class ParseError(Exception):
    """Erreur de parsing typée, avec la source et la raison."""

    def __init__(self, source: Source, reason: str) -> None:
        super().__init__(f"{source.value}: {reason}")
        self.source = source
        self.reason = reason


class EmailParseError(ParseError):
    pass


class PageParseError(ParseError):
    pass


@dataclass(frozen=True)
class EmailListing:
    """Ce qu'un email d'alerte dit d'une annonce."""

    source: Source
    listing_id: str
    url: str
    title: str | None = None
    price_eur: int | None = None
    city: str | None = None
    postal_code: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    fuel: str | None = None
    gearbox: str | None = None
    photo_url: str | None = None


@dataclass
class ParsedEmail:
    source: Source
    listings: list[EmailListing] = field(default_factory=list)
    unresolved_links: list[str] = field(default_factory=list)
    block_errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PageDetails:
    """Ce que la page d'une annonce apporte en plus de l'email."""

    title: str | None = None
    brand: str | None = None
    model: str | None = None
    version: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    fuel: str | None = None
    gearbox: str | None = None
    price_eur: int | None = None
    seller_type: str | None = None
    city: str | None = None
    postal_code: str | None = None
    lat: float | None = None
    lon: float | None = None
    description: str | None = None
    photo_url: str | None = None


# ---------- Utilitaires ----------


def html_from_mime(raw: bytes) -> str:
    """Extrait la partie HTML d'un email MIME brut (repli sur le texte brut)."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    assert isinstance(msg, EmailMessage)
    part = msg.get_body(preferencelist=("html", "plain"))
    if part is None:
        return ""
    content = part.get_content()
    text = content if isinstance(content, str) else content.decode("utf-8", "replace")
    if part.get_content_type() == "text/plain":
        return "<pre>" + text.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
    return text


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def deep_unquote(url: str, rounds: int = 3) -> str:
    for _ in range(rounds):
        decoded = unquote(url)
        if decoded == url:
            break
        url = decoded
    return url


def iter_dicts(obj: Any) -> Iterator[dict[str, Any]]:
    """Parcourt récursivement toutes les tables d'un JSON."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except json.JSONDecodeError:
            continue
        out.extend(d for d in iter_dicts(data) if "@type" in d)
    return out


def script_json(soup: BeautifulSoup, script_id: str) -> Any:
    tag = soup.find("script", id=script_id)
    if not isinstance(tag, Tag):
        return None
    try:
        return json.loads(tag.string or tag.get_text() or "")
    except json.JSONDecodeError:
        return None


def ld_types(d: dict[str, Any]) -> set[str]:
    t = d.get("@type")
    return {str(x) for x in t} if isinstance(t, list) else {str(t)}


def text_of(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return text_of(value.get("name") or value.get("value") or value.get("label"))
    if isinstance(value, list):
        return text_of(value[0]) if value else None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None
