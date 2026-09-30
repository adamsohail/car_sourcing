"""Interfaces entre la logique et les services externes. Les tests les remplacent par des faux."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from car_sourcing.domain.config import Config
from car_sourcing.domain.models import AlertLevel, Comparable, Evaluation, FeedbackStatus, Listing, Source
from car_sourcing.domain.rules import PreviousAlert


@dataclass(frozen=True)
class RawEmail:
    message_id: str
    sender: str
    subject: str
    received_at: datetime
    raw: bytes


class MailSource(Protocol):
    def list_unprocessed(self, limit: int) -> list[RawEmail]: ...
    def mark_processed(self, message_id: str) -> None: ...
    def mark_failed(self, message_id: str) -> None: ...
    def latest_alert_email_at(self) -> datetime | None: ...


class PageFetcher(Protocol):
    def fetch(self, url: str) -> str | None: ...
    def resolve_redirect(self, url: str) -> str | None: ...


class ConfigSource(Protocol):
    def load(self) -> Config: ...


class Geocoder(Protocol):
    def geocode(self, postal_code: str | None, city: str | None) -> tuple[float, float] | None: ...


@dataclass(frozen=True)
class SentAlert:
    message_id: int | None


class Notifier(Protocol):
    def send_alert(self, listing: Listing, evaluation: Evaluation, config: Config) -> SentAlert: ...
    def send_technical(self, text: str) -> None: ...


class Repository(Protocol):
    def get_listing(self, source: Source, listing_id: str) -> Listing | None: ...
    def upsert_listing(self, listing: Listing) -> None: ...
    def comparables_candidates(
        self, listing: Listing, config: Config, now: datetime
    ) -> Sequence[Comparable]: ...
    def insert_evaluation(self, evaluation: Evaluation) -> None: ...
    def last_alert(self, source: Source, listing_id: str) -> PreviousAlert | None: ...
    def insert_alert(
        self,
        source: Source,
        listing_id: str,
        level: AlertLevel,
        price_eur: int | None,
        telegram_message_id: int | None,
        sent_at: datetime,
    ) -> None: ...
    def insert_feedback(
        self,
        source: Source,
        listing_id: str,
        status: FeedbackStatus,
        purchase_price_eur: int | None,
        author: str | None,
        created_at: datetime,
    ) -> None: ...
    def last_technical_alert(self, kind: str) -> datetime | None: ...
    def insert_technical_alert(self, kind: str, message: str, sent_at: datetime) -> None: ...
