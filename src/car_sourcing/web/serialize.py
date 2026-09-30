"""Format JSON échangé avec l'interface (mêmes noms que la version de démonstration)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from car_sourcing.domain.config import Config
from car_sourcing.domain.models import Comparable, Evaluation, Listing


def _ms(value: Any) -> int | None:
    return int(value.timestamp() * 1000) if isinstance(value, datetime) else None


def _motif(reason: Any, detail: Any) -> dict[str, Any] | None:
    return {"code": str(reason), "detail": detail} if reason else None


def evaluation_dict(ev: dict[str, Any] | Evaluation) -> dict[str, Any]:
    e = ev.model_dump() if isinstance(ev, Evaluation) else ev
    level = e.get("alert_level")
    reason = e.get("exclusion_reason")
    if level:
        statut = "alerte"
    elif reason == "cote_indisponible":
        statut = "sans_cote"
    elif reason:
        statut = "exclue"
    elif e.get("margin_eur") is not None:
        statut = "sous_seuil"
    else:
        statut = "non_evaluee"
    return {
        "kmAn": e.get("km_per_year"),
        "motif": _motif(reason, e.get("exclusion_detail")),
        "distance": e.get("distance_km"),
        "cote": e.get("market_price_eur"),
        "n": e.get("comparables_count") or 0,
        "widened": bool(e.get("comparables_widened")),
        "fiabilite": e.get("reliability"),
        "niveau": str(level) if level else None,
        "statut": statut,
        "revente": e.get("resale_price_eur"),
        "decote": e.get("negotiation_discount_eur"),
        "frais": e.get("fees_eur"),
        "transport": e.get("transport_eur"),
        "marge": e.get("margin_eur"),
        "configVersion": e.get("config_version"),
        "evaluatedAt": _ms(e.get("evaluated_at")),
    }


def listing_dict(row: dict[str, Any], with_description: bool = False) -> dict[str, Any]:
    out = {
        "id": f"{row['source']}:{row['listing_id']}",
        "source": row["source"],
        "url": row.get("url"),
        "titre": row.get("title"),
        "marque": row.get("brand") or "",
        "modele": row.get("model") or "",
        "version": row.get("version"),
        "annee": row.get("year"),
        "km": row.get("mileage_km"),
        "carburant": row.get("fuel"),
        "boite": row.get("gearbox"),
        "prix": row.get("price_eur"),
        "vendeur": row.get("seller_type"),
        "ville": row.get("city"),
        "cp": row.get("postal_code"),
        "photo": row.get("photo_url"),
        "first_seen_at": _ms(row.get("first_seen_at")),
        "last_seen_at": _ms(row.get("last_seen_at")),
        "detailIndisponible": row.get("enrichment_status") == "detail_indisponible",
        "manual": row["source"] == "manuel",
    }
    if with_description:
        out["description"] = row.get("description")
    if "statut" in row:
        out["ev"] = evaluation_dict(row) if row.get("evaluated_at") else None
        status = row.get("feedback_status")
        out["fb"] = (
            {"statut": status, "prix_achat": row.get("purchase_price_eur"), "at": _ms(row.get("feedback_at"))}
            if status
            else None
        )
    return out


def listing_to_row(listing: Listing) -> dict[str, Any]:
    row = listing.model_dump()
    return {k: (v.value if hasattr(v, "value") else v) for k, v in row.items()}


def comparable_dict(c: Comparable) -> dict[str, Any]:
    return {
        "annee": c.year,
        "km": c.mileage_km,
        "prix": c.price_eur,
        "vendeur": c.seller_type.value if c.seller_type else None,
        "ville": c.city,
    }


def config_dict(config: Config) -> dict[str, Any]:
    return {
        "params": config.model_dump(exclude={"mots_cles_exclusion"}),
        "keywords": list(config.mots_cles_exclusion),
        "version": config.version,
    }
