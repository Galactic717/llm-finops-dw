import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

from ingestion.files import write_json
from ingestion.warehouse import connect

MARGIN = 0.015
ARMS = ("all_cloud", "hybrid")


def load_experiment(experiment_id: str, data_kind: str) -> pd.DataFrame:
    with connect() as conn:
        cursor = conn.execute("""
            SELECT event_id, occurred_at, workflow, arm, status, ground_truth, prediction,
                   latency_ms, cost_usd AS charged_usd, data_kind, fallback
            FROM gold.fct_llm_runs
            WHERE experiment_id = %s AND data_kind = %s
            ORDER BY occurred_at, event_id
        """, (experiment_id, data_kind))
        return pd.DataFrame(cursor.fetchall(), columns=[d.name for d in cursor.description])


def indicators(frame: pd.DataFrame, labels: np.ndarray) -> np.ndarray:
    actual = frame["ground_truth"].to_numpy()[:, None] == labels
    predicted = frame["prediction"].fillna("__no_prediction__").to_numpy()[:, None] == labels
    return np.stack((2 * (actual & predicted), actual.astype(float) + predicted), axis=-1)


def f1(matrix: np.ndarray) -> float:
    numerator, denominator = matrix.mean(axis=0).T
    return float(np.divide(numerator, denominator, out=np.zeros_like(numerator),
                           where=denominator != 0).mean())


def influence_variance(matrix: np.ndarray) -> float:
    mean = matrix.mean(axis=0)
    if np.any(mean[:, 1] == 0):
        raise ValueError("Each class needs representation in both arms for the power estimate")
    influence = (matrix[:, :, 0] / mean[:, 1]
                 - matrix[:, :, 1] * mean[:, 0] / mean[:, 1] ** 2).mean(axis=1)
    return float(influence.var(ddof=1))


def analyze_experiment(frame: pd.DataFrame, resamples: int = 1000, seed: int = 42) -> dict:
    if resamples < 100:
        raise ValueError("Use at least 100 bootstrap replicates")
    if frame.empty or frame["event_id"].duplicated().any() or set(frame["arm"]) != set(ARMS):
        raise ValueError("Experiment requires unique assignments in both arms")
    if frame["ground_truth"].isna().any():
        raise ValueError("Every assignment needs a ground-truth label for intention-to-treat analysis")
    if frame["charged_usd"].isna().any():
        raise ValueError("Complete cost coverage is required for a policy savings estimate")

    control, hybrid = [frame.loc[frame["arm"] == arm].reset_index(drop=True) for arm in ARMS]
    if min(len(control), len(hybrid)) < 2:
        raise ValueError("Both arms need at least two assignments")
    srm = stats.chisquare([len(control), len(hybrid)])
    labels = np.sort(frame["ground_truth"].unique())
    costs = [part["charged_usd"].astype(float).to_numpy() for part in (control, hybrid)]
    if costs[0].mean() <= 0:
        raise ValueError("Control must have a positive mean cost")
    latencies = [part.loc[part["status"] == "ok", "latency_ms"].dropna().astype(float)
                 for part in (control, hybrid)]
    matrices = [indicators(part, labels) for part in (control, hybrid)]
    point_f1 = [f1(matrix) for matrix in matrices]
    rng = np.random.default_rng(seed)
    samples = np.empty((resamples, 2))
    for index in range(resamples):
        c, h = [rng.integers(0, len(part), size=len(part)) for part in (control, hybrid)]
        baseline_cost = costs[0][c].mean()
        samples[index] = [
            f1(matrices[1][h]) - f1(matrices[0][c]),
            1 - costs[1][h].mean() / baseline_cost if baseline_cost > 0 else np.nan,
        ]

    if not np.isfinite(samples).all():
        raise ValueError("Zero baseline spend in at least one bootstrap draw")
    f1_ci, savings_ci = np.quantile(samples, [0.025, 0.975], axis=0).T
    variance = sum(influence_variance(matrix) for matrix in matrices)
    power_per_arm = int(np.ceil(variance * (stats.norm.ppf(0.975) + stats.norm.ppf(0.8))**2
                                / MARGIN ** 2))
    return {
        "arm_sizes": dict(zip(ARMS, map(len, (control, hybrid)), strict=True)),
        "srm_p": float(srm.pvalue),
        "macro_f1": dict(zip(ARMS, point_f1, strict=True)),
        "macro_f1_delta": point_f1[1] - point_f1[0],
        "macro_f1_delta_ci95": f1_ci.tolist(),
        "noninferiority_margin": -MARGIN,
        "noninferiority_supported": bool(srm.pvalue >= 0.05 and f1_ci[0] > -MARGIN),
        "cost_savings": float(1 - costs[1].mean() / costs[0].mean()),
        "cost_savings_ci95": savings_ci.tolist(),
        "cost_welch_p_secondary": float(stats.ttest_ind(*costs, equal_var=False).pvalue),
        "success_latency_mwu_p_secondary": (
            float(stats.mannwhitneyu(*latencies).pvalue) if all(len(x) for x in latencies) else None
        ),
        "success_latency_p95_ms": {
            arm: float(x.quantile(0.95)) if len(x) else None
            for arm, x in zip(ARMS, latencies, strict=True)
        },
        "pilot_n_per_arm_at_80pct_power_assuming_equal_f1": power_per_arm,
        "bootstrap_replicates": resamples,
    }


