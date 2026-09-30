"""Parsers des emails d'alerte.

Chaque email contient une liste d'annonces. On repère les liens d'annonce (identifiant dans l'URL,
éventuellement derrière une redirection de suivi), puis on lit le bloc HTML qui entoure chaque lien :
titre, prix, lieu, année, kilométrage.

Les liens de suivi qu'on ne sait pas décoder sont renvoyés dans `unresolved_links` : le pipeline
les résout par une requête HTTP (en-tête Location) avant de relancer l'extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from car_sourcing.domain.models import Source
from car_sourcing.domain.text import normalize_fuel, normalize_gearbox, parse_int
from car_sourcing.parsers.base import EmailListing, EmailParseError, ParsedEmail, deep_unquote, soup_of

PRICE_RE = re.compile(r"(\d{1,3}(?:[ \u00a0\u202f.]\d{3})+|\d{3,6})\s?(?:€|EUR\b)")
KM_RE = re.compile(r"(\d{1,3}(?:[ \u00a0\u202f.]\d{3})+|\d{1,6})\s?km\b", re.IGNORECASE)
YEAR_RE = re.compile(r"(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)")
CP_CITY_RE = re.compile(
    r"(?:(?P<city1>[A-Za-zÀ-ÿ'’\- ]{2,40}?)\s*\(?(?P<cp1>\d{5})\)?|(?P<cp2>\d{5})\s+(?P<city2>[A-Za-zÀ-ÿ'’\- ]{2,40}))"
)
FUEL_WORDS = re.compile(r"\b(essence|diesel|hybride(?: rechargeable)?|[ée]lectrique|gpl)\b", re.IGNORECASE)
GEAR_WORDS = re.compile(r"\b(manuelle|automatique)\b", re.IGNORECASE)


@dataclass(frozen=True)
class EmailFormat:
    source: Source
    sender_domains: tuple[str, ...]
    ad_url: re.Pattern[str]
    tracking_hosts: tuple[str, ...]

    def canonical_url(self, listing_id: str) -> str:
        if self.source is Source.LEBONCOIN:
            return f"https://www.leboncoin.fr/ad/voitures/{listing_id}"
        return f"https://www.lacentrale.fr/auto-occasion-annonce-{listing_id}.html"


LEBONCOIN = EmailFormat(
    source=Source.LEBONCOIN,
    sender_domains=("leboncoin.fr",),
    ad_url=re.compile(r"leboncoin\.fr/(?:ad/)?[a-z_]+/(\d{8,12})(?:\.htm)?", re.IGNORECASE),
    tracking_hosts=(
        "leboncoin",
        "lbc",
        "adobe",
        "sendgrid",
        "mailjet",
        "emarsys",
        "list-manage",
        "tracking",
        "click",
    ),
)
LACENTRALE = EmailFormat(
    source=Source.LACENTRALE,
    sender_domains=("lacentrale.fr",),
    ad_url=re.compile(r"lacentrale\.fr/auto-occasion-annonce-(\d{6,14})\.html", re.IGNORECASE),
    tracking_hosts=(
        "lacentrale",
        "adobe",
        "sendgrid",
        "mailjet",
        "emarsys",
        "list-manage",
        "tracking",
        "click",
    ),
)
FORMATS = (LEBONCOIN, LACENTRALE)


def detect_format(sender: str) -> EmailFormat | None:
    s = sender.lower()
    return next((f for f in FORMATS if any(d in s for d in f.sender_domains)), None)


def _listing_id(fmt: EmailFormat, href: str) -> str | None:
    m = fmt.ad_url.search(deep_unquote(href))
    return m.group(1) if m else None


def _block_for(anchor: Tag, fmt: EmailFormat, listing_id: str) -> Tag:
    """Remonte jusqu'au plus grand ancêtre qui ne contient que cette annonce et un prix."""
    best: Tag = anchor
    node: Tag | None = anchor
    while (
        node is not None
        and isinstance(node.parent, Tag)
        and node.parent.name not in {"body", "html", "[document]"}
    ):
        parent = node.parent
        ids = {i for a in parent.find_all("a", href=True) if (i := _listing_id(fmt, str(a["href"])))}
        if ids - {listing_id}:
            break
        best = parent
        node = parent
        text = parent.get_text(" ")
        # Le bloc contient déjà le prix : on s'arrête au premier niveau « table », « tr » ou « div ».
        if PRICE_RE.search(text) and len(text) > 40 and parent.name in {"table", "div", "tr"}:
            break
    return best


