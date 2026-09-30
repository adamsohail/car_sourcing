"""Contrat de l'API utilisée par l'interface, vérifié sur le dépôt de démonstration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from car_sourcing.demo import DemoGeocoder, DemoRepository, DemoTelegram, demo_config, seed
from car_sourcing.settings import Settings
from car_sourcing.web.app import Deps, create_app

EV_KEYS = {
    "kmAn",
    "motif",
    "distance",
    "cote",
    "n",
    "widened",
    "fiabilite",
    "niveau",
    "statut",
    "revente",
    "decote",
    "frais",
    "transport",
    "marge",
    "configVersion",
    "evaluatedAt",
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    repo = DemoRepository()
    seed(repo, demo_config(), n=400)
    settings = Settings(
        web_password=SecretStr("demo"), session_secret=SecretStr("y" * 32), cookie_secure=False
    )
    app = create_app(
        Deps(
            settings=settings,
            repo=repo,
            telegram=DemoTelegram(),
            config_loader=demo_config,
            geocoder=DemoGeocoder(),
        )
    )
    c = TestClient(app)
    assert c.post("/api/login", json={"password": "demo"}).status_code == 200
    return c


def test_opportunites(client: TestClient) -> None:
    items = client.get("/api/opportunities?period=30").json()["items"]
    assert items
    first = items[0]
    assert set(first["ev"]) == EV_KEYS
    assert first["ev"]["statut"] == "alerte"
    assert first["id"].count(":") == 1
    margins = [i["ev"]["marge"] for i in items]
    assert margins == sorted(margins, reverse=True)


def test_recherche_et_compteurs(client: TestClient) -> None:
    body = client.get("/api/listings?q=peugeot&statut=all&limit=10").json()
    assert body["total"] == sum(body["counts"].values())
    assert len(body["items"]) <= 10
    assert all("peugeot" in i["titre"].lower() for i in body["items"])
    excl = client.get("/api/listings?statut=exclue").json()["items"]
    assert all(i["ev"]["statut"] == "exclue" for i in excl)
    assert client.get("/api/listings?statut=nimporte").status_code == 400


def test_fiche_avec_comparables_et_retour(client: TestClient) -> None:
    item = client.get("/api/opportunities?period=30").json()["items"][0]
    detail = client.get(f"/api/listing/{item['id']}").json()
    assert detail["description"]
    assert len(detail["comps"]) == detail["compsInfo"]["n"] >= detail["ev"]["n"]
    assert {"annee", "km", "prix", "vendeur", "ville"} <= set(detail["comps"][0])
    client.post("/api/feedback", json={"id": item["id"], "statut": "achete", "prix_achat": 1000})
    assert client.get(f"/api/listing/{item['id']}").json()["fb"]["prix_achat"] == 1000
    client.post("/api/feedback", json={"id": item["id"], "statut": "aucun"})
    assert client.get(f"/api/listing/{item['id']}").json()["fb"] is None
    assert client.get("/api/listing/inconnu:1").status_code == 404


def test_saisie_manuelle_et_stats(client: TestClient) -> None:
    draft = {
        "marque": "Peugeot",
        "modele": "208",
        "version": "1.2 PureTech 100 Allure",
        "annee": "2020",
        "km": "60000",
        "carburant": "Essence",
        "boite": "Manuelle",
        "prix": "6000",
        "cp": "69003",
        "ville": "Lyon",
    }
    ev = client.post("/api/evaluate", json=draft).json()["ev"]
    assert ev["statut"] in {"alerte", "sous_seuil", "sans_cote"}
    new_id = client.post("/api/manual", json=draft).json()["id"]
    assert new_id.startswith("manuel:")
    assert client.get(f"/api/listing/{new_id}").json()["manual"] is True
    stats = client.get("/api/stats").json()
    assert {"by_status", "motifs", "per_day", "feedback", "purchases"} <= set(stats)
    assert client.get("/api/config").json()["config"]["params"]["base_code_postal"] == "69003"