def fit_latency(frame: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    events = frame.loc[frame["status"] == "ok"].copy()
    events["event_date"] = pd.to_datetime(events["occurred_at"], utc=True).dt.floor("D")
    timeline = (events.groupby(["event_date", "arm", "workflow"], observed=True)["latency_ms"]
                .agg(samples="count", p95_ms=lambda s: s.quantile(0.95)).reset_index())
    timeline = timeline[timeline["samples"] >= 12].sort_values("event_date").copy()
    timeline["weekday"] = timeline["event_date"].dt.dayofweek
    timeline["last_p95_ms"] = timeline.groupby(["arm", "workflow"])["p95_ms"].shift()
    timeline = timeline.dropna(subset=["last_p95_ms"])
    days = sorted(timeline["event_date"].unique())
    if len(days) < 15:
        raise ValueError("Latency training needs at least 15 distinct fit-ready days")
    split = days[int(len(days) * 0.8)]
    train = timeline.loc[timeline["event_date"] < split]
    test = timeline.loc[timeline["event_date"] >= split].copy()
    inputs = ["arm", "workflow", "weekday", "last_p95_ms"]
    model = make_pipeline(
        ColumnTransformer([("category", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                            ["arm", "workflow"])], remainder="passthrough"),
        HistGradientBoostingRegressor(max_iter=120, max_leaf_nodes=12, random_state=42),
    )
    model.fit(train[inputs], train["p95_ms"])
    test["predicted_p95_ms"] = model.predict(test[inputs])
    return ({
        "train_last_day": train["event_date"].max().date().isoformat(),
        "test_first_day": test["event_date"].min().date().isoformat(),
        "test_last_day": test["event_date"].max().date().isoformat(),
        "train_groups": len(train),
        "test_groups": len(test),
        "model_mae_ms": float(mean_absolute_error(test["p95_ms"], test["predicted_p95_ms"])),
        "last_observation_mae_ms": float(mean_absolute_error(test["p95_ms"], test["last_p95_ms"])),
    }, test)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a single routing experiment")
    parser.add_argument("--experiment", default="routing-demo-42")
    parser.add_argument("--data-kind", default="synthetic", choices=["synthetic", "observed", "live"])
    parser.add_argument("--out", type=Path, default=Path("output/analysis"))
    args = parser.parse_args()
    events = load_experiment(args.experiment, args.data_kind)
    result = analyze_experiment(events)
    ml, predictions = fit_latency(events)
    report = {"experiment": args.experiment, "data_kind": args.data_kind,
              "ab": result, "ml": ml}
    write_json(args.out / "routing.json", report)
    predictions.to_csv(args.out / "p95_predictions.csv", index=False)
    print(report)


if __name__ == "__main__":
    main()
