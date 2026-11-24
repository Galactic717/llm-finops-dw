from datetime import date

import pytest


def test_demo_is_deterministic_and_covers_ninety_days():
    from ingestion.ingest_verstak_logs import generate_demo

    rows = generate_demo(date(2026, 11, 24), 90, 5, 42)
    assert rows == generate_demo(date(2026, 11, 24), 90, 5, 42)
    assert len({row["event_id"] for row in rows}) == 450
    assert len({row["occurred_at"][:10] for row in rows}) == 90
    assert {row["data_kind"] for row in rows} == {"synthetic"}


def test_bad_latency_or_conflicting_id_is_rejected():
    from ingestion.contracts import validate_events
    from ingestion.ingest_verstak_logs import generate_demo

    event = generate_demo(date(2026, 11, 24), 1, 1, 42)[0]
    assert len(validate_events([event, event])) == 1
    with pytest.raises(ValueError, match="Conflicting"):
        validate_events([event, {**event, "latency_ms": 42}])
    with pytest.raises(ValueError):
        validate_events([{**event, "latency_ms": -1}])
    with pytest.raises(ValueError, match="offset"):
        validate_events([{**event, "occurred_at": "2026-11-24T00:00:00"}])


def test_changed_simulation_windows_can_coexist():
    from ingestion.contracts import validate_events
    from ingestion.ingest_verstak_logs import generate_demo

    start = generate_demo(date(2026, 11, 24), 2, 3, 42)
    shifted = generate_demo(date(2026, 11, 25), 2, 3, 42)
    resized = generate_demo(date(2026, 11, 24), 2, 4, 42)
    assert len(validate_events(start + shifted + resized)) == 20
    assert len({row["experiment_id"] for row in start + shifted + resized}) == 3


def test_openrouter_prices_are_per_token_and_missing_prices_are_unknown():
    from ingestion.fetch_open_models import openrouter_prices

    models = {"data": [
        {"id": "a/b", "pricing": {"prompt": "0.000001", "completion": "0"}},
        {"id": "a/c", "pricing": {"prompt": "0.2"}},
        {"id": "a/d", "pricing": {"prompt": "-1", "completion": "0"}},
    ]}
    rows = openrouter_prices(models, "2026-11-24T00:00:00Z")
    assert [(r["model_id"], r["input_usd"], r["output_usd"]) for r in rows] == [
        ("a/b", "0.000001", "0")
    ]


def test_serving_import_strips_prediction_and_keeps_unknown_cost():
    from ingestion.ingest_verstak_logs import verifine_events

    report = {"model": "q4", "requests": [
        {"id": "invoice-1", "elapsed_ms": 20, "schema_valid": True,
         "prompt_tokens": 100, "completion_tokens": 20, "text": "private"}
    ]}
    [row] = verifine_events(report, "2026-11-24T00:00:00Z", "serving.json")
    assert row["input_tokens"] == 100
    assert row["charged_usd"] is None
    assert row["data_kind"] == "observed"
    assert "private" not in str(row)
