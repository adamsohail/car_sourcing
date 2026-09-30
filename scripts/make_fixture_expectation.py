"""Génère le fichier .expected.json d'une nouvelle fixture, à relire et corriger à la main.

Usage : uv run python scripts/make_fixture_expectation.py tests/fixtures/emails/leboncoin/vrai_01.eml
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from car_sourcing.domain.models import Source
from car_sourcing.parsers.base import html_from_mime
from car_sourcing.parsers.emails import LACENTRALE, LEBONCOIN, parse_alert_email
from car_sourcing.parsers.pages import parse_page

path = Path(sys.argv[1])
source = path.parent.name
html = html_from_mime(path.read_bytes()) if path.suffix == ".eml" else path.read_text(encoding="utf-8")
if path.parent.parent.name == "emails":
    parsed = parse_alert_email(html, {"leboncoin": LEBONCOIN, "lacentrale": LACENTRALE}[source])
    keys = (
        "listing_id",
        "title",
        "price_eur",
        "city",
        "postal_code",
        "year",
        "mileage_km",
        "fuel",
        "gearbox",
    )
    data = {
        "listings": [{k: asdict(x)[k] for k in keys} for x in parsed.listings],
        "unresolved_links": len(parsed.unresolved_links),
    }
else:
    data = {
        k: v
        for k, v in asdict(parse_page(Source(source), html)).items()
        if v is not None and k != "description"
    }
out = path.with_suffix(".expected.json")
out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
print(f"{out} écrit : vérifiez chaque valeur avant de le valider.")
