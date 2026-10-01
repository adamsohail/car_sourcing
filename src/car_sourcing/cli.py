"""Points d'entrée : `run` (job planifié), `serve` (service web), `smoke`, `set-webhook`, `test-alert`, `demo`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime

from car_sourcing.adapters.bigquery import BigQueryRepository
from car_sourcing.settings import get_settings, log, setup_logging

logger = logging.getLogger("car_sourcing")


def _repo() -> BigQueryRepository:

    s = get_settings()
    return BigQueryRepository(s.gcp_project, s.bq_dataset, s.bq_location)


def cmd_run() -> int:
    from car_sourcing.adapters.bigquery import StoredConfigSource
    from car_sourcing.adapters.external import GmailSource, IgnGeocoder, PoliteFetcher
    from car_sourcing.adapters.messaging import TelegramNotifier
    from car_sourcing.domain.config import ConfigError
    from car_sourcing.pipeline import Pipeline

    s = get_settings()
    repo = _repo()
    notifier = TelegramNotifier(s)
    pipeline = Pipeline(
        settings=s,
        mail=GmailSource(s),
        fetcher=PoliteFetcher(s),
        repo=repo,
        config_source=StoredConfigSource(repo),
        geocoder=IgnGeocoder(repo),
        notifier=notifier,
    )
    try:
        pipeline.run()
    except ConfigError:
        return 2  # alerte technique déjà envoyée par le pipeline
    except Exception as exc:
        log(logger, logging.CRITICAL, "run en échec", error=repr(exc))
        try:
            pipeline.technical_alert("run_echec", f"Le run a échoué : {exc!r}")
        except Exception as alert_exc:  # la supervision ne doit pas masquer l'erreur d'origine
            log(logger, logging.ERROR, "alerte technique impossible", error=repr(alert_exc))
        return 1
    return 0


def build_web_app():  # type: ignore[no-untyped-def]
    from car_sourcing.adapters.bigquery import StoredConfigSource
    from car_sourcing.adapters.external import IgnGeocoder
    from car_sourcing.adapters.messaging import TelegramNotifier
    from car_sourcing.web.app import Deps, create_app

    s = get_settings()
    repo = _repo()
    return create_app(
        Deps(
            settings=s,
            repo=repo,
            telegram=TelegramNotifier(s),
            config_loader=StoredConfigSource(repo).load,
            geocoder=IgnGeocoder(repo),
        )
    )


def cmd_serve(port: int) -> int:
    import uvicorn

    uvicorn.run(
        "car_sourcing.cli:build_web_app",
        factory=True,
        host="0.0.0.0",
        port=port,
        log_config=None,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


def cmd_demo(port: int) -> int:
    """Interface avec des annonces simulées, sans aucune connexion externe. Mot de passe : demo."""
    import uvicorn
    from pydantic import SecretStr

    from car_sourcing.demo import DemoGeocoder, DemoRepository, DemoTelegram, demo_config, seed
    from car_sourcing.settings import Settings
    from car_sourcing.web.app import Deps, create_app

    settings = Settings(
        web_password=SecretStr("demo"),
        session_secret=SecretStr("demo-" * 8),
        cookie_secure=False,
    )
    repo = DemoRepository()
    seed(repo, demo_config())
    app = create_app(
        Deps(
            settings=settings,
            repo=repo,
            telegram=DemoTelegram(),
            config_loader=repo.load_config,
            geocoder=DemoGeocoder(),
        )
    )
    print(f"Démonstration sur http://localhost:{port} (mot de passe : demo)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


def cmd_smoke() -> int:
    """Vérifie chaque dépendance externe ; à lancer après chaque déploiement."""
    from car_sourcing.adapters.bigquery import StoredConfigSource
    from car_sourcing.adapters.external import GmailSource, IgnGeocoder
    from car_sourcing.adapters.messaging import TelegramNotifier

    s = get_settings()
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, fn) -> None:  # type: ignore[no-untyped-def]
        try:
            checks.append((name, True, str(fn())))
        except Exception as exc:
            checks.append((name, False, repr(exc)))

    repo = _repo()
    check(
        "BigQuery", lambda: f"{len(repo._query(f'SELECT 1 FROM {repo.table("listings")} LIMIT 1'))} ligne lue"
    )
    check("Réglages", lambda: f"version {StoredConfigSource(repo).load().version}")
    check("Gmail", lambda: f"dernier email d'alerte : {GmailSource(s).latest_alert_email_at()}")
    check("Géocodage", lambda: IgnGeocoder(repo).geocode("69003", "Lyon"))
    check("Telegram", lambda: TelegramNotifier(s).call("getMe")["result"]["username"])
    for name, ok, detail in checks:
        print(f"{'OK ' if ok else 'KO '} {name} : {detail}")
    return 0 if all(ok for _, ok, _ in checks) else 1


def cmd_set_webhook(url: str) -> int:
    from car_sourcing.adapters.messaging import TelegramNotifier

    s = get_settings()
    if s.telegram_webhook_secret is None:
        print("TELEGRAM_WEBHOOK_SECRET manquant", file=sys.stderr)
        return 1
    res = TelegramNotifier(s).call(
        "setWebhook",
        url=url.rstrip("/") + "/telegram/webhook",
        secret_token=s.telegram_webhook_secret.get_secret_value(),
        allowed_updates=["callback_query", "message"],
    )
    print(res)
    return 0


def cmd_test_alert() -> int:
    """Envoie une alerte de démonstration sur Telegram (validation de l'étape 6)."""
    from car_sourcing.adapters.bigquery import StoredConfigSource
    from car_sourcing.adapters.messaging import TelegramNotifier
    from car_sourcing.domain.models import AlertLevel, Evaluation, Listing, Reliability, Source

    s = get_settings()
    now = datetime.now(UTC)
    listing = Listing(
        source=Source.MANUEL,
        listing_id="test",
        url="https://www.leboncoin.fr",
        brand="Peugeot",
        model="208",
        version="1.2 PureTech (test)",
        year=2019,
        mileage_km=72000,
        price_eur=8900,
        city="Lyon",
        postal_code="69003",
        first_seen_at=now,
        last_seen_at=now,
    )
    ev = Evaluation(
        source=Source.MANUEL,
        listing_id="test",
        evaluated_at=now,
        config_version="test",
        km_per_year=10286,
        distance_km=12,
        market_price_eur=13000,
        comparables_count=8,
        reliability=Reliability.FIABLE,
        margin_eur=2426,
        alert_level=AlertLevel.PRIORITAIRE,
        price_eur=8900,
    )
    print(TelegramNotifier(s).send_alert(listing, ev, StoredConfigSource(_repo()).load()))
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(prog="car-sourcing")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="traite les emails d'alerte (job toutes les 10 minutes)")
    serve = sub.add_parser("serve", help="service web : webhook Telegram, API et interface")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    demo = sub.add_parser("demo", help="interface de démonstration avec des annonces simulées")
    demo.add_argument("--port", type=int, default=8080)
    sub.add_parser("smoke", help="vérifie les dépendances externes")
    hook = sub.add_parser("set-webhook", help="enregistre l'URL du webhook auprès de Telegram")
    hook.add_argument("url")
    sub.add_parser("test-alert", help="envoie une alerte de test sur Telegram")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run()
    if args.cmd == "serve":
        return cmd_serve(args.port)
    if args.cmd == "demo":
        return cmd_demo(args.port)
    if args.cmd == "smoke":
        return cmd_smoke()
    if args.cmd == "set-webhook":
        return cmd_set_webhook(args.url)
    return cmd_test_alert()


if __name__ == "__main__":
    sys.exit(main())
