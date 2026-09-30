"""Faux adaptateurs en mémoire pour tester le pipeline de bout en bout."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from car_sourcing.adapters.ports import RawEmail, SentAlert
from car_sourcing.domain.config import Config
from car_sourcing.domain.models import AlertLevel, Comparable, Evaluation, FeedbackStatus, Listing, Source
from car_sourcing.domain.rules import PreviousAlert


def mime(sender: str, html: str, subject: str = "Nouvelles annonces") -> bytes:
    return (
        f"From: {sender}\r\nSubject: {subject}\r\nMIME-Version: 1.0\r\n"
        "Content-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"
    ).encode() + html.encode("utf-8")


@dataclass
class FakeMail:
    emails: list[RawEmail] = field(default_factory=list)
    done: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    latest: datetime | None = None

    def list_unprocessed(self, limit: int) -> list[RawEmail]:
        return [e for e in self.emails if e.message_id not in self.done | self.failed][:limit]

    def mark_processed(self, message_id: str) -> None:
        self.done.add(message_id)

    def mark_failed(self, message_id: str) -> None:
        self.failed.add(message_id)

    def latest_alert_email_at(self) -> datetime | None:
        return self.latest or (max(e.received_at for e in self.emails) if self.emails else None)


@dataclass
class FakeFetcher:
    pages: dict[str, str] = field(default_factory=dict)
    redirects: dict[str, str] = field(default_factory=dict)
    fetched: list[str] = field(default_factory=list)

    def fetch(self, url: str) -> str | None:
        self.fetched.append(url)
        return self.pages.get(url)

    def resolve_redirect(self, url: str) -> str | None:
        return self.redirects.get(url)


@dataclass
class FakeConfig:
    config: Config

    def load(self) -> Config:
        return self.config


@dataclass
class FakeGeocoder:
    places: dict[str, tuple[float, float]] = field(default_factory=dict)

    def geocode(self, postal_code: str | None, city: str | None) -> tuple[float, float] | None:
        return self.places.get(postal_code or "")


@dataclass
class FakeNotifier:
    alerts: list[tuple[Listing, Evaluation]] = field(default_factory=list)
    technical: list[str] = field(default_factory=list)

    def send_alert(self, listing: Listing, evaluation: Evaluation, config: Config) -> SentAlert:
        self.alerts.append((listing, evaluation))
        return SentAlert(len(self.alerts))

    def send_technical(self, text: str) -> None:
        self.technical.append(text)


@dataclass
class FakeRepo:
    listings: dict[str, Listing] = field(default_factory=dict)
    evaluations: list[Evaluation] = field(default_factory=list)
    alerts: list[tuple[str, AlertLevel, int | None, datetime]] = field(default_factory=list)
    feedback: list[tuple[str, FeedbackStatus, int | None]] = field(default_factory=list)
    tech: list[tuple[str, datetime]] = field(default_factory=list)

    def get_listing(self, source: Source, listing_id: str) -> Listing | None:
        return self.listings.get(f"{source.value}:{listing_id}")

    def upsert_listing(self, listing: Listing) -> None:
        old = self.listings.get(listing.key)
        if old is not None:
            listing = listing.model_copy(update={"first_seen_at": old.first_seen_at})
        self.listings[listing.key] = listing

    def comparables_candidates(self, listing: Listing, config: Config, now: datetime) -> list[Comparable]:
        latest = {e.key: e for e in self.evaluations}
        since = now - timedelta(days=config.fenetre_comparables_jours)
        out = []
        for other in self.listings.values():
            ev = latest.get(other.key)
            if (
                other.key == listing.key
                or other.brand_norm != listing.brand_norm
                or other.model_norm != listing.model_norm
                or other.fuel != listing.fuel
                or other.gearbox != listing.gearbox
                or other.last_seen_at < since
                or None in (other.price_eur, other.year, other.mileage_km)
                or (ev is not None and ev.exclusion_reason and ev.exclusion_reason.value == "mot_cle")
            ):
                continue
            assert other.year is not None
            assert other.mileage_km is not None
            assert other.price_eur is not None
            assert listing.year is not None
            assert listing.mileage_km is not None
            if abs(other.year - listing.year) <= 2 and abs(other.mileage_km - listing.mileage_km) <= 40_000:
                out.append(
                    Comparable(
                        source=other.source,
                        listing_id=other.listing_id,
                        price_eur=other.price_eur,
                        year=other.year,
                        mileage_km=other.mileage_km,
                        seller_type=other.seller_type,
                    )
                )
        return out

    def insert_evaluation(self, evaluation: Evaluation) -> None:
        self.evaluations.append(evaluation)

    def last_alert(self, source: Source, listing_id: str) -> PreviousAlert | None:
        mine = [a for a in self.alerts if a[0] == f"{source.value}:{listing_id}"]
        return PreviousAlert(mine[-1][1], mine[-1][2]) if mine else None

    def insert_alert(
        self,
        source: Source,
        listing_id: str,
        level: AlertLevel,
        price_eur: int | None,
        telegram_message_id: int | None,
        sent_at: datetime,
    ) -> None:
        self.alerts.append((f"{source.value}:{listing_id}", level, price_eur, sent_at))

    def insert_feedback(
        self,
        source: Source,
        listing_id: str,
        status: FeedbackStatus,
        purchase_price_eur: int | None,
        author: str | None,
        created_at: datetime,
    ) -> None:
        self.feedback.append((f"{source.value}:{listing_id}", status, purchase_price_eur))

    def last_technical_alert(self, kind: str) -> datetime | None:
        times = [t for k, t in self.tech if k == kind]
        return max(times) if times else None

    def insert_technical_alert(self, kind: str, message: str, sent_at: datetime) -> None:
        self.tech.append((kind, sent_at))
