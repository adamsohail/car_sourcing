"""Configuration technique par variables d'environnement (la configuration métier vient du Sheet)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gcp_project: str = ""
    bq_dataset: str = "car_sourcing"
    bq_location: str = "EU"
    sheet_id: str = ""

    gmail_oauth_json: SecretStr | None = None
    gmail_query: str = "(from:leboncoin.fr OR from:lacentrale.fr) -label:traite -label:erreur_parsing"
    gmail_label_done: str = "traite"
    gmail_label_error: str = "erreur_parsing"

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str = ""
    telegram_webhook_secret: SecretStr | None = None

    web_password: SecretStr | None = None
    session_secret: SecretStr | None = None
    public_base_url: str = ""
    cookie_secure: bool = True

    http_min_delay_s: float = 3.0
    http_max_delay_s: float = 6.0
    http_timeout_s: float = 20.0
    max_emails_per_run: int = 30
    max_new_listings_per_run: int = 60
    parse_failure_alert_ratio: float = 0.20
    no_email_alert_hours: int = 24
    dry_run: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


class JsonFormatter(logging.Formatter):
    """Un objet JSON par ligne : `severity` et les champs `extra` sont lus par Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": datetime.now(UTC).isoformat(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def log(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"fields": fields})