def _clean_lines(block: Tag) -> list[str]:
    lines = [re.sub(r"\s+", " ", t).strip() for t in block.get_text("\n").split("\n")]
    return [line for line in lines if line]


def _extract(block: Tag, fmt: EmailFormat, listing_id: str, anchor: Tag) -> EmailListing:
    lines = _clean_lines(block)
    text = " \n ".join(lines)
    price_m = PRICE_RE.search(text)
    km_m = KM_RE.search(text)
    year = next((int(y) for y in YEAR_RE.findall(text.replace(km_m.group(0), "") if km_m else text)), None)
    title = None
    for candidate in [
        anchor.get_text(" ", strip=True),
        *(str(i.get("alt") or "") for i in block.find_all("img")),
        *lines,
    ]:
        c = candidate.strip()
        if (
            len(c) >= 3
            and not PRICE_RE.search(c)
            and not re.fullmatch(r"(voir|découvrir).*", c, re.IGNORECASE)
        ):
            title = c
            break
    city = cp = None
    for line in lines:
        m = CP_CITY_RE.search(line)
        if m and not PRICE_RE.search(line) and not KM_RE.search(line):
            cp = m.group("cp1") or m.group("cp2")
            city = (m.group("city1") or m.group("city2") or "").strip(" -,") or None
            break
    img = block.find("img", src=True)
    photo = str(img["src"]) if isinstance(img, Tag) and str(img["src"]).startswith("http") else None
    fuel = FUEL_WORDS.search(text)
    gear = GEAR_WORDS.search(text)
    return EmailListing(
        source=fmt.source,
        listing_id=listing_id,
        url=fmt.canonical_url(listing_id),
        title=title,
        price_eur=parse_int(price_m.group(1)) if price_m else None,
        city=city,
        postal_code=cp,
        year=year,
        mileage_km=parse_int(km_m.group(1)) if km_m else None,
        fuel=normalize_fuel(fuel.group(1)) if fuel else None,
        gearbox=normalize_gearbox(gear.group(1)) if gear else None,
        photo_url=photo,
    )


def parse_alert_email(html: str, fmt: EmailFormat, resolved: dict[str, str] | None = None) -> ParsedEmail:
    """Extrait les annonces d'un email. `resolved` associe un lien de suivi à son URL finale."""
    resolved = resolved or {}
    soup: BeautifulSoup = soup_of(html)
    result = ParsedEmail(source=fmt.source)
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        listing_id = _listing_id(fmt, href) or (
            _listing_id(fmt, resolved[href]) if href in resolved else None
        )
        if listing_id is None:
            host = href.split("/")[2].lower() if href.startswith("http") and href.count("/") >= 2 else ""
            block_text = anchor.find_parent(["td", "div", "table"])
            if (
                host
                and any(t in host for t in fmt.tracking_hosts)
                and href not in resolved
                and block_text is not None
                and PRICE_RE.search(block_text.get_text(" "))
                and href not in result.unresolved_links
            ):
                result.unresolved_links.append(href)
            continue
        if listing_id in seen:
            continue
        seen.add(listing_id)
        try:
            result.listings.append(_extract(_block_for(anchor, fmt, listing_id), fmt, listing_id, anchor))
        except (ValueError, AttributeError) as exc:  # bloc inattendu : on le compte, on continue
            result.block_errors.append(f"{listing_id}: {exc}")
    if not result.listings and not result.unresolved_links:
        raise EmailParseError(fmt.source, "aucune annonce trouvée dans l'email")
    return result
