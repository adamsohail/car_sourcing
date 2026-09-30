"""Service web : authentification, retours et webhook Telegram."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from car_sourcing.alerts_format import (
    alert_keyboard,
    decode_callback,
    encode_callback,
    format_alert,
    price_prompt,
)
from car_sourcing.domain.models import AlertLevel, Evaluation, FeedbackStatus, Reliability, Source
from car_sourcing.settings import Settings
from car_sourcing.web.app import Deps, create_app
from tests.conftest import NOW, make_config, make_listing
from tests.fakes import FakeGeocoder, FakeRepo

SECRET = "s3cret-webhook"


class FakeTelegram:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, **payload: Any) -> dict[str, Any]:
        self.calls.append((method, payload))
        return {"ok": True, "result": {}}


@pytest.fixture
def ctx():
    settings = Settings(
        web_password=SecretStr("motdepasse"),
        session_secret=SecretStr("x" * 32),
        telegram_webhook_secret=SecretStr(SECRET),
        telegram_chat_id="-100",
    )
    repo, tg = FakeRepo(), FakeTelegram()
    deps = Deps(
        settings=settings,
        repo=repo,
        telegram=tg,
        config_loader=make_config,
        geocoder=FakeGeocoder({"69003": (45.759, 4.861)}),
        clock=lambda: NOW,
    )
    client = TestClient(create_app(deps), base_url="https://testserver")
    return client, repo, tg


def test_api_fermee_sans_connexion(ctx) -> None:
    client, _, _ = ctx
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/session").json() == {"ok": False}
    assert client.get("/healthz").json() == {"status": "ok"}


def test_connexion_et_retour(ctx) -> None:
    client, repo, _ = ctx
    assert client.post("/api/login", json={"password": "faux"}).status_code == 401
    assert client.post("/api/login", json={"password": "motdepasse"}).status_code == 200
    assert client.get("/api/session").json() == {"ok": True}
    res = client.post("/api/feedback", json={"id": "leboncoin:123", "statut": "achete", "prix_achat": 7800})
    assert res.status_code == 200
    assert repo.feedback == [("leboncoin:123", FeedbackStatus.ACHETE, 7800)]
    assert client.get("/api/config").json()["config"]["params"]["base_code_postal"] == "69003"


def test_evaluation_manuelle(ctx) -> None:
    client, _, _ = ctx
    client.post("/api/login", json={"password": "motdepasse"})
    res = client.post(
        "/api/evaluate",
        json={
            "marque": "Peugeot",
            "modele": "208",
            "annee": "2019",
            "km": "70 000",
            "carburant": "Essence",
            "boite": "Manuelle",
            "prix": "8 000",
            "cp": "69003",
        },
    )
    body = res.json()
    assert res.status_code == 200
    assert body["ev"]["motif"]["code"] == "cote_indisponible"
    assert body["geocoded"] is True


def _callback(data: str, chat: str = "-100") -> dict[str, Any]:
    listing = make_listing(listing_id="2845123456")
    return {
        "update_id": 1,
        "callback_query": {
            "id": "cb1",
            "data": data,
            "from": {"id": 7, "first_name": "Adam"},
            "message": {
                "message_id": 55,
                "chat": {"id": int(chat)},
                "caption": "◆ ALERTE\n<b>Peugeot 208</b> (2019)",
                "reply_markup": alert_keyboard(listing, None),
            },
        },
    }


def test_webhook_refuse_sans_secret(ctx) -> None:
    client, repo, _ = ctx
    assert client.post("/telegram/webhook", json=_callback("fb|i|l|1")).status_code == 403
    assert not repo.feedback


def test_webhook_bouton_interessant(ctx) -> None:
    client, repo, tg = ctx
    data = encode_callback(FeedbackStatus.INTERESSANT, Source.LEBONCOIN, "2845123456")
    res = client.post(
        "/telegram/webhook", json=_callback(data), headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert res.status_code == 200
    assert repo.feedback == [("leboncoin:2845123456", FeedbackStatus.INTERESSANT, None)]
    methods = [m for m, _ in tg.calls]
    assert methods == ["answerCallbackQuery", "editMessageReplyMarkup"]
    first_button = tg.calls[1][1]["reply_markup"]["inline_keyboard"][0][0]["text"]
    assert first_button.startswith("✓ ")


def test_webhook_achat_puis_prix(ctx) -> None:
    client, repo, tg = ctx
    headers = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
    data = encode_callback(FeedbackStatus.ACHETE, Source.LEBONCOIN, "2845123456")
    client.post("/telegram/webhook", json=_callback(data), headers=headers)
    prompt = tg.calls[-1][1]["text"]
    assert "réf. leboncoin:2845123456" in prompt
    reply = {
        "update_id": 2,
        "message": {
            "chat": {"id": -100},
            "text": "7 800 €",
            "from": {"first_name": "Adam"},
            "reply_to_message": {"text": prompt},
        },
    }
    client.post("/telegram/webhook", json=reply, headers=headers)
    assert repo.feedback[-1] == ("leboncoin:2845123456", FeedbackStatus.ACHETE, 7800)


def test_webhook_autre_groupe_ignore(ctx) -> None:
    client, repo, _ = ctx
    data = encode_callback(FeedbackStatus.INTERESSANT, Source.LEBONCOIN, "1")
    client.post(
        "/telegram/webhook",
        json=_callback(data, chat="-999"),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert not repo.feedback


def test_format_alerte_et_boutons() -> None:
    listing = make_listing(version="1.2 PureTech", photo_url=None)
    ev = Evaluation(
        source=Source.LEBONCOIN,
        listing_id="1",
        evaluated_at=NOW,
        config_version="v",
        km_per_year=10000,
        distance_km=32.4,
        market_price_eur=13000,
        comparables_count=3,
        reliability=Reliability.FAIBLE,
        margin_eur=2340.4,
        alert_level=AlertLevel.PRIORITAIRE,
        price_eur=8000,
    )
    text = format_alert(listing, ev, make_config())
    for expected in (
        "ALERTE PRIORITAIRE",
        "Peugeot 208 1.2 PureTech",
        "8\u00a0000\u00a0€",
        "à 32\u00a0km",
        "+2\u00a0340\u00a0€",
        "3 comparables",
        "peu fiable",
    ):
        assert expected in text
    keyboard = alert_keyboard(listing, FeedbackStatus.ACHETE, "https://app.example")
    assert keyboard["inline_keyboard"][1][0]["text"].startswith("✓ ")
    assert keyboard["inline_keyboard"][2][1]["url"].endswith("#/annonce/leboncoin:1")
    for status in (FeedbackStatus.INTERESSANT, FeedbackStatus.PAS_INTERESSANT, FeedbackStatus.ACHETE):
        code = encode_callback(status, Source.LACENTRALE, "87101234567")
        assert len(code.encode()) <= 64
        assert decode_callback(code) == (status, Source.LACENTRALE, "87101234567")
    assert decode_callback("autre") is None
    assert "réf. manuel:m1" in price_prompt("manuel:m1", "<b>x</b>")
