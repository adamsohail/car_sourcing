"""Démonstration locale : `car-sourcing demo` sert l'interface avec des annonces simulées en mémoire.

Aucune connexion à GCP, Gmail ou Telegram. Les calculs utilisent le vrai domaine.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from car_sourcing.domain.config import (
    DEFAULT_KEYWORDS,
    DEFAULT_PARAMETERS,
    NO_CONFIG_MESSAGE,
    Config,
    ConfigError,
    config_from_payload,
    parse_rows,
    payload_from_config,
)
from car_sourcing.domain.models import (
    Comparable,
    EnrichmentStatus,
    Evaluation,
    FeedbackStatus,
    Listing,
    SellerType,
    Source,
)
from car_sourcing.domain.rules import evaluate
from car_sourcing.domain.text import normalize

CITIES = [
    ("Paris", "75011", 48.859, 2.379, 10),
    ("Marseille", "13005", 43.293, 5.395, 6),
    ("Lyon", "69003", 45.759, 4.861, 6),
    ("Toulouse", "31000", 43.605, 1.444, 5),
    ("Nantes", "44000", 47.218, -1.554, 4),
    ("Bordeaux", "33000", 44.838, -0.579, 4),
    ("Lille", "59000", 50.629, 3.057, 4),
    ("Grenoble", "38000", 45.188, 5.724, 2),
    ("Dijon", "21000", 47.322, 5.041, 2),
    ("Rennes", "35000", 48.117, -1.678, 3),
    ("Strasbourg", "67000", 48.573, 7.752, 3),
    ("Saint-Étienne", "42000", 45.44, 4.387, 2),
]
MODELS = [
    ("Peugeot", "208", 20000, 0.11, 10, ["1.2 PureTech 100 Allure", "1.5 BlueHDi 100 Active"]),
    ("Renault", "Clio", 19500, 0.11, 10, ["1.0 TCe 90 Zen", "1.5 dCi 90 Business"]),
    ("Volkswagen", "Golf", 28000, 0.11, 7, ["1.0 TSI 110 Life", "2.0 TDI 150 Style"]),
    ("Toyota", "Yaris", 21000, 0.09, 6, ["Hybride 116h Design"]),
    ("Dacia", "Sandero", 14000, 0.10, 7, ["TCe 90 Stepway", "ECO-G 100 Confort"]),
    ("Citroën", "C3", 18000, 0.12, 6, ["PureTech 83 Feel", "BlueHDi 100 Shine"]),
    ("Peugeot", "3008", 33000, 0.12, 5, ["1.5 BlueHDi 130 Allure"]),
    ("Renault", "Captur", 24000, 0.11, 5, ["TCe 90 Zen"]),
]
FUELS = {
    "PureTech": "Essence",
    "TCe": "Essence",
    "TSI": "Essence",
    "ECO-G": "GPL",
    "Hybride": "Hybride",
    "BlueHDi": "Diesel",
    "dCi": "Diesel",
    "TDI": "Diesel",
}
PHOTO = None


def demo_config() -> Config:
    params = dict(DEFAULT_PARAMETERS)
    params["base_code_postal"] = "69003"
    return parse_rows(list(params.items()), [[k] for k in DEFAULT_KEYWORDS])


class DemoGeocoder:
    def geocode(self, postal_code: str | None, city: str | None) -> tuple[float, float] | None:
        for name, cp, lat, lon, _ in CITIES:
            if cp == postal_code or (city and normalize(city) == normalize(name)):
                return lat, lon
        return (46.6, 2.4) if postal_code else None


class DemoTelegram:
    def call(self, method: str, **payload: Any) -> dict[str, Any]:
        return {"ok": True, "result": {}}


class DemoRepository:
    def __init__(self) -> None:
        self.listings: dict[str, Listing] = {}
        self.evals: dict[str, Evaluation] = {}
        self.feedback: dict[str, tuple[FeedbackStatus, int | None, datetime]] = {}
        self.configs: list[dict[str, Any]] = []

    # --- réglages ---
    def latest_config(self) -> dict[str, Any] | None:
        return self.configs[-1] if self.configs else None

    def insert_config(
        self, number: int, payload: dict[str, Any], config_hash: str, author: str | None, created_at: datetime
    ) -> None:
        self.configs.append(
            {
                "number": number,
                "payload": payload,
                "config_hash": config_hash,
                "author": author,
                "created_at": created_at,
            }
        )

    def load_config(self) -> Config:
        row = self.latest_config()
        if row is None:
            raise ConfigError([NO_CONFIG_MESSAGE])
        return config_from_payload(row["payload"])

    def recent_for_preview(self, since: datetime) -> list[dict[str, Any]]:
        return [self._row(x) for x in self.listings.values() if x.first_seen_at >= since]

    # --- pipeline ---
    def get_listing(self, source: Source, listing_id: str) -> Listing | None:
        return self.listings.get(f"{source.value}:{listing_id}")

    def upsert_listing(self, listing: Listing) -> None:
        self.listings[listing.key] = listing

    def comparables_candidates(self, listing: Listing, config: Config, now: datetime) -> list[Comparable]:
        since = now - timedelta(days=config.fenetre_comparables_jours)
        out = []
        for o in self.listings.values():
            ev = self.evals.get(o.key)
            if (
                o.key == listing.key
                or o.brand_norm != listing.brand_norm
                or o.model_norm != listing.model_norm
                or o.fuel != listing.fuel
                or o.gearbox != listing.gearbox
                or o.last_seen_at < since
                or o.price_eur is None
                or o.year is None
                or o.mileage_km is None
                or listing.year is None
                or listing.mileage_km is None
                or (ev and ev.exclusion_reason and ev.exclusion_reason.value == "mot_cle")
            ):
                continue
            if abs(o.year - listing.year) <= 2 and abs(o.mileage_km - listing.mileage_km) <= 40_000:
                out.append(
                    Comparable(
                        source=o.source,
                        listing_id=o.listing_id,
                        price_eur=o.price_eur,
                        year=o.year,
                        mileage_km=o.mileage_km,
                        seller_type=o.seller_type,
                        city=o.city,
                    )
                )
        return out

    def insert_evaluation(self, evaluation: Evaluation) -> None:
        self.evals[evaluation.key] = evaluation

    def insert_feedback(
        self,
        source: Source,
        listing_id: str,
        status: FeedbackStatus,
        purchase_price_eur: int | None,
        author: str | None,
        created_at: datetime,
    ) -> None:
        key = f"{source.value}:{listing_id}"
        if status is FeedbackStatus.AUCUN:
            self.feedback.pop(key, None)
        else:
            self.feedback[key] = (status, purchase_price_eur, created_at)

    # --- interface ---
    def _row(self, listing: Listing) -> dict[str, Any]:
        row: dict[str, Any] = listing.model_dump()
        row = {k: (v.value if hasattr(v, "value") else v) for k, v in row.items()}
        ev = self.evals.get(listing.key)
        if ev:
            e = ev.model_dump()
            row.update(
                {
                    k: (v.value if hasattr(v, "value") else v)
                    for k, v in e.items()
                    if k not in {"source", "listing_id", "price_eur"}
                }
            )
        fb = self.feedback.get(listing.key)
        row.update(
            feedback_status=fb[0].value if fb else None,
            purchase_price_eur=fb[1] if fb else None,
            feedback_at=fb[2] if fb else None,
        )
        reason, level = row.get("exclusion_reason"), row.get("alert_level")
        row["statut"] = (
            "alerte"
            if level
            else "sans_cote"
            if reason == "cote_indisponible"
            else "exclue"
            if reason
            else "sous_seuil"
            if row.get("margin_eur") is not None
            else "non_evaluee"
        )
        return row

    def status_row(self, source: Source, listing_id: str) -> dict[str, Any] | None:
        listing = self.get_listing(source, listing_id)
        return self._row(listing) if listing else None

    def opportunities(self, since: datetime) -> list[dict[str, Any]]:
        rows = [self._row(x) for x in self.listings.values()]
        rows = [
            r
            for r in rows
            if (r["statut"] == "alerte" and r["first_seen_at"] >= since) or r["feedback_status"]
        ]
        return sorted(rows, key=lambda r: -(r.get("margin_eur") or -1e9))

    def search_listings(
        self, tokens: Sequence[str], statut: str | None, since: datetime, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        rows = [self._row(x) for x in self.listings.values() if x.first_seen_at >= since]
        rows = [
            r
            for r in rows
            if all(t in normalize(f"{r['title']} {r['city']} {r['postal_code']} {r['year']}") for t in tokens)
        ]
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["statut"]] = counts.get(r["statut"], 0) + 1
        rows = [r for r in rows if statut is None or r["statut"] == statut]
        rows.sort(key=lambda r: r["first_seen_at"], reverse=True)
        return rows[offset : offset + limit], counts

    def stats(self, since: datetime) -> dict[str, Any]:
        rows = [self._row(x) for x in self.listings.values() if x.first_seen_at >= since]
        by: dict[str, int] = {}
        motifs: dict[str, int] = {}
        per_day: dict[tuple[str, str], int] = {}
        fb: dict[str, int] = {}
        two_weeks = datetime.now(UTC) - timedelta(days=14)
        for r in rows:
            by[r["statut"]] = by.get(r["statut"], 0) + 1
            if r.get("exclusion_reason"):
                motifs[r["exclusion_reason"]] = motifs.get(r["exclusion_reason"], 0) + 1
            if r.get("alert_level") and r["first_seen_at"] >= two_weeks:
                k = (r["first_seen_at"].date().isoformat(), r["alert_level"])
                per_day[k] = per_day.get(k, 0) + 1
            if r["feedback_status"]:
                fb[r["feedback_status"]] = fb.get(r["feedback_status"], 0) + 1
        purchases = [
            {
                k: r.get(k)
                for k in (
                    "source",
                    "listing_id",
                    "brand",
                    "model",
                    "year",
                    "price_eur",
                    "purchase_price_eur",
                    "market_price_eur",
                    "margin_eur",
                    "feedback_at",
                )
            }
            for r in rows
            if r["feedback_status"] == "achete"
        ]
        return {
            "by_status": [{"statut": k, "n": v} for k, v in by.items()],
            "motifs": [{"motif": k, "n": v} for k, v in sorted(motifs.items(), key=lambda x: -x[1])],
            "per_day": [{"jour": d, "alert_level": lvl, "n": n} for (d, lvl), n in sorted(per_day.items())],
            "feedback": [{"status": k, "n": v} for k, v in fb.items()],
            "purchases": purchases,
        }


def seed(repo: DemoRepository, config: Config, n: int = 1100, now: datetime | None = None) -> None:
    rng = random.Random(20260926)  # noqa: S311 - données de démonstration
    now = now or datetime.now(UTC)
    repo.insert_config(1, payload_from_config(config), config.version, "démo", now)
    base = (45.759, 4.861)
    damaged = [
        "Vendue pour pièces, moteur HS.",
        "Joint de culasse à prévoir.",
        "Véhicule accidenté à l'avant.",
        "Vendue sans CT.",
    ]
    items = []
    for i in range(n):
        marque, modele, prix_neuf, dep, _, versions = rng.choices(MODELS, weights=[m[4] for m in MODELS])[0]
        version = rng.choice(versions)
        fuel = next(f for k, f in FUELS.items() if k in version)
        age = max(1, min(14, round(rng.gauss(7, 3))))
        year = now.year - age
        km = max(1000, round(age * max(4000, rng.gauss(12500, 3800)) / 100) * 100)
        value = prix_neuf * (1 - dep) ** age * min(1.1, max(0.65, 1 - (km - age * 13000) / 260000))
        pro = rng.random() < 0.38
        price = value * (1.09 if pro else 1) * math.exp(rng.gauss(0, 0.065))
        desc = "Entretien à jour, CT OK. Très bon état général."
        roll = rng.random()
        if not pro and roll < 0.05:
            price *= 0.5
            desc = rng.choice(damaged)
        elif not pro and roll < 0.15:
            price *= 0.66 + rng.random() * 0.2
        city = rng.choices(CITIES, weights=[c[4] for c in CITIES])[0]
        recent = i >= n - 260
        seen = (
            now - timedelta(days=rng.random() ** 1.5 * 7)
            if recent
            else now - timedelta(days=7 + rng.random() * 80)
        )
        items.append(
            Listing(
                source=Source.LEBONCOIN if not pro or rng.random() < 0.4 else Source.LACENTRALE,
                listing_id=f"demo{i:04d}",
                url="https://www.leboncoin.fr/",
                title=f"{marque} {modele} {version}",
                brand=marque,
                model=modele,
                version=version,
                year=year,
                mileage_km=km,
                fuel=fuel,
                gearbox="Automatique" if fuel == "Hybride" else "Manuelle",
                price_eur=round(price / 100) * 100,
                seller_type=SellerType.PRO if pro else SellerType.PARTICULIER,
                city=city[0],
                postal_code=city[1],
                lat=city[2],
                lon=city[3],
                description=f"Vends ma {modele}. {desc}",
                first_seen_at=seen,
                last_seen_at=seen,
                enrichment_status=EnrichmentStatus.ENRICHI,
            )
        )
    for listing in sorted(items, key=lambda x: x.first_seen_at):
        repo.upsert_listing(listing)
        repo.insert_evaluation(
            evaluate(
                listing,
                config,
                repo.comparables_candidates(listing, config, listing.first_seen_at),
                base,
                listing.first_seen_at,
            )
        )
