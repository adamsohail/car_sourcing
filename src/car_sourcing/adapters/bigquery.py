"""Stockage BigQuery.

- `listings` : MERGE (DML) car une annonce est mise à jour (dernière vue, baisse de prix).
- `evaluations`, `alerts`, `feedback`, `geocode_cache`, `tech_alerts` : ajout seul (insertion en flux).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from car_sourcing.domain.config import Config
from car_sourcing.domain.models import AlertLevel, Comparable, Evaluation, FeedbackStatus, Listing, Source
from car_sourcing.domain.rules import PreviousAlert

SQL_DIR = Path(__file__).resolve().parents[3] / "sql"
if not SQL_DIR.exists():  # image Docker : sql/ copié à côté du paquet
    SQL_DIR = Path("/app/sql")

_BQ_TYPES = {
    "STRING": "STRING",
    "INT64": "INT64",
    "FLOAT64": "FLOAT64",
    "TIMESTAMP": "TIMESTAMP",
    "BOOL": "BOOL",
}


def load_schema(table: str) -> list[dict[str, str]]:
    return list(json.loads((SQL_DIR / "schemas" / f"{table}.json").read_text()))


def render_sql(name: str, project: str, dataset: str) -> str:
    return (SQL_DIR / name).read_text().replace("${project}", project).replace("${dataset}", dataset)


def listing_row(listing: Listing) -> dict[str, Any]:
    row = listing.model_dump(mode="json")
    row["brand_norm"] = listing.brand_norm
    row["model_norm"] = listing.model_norm
    return row


def row_to_listing(row: dict[str, Any]) -> Listing:
    fields = {k: row.get(k) for k in Listing.model_fields}
    return Listing.model_validate(fields)


class BigQueryRepository:
    def __init__(
        self, project: str, dataset: str, location: str = "EU", client: bigquery.Client | None = None
    ) -> None:
        self.project, self.dataset = project, dataset
        self.client = client or bigquery.Client(project=project, location=location)
        self._listing_cols = [c["name"] for c in load_schema("listings")]
        self._listing_types = {c["name"]: _BQ_TYPES[c["type"]] for c in load_schema("listings")}

    def table(self, name: str) -> str:
        return f"`{self.project}.{self.dataset}.{name}`"

    def _query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        job = self.client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=list(params)))
        return [dict(r.items()) for r in job.result()]

    def _insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        errors = self.client.insert_rows_json(f"{self.project}.{self.dataset}.{table}", rows)
        if errors:
            raise RuntimeError(f"insertion {table} refusée : {errors}")

    # ---------- Pipeline ----------

    def get_listing(self, source: Source, listing_id: str) -> Listing | None:
        rows = self._query(
            f"SELECT * FROM {self.table('listings')} WHERE source = @s AND listing_id = @id LIMIT 1",
            [
                bigquery.ScalarQueryParameter("s", "STRING", source.value),
                bigquery.ScalarQueryParameter("id", "STRING", listing_id),
            ],
        )
        return row_to_listing(rows[0]) if rows else None

    def upsert_listing(self, listing: Listing) -> None:
        row = listing_row(listing)
        cols = self._listing_cols
        select = ", ".join(f"@{c} AS {c}" for c in cols)
        keep_first = {"source", "listing_id", "first_seen_at"}
        updates = ", ".join(
            f"{c} = GREATEST(t.{c}, s.{c})"
            if c == "last_seen_at"
            else f"{c} = s.{c}"
            if c in {"url", "enrichment_status", "price_eur"}
            else f"{c} = COALESCE(s.{c}, t.{c})"
            for c in cols
            if c not in keep_first
        )
        sql = (
            f"MERGE {self.table('listings')} AS t USING (SELECT {select}) AS s "
            "ON t.source = s.source AND t.listing_id = s.listing_id "
            f"WHEN MATCHED THEN UPDATE SET {updates} "
            f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join('s.' + c for c in cols)})"
        )
        params = [bigquery.ScalarQueryParameter(c, self._listing_types[c], row.get(c)) for c in cols]
        self._query(sql, params)

    def comparables_candidates(self, listing: Listing, config: Config, now: datetime) -> list[Comparable]:
        if None in (
            listing.brand_norm,
            listing.model_norm,
            listing.fuel,
            listing.gearbox,
            listing.year,
            listing.mileage_km,
        ):
            return []
        sql = render_sql("queries/comparables_candidates.sql", self.project, self.dataset)
        p = bigquery.ScalarQueryParameter
        rows = self._query(
            sql,
            [
                p("brand_norm", "STRING", listing.brand_norm),
                p("model_norm", "STRING", listing.model_norm),
                p("fuel", "STRING", listing.fuel.value if listing.fuel else None),
                p("gearbox", "STRING", listing.gearbox.value if listing.gearbox else None),
                p("since", "TIMESTAMP", now - timedelta(days=config.fenetre_comparables_jours)),
                p("source", "STRING", listing.source.value),
                p("listing_id", "STRING", listing.listing_id),
                p("year", "INT64", listing.year),
                p("mileage_km", "INT64", listing.mileage_km),
            ],
        )
        return [Comparable.model_validate(r) for r in rows]

    def insert_evaluation(self, evaluation: Evaluation) -> None:
        self._insert("evaluations", [evaluation.model_dump(mode="json")])

    def last_alert(self, source: Source, listing_id: str) -> PreviousAlert | None:
        rows = self._query(
            f"SELECT alert_level, price_eur FROM {self.table('alerts')} "
            "WHERE source = @s AND listing_id = @id ORDER BY sent_at DESC LIMIT 1",
            [
                bigquery.ScalarQueryParameter("s", "STRING", source.value),
                bigquery.ScalarQueryParameter("id", "STRING", listing_id),
            ],
        )
        return PreviousAlert(AlertLevel(rows[0]["alert_level"]), rows[0]["price_eur"]) if rows else None

    def insert_alert(
        self,
        source: Source,
        listing_id: str,
        level: AlertLevel,
        price_eur: int | None,
        telegram_message_id: int | None,
        sent_at: datetime,
    ) -> None:
        self._insert(
            "alerts",
            [
                {
                    "source": source.value,
                    "listing_id": listing_id,
                    "sent_at": sent_at.isoformat(),
                    "alert_level": level.value,
                    "price_eur": price_eur,
                    "telegram_message_id": telegram_message_id,
                }
            ],
        )

    def insert_feedback(
        self,
        source: Source,
        listing_id: str,
        status: FeedbackStatus,
        purchase_price_eur: int | None,
        author: str | None,
        created_at: datetime,
    ) -> None:
        self._insert(
            "feedback",
            [
                {
                    "source": source.value,
                    "listing_id": listing_id,
                    "created_at": created_at.isoformat(),
                    "status": status.value,
                    "purchase_price_eur": purchase_price_eur,
                    "author": author,
                }
            ],
        )

    def last_technical_alert(self, kind: str) -> datetime | None:
        rows = self._query(
            f"SELECT MAX(sent_at) AS t FROM {self.table('tech_alerts')} WHERE kind = @k",
            [bigquery.ScalarQueryParameter("k", "STRING", kind)],
        )
        value = rows[0]["t"] if rows else None
        return value if isinstance(value, datetime) else None

    def insert_technical_alert(self, kind: str, message: str, sent_at: datetime) -> None:
        self._insert(
            "tech_alerts", [{"kind": kind, "message": message[:1000], "sent_at": sent_at.isoformat()}]
        )

    # ---------- Cache de géocodage ----------

    def get_geocode(self, postal_code: str, city: str) -> tuple[float, float] | None:
        rows = self._query(
            f"SELECT lat, lon FROM {self.table('geocode_cache')} WHERE postal_code = @cp AND city = @c "
            "ORDER BY created_at DESC LIMIT 1",
            [
                bigquery.ScalarQueryParameter("cp", "STRING", postal_code),
                bigquery.ScalarQueryParameter("c", "STRING", city),
            ],
        )
        return (rows[0]["lat"], rows[0]["lon"]) if rows else None

    def put_geocode(self, postal_code: str, city: str, lat: float, lon: float) -> None:
        self._insert(
            "geocode_cache",
            [
                {
                    "postal_code": postal_code,
                    "city": city,
                    "lat": lat,
                    "lon": lon,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ],
        )

    # ---------- Interface web ----------

    def _status_rows(
        self, where: str, params: Sequence[Any], order: str, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        sql = (
            f"SELECT * EXCEPT (description) FROM {self.table('v_listing_status')} WHERE {where} "
            f"ORDER BY {order} LIMIT {int(limit)} OFFSET {int(offset)}"
        )
        return self._query(sql, params)

    def opportunities(self, since: datetime) -> list[dict[str, Any]]:
        """Alertes vues depuis `since`, plus toutes les annonces ayant reçu un avis."""
        return self._status_rows(
            "(statut = 'alerte' AND first_seen_at >= @since) OR feedback_status IS NOT NULL",
            [bigquery.ScalarQueryParameter("since", "TIMESTAMP", since)],
            "margin_eur DESC",
            500,
            0,
        )

    def search_listings(
        self, tokens: Sequence[str], statut: str | None, since: datetime, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        haystack = (
            "REGEXP_REPLACE(NORMALIZE(LOWER(CONCAT(IFNULL(title, ''), ' ', IFNULL(city, ''), ' ', "
            "IFNULL(postal_code, ''), ' ', IFNULL(CAST(year AS STRING), ''))), NFD), r'\\pM', '')"
        )
        where = ["first_seen_at >= @since"]
        params: list[Any] = [bigquery.ScalarQueryParameter("since", "TIMESTAMP", since)]
        for i, token in enumerate(tokens[:6]):
            where.append(f"{haystack} LIKE @q{i}")
            params.append(bigquery.ScalarQueryParameter(f"q{i}", "STRING", f"%{token}%"))
        base = " AND ".join(where)
        rows = self._query(
            f"SELECT statut, COUNT(*) AS n FROM {self.table('v_listing_status')} WHERE {base} GROUP BY statut",
            params,
        )
        counts = {r["statut"]: r["n"] for r in rows}
        if statut:
            base += " AND statut = @statut"
            params.append(bigquery.ScalarQueryParameter("statut", "STRING", statut))
        return self._status_rows(base, params, "first_seen_at DESC", limit, offset), counts

    def status_row(self, source: Source, listing_id: str) -> dict[str, Any] | None:
        rows = self._query(
            f"SELECT * FROM {self.table('v_listing_status')} WHERE source = @s AND listing_id = @id LIMIT 1",
            [
                bigquery.ScalarQueryParameter("s", "STRING", source.value),
                bigquery.ScalarQueryParameter("id", "STRING", listing_id),
            ],
        )
        return rows[0] if rows else None

    def stats(self, since: datetime) -> dict[str, Any]:
        p = [bigquery.ScalarQueryParameter("since", "TIMESTAMP", since)]
        t = self.table("v_listing_status")
        by_status = self._query(
            f"SELECT statut, COUNT(*) AS n FROM {t} WHERE first_seen_at >= @since GROUP BY statut", p
        )
        motifs = self._query(
            f"SELECT exclusion_reason AS motif, COUNT(*) AS n FROM {t} WHERE first_seen_at >= @since "
            "AND exclusion_reason IS NOT NULL GROUP BY motif ORDER BY n DESC",
            p,
        )
        per_day = self._query(
            f"SELECT DATE(first_seen_at, 'Europe/Paris') AS jour, alert_level, COUNT(*) AS n FROM {t} "
            "WHERE first_seen_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY) AND alert_level IS NOT NULL "
            "GROUP BY jour, alert_level ORDER BY jour"
        )
        feedback = self._query(
            f"SELECT feedback_status AS status, COUNT(*) AS n FROM {t} WHERE feedback_status IS NOT NULL GROUP BY status"
        )
        purchases = self._query(
            f"SELECT source, listing_id, brand, model, year, price_eur, purchase_price_eur, market_price_eur, margin_eur, feedback_at "
            f"FROM {t} WHERE feedback_status = 'achete' ORDER BY feedback_at DESC LIMIT 100"
        )
        return {
            "by_status": by_status,
            "motifs": motifs,
            "per_day": per_day,
            "feedback": feedback,
            "purchases": purchases,
        }
