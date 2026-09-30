"""Pipeline de bout en bout avec des faux adaptateurs."""

from __future__ import annotations

from datetime import timedelta

import pytest

from car_sourcing.adapters.ports import RawEmail
from car_sourcing.domain.config import ConfigError
from car_sourcing.domain.models import AlertLevel, EnrichmentStatus, ExclusionReason, SellerType, Source
from car_sourcing.pipeline import Pipeline
from car_sourcing.settings import Settings
from tests.conftest import FIXTURES, NOW, make_config, make_listing
from tests.fakes import FakeConfig, FakeFetcher, FakeGeocoder, FakeMail, FakeNotifier, FakeRepo, mime

LBC_SENDER = "leboncoin <no-reply@leboncoin.fr>"
PAGE_URL = "https://www.leboncoin.fr/ad/voitures/2845123456"


def seed_market(repo: FakeRepo) -> None:
    """Six Peugeot 208 essence manuelles de 2019, autour de 13 000 €."""
    for i, (price, km) in enumerate(
        [(12800, 70000), (13000, 65000), (13200, 80000), (12900, 75000), (13100, 60000), (13400, 72000)]
    ):
        repo.upsert_listing(
            make_listing(
                listing_id=f"m{i}",
                price_eur=price,
                mileage_km=km,
                seller_type=SellerType.PRO,
                first_seen_at=NOW - timedelta(days=10),
                last_seen_at=NOW - timedelta(days=5),
            )
        )


def build(repo: FakeRepo | None = None, mail: FakeMail | None = None, **cfg: str):
    repo = repo or FakeRepo()
    mail = mail or FakeMail()
    fetcher = FakeFetcher(pages={PAGE_URL: (FIXTURES / "pages/leboncoin/synthetique_01.html").read_text()})
    notifier = FakeNotifier()
    pipeline = Pipeline(
        settings=Settings(http_min_delay_s=0, http_max_delay_s=0),
        mail=mail,
        fetcher=fetcher,
        repo=repo,
        config_source=FakeConfig(make_config(**cfg)),
        geocoder=FakeGeocoder({"69003": (45.759, 4.861), "69100": (45.77, 4.88)}),
        notifier=notifier,
        clock=lambda: NOW,
    )
    return pipeline, repo, mail, fetcher, notifier


def alert_email(message_id: str = "e1") -> RawEmail:
    html = (FIXTURES / "emails/leboncoin/synthetique_01.html").read_text()
    return RawEmail(
        message_id, LBC_SENDER, "Nouvelles annonces", NOW - timedelta(minutes=3), mime(LBC_SENDER, html)
    )


def test_un_email_produit_une_alerte_et_un_second_run_aucune() -> None:
    pipeline, repo, mail, _, notifier = build()
    seed_market(repo)
    mail.emails.append(alert_email())

    stats = pipeline.run()
    assert stats.emails == 1
    assert stats.new_listings == 3
    assert stats.alerts_sent == 1
    listing, ev = notifier.alerts[0]
    assert listing.listing_id == "2845123456"
    assert listing.enrichment_status is EnrichmentStatus.ENRICHI
    assert listing.seller_type is SellerType.PARTICULIER
    assert ev.alert_level is AlertLevel.PRIORITAIRE
    assert ev.comparables_count == 6
    assert "e1" in mail.done
    assert len(repo.evaluations) == 3

    # Second run : l'email est marqué traité, rien n'est renvoyé.
    stats2 = pipeline.run()
    assert stats2.emails == 0
    assert len(notifier.alerts) == 1


def test_email_retraite_sans_doublon() -> None:
    pipeline, repo, mail, _, notifier = build()
    seed_market(repo)
    mail.emails.append(alert_email("e1"))
    pipeline.run()
    mail.emails.append(alert_email("e2"))  # même contenu, autre email
    stats = pipeline.run()
    assert stats.new_listings == 0
    assert stats.alerts_sent == 0
    assert len(notifier.alerts) == 1
    assert len(repo.listings) == 9


def test_page_inaccessible_repli_sur_l_email() -> None:
    pipeline, repo, mail, fetcher, _ = build()
    fetcher.pages.clear()
    mail.emails.append(alert_email())
    pipeline.run()
    listing = repo.listings["leboncoin:2845123456"]
    assert listing.enrichment_status is EnrichmentStatus.DETAIL_INDISPONIBLE
    assert listing.price_eur == 8900
    assert listing.lat == pytest.approx(45.759)  # géocodé depuis le code postal de l'email


def test_baisse_de_prix_qui_franchit_un_seuil() -> None:
    pipeline, repo, mail, _, notifier = build(marge_prioritaire_eur="3000")
    seed_market(repo)
    mail.emails.append(alert_email("e1"))
    pipeline.run()
    assert notifier.alerts[0][1].alert_level is AlertLevel.NORMALE
    cheaper = (FIXTURES / "emails/leboncoin/synthetique_01.html").read_text().replace("8 900 €", "7 900 €")
    mail.emails.append(RawEmail("e2", LBC_SENDER, "x", NOW, mime(LBC_SENDER, cheaper)))
    stats = pipeline.run()
    assert stats.price_changes == 1
    assert stats.alerts_sent == 1
    assert notifier.alerts[1][1].alert_level is AlertLevel.PRIORITAIRE


def test_email_illisible_et_alerte_de_taux_d_echec() -> None:
    pipeline, _, mail, _, notifier = build()
    for i in range(5):
        mail.emails.append(RawEmail(f"x{i}", LBC_SENDER, "Promo", NOW, mime(LBC_SENDER, "<p>Newsletter</p>")))
    stats = pipeline.run()
    assert stats.parse_failures == 5
    assert mail.failed == {f"x{i}" for i in range(5)}
    assert any("échecs de parsing" in t for t in notifier.technical)


def test_expediteur_inconnu_ignore() -> None:
    pipeline, repo, mail, _, _ = build()
    mail.emails.append(
        RawEmail("z", "banque@example.com", "Relevé", NOW, mime("banque@example.com", "<p>x</p>"))
    )
    stats = pipeline.run()
    assert stats.emails_skipped == 1
    assert "z" in mail.done
    assert not repo.listings


def test_sheet_invalide_bloque_le_run() -> None:
    pipeline, _, _, _, notifier = build()

    class Broken:
        def load(self):
            raise ConfigError(["taux_frais_pct : « dix » n'est pas un nombre"])

    pipeline.config_source = Broken()
    with pytest.raises(ConfigError):
        pipeline.run()
    assert "taux_frais_pct" in notifier.technical[0]
    with pytest.raises(ConfigError):
        pipeline.run()
    assert len(notifier.technical) == 1  # pas de répétition avant 6 h


def test_aucun_email_depuis_24h() -> None:
    pipeline, _, mail, _, notifier = build()
    mail.latest = NOW - timedelta(hours=30)
    pipeline.run()
    assert any("Aucun email" in t for t in notifier.technical)


def test_annonce_exclue_ne_sert_pas_de_comparable() -> None:
    pipeline, repo, mail, _, _ = build()
    seed_market(repo)
    html = (
        (FIXTURES / "emails/leboncoin/synthetique_01.html")
        .read_text()
        .replace("Renault Clio IV dCi 90", "Renault Clio épave")
    )
    mail.emails.append(RawEmail("e1", LBC_SENDER, "x", NOW, mime(LBC_SENDER, html)))
    pipeline.run()
    clio = next(e for e in repo.evaluations if e.listing_id == "2845123457")
    assert clio.exclusion_reason is ExclusionReason.MOT_CLE
    assert repo.listings["leboncoin:2845123457"].source is Source.LEBONCOIN
