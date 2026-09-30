"""Service web (Cloud Run Service) : boutons Telegram, API et interface.

- `/telegram/webhook` est public mais vérifie l'en-tête secret envoyé par Telegram.
- `/api/*` et l'interface demandent une connexion par mot de passe (cookie signé, 30 jours).
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from pydantic import BaseModel, Field

from car_sourcing.alerts_format import PRICE_PROMPT_RE, decode_callback, price_prompt
from car_sourcing.domain.config import Config, ConfigError
from car_sourcing.domain.models import EnrichmentStatus, FeedbackStatus, Listing, SellerType, Source
from car_sourcing.domain.rules import evaluate, market_price
from car_sourcing.domain.text import normalize, normalize_fuel, normalize_gearbox, parse_int
from car_sourcing.settings import Settings, log
from car_sourcing.web.serialize import comparable_dict, config_dict, evaluation_dict, listing_dict

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
SESSION_COOKIE = "cs_session"
SESSION_MAX_AGE = 30 * 24 * 3600
FEEDBACK_LABELS = {
    FeedbackStatus.INTERESSANT: "Marquée intéressante",
    FeedbackStatus.PAS_INTERESSANT: "Marquée pas intéressante",
    FeedbackStatus.ACHETE: "Marquée achetée",
}


@dataclass
class Deps:
    settings: Settings
    repo: Any
    telegram: Any
    config_loader: Callable[[], Config]
    geocoder: Any
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _config_cache: dict[str, Any] = field(default_factory=dict)

    def config(self) -> Config:
        """Configuration du Sheet, mise en cache 60 s ; lève ConfigError si invalide."""
        cached = self._config_cache.get("value")
        if cached is not None and time.monotonic() - self._config_cache["at"] < 60:
            if isinstance(cached, ConfigError):
                raise cached
            return cached  # type: ignore[no-any-return]
        try:
            value: Config | ConfigError = self.config_loader()
        except ConfigError as exc:
            value = exc
        self._config_cache.update(value=value, at=time.monotonic())
        if isinstance(value, ConfigError):
            raise value
        return value


class FeedbackIn(BaseModel):
    id: str
    statut: FeedbackStatus
    prix_achat: int | None = Field(default=None, ge=0)


class DraftIn(BaseModel):
    source: str = "manuel"
    url: str = ""
    marque: str = ""
    modele: str = ""
    version: str = ""
    annee: str | int | None = None
    km: str | int | None = None
    carburant: str = ""
    boite: str = ""
    prix: str | int | None = None
    vendeur: str = "particulier"
    cp: str = ""
    ville: str = ""
    description: str = ""


def split_key(key: str) -> tuple[Source, str]:
    source, _, listing_id = key.partition(":")
    try:
        return Source(source), listing_id
    except ValueError as exc:
        raise HTTPException(404, "annonce inconnue") from exc


def create_app(deps: Deps) -> FastAPI:
    app = FastAPI(title="Sourcing auto", docs_url=None, redoc_url=None)
    s = deps.settings
    signer = TimestampSigner(s.session_secret.get_secret_value()) if s.session_secret else None

    def require_session(request: Request) -> None:
        token = request.cookies.get(SESSION_COOKIE, "")
        if signer is None:
            raise HTTPException(503, "SESSION_SECRET non configuré")
        try:
            signer.unsign(token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired) as exc:
            raise HTTPException(401, "connexion requise") from exc

    @app.middleware("http")
    async def auth_gate(request: Request, call_next: Any) -> Any:
        path = request.url.path
        if path.startswith("/api/") and path not in {"/api/login", "/api/session"}:
            try:
                require_session(request)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)

    # ---------- Santé et interface ----------

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    # ---------- Connexion ----------

    @app.post("/api/login")
    async def login(request: Request, response: Response) -> dict[str, bool]:
        body = await request.json()
        if s.web_password is None or signer is None:
            raise HTTPException(503, "WEB_PASSWORD ou SESSION_SECRET non configuré")
        if not hmac.compare_digest(
            str(body.get("password", "")).encode(), s.web_password.get_secret_value().encode()
        ):
            await asyncio.sleep(0.8)
            raise HTTPException(401, "mot de passe incorrect")
        response.set_cookie(
            SESSION_COOKIE,
            signer.sign(uuid.uuid4().hex).decode(),
            max_age=SESSION_MAX_AGE,
            httponly=True,
            secure=s.cookie_secure,
            samesite="lax",
        )
        return {"ok": True}

    @app.get("/api/session")
    def session(request: Request) -> dict[str, bool]:
        try:
            require_session(request)
        except HTTPException:
            return {"ok": False}
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response) -> dict[str, bool]:
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    # ---------- Données ----------

    def config_or_errors() -> tuple[Config | None, list[str] | None]:
        try:
            return deps.config(), None
        except ConfigError as exc:
            return None, exc.errors

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        cfg, errors = config_or_errors()
        sheet_url = f"https://docs.google.com/spreadsheets/d/{s.sheet_id}/edit" if s.sheet_id else None
        return {"config": config_dict(cfg) if cfg else None, "errors": errors, "sheetUrl": sheet_url}

    @app.get("/api/opportunities")
    def opportunities(period: int = 7) -> dict[str, Any]:
        since = deps.clock() - timedelta(days=max(1, min(period, 90)))
        return {"items": [listing_dict(r) for r in deps.repo.opportunities(since)]}

    @app.get("/api/listings")
    def listings(q: str = "", statut: str = "all", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if statut not in {"all", "alerte", "sous_seuil", "exclue", "sans_cote"}:
            raise HTTPException(400, "statut inconnu")
        rows, counts = deps.repo.search_listings(
            normalize(q).split(),
            None if statut == "all" else statut,
            deps.clock() - timedelta(days=90),
            max(1, min(limit, 200)),
            max(0, offset),
        )
        return {"items": [listing_dict(r) for r in rows], "counts": counts, "total": sum(counts.values())}

    @app.get("/api/listing/{key}")
    def listing_detail(key: str) -> dict[str, Any]:
        source, listing_id = split_key(key)
        row = deps.repo.status_row(source, listing_id)
        if row is None:
            raise HTTPException(404, "annonce inconnue")
        out = listing_dict(row, with_description=True)
        cfg, _ = config_or_errors()
        comps: list[dict[str, Any]] = []
        info: dict[str, Any] | None = None
        if cfg is not None and row.get("year") and row.get("mileage_km"):
            listing = Listing.model_validate({k: row.get(k) for k in Listing.model_fields})
            cands = deps.repo.comparables_candidates(listing, cfg, deps.clock())
            mp = market_price(row["year"], row["mileage_km"], cands, cfg.comparables_min)
            comps = [comparable_dict(c) for c in mp.comparables]
            # Marché actuel : peut différer de celui du moment de l'évaluation.
            info = {
                "cote": mp.value,
                "n": len(mp.comparables),
                "widened": mp.widened,
                "fiabilite": mp.reliability.value if mp.reliability else None,
            }
        out["compsInfo"] = info
        out["comps"] = comps
        return out

    @app.post("/api/feedback")
    def post_feedback(body: FeedbackIn) -> dict[str, bool]:
        source, listing_id = split_key(body.id)
        deps.repo.insert_feedback(source, listing_id, body.statut, body.prix_achat, "web", deps.clock())
        return {"ok": True}

    def draft_listing(d: DraftIn, listing_id: str) -> Listing:
        now = deps.clock()
        coords = deps.geocoder.geocode(d.cp or None, d.ville or None) if (d.cp or d.ville) else None
        return Listing.model_validate(
            {
                "source": Source.MANUEL,
                "listing_id": listing_id,
                "url": d.url.strip() or f"manuel:{listing_id}",
                "title": " ".join(p for p in (d.marque, d.modele, d.version) if p.strip()) or None,
                "brand": d.marque.strip() or None,
                "model": d.modele.strip() or None,
                "version": d.version.strip() or None,
                "year": parse_int(d.annee),
                "mileage_km": parse_int(d.km),
                "price_eur": parse_int(d.prix),
                "fuel": normalize_fuel(d.carburant),
                "gearbox": normalize_gearbox(d.boite),
                "seller_type": SellerType.PRO if d.vendeur == "pro" else SellerType.PARTICULIER,
                "city": d.ville.strip() or None,
                "postal_code": d.cp.strip() or None,
                "lat": coords[0] if coords else None,
                "lon": coords[1] if coords else None,
                "description": d.description.strip() or None,
                "first_seen_at": now,
                "last_seen_at": now,
                "enrichment_status": EnrichmentStatus.ENRICHI,
            }
        )

    def evaluate_draft(d: DraftIn, listing_id: str) -> tuple[Listing, Any, list[Any]]:
        cfg, errors = config_or_errors()
        if cfg is None:
            raise HTTPException(409, {"errors": errors})
        base = deps.geocoder.geocode(cfg.base_code_postal, None)
        if base is None:
            raise HTTPException(409, {"errors": ["code postal de la base introuvable"]})
        listing = draft_listing(d, listing_id)
        cands = deps.repo.comparables_candidates(listing, cfg, deps.clock())
        ev = evaluate(listing, cfg, cands, base, deps.clock())
        return listing, ev, cands

    @app.post("/api/evaluate")
    def post_evaluate(d: DraftIn) -> dict[str, Any]:
        listing, ev, _ = evaluate_draft(d, "brouillon")
        return {"ev": evaluation_dict(ev), "geocoded": listing.lat is not None}

    @app.post("/api/manual")
    def post_manual(d: DraftIn) -> dict[str, Any]:
        listing, ev, _ = evaluate_draft(d, "m" + uuid.uuid4().hex[:12])
        deps.repo.upsert_listing(listing)
        deps.repo.insert_evaluation(ev)
        return {"id": listing.key}

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        raw: dict[str, Any] = deps.repo.stats(deps.clock() - timedelta(days=90))
        for p in raw["purchases"]:
            p["feedback_at"] = (
                p["feedback_at"].timestamp() * 1000 if isinstance(p.get("feedback_at"), datetime) else None
            )
        for d in raw["per_day"]:
            d["jour"] = str(d["jour"])
        return raw

    # ---------- Webhook Telegram ----------

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request) -> dict[str, bool]:
        secret = s.telegram_webhook_secret.get_secret_value() if s.telegram_webhook_secret else ""
        given = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secret or not hmac.compare_digest(given, secret):
            raise HTTPException(403, "secret invalide")
        update = await request.json()
        try:
            if "callback_query" in update:
                handle_callback(update["callback_query"])
            elif "message" in update:
                handle_price_reply(update["message"])
        except Exception as exc:  # toujours répondre 200 à Telegram, sinon il réessaie en boucle
            log(logger, logging.ERROR, "webhook Telegram en erreur", error=repr(exc))
        return {"ok": True}

    def handle_callback(cb: dict[str, Any]) -> None:
        message = cb.get("message") or {}
        if str(message.get("chat", {}).get("id")) != str(s.telegram_chat_id):
            return
        decoded = decode_callback(str(cb.get("data", "")))
        if decoded is None:
            return
        status, source, listing_id = decoded
        author = (cb.get("from") or {}).get("first_name") or str((cb.get("from") or {}).get("id", ""))
        deps.repo.insert_feedback(source, listing_id, status, None, author, deps.clock())
        deps.telegram.call("answerCallbackQuery", callback_query_id=cb["id"], text=FEEDBACK_LABELS[status])
        markup = message.get("reply_markup") or {}
        for row in markup.get("inline_keyboard", []):
            for button in row:
                if "callback_data" in button:
                    label = re.sub(r"^✓ ", "", button["text"])
                    button["text"] = ("✓ " if button["callback_data"] == cb.get("data") else "") + label
        deps.telegram.call(
            "editMessageReplyMarkup",
            chat_id=message["chat"]["id"],
            message_id=message["message_id"],
            reply_markup=markup,
        )
        if status is FeedbackStatus.ACHETE:
            name = (message.get("caption") or message.get("text") or "").split("\n")[1:2]
            deps.telegram.call(
                "sendMessage",
                chat_id=message["chat"]["id"],
                text=price_prompt(
                    f"{source.value}:{listing_id}", re.sub("<[^>]+>", "", name[0]) if name else listing_id
                ),
                reply_markup={"force_reply": True, "selective": True},
                reply_parameters={"message_id": message["message_id"]},
            )

    def handle_price_reply(message: dict[str, Any]) -> None:
        if str(message.get("chat", {}).get("id")) != str(s.telegram_chat_id):
            return
        original = (message.get("reply_to_message") or {}).get("text", "")
        match = PRICE_PROMPT_RE.search(original)
        if not match:
            return
        price = parse_int(message.get("text"))
        if price is None or price <= 0:
            deps.telegram.call(
                "sendMessage",
                chat_id=message["chat"]["id"],
                text="Montant non reconnu. Répondez avec un nombre, par exemple 7800.",
            )
            return
        author = (message.get("from") or {}).get("first_name")
        deps.repo.insert_feedback(
            Source(match.group(1)), match.group(2), FeedbackStatus.ACHETE, price, author, deps.clock()
        )
        deps.telegram.call(
            "sendMessage",
            chat_id=message["chat"]["id"],
            text=f"Prix d'achat enregistré : {price:,} €".replace(",", "\u00a0"),
        )

    return app
