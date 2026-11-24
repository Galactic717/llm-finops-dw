from datetime import date

import pandas as pd
import pytest


def test_experiment_rejects_missing_cost_and_retains_failed_assignments():
    from analysis.routing import analyze_experiment
    from ingestion.ingest_verstak_logs import generate_demo

    rows = pd.DataFrame(generate_demo(date(2026, 11, 24), 5, 100, 42))
    rows.loc[0, ["prediction", "status"]] = [None, "error"]
    result = analyze_experiment(rows, resamples=100)
    assert sum(result["arm_sizes"].values()) == 500
    rows.loc[0, "charged_usd"] = None
    with pytest.raises(ValueError, match="cost"):
        analyze_experiment(rows, resamples=100)


def test_latency_holdout_is_later_than_training():
    from analysis.routing import fit_latency
    from ingestion.ingest_verstak_logs import generate_demo

    rows = pd.DataFrame(generate_demo(date(2026, 11, 24), 30, 240, 42))
    result, predictions = fit_latency(rows)
    assert result["train_last_day"] < result["test_first_day"]
    assert predictions["event_date"].nunique() >= 5
    assert result["model_mae_ms"] > 0
