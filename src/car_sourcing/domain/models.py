"""Modèles métier purs. Aucune dépendance externe hormis Pydantic."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from car_sourcing.domain.text import normalize


class Source(StrEnum):
    LEBONCOIN = "leboncoin"
    LACENTRALE = "lacentrale"
    MANUEL = "manuel"


class SellerType(StrEnum):
    PARTICULIER = "particulier"
    PRO = "pro"


class Fuel(StrEnum):
    ESSENCE = "Essence"
    DIESEL = "Diesel"
    HYBRIDE = "Hybride"
    ELECTRIQUE = "Électrique"
    GPL = "GPL"
    AUTRE = "Autre"


class Gearbox(StrEnum):
    MANUELLE = "Manuelle"
    AUTOMATIQUE = "Automatique"


class EnrichmentStatus(StrEnum):
    EMAIL_SEUL = "email_seul"
    ENRICHI = "enrichi"
    DETAIL_INDISPONIBLE = "detail_indisponible"


class ExclusionReason(StrEnum):
    PRIX_HORS_BORNES = "prix_hors_bornes"
    VENDEUR_PRO = "vendeur_pro"
    KM_MAX = "km_max"
    KM_PAR_AN = "km_par_an"
    MOT_CLE = "mot_cle"
    DONNEES_INCOMPLETES = "donnees_incompletes"
    COTE_INDISPONIBLE = "cote_indisponible"


class Reliability(StrEnum):
    FIABLE = "fiable"
    MOYENNE = "moyenne"
    FAIBLE = "faible"


class AlertLevel(StrEnum):
    NORMALE = "normale"
    PRIORITAIRE = "prioritaire"

    @property
    def rank(self) -> int:
        return 2 if self is AlertLevel.PRIORITAIRE else 1


class FeedbackStatus(StrEnum):
    INTERESSANT = "interessant"
    PAS_INTERESSANT = "pas_interessant"
    ACHETE = "achete"
    AUCUN = "aucun"  # avis retiré


class Listing(BaseModel):
    """Une annonce unique, identifiée par `source` + `listing_id`."""

    model_config = ConfigDict(frozen=True)

    source: Source
    listing_id: str = Field(min_length=1)
    url: str
    title: str | None = None
    brand: str | None = None
    model: str | None = None
    version: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    mileage_km: int | None = Field(default=None, ge=0)
    fuel: Fuel | None = None
    gearbox: Gearbox | None = None
    price_eur: int | None = Field(default=None, ge=0)
    seller_type: SellerType | None = None
    city: str | None = None
    postal_code: str | None = None
    lat: float | None = None
    lon: float | None = None
    description: str | None = None
    photo_url: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    enrichment_status: EnrichmentStatus = EnrichmentStatus.EMAIL_SEUL

    @property
    def key(self) -> str:
        return f"{self.source.value}:{self.listing_id}"

    @property
    def brand_norm(self) -> str | None:
        return normalize(self.brand) if self.brand else None

    @property
    def model_norm(self) -> str | None:
        return normalize(self.model) if self.model else None

    @property
    def display_name(self) -> str:
        parts = [p for p in (self.brand, self.model) if p]
        return " ".join(parts) if parts else (self.title or self.listing_id)


class Comparable(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Source
    listing_id: str
    price_eur: int
    year: int
    mileage_km: int
    seller_type: SellerType | None = None
    city: str | None = None


class Evaluation(BaseModel):
    """Résultat de l'évaluation d'une annonce avec une version de configuration."""

    model_config = ConfigDict(frozen=True)

    source: Source
    listing_id: str
    evaluated_at: datetime
    config_version: str
    exclusion_reason: ExclusionReason | None = None
    exclusion_detail: str | None = None
    km_per_year: float | None = None
    distance_km: float | None = None
    market_price_eur: float | None = None
    resale_price_eur: float | None = None
    negotiation_discount_eur: float | None = None
    comparables_count: int = 0
    comparables_widened: bool = False
    reliability: Reliability | None = None
    fees_eur: float | None = None
    transport_eur: float | None = None
    margin_eur: float | None = None
    alert_level: AlertLevel | None = None
    price_eur: int | None = None

    @property
    def key(self) -> str:
        return f"{self.source.value}:{self.listing_id}"
