"""Règles de calcul (fonctions pures, testées unitairement).

Ordre des filtres : prix, vendeur, kilométrage, km/an, mots-clés, données incomplètes.
Le premier motif rencontré est enregistré.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from car_sourcing.domain.config import Config
from car_sourcing.domain.models import (
    AlertLevel,
    Comparable,
    Evaluation,
    ExclusionReason,
    Listing,
    Reliability,
    SellerType,
)
from car_sourcing.domain.text import find_keyword

ROAD_FACTOR = 1.3
STRICT_YEAR, STRICT_KM = 1, 20_000
WIDE_YEAR, WIDE_KM = 2, 40_000


# ---------- Filtres ----------


def km_per_year(mileage_km: int | None, year: int | None, current_year: int) -> float | None:
    """Âge minimum d'un an : pas de division par zéro pour un véhicule de l'année."""
    if mileage_km is None or year is None:
        return None
    return mileage_km / max(1, current_year - year)


@dataclass(frozen=True)
class FilterResult:
    reason: ExclusionReason | None
    detail: str | None = None

    @property
    def passed(self) -> bool:
        return self.reason is None


def apply_filters(listing: Listing, config: Config, current_year: int) -> FilterResult:
    price, mileage, year = listing.price_eur, listing.mileage_km, listing.year
    if price is not None and not (config.prix_min_eur <= price <= config.prix_max_eur):
        return FilterResult(ExclusionReason.PRIX_HORS_BORNES)
    if config.vendeur_particulier_uniquement and listing.seller_type is SellerType.PRO:
        return FilterResult(ExclusionReason.VENDEUR_PRO)
    if mileage is not None and mileage > config.km_max:
        return FilterResult(ExclusionReason.KM_MAX)
    kpa = km_per_year(mileage, year, current_year)
    if kpa is not None and kpa > config.km_par_an_max:
        return FilterResult(ExclusionReason.KM_PAR_AN)
    keyword = find_keyword([listing.title, listing.description], config.mots_cles_exclusion)
    if keyword:
        return FilterResult(ExclusionReason.MOT_CLE, keyword)
    if price is None or year is None or mileage is None:
        return FilterResult(ExclusionReason.DONNEES_INCOMPLETES)
    return FilterResult(None)


# ---------- Cote ----------


@dataclass(frozen=True)
class MarketPrice:
    value: float | None
    comparables: tuple[Comparable, ...]
    widened: bool
    reliability: Reliability | None


def _within(c: Comparable, year: int, mileage: int, dy: int, dk: int) -> bool:
    return abs(c.year - year) <= dy and abs(c.mileage_km - mileage) <= dk


def market_price(
    year: int, mileage_km: int, candidates: Sequence[Comparable], comparables_min: int
) -> MarketPrice:
    """Médiane des comparables ; un seul élargissement si leur nombre est insuffisant.

    `candidates` sont déjà du même groupe (marque, modèle, carburant, boîte), dans la fenêtre,
    hors annonce évaluée et hors annonces signalées par un mot-clé.
    """
    strict = tuple(c for c in candidates if _within(c, year, mileage_km, STRICT_YEAR, STRICT_KM))
    if len(strict) >= comparables_min:
        return MarketPrice(statistics.median(c.price_eur for c in strict), strict, False, Reliability.FIABLE)
    wide = tuple(c for c in candidates if _within(c, year, mileage_km, WIDE_YEAR, WIDE_KM))
    if not wide:
        return MarketPrice(None, (), True, None)
    reliability = Reliability.MOYENNE if len(wide) >= comparables_min else Reliability.FAIBLE
    return MarketPrice(statistics.median(c.price_eur for c in wide), wide, True, reliability)


# ---------- Distance ----------


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def road_distance_km(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    return haversine_km(*origin, *destination) * ROAD_FACTOR


# ---------- Marge (interface par régime fiscal) ----------


@dataclass(frozen=True)
class MarginBreakdown:
    resale_eur: float
    negotiation_discount_eur: float
    fees_eur: float
    transport_eur: float
    margin_eur: float


class MarginCalculator(Protocol):
    def compute(
        self, market_price: float, price_eur: int, distance_km: float, config: Config
    ) -> MarginBreakdown: ...


class ParticulierMargin:
    """Particulier, sans TVA : cote × (1 − décote) − prix × (1 + frais) − distance × coût/km."""

    def compute(
        self, market_price: float, price_eur: int, distance_km: float, config: Config
    ) -> MarginBreakdown:
        resale = market_price * (1 - config.decote_negociation_pct / 100)
        fees = price_eur * config.taux_frais_pct / 100
        transport = distance_km * config.cout_transport_eur_km
        return MarginBreakdown(
            resale, market_price - resale, fees, transport, resale - price_eur - fees - transport
        )


MARGIN_CALCULATORS: dict[str, MarginCalculator] = {"particulier": ParticulierMargin()}


# ---------- Niveaux d'alerte ----------


def alert_level(margin_eur: float | None, config: Config) -> AlertLevel | None:
    if margin_eur is None:
        return None
    if margin_eur >= config.marge_prioritaire_eur:
        return AlertLevel.PRIORITAIRE
    if margin_eur >= config.marge_min_eur:
        return AlertLevel.NORMALE
    return None


@dataclass(frozen=True)
class PreviousAlert:
    level: AlertLevel
    price_eur: int | None


def should_alert(level: AlertLevel | None, price_eur: int | None, previous: PreviousAlert | None) -> bool:
    """Une annonce n'est alertée qu'une fois, sauf baisse de prix qui lui fait franchir un seuil."""
    if level is None:
        return False
    if previous is None:
        return True
    dropped = price_eur is not None and previous.price_eur is not None and price_eur < previous.price_eur
    return dropped and level.rank > previous.level.rank


# ---------- Évaluation complète ----------


def evaluate(
    listing: Listing,
    config: Config,
    candidates: Sequence[Comparable],
    base: tuple[float, float],
    now: datetime,
) -> Evaluation:
    fields: dict[str, object] = {
        "source": listing.source,
        "listing_id": listing.listing_id,
        "evaluated_at": now,
        "config_version": config.version,
        "price_eur": listing.price_eur,
        "km_per_year": km_per_year(listing.mileage_km, listing.year, now.year),
    }
    distance = None
    if listing.lat is not None and listing.lon is not None:
        distance = road_distance_km(base, (listing.lat, listing.lon))
    fields["distance_km"] = distance

    result = apply_filters(listing, config, now.year)
    if not result.passed:
        return Evaluation.model_validate(
            {**fields, "exclusion_reason": result.reason, "exclusion_detail": result.detail}
        )

    assert listing.year is not None
    assert listing.mileage_km is not None
    assert listing.price_eur is not None
    mp = market_price(listing.year, listing.mileage_km, candidates, config.comparables_min)
    fields.update(
        comparables_count=len(mp.comparables), comparables_widened=mp.widened, reliability=mp.reliability
    )
    if mp.value is None:
        return Evaluation.model_validate({**fields, "exclusion_reason": ExclusionReason.COTE_INDISPONIBLE})

    # Lieu inconnu : transport compté à 0, la distance reste vide et l'alerte le signale.
    breakdown = MARGIN_CALCULATORS[config.regime_fiscal].compute(
        mp.value, listing.price_eur, distance or 0.0, config
    )
    return Evaluation.model_validate(
        {
            **fields,
            "market_price_eur": mp.value,
            "resale_price_eur": breakdown.resale_eur,
            "negotiation_discount_eur": breakdown.negotiation_discount_eur,
            "fees_eur": breakdown.fees_eur,
            "transport_eur": breakdown.transport_eur,
            "margin_eur": breakdown.margin_eur,
            "alert_level": alert_level(breakdown.margin_eur, config),
        }
    )
