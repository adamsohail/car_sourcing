"""Tests des parsers : chaque couple fixture + attendu est vérifié automatiquement."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from car_sourcing.domain.models import Source
from car_sourcing.parsers.base import EmailParseError, PageParseError, html_from_mime
from car_sourcing.parsers.emails import LACENTRALE, LEBONCOIN, detect_format, parse_alert_email
from car_sourcing.parsers.pages import parse_page
from tests.conftest import FIXTURES

FORMATS = {"leboncoin": LEBONCOIN, "lacentrale": LACENTRALE}
REQUIRED_EMAIL = ("listing_id", "url", "title", "price_eur")
REQUIRED_PAGE = ("price_eur", "year", "mileage_km")


def _pairs(kind: str) -> list[tuple[str, Path]]:
    out = []
    for source in FORMATS:
        for f in sorted((FIXTURES / kind / source).glob("*")):
            if f.suffix in {".html", ".eml"}:
                out.append((source, f))
    return out


def _read(path: Path) -> str:
    return html_from_mime(path.read_bytes()) if path.suffix == ".eml" else path.read_text(encoding="utf-8")


def _expected(path: Path) -> dict:
    return json.loads(path.with_suffix(".expected.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("source", "path"), _pairs("emails"), ids=lambda v: v.name if isinstance(v, Path) else v
)
def test_email_fixture(source: str, path: Path) -> None:
    fmt = FORMATS[source]
    expected = _expected(path)
    parsed = parse_alert_email(_read(path), fmt)
    assert len(parsed.unresolved_links) == expected.get("unresolved_links", 0)
    listings = parsed.listings
    if "resolved" in expected:
        listings = parse_alert_email(_read(path), fmt, resolved=expected["resolved"]).listings
        wanted = expected["after_resolution"]
    else:
        wanted = expected["listings"]
    assert [x.listing_id for x in listings] == [w["listing_id"] for w in wanted]
    for got, want in zip(listings, wanted, strict=True):
        data = asdict(got)
        for key in REQUIRED_EMAIL:
            assert data[key] is not None, f"{key} manquant pour {got.listing_id}"
        for key, value in want.items():
            assert data[key] == value, f"{got.listing_id}.{key}"
    assert not parsed.block_errors


@pytest.mark.parametrize(
    ("source", "path"), _pairs("pages"), ids=lambda v: v.name if isinstance(v, Path) else v
)
def test_page_fixture(source: str, path: Path) -> None:
    details = asdict(parse_page(Source(source), _read(path)))
    for key in REQUIRED_PAGE:
        assert details[key] is not None, f"{key} manquant"
    for key, value in _expected(path).items():
        got = details[key]
        assert got == pytest.approx(value) if isinstance(value, float) else got == value, key


def test_email_sans_annonce_leve_une_erreur_typee() -> None:
    with pytest.raises(EmailParseError):
        parse_alert_email(
            "<html><body><p>Newsletter</p><a href='https://www.leboncoin.fr/'>x</a></body></html>", LEBONCOIN
        )


def test_page_sans_donnees_leve_une_erreur_typee() -> None:
    with pytest.raises(PageParseError):
        parse_page(Source.LEBONCOIN, "<html><body>Accès refusé</body></html>")
    with pytest.raises(PageParseError):
        parse_page(
            Source.LACENTRALE, "<html><body><script type='application/ld+json'>{bad</script></body></html>"
        )


def test_detection_de_l_expediteur() -> None:
    assert detect_format("leboncoin <no-reply@leboncoin.fr>") is LEBONCOIN
    assert detect_format("La Centrale <alertes@info.lacentrale.fr>") is LACENTRALE
    assert detect_format("autre@example.com") is None


def test_email_mime_multipart() -> None:
    raw = (
        b"From: leboncoin <no-reply@leboncoin.fr>\r\nSubject: Alerte\r\nMIME-Version: 1.0\r\n"
        b"Content-Type: multipart/alternative; boundary=b\r\n\r\n--b\r\nContent-Type: text/plain\r\n\r\ntexte\r\n"
        b"--b\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>html</p>\r\n--b--\r\n"
    )
    assert "<p>html</p>" in html_from_mime(raw)
