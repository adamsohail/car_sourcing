from __future__ import annotations

from dataclasses import replace

import pytest

from car_sourcing.domain.models import (
    AlertLevel,
    Comparable,
    ExclusionReason,
    Reliability,
    SellerType,
    Source,
)
from car_sourcing.domain.rules import (
    MARGIN_CALCULATORS,
    PreviousAlert,
    alert_level,
    apply_filters,
    evaluate,
    km_per_year,
    market_price,
    road_distance_km,
    should_alert,
)
from tests.conftest import NOW, make_config, make_listing

LYON = (45.759, 4.861)


def comp(price: int, year: int = 2019, km: int = 70_000, i: int = 0) -> Comparable:
    return Comparable(
        source=Source.LEBONCOIN, listing_id=f"c{i}-{price}", price_eur=price, year=year, mileage_km=km
    )


class TestFilters:
    def test_annonce_valide(self, config) -> None:
        assert apply_filters(make_listing(), config, 2026).passed

    @pytest.mark.parametrize("price", [2000, 30000])
    def test_bornes_de_prix_incluses(self, config, price: int) -> None:
        assert apply_filters(make_listing(price_eur=price), config, 2026).passed

    @pytest.mark.parametrize("price", [1999, 30001])
    def test_prix_hors_bornes(self, config, price: int) -> None:
        assert (
            apply_filters(make_listing(price_eur=price), config, 2026).reason
            is ExclusionReason.PRIX_HORS_BORNES
        )

    def test_vendeur_pro(self, config) -> None:
        pro = make_listing(seller_type=SellerType.PRO)
        assert apply_filters(pro, config, 2026).reason is ExclusionReason.VENDEUR_PRO
        assert apply_filters(pro, make_config(vendeur_particulier_uniquement="FAUX"), 2026).passed

    def test_vendeur_inconnu_accepte(self, config) -> None:
        assert apply_filters(make_listing(seller_type=None), config, 2026).passed

    def test_kilometrage(self, config) -> None:
        assert apply_filters(make_listing(mileage_km=200_000, year=2012), config, 2026).passed
        assert (
            apply_filters(make_listing(mileage_km=200_001, year=2012), config, 2026).reason
            is ExclusionReason.KM_MAX
        )

    def test_km_par_an(self, config) -> None:
        assert apply_filters(
            make_listing(mileage_km=140_000, year=2019), config, 2026
        ).passed  # 20 000/an pile
        assert (
            apply_filters(make_listing(mileage_km=140_007, year=2019), config, 2026).reason
            is ExclusionReason.KM_PAR_AN
        )

    def test_km_par_an_vehicule_de_l_annee(self) -> None:
        assert km_per_year(15_000, 2026, 2026) == 15_000
        assert km_per_year(15_000, 2027, 2026) == 15_000
        assert km_per_year(None, 2020, 2026) is None

    def test_mot_cle(self, config) -> None:
        res = apply_filters(make_listing(description="Vendue pour Pièces"), config, 2026)
        assert res.reason is ExclusionReason.MOT_CLE
        assert res.detail == "pour pièces"

    def test_mot_cle_dans_le_titre(self, config) -> None:
        res = apply_filters(make_listing(title="Clio ÉPAVE", description=None), config, 2026)
        assert res.reason is ExclusionReason.MOT_CLE

    @pytest.mark.parametrize("field", ["price_eur", "year", "mileage_km"])
    def test_donnees_incompletes(self, config, field: str) -> None:
        assert (
            apply_filters(make_listing(**{field: None}), config, 2026).reason
            is ExclusionReason.DONNEES_INCOMPLETES
        )

    def test_ordre_premier_motif(self, config) -> None:
        listing = make_listing(price_eur=1500, seller_type=SellerType.PRO, description="épave")
        assert apply_filters(listing, config, 2026).reason is ExclusionReason.PRIX_HORS_BORNES


