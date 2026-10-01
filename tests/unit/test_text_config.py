from __future__ import annotations

import pytest

from car_sourcing.domain.config import DEFAULT_KEYWORDS, DEFAULT_PARAMETERS, ConfigError, parse_rows
from car_sourcing.domain.text import find_keyword, normalize, normalize_fuel, normalize_gearbox, parse_int
from tests.conftest import make_config


class TestKeywords:
    @pytest.mark.parametrize(
        "text", ["MOTEUR HS", "moteur hs, à réparer", "Vendue pour PIÈCES", "Vehicule ACCIDENTE"]
    )
    def test_insensible_casse_et_accents(self, text: str) -> None:
        assert find_keyword([text], DEFAULT_KEYWORDS) is not None

    @pytest.mark.parametrize("text", ["Jamais accidentée", "véhicule inaccidenté", "épaves", "vei2"])
    def test_mots_entiers_uniquement(self, text: str) -> None:
        assert find_keyword([text], DEFAULT_KEYWORDS) is None

    def test_espaces_multiples_et_titre(self) -> None:
        assert find_keyword(["Clio", "joint  de\nculasse à faire"], DEFAULT_KEYWORDS) == "joint de culasse"
        assert find_keyword([None, "rien"], DEFAULT_KEYWORDS) is None


def test_normalisations() -> None:
    assert normalize("  Citroën   C3 ") == "citroen c3"
    assert normalize_fuel("Électrique") == "Électrique"
    assert normalize_fuel("Bicarburation essence GPL") == "GPL"
    assert normalize_fuel("Hydrogène") == "Autre"
    assert normalize_gearbox("Boîte automatique") == "Automatique"
    assert normalize_gearbox("manuelle") == "Manuelle"
    assert parse_int("12 500 €") == 12500
    assert parse_int("78\u202f000 km") == 78000
    assert parse_int("") is None


class TestSheet:
    def test_valeurs_initiales_avec_base(self) -> None:
        cfg = make_config()
        assert cfg.cout_transport_eur_km == pytest.approx(0.30)
        assert cfg.vendeur_particulier_uniquement is True
        assert "moteur HS" in cfg.mots_cles_exclusion
        assert len(cfg.version) == 12

    def test_version_change_avec_contenu(self) -> None:
        assert make_config().version != make_config(marge_min_eur="1200").version

    def test_base_manquante_rejetee(self) -> None:
        with pytest.raises(ConfigError, match="base_code_postal"):
            parse_rows(DEFAULT_PARAMETERS, [])

    @pytest.mark.parametrize(
        ("key", "value", "message"),
        [
            ("taux_frais_pct", "dix", "n'est pas un nombre"),
            ("km_max", "200 000,5", "entier"),
            ("vendeur_particulier_uniquement", "peut-être", "VRAI ou FAUX"),
            ("taux_frais_pct", "150", "taux_frais_pct"),
            ("prix_max_eur", "1000", "prix_max_eur doit être supérieur"),
            ("marge_prioritaire_eur", "500", "marge_prioritaire_eur doit être"),
            ("regime_fiscal", "pro_tva_marge", "particulier"),
            ("comparables_min", "", "valeur manquante"),
        ],
    )
    def test_valeur_invalide_rejetee(self, key: str, value: str, message: str) -> None:
        with pytest.raises(ConfigError, match=message):
            make_config(**{key: value})

    def test_parametre_manquant_ou_inconnu(self) -> None:
        rows = [r for r in DEFAULT_PARAMETERS if r[0] not in {"km_max", "base_code_postal"}]
        rows += [("base_code_postal", "69003"), ("inconnu", "1")]
        with pytest.raises(ConfigError) as exc:
            parse_rows(rows, [])
        assert any("km_max" in e for e in exc.value.errors)
        assert any("inconnu" in e for e in exc.value.errors)

    def test_entetes_et_doublons_ignores(self) -> None:
        rows = [
            ("cle", "valeur"),
            *[r for r in DEFAULT_PARAMETERS if r[0] != "base_code_postal"],
            ("base_code_postal", "69003"),
        ]
        cfg = parse_rows(rows, [["mot-clé"], ["Épave"], ["epave"], [""], []])
        assert cfg.mots_cles_exclusion == ("Épave",)
