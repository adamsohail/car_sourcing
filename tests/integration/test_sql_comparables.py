"""Test SQL sur un vrai dataset BigQuery de test.

Lancer : BQ_TEST_PROJECT=mon-projet BQ_TEST_DATASET=car_sourcing_test uv run pytest -m bigquery
Le dataset est créé, rempli d'un petit jeu de données, puis supprimé.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest

from car_sourcing.domain.models import ExclusionReason, SellerType
from car_sourcing.domain.rules import evaluate, market_price
from tests.conftest import NOW, make_config, make_listing

pytestmark = pytest.mark.bigquery

PROJECT = os.environ.get("BQ_TEST_PROJECT")
DATASET = os.environ.get("BQ_TEST_DATASET")


@pytest.fixture(scope="module")
def repo():
    if not (PROJECT and DATASET):
        pytest.skip("BQ_TEST_PROJECT et BQ_TEST_DATASET non définis")
    from google.cloud import bigquery

    from car_sourcing.adapters.bigquery import BigQueryRepository, load_schema, render_sql

    client = bigquery.Client(project=PROJECT, location="EU")
    ds = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    ds.location = "EU"
    client.create_dataset(ds, exists_ok=True)
    for table in ("listings", "evaluations", "alerts", "feedback", "geocode_cache", "tech_alerts"):
        schema = [bigquery.SchemaField(c["name"], c["type"], mode=c["mode"]) for c in load_schema(table)]
        client.create_table(bigquery.Table(f"{PROJECT}.{DATASET}.{table}", schema=schema), exists_ok=True)
    for view in ("v_latest_evaluation", "v_latest_feedback", "v_listing_status"):
        v = bigquery.Table(f"{PROJECT}.{DATASET}.{view}")
        v.view_query = render_sql(f"views/{view}.sql", PROJECT, DATASET)
        client.create_table(v, exists_ok=True)
    yield BigQueryRepository(PROJECT, DATASET, client=client)
    client.delete_dataset(f"{PROJECT}.{DATASET}", delete_contents=True, not_found_ok=True)


def test_upsert_et_comparables(repo) -> None:
    config = make_config()
    recent, old = NOW - timedelta(days=5), NOW - timedelta(days=120)
    rows = [
        make_listing(listing_id="a", price_eur=12000, first_seen_at=recent, last_seen_at=recent),
        make_listing(
            listing_id="b",
            price_eur=12500,
            mileage_km=85000,
            seller_type=SellerType.PRO,
            first_seen_at=recent,
            last_seen_at=recent,
        ),
        make_listing(listing_id="c", price_eur=11800, year=2021, first_seen_at=recent, last_seen_at=recent),
        make_listing(listing_id="trop_vieux", price_eur=9000, first_seen_at=old, last_seen_at=old),
        make_listing(
            listing_id="diesel", price_eur=9000, fuel="Diesel", first_seen_at=recent, last_seen_at=recent
        ),
        make_listing(
            listing_id="loin_km", price_eur=9000, mileage_km=150000, first_seen_at=recent, last_seen_at=recent
        ),
        make_listing(
            listing_id="epave", price_eur=3000, description="épave", first_seen_at=recent, last_seen_at=recent
        ),
        make_listing(listing_id="cible", price_eur=8000, first_seen_at=NOW, last_seen_at=NOW),
    ]
    for listing in rows:
        repo.upsert_listing(listing)
    epave = rows[6]
    repo.insert_evaluation(evaluate(epave, config, [], (45.76, 4.86), NOW))

    # Second upsert : dernière vue et prix mis à jour, première vue conservée.
    repo.upsert_listing(rows[0].model_copy(update={"last_seen_at": NOW, "price_eur": 11900}))
    stored = repo.get_listing(rows[0].source, "a")
    assert stored is not None
    assert stored.price_eur == 11900
    assert stored.first_seen_at == recent
    assert stored.last_seen_at == NOW

    target = rows[-1]
    cands = repo.comparables_candidates(target, config, NOW)
    ids = sorted(c.listing_id for c in cands)
    assert ids == ["a", "b", "c"]
    assert repo.get_listing(target.source, "epave") is not None
    mp = market_price(2019, 70000, cands, config.comparables_min)
    assert mp.value == 11900
    ev = repo.status_row(epave.source, "epave")
    assert ev is not None
    assert ev["exclusion_reason"] == ExclusionReason.MOT_CLE.value
    assert ev["statut"] == "exclue"