class TestMarketPrice:
    def test_mediane_stricte(self) -> None:
        cands = [comp(p, i=i) for i, p in enumerate([9000, 9500, 10000, 10500, 11000])]
        mp = market_price(2019, 70_000, cands, 5)
        assert mp.value == 10_000
        assert mp.reliability is Reliability.FIABLE
        assert not mp.widened

    def test_elargissement_une_fois(self) -> None:
        cands = [
            comp(9000),
            comp(9400, year=2021, i=1),
            comp(9800, km=105_000, i=2),
            comp(9900, year=2017, i=3),
            comp(10200, km=40_000, i=4),
            comp(20000, year=2015, i=5),
        ]
        mp = market_price(2019, 70_000, cands, 5)
        assert mp.widened
        assert mp.reliability is Reliability.MOYENNE
        assert len(mp.comparables) == 5
        assert mp.value == 9800

    def test_fiabilite_faible_et_absence(self) -> None:
        assert market_price(2019, 70_000, [comp(9000)], 5).reliability is Reliability.FAIBLE
        none = market_price(2019, 70_000, [comp(9000, year=2010)], 5)
        assert none.value is None
        assert none.reliability is None


class TestMarginAndLevels:
    def test_marge_nominale_frais_et_transport(self, config) -> None:
        b = MARGIN_CALCULATORS["particulier"].compute(12_000, 8_000, 100, config)
        assert b.resale_eur == pytest.approx(11_280)
        assert b.negotiation_discount_eur == pytest.approx(720)
        assert b.fees_eur == pytest.approx(800)
        assert b.transport_eur == pytest.approx(30)
        assert b.margin_eur == pytest.approx(11_280 - 8_000 - 800 - 30)

    @pytest.mark.parametrize(
        ("margin", "level"),
        [
            (999, None),
            (999.99, None),
            (1000, AlertLevel.NORMALE),
            (1999, AlertLevel.NORMALE),
            (2000, AlertLevel.PRIORITAIRE),
            (None, None),
        ],
    )
    def test_seuils(self, config, margin: float | None, level: AlertLevel | None) -> None:
        assert alert_level(margin, config) is level

    def test_distance_routiere(self) -> None:
        paris, lyon = (48.857, 2.352), (45.764, 4.836)
        assert road_distance_km(paris, lyon) == pytest.approx(392 * 1.3, rel=0.02)

    def test_alerte_unique_sauf_baisse_de_prix(self) -> None:
        prev = PreviousAlert(AlertLevel.NORMALE, 9000)
        assert should_alert(AlertLevel.NORMALE, 9000, None)
        assert not should_alert(None, 9000, None)
        assert not should_alert(AlertLevel.NORMALE, 8500, prev)
        assert not should_alert(AlertLevel.PRIORITAIRE, 9000, prev)
        assert should_alert(AlertLevel.PRIORITAIRE, 8500, prev)
        assert not should_alert(AlertLevel.PRIORITAIRE, 8000, replace(prev, level=AlertLevel.PRIORITAIRE))


class TestEvaluate:
    def test_evaluation_complete(self, config) -> None:
        cands = [comp(p, i=i) for i, p in enumerate([11000, 11500, 12000, 12500, 13000])]
        ev = evaluate(make_listing(lat=45.19, lon=5.72), config, cands, LYON, NOW)
        assert ev.exclusion_reason is None
        assert ev.market_price_eur == 12_000
        assert ev.comparables_count == 5
        assert ev.distance_km == pytest.approx(road_distance_km(LYON, (45.19, 5.72)))
        expected = 12_000 * 0.94 - 8_000 * 1.1 - ev.distance_km * 0.30
        assert ev.margin_eur == pytest.approx(expected)
        assert ev.alert_level is AlertLevel.PRIORITAIRE
        assert ev.config_version == config.version

    def test_exclue_sans_calcul(self, config) -> None:
        ev = evaluate(make_listing(description="moteur HS"), config, [comp(12000)], LYON, NOW)
        assert ev.exclusion_reason is ExclusionReason.MOT_CLE
        assert ev.margin_eur is None
        assert ev.alert_level is None

    def test_sans_comparable(self, config) -> None:
        ev = evaluate(make_listing(), config, [], LYON, NOW)
        assert ev.exclusion_reason is ExclusionReason.COTE_INDISPONIBLE

    def test_lieu_inconnu_transport_nul(self, config) -> None:
        cands = [comp(12000, i=i) for i in range(5)]
        ev = evaluate(make_listing(lat=None, lon=None), config, cands, LYON, NOW)
        assert ev.distance_km is None
        assert ev.transport_eur == 0
