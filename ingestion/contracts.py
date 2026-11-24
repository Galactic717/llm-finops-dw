from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaError

EVENT_FIELDS = (
    "event_id", "occurred_at", "tenant_id", "workflow", "model_id", "data_kind", "source",
    "status", "input_tokens", "output_tokens", "latency_ms", "charged_usd", "ttft_ms",
    "experiment_id", "arm", "ground_truth", "prediction", "fallback",
)
PRICE_FIELDS = ("model_id", "observed_at", "input_usd", "output_usd", "source")
SCORE_FIELDS = ("source", "model_id", "benchmark", "score", "observed_at", "revision")
KINDS = ["synthetic", "observed", "live"]
STATUSES = ["ok", "error", "rejected", "pending"]
ARMS = ["all_cloud", "hybrid"]


def timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Timestamp must have an explicit UTC offset")
    return parsed.astimezone(timezone.utc).isoformat()


def money(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid USD amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("USD amount must be finite and non-negative")
    return format(amount.normalize(), "f")


def finite(series: pd.Series) -> pd.Series:
    return series.abs().lt(float("inf"))


def string(nullable: bool = False) -> pa.Column:
    return pa.Column(str, pa.Check.str_length(min_value=1, max_value=255), nullable=nullable)


EVENT_SCHEMA = pa.DataFrameSchema({
    **{name: string() for name in EVENT_FIELDS[:7]},
    "data_kind": pa.Column(str, pa.Check.isin(KINDS)),
    "status": pa.Column(str, pa.Check.isin(STATUSES)),
    "input_tokens": pa.Column(pd.Int64Dtype(), pa.Check.ge(0), nullable=True),
    "output_tokens": pa.Column(pd.Int64Dtype(), pa.Check.ge(0), nullable=True),
    "latency_ms": pa.Column(float, [pa.Check.gt(0), pa.Check(finite)], nullable=True),
    "charged_usd": string(nullable=True),
    "ttft_ms": pa.Column(float, [pa.Check.gt(0), pa.Check(finite)], nullable=True),
    "experiment_id": string(nullable=True),
    "arm": pa.Column(str, pa.Check.isin(ARMS), nullable=True),
    "ground_truth": string(nullable=True),
    "prediction": string(nullable=True),
    "fallback": pa.Column(pd.BooleanDtype(), nullable=True),
}, strict=True)
PRICE_SCHEMA = pa.DataFrameSchema({name: string() for name in PRICE_FIELDS}, strict=True)
SCORE_SCHEMA = pa.DataFrameSchema({
    **{name: string() for name in SCORE_FIELDS if name != "score"},
    "score": pa.Column(float, pa.Check.in_range(0, 100)),
}, strict=True)


def validate(records: list[dict], kind: str) -> list[dict]:
    fields, schema, keys = {
        "events": (EVENT_FIELDS, EVENT_SCHEMA, ("event_id",)),
        "prices": (PRICE_FIELDS, PRICE_SCHEMA, ("model_id", "observed_at", "source")),
        "scores": (SCORE_FIELDS, SCORE_SCHEMA, SCORE_FIELDS[:3] + ("observed_at", "revision")),
    }[kind]
    unique = {}
    for record in records:
        row = {field: record.get(field) for field in fields}
        for field in ("occurred_at", "observed_at"):
            if field in row:
                row[field] = timestamp(row[field])
        for field in ("charged_usd", "input_usd", "output_usd"):
            if row.get(field) is not None:
                row[field] = money(row[field])
        if kind == "events":
            if bool(row["arm"]) != bool(row["experiment_id"]):
                raise ValueError("Arm and experiment ID must be supplied together")
            if row["ttft_ms"] is not None and (
                row["latency_ms"] is None or row["ttft_ms"] > row["latency_ms"]
            ):
                raise ValueError("TTFT must fit within request latency")
            for field in ("input_tokens", "output_tokens"):
                if row[field] is not None and type(row[field]) is not int:
                    raise ValueError("Token counts must be integers")
            if row["fallback"] is not None and type(row["fallback"]) is not bool:
                raise ValueError("Fallback must be boolean")
        key = tuple(row[field] for field in keys)
        if key in unique and unique[key] != row:
            raise ValueError(f"Conflicting {kind} key {key}")
        unique[key] = row

    rows = list(unique.values())
    if rows:
        frame = pd.DataFrame(rows, columns=list(fields))
        casts = {
            "input_tokens": "Int64", "output_tokens": "Int64", "fallback": "boolean",
            "latency_ms": float, "ttft_ms": float, "score": float,
        }
        try:
            schema.validate(frame.astype({k: v for k, v in casts.items() if k in fields}))
        except (SchemaError, TypeError) as exc:
            raise ValueError(f"Invalid {kind} contract: {exc}") from exc
    return rows


def validate_events(records: list[dict]) -> list[dict]:
    return validate(records, "events")
