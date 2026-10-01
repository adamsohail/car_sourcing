"""Réglages saisis dans l'interface : validation par champ, versions, conflits et aperçu d'impact."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from car_sourcing.demo import DemoGeocoder, DemoRepository, DemoTelegram, demo_config, seed
from car_sourcing.domain.config import (
    NO_CONFIG_MESSAGE,
    ConfigError,
    config_from_payload,
    errors_by_field,
    payload_from_config,
)
from car_sourcing.domain.models import AlertLevel, SellerType
from car_sourcing.domain.rules import reprice
from car_sourcing.settings import Settings
from car_sourcing.web.app import Deps, create_app
from tests.conftest import make_config, make_listing


def test_aller_retour_payload() -> None:
    cfg = make_config()
    again = config_from_payload(payload_from_config(cfg))
    assert again == cfg
    assert again.version == cfg.version


def test_payload_depuis_le_formulaire() -> None:
    payload = payload_from_config(make_config())
    payload["params"] = {
        k: str(v).replace(".", ",") if isinstance(v, float) else v for k, v in payload["params"].items()
    }
    payload["params"]["vendeur_particulier_uniquement"] = False
    cfg = config_from_payload(payload)
    assert cfg.vendeur_particulier_uniquement is False
    assert cfg.cout_transport_eur_km == pytest.approx(0.30)


def test_erreurs_par_champ() -> None:
    payload = payload_from_config(make_config())
    payload["params"].update(taux_frais_pct="dix", base_code_postal="123", marge_prioritaire_eur=500)
    with pytest.raises(ConfigError) as exc:
        config_from_payload(payload)
    fields = errors_by_field(exc.value.errors)
    assert set(fields) == {"taux_frais_pct", "base_code_postal"}
    payload["params"].update(taux_frais_pct=10, base_code_postal="69003")
    with pytest.raises(ConfigError) as exc2:
        config_from_payload(payload)
    assert "marge_prioritaire_eur" in errors_by_field(exc2.value.errors)
    with pytest.raises(ConfigError):
        config_from_payload({"params": "x"})


def test_recalcul_pour_l_apercu() -> None:
    cfg = make_config()
    listing = make_listing(price_eur=8000)
    assert reprice(listing, 12000, 10, cfg, 2026) is AlertLevel.PRIORITAIRE
    assert reprice(listing, 10000, 10, cfg, 2026) is None
    assert reprice(listing, 10000, 10, make_config(marge_min_eur="500"), 2026) is AlertLevel.NORMALE
    assert reprice(make_listing(seller_type=SellerType.PRO), 20000, 0, cfg, 2026) is None
    assert reprice(listing, None, 0, cfg, 2026) is None


@pytest.fixture
def client() -> tuple[TestClient, DemoRepository]:
    repo = DemoRepository()
    seed(repo, demo_config(), n=300)
    repo.configs.clear()  # comme au premier démarrage : aucun réglage enregistré
    settings = Settings(
        web_password=SecretStr("demo"), session_secret=SecretStr("z" * 32), cookie_secure=False
    )
    c = TestClient(
        create_app(
            Deps(
                settings=settings,
                repo=repo,
                telegram=DemoTelegram(),
                config_loader=repo.load_config,
                geocoder=DemoGeocoder(),
            )
        )
    )
    c.post("/api/login", json={"password": "demo"})
    return c, repo


def test_premier_demarrage_puis_enregistrement(client) -> None:
    c, repo = client
    body = c.get("/api/config").json()
    assert body["config"] is None
    assert body["errors"] == [NO_CONFIG_MESSAGE]
    assert body["meta"] is None
    draft = body["draft"]
    assert draft["params"]["base_code_postal"] == ""
    assert draft["params"]["vendeur_particulier_uniquement"] is True

    res = c.post("/api/config", json={**draft, "based_on": 0})
    assert res.status_code == 422
    assert "base_code_postal" in res.json()["detail"]["errors"]

    draft["params"]["base_code_postal"] = "69003"
    res = c.post("/api/config", json={**draft, "based_on": 0})
    assert res.status_code == 200
    assert res.json()["meta"]["number"] == 1
    assert repo.load_config().base_code_postal == "69003"
    after = c.get("/api/config").json()
    assert after["errors"] is None
    assert after["meta"]["number"] == 1

    # Un second enregistrement basé sur une version périmée est refusé.
    assert c.post("/api/config", json={**draft, "based_on": 0}).status_code == 409
    assert c.post("/api/config", json={**draft, "based_on": 1}).json()["meta"]["number"] == 2


def test_apercu_d_impact(client) -> None:
    c, _ = client
    draft = c.get("/api/config").json()["draft"]
    draft["params"]["base_code_postal"] = "69003"
    base = c.post("/api/config/preview", json=draft).json()
    draft["params"]["marge_min_eur"] = "300"
    looser = c.post("/api/config/preview", json=draft).json()
    assert looser["n"] >= base["n"]
    assert base["current"] >= 0
    draft["params"]["marge_min_eur"] = "abc"
    assert c.post("/api/config/preview", json=draft).status_code == 422
