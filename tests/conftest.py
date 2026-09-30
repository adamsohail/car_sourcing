from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from car_sourcing.domain.config import DEFAULT_KEYWORDS, DEFAULT_PARAMETERS, Config, parse_sheet
from car_sourcing.domain.models import Listing, SellerType, Source

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def make_config(**overrides: str) -> Config:
    params = dict(DEFAULT_PARAMETERS)
    params["base_code_postal"] = "69003"
    params.update(overrides)
    return parse_sheet(list(params.items()), [[k] for k in DEFAULT_KEYWORDS])


@pytest.fixture
def config() -> Config:
    return make_config()


def make_listing(**kw: object) -> Listing:
    data: dict[str, object] = {
        "source": Source.LEBONCOIN,
        "listing_id": "1",
        "url": "https://www.leboncoin.fr/ad/voitures/1",
        "title": "Peugeot 208",
        "brand": "Peugeot",
        "model": "208",
        "year": 2019,
        "mileage_km": 70_000,
        "fuel": "Essence",
        "gearbox": "Manuelle",
        "price_eur": 8_000,
        "seller_type": SellerType.PARTICULIER,
        "city": "Lyon",
        "postal_code": "69003",
        "lat": 45.76,
        "lon": 4.86,
        "description": "Très bon état.",
        "first_seen_at": NOW,
        "last_seen_at": NOW,
    }
    data.update(kw)
    return Listing.model_validate(data)
