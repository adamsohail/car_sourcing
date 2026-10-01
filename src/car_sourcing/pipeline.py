"""Orchestration d'un run d'ingestion. Une erreur sur une annonce ne bloque jamais le run."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from car_sourcing.adapters.ports import (
    ConfigSource,
    Geocoder,
    MailSource,
    Notifier,
    PageFetcher,
    RawEmail,
    Repository,
)
from car_sourcing.domain.config import Config, ConfigError
from car_sourcing.domain.models import EnrichmentStatus, Evaluation, Listing
from car_sourcing.domain.rules import evaluate, should_alert
from car_sourcing.domain.text import normalize_fuel, normalize_gearbox
from car_sourcing.parsers.base import (
    EmailListing,
    EmailParseError,
    PageDetails,
    PageParseError,
    html_from_mime,
)
from car_sourcing.parsers.emails import EmailFormat, detect_format, parse_alert_email
from car_sourcing.parsers.pages import parse_page
from car_sourcing.settings import Settings, log

logger = logging.getLogger(__name__)
TECH_ALERT_COOLDOWN = timedelta(hours=6)


@dataclass
class RunStats:
    emails: int = 0
    emails_skipped: int = 0
    listings_seen: int = 0
    new_listings: int = 0
    price_changes: int = 0
    alerts_sent: int = 0
    parse_attempts: int = 0
    parse_failures: int = 0
    item_errors: int = 0
    capped: bool = False
    failures: list[str] = field(default_factory=list)

    @property
    def parse_failure_ratio(self) -> float:
        return self.parse_failures / self.parse_attempts if self.parse_attempts else 0.0


def merge_listing(
    item: EmailListing, page: PageDetails | None, status: EnrichmentStatus, now: datetime
) -> Listing:
    """Les données de la page complètent et corrigent celles de l'email."""
    p = page or PageDetails()

    def pick(page_value: object, email_value: object) -> object:
        return page_value if page_value not in (None, "") else email_value

    return Listing.model_validate(
        {
            "source": item.source,
            "listing_id": item.listing_id,
            "url": item.url,
            "title": pick(p.title, item.title),
            "brand": p.brand,
            "model": p.model,
            "version": p.version,
            "year": pick(p.year, item.year),
            "mileage_km": pick(p.mileage_km, item.mileage_km),
            "fuel": normalize_fuel(str(pick(p.fuel, item.fuel) or "")) or None,
            "gearbox": normalize_gearbox(str(pick(p.gearbox, item.gearbox) or "")) or None,
            "price_eur": pick(p.price_eur, item.price_eur),
            "seller_type": p.seller_type,
            "city": pick(p.city, item.city),
            "postal_code": pick(p.postal_code, item.postal_code),
            "lat": p.lat,
            "lon": p.lon,
            "description": p.description,
            "photo_url": pick(p.photo_url, item.photo_url),
            "first_seen_at": now,
            "last_seen_at": now,
            "enrichment_status": status,
        }
    )


class Pipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        mail: MailSource,
        fetcher: PageFetcher,
        repo: Repository,
        config_source: ConfigSource,
        geocoder: Geocoder,
        notifier: Notifier,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.s, self.mail, self.fetcher, self.repo = settings, mail, fetcher, repo
        self.config_source, self.geocoder, self.notifier, self.clock = (
            config_source,
            geocoder,
            notifier,
            clock,
        )

    # ---------- Point d'entrée ----------

    def run(self) -> RunStats:
        stats = RunStats()
        try:
            config = self.config_source.load()
        except ConfigError as exc:
            self.technical_alert(
                "reglages_invalides",
                "Réglages invalides ou absents, aucune annonce traitée :\n- "
                + "\n- ".join(exc.errors)
                + (
                    f"\nÀ corriger dans la page Réglages : {self.s.public_base_url}/#/reglages"
                    if self.s.public_base_url
                    else ""
                ),
            )
            raise
        base = self.geocoder.geocode(config.base_code_postal, None)
        if base is None:
            raise RuntimeError(f"code postal de la base introuvable : {config.base_code_postal}")
        for email in self.mail.list_unprocessed(self.s.max_emails_per_run):
            if stats.new_listings >= self.s.max_new_listings_per_run:
                stats.capped = True  # le reste sera traité au prochain run
                break
            self.process_email(email, config, base, stats)
        self.supervise(stats)
        log(
            logger,
            logging.INFO,
            "run terminé",
            **{k: v for k, v in stats.__dict__.items() if k != "failures"},
            parse_failure_ratio=round(stats.parse_failure_ratio, 3),
        )
        return stats

    def process_email(
        self, email: RawEmail, config: Config, base: tuple[float, float], stats: RunStats
    ) -> None:
        fmt = detect_format(email.sender)
        if fmt is None:
            stats.emails_skipped += 1
            self.mail.mark_processed(email.message_id)
            return
        stats.emails += 1
        stats.parse_attempts += 1
        html = html_from_mime(email.raw)
        try:
            parsed = parse_alert_email(html, fmt)
            if parsed.unresolved_links:
                resolved = {u: r for u in parsed.unresolved_links if (r := self.fetcher.resolve_redirect(u))}
                parsed = parse_alert_email(html, fmt, resolved)
        except EmailParseError as exc:
            stats.parse_failures += 1
            stats.failures.append(f"email {email.message_id} : {exc.reason}")
            log(
                logger,
                logging.ERROR,
                "email illisible",
                message_id=email.message_id,
                subject=email.subject,
                reason=exc.reason,
            )
            self.mail.mark_failed(email.message_id)
            return
        stats.parse_failures += len(parsed.block_errors)
        stats.parse_attempts += len(parsed.block_errors)
        for item in parsed.listings:
            stats.listings_seen += 1
            try:
                self.process_item(item, fmt, config, base, stats)
            except Exception as exc:  # une annonce en erreur ne bloque jamais le run
                stats.item_errors += 1
                log(
                    logger,
                    logging.ERROR,
                    "annonce en erreur",
                    listing=f"{item.source.value}:{item.listing_id}",
                    error=repr(exc),
                )
        self.mail.mark_processed(email.message_id)

    # ---------- Une annonce ----------

    def process_item(
        self, item: EmailListing, fmt: EmailFormat, config: Config, base: tuple[float, float], stats: RunStats
    ) -> None:
        now = self.clock()
        key = f"{item.source.value}:{item.listing_id}"
        existing = self.repo.get_listing(item.source, item.listing_id)
        if existing is not None:
            price_changed = item.price_eur is not None and item.price_eur != existing.price_eur
            listing = existing.model_copy(
                update={"last_seen_at": now, **({"price_eur": item.price_eur} if price_changed else {})}
            )
            self.repo.upsert_listing(listing)
            if not price_changed:
                log(logger, logging.INFO, "annonce déjà vue", listing=key, outcome="doublon")
                return
            stats.price_changes += 1
        else:
            listing = self.enrich(item, stats, now)
            if listing.lat is None:
                coords = self.geocoder.geocode(listing.postal_code, listing.city)
                if coords:
                    listing = listing.model_copy(update={"lat": coords[0], "lon": coords[1]})
            self.repo.upsert_listing(listing)
            stats.new_listings += 1
        candidates = self.repo.comparables_candidates(listing, config, now)
        ev = evaluate(listing, config, candidates, base, now)
        self.repo.insert_evaluation(ev)
        self.maybe_alert(listing, ev, config, stats)
        log(
            logger,
            logging.INFO,
            "annonce évaluée",
            listing=key,
            outcome=ev.exclusion_reason or ev.alert_level or "sous_seuil",
            margin=round(ev.margin_eur) if ev.margin_eur is not None else None,
            comparables=ev.comparables_count,
        )

    def enrich(self, item: EmailListing, stats: RunStats, now: datetime) -> Listing:
        html = self.fetcher.fetch(item.url)
        if html is None:
            return merge_listing(item, None, EnrichmentStatus.DETAIL_INDISPONIBLE, now)
        stats.parse_attempts += 1
        try:
            page = parse_page(item.source, html)
        except PageParseError as exc:
            stats.parse_failures += 1
            stats.failures.append(f"page {item.url} : {exc.reason}")
            return merge_listing(item, None, EnrichmentStatus.DETAIL_INDISPONIBLE, now)
        return merge_listing(item, page, EnrichmentStatus.ENRICHI, now)

    def maybe_alert(self, listing: Listing, ev: Evaluation, config: Config, stats: RunStats) -> None:
        previous = self.repo.last_alert(listing.source, listing.listing_id)
        if not should_alert(ev.alert_level, listing.price_eur, previous) or ev.alert_level is None:
            return
        if self.s.dry_run:
            log(logger, logging.INFO, "alerte simulée", listing=listing.key)
            return
        sent = self.notifier.send_alert(listing, ev, config)
        self.repo.insert_alert(
            listing.source,
            listing.listing_id,
            ev.alert_level,
            listing.price_eur,
            sent.message_id,
            self.clock(),
        )
        stats.alerts_sent += 1

    # ---------- Supervision ----------

    def technical_alert(self, kind: str, message: str) -> None:
        now = self.clock()
        last = self.repo.last_technical_alert(kind)
        if last is not None and now - last < TECH_ALERT_COOLDOWN:
            return
        self.notifier.send_technical(message)
        self.repo.insert_technical_alert(kind, message, now)

    def supervise(self, stats: RunStats) -> None:
        if stats.parse_attempts >= 5 and stats.parse_failure_ratio > self.s.parse_failure_alert_ratio:
            details = "\n".join(stats.failures[:5])
            self.technical_alert(
                "parsing",
                f"{stats.parse_failure_ratio:.0%} d'échecs de parsing sur ce run "
                f"({stats.parse_failures}/{stats.parse_attempts}).\n{details}",
            )
        latest = self.mail.latest_alert_email_at()
        if latest is None or self.clock() - latest > timedelta(hours=self.s.no_email_alert_hours):
            since = latest.strftime("%d/%m %H:%M") if latest else "jamais"
            self.technical_alert(
                "aucun_email",
                f"Aucun email d'alerte reçu depuis {self.s.no_email_alert_hours} h "
                f"(dernier : {since}). Vérifiez les alertes Leboncoin et La Centrale.",
            )
