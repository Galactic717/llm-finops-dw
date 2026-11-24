import argparse
import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ingestion.contracts import validate_events
from ingestion.files import DATA_DIR, read_jsonl, write_jsonl

CLOUD = "demo/cloud-frontier"
LOCAL = "demo/verifine-slm"
LABELS = ("invoice", "support", "risk", "other")
REFERENCE_END = date(2026, 11, 24)
REFERENCE_DAYS = 90
REFERENCE_PER_DAY = 240


def demo_model_ids(end: date, days: int) -> tuple[str, str]:
    suffix = "" if (end, days) == (REFERENCE_END, REFERENCE_DAYS) else f"/{end}-{days}d"
    return CLOUD + suffix, LOCAL + suffix


def generate_demo(end: date, days: int, per_day: int, seed: int) -> list[dict]:
    if min(days, per_day) < 1:
        raise ValueError("Days and events per day must be positive")
    is_reference = (end, days, per_day) == (REFERENCE_END, REFERENCE_DAYS, REFERENCE_PER_DAY)
    experiment = f"routing-demo-{seed}"
    namespace = f"finops/{seed}"
    if not is_reference:
        experiment += f"-{end}-{days}d-{per_day}r"
        namespace = f"finops/{experiment}"
    cloud, local = demo_model_ids(end, days)
    rng = random.Random(seed)
    rows = []
    for day_index in range(days):
        day = end - timedelta(days=days - 1 - day_index)
        midnight = datetime.combine(day, datetime.min.time(), timezone.utc)
        for index in range(per_day):
            at = midnight + timedelta(seconds=rng.randrange(86400))
            tenant = rng.choices(range(1, 25), [1 / n for n in range(1, 25)])[0]
            truth = rng.choices(LABELS, [0.32, 0.36, 0.12, 0.20])[0]
            hybrid = rng.random() < 0.5
            fallback = hybrid and rng.random() < (0.39 if truth == "risk" else 0.23)
            local_final = hybrid and not fallback
            failed = rng.random() < 0.008
            correct = rng.random() < (0.946 if local_final else 0.953)
            inp = rng.randint(128, 3000)
            out = rng.randint(24, 300)
            latency = rng.lognormvariate(math.log(410 if local_final else 1100), 0.38)
            latency += inp * (0.26 if local_final else 0.38) + (450 if fallback else 0)
            latency *= 1 + 0.18 * math.sin(day_index / 7)
            delta = DecimalRates(at.date() < end - timedelta(days=44))
            cost = (inp * delta.input + out * delta.output) if not local_final else 0
            if hybrid:
                cost += inp * 0.00000007 + out * 0.00000013
            rows.append(dict(
                event_id=str(uuid5(NAMESPACE_URL, f"{namespace}/{day}/{index}")),
                occurred_at=at.isoformat(), tenant_id=f"demo-{tenant:02}",
                workflow={"other": "classification"}.get(truth, truth),
                model_id=local if local_final else cloud,
                data_kind="synthetic", source="demo", status="error" if failed else "ok",
                input_tokens=inp, output_tokens=out, latency_ms=round(latency, 3),
                charged_usd=f"{cost:.10f}", experiment_id=experiment,
                arm="hybrid" if hybrid else "all_cloud", ground_truth=truth,
                prediction=None if failed else (truth if correct else rng.choice(
                    [label for label in LABELS if label != truth])),
                fallback=bool(fallback),
            ))
    return rows


class DecimalRates:
    def __init__(self, older: bool) -> None:
        self.input = 0.0000038 if older else 0.0000032
        self.output = 0.000013 if older else 0.000011


def demo_prices(end: date, days: int) -> list[dict]:
    change = end - timedelta(days=44)
    start = min(end - timedelta(days=days - 1), change - timedelta(days=1))
    cloud, local = demo_model_ids(end, days)
    return [
        dict(model_id=model, observed_at=f"{day}T00:00:00Z", input_usd=inp,
             output_usd=out, source="demo")
        for model, day, inp, out in [
            (cloud, start, "0.0000038", "0.000013"),
            (cloud, change, "0.0000032", "0.000011"),
            (local, start, "0.00000007", "0.00000013"),
        ]
    ]


def verifine_events(report: dict, occurred_at: str, revision: str) -> list[dict]:
    items = report.get("predictions", report.get("requests"))
    if not isinstance(items, list):
        raise ValueError("Report must contain predictions or requests")
    return validate_events([
        dict(
            event_id=str(uuid5(NAMESPACE_URL, f"verifine/{revision}/{index}/{row['id']}")),
            occurred_at=row.get("occurred_at") or occurred_at,
            tenant_id="verifine-benchmark", workflow=row.get("task") or "serving_benchmark",
            model_id=f"verifine/{report['model']}", data_kind="observed", source="verifine",
            status="error" if row.get("error") else "ok",
            input_tokens=row.get("prompt_tokens"), output_tokens=row.get("completion_tokens"),
            latency_ms=row.get("elapsed_ms"), ttft_ms=row.get("ttft_ms"),
            charged_usd=None,
        )
        for index, row in enumerate(items)
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo telemetry or import existing runs")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--end", type=date.fromisoformat, default=REFERENCE_END)
    demo.add_argument("--days", type=int, default=REFERENCE_DAYS)
    demo.add_argument("--per-day", type=int, default=REFERENCE_PER_DAY)
    demo.add_argument("--seed", type=int, default=42)
    verstak = commands.add_parser("jsonl")
    verstak.add_argument("path", type=Path)
    verifine = commands.add_parser("verifine")
    verifine.add_argument("path", type=Path)
    verifine.add_argument("--at", help="UTC timestamp. Defaults to the report file's modification time.")
    args = parser.parse_args()
    inbox = args.data_dir / "inbox"
    if args.command == "demo":
        rows = validate_events(generate_demo(args.end, args.days, args.per_day, args.seed))
        experiment = rows[0]["experiment_id"]
        filename = "demo" if experiment == "routing-demo-42" else experiment
        write_jsonl(inbox / "prices" / f"{filename}.jsonl", demo_prices(args.end, args.days))
    elif args.command == "verifine":
        revision = hashlib.sha256(args.path.read_bytes()).hexdigest()
        at = args.at or datetime.fromtimestamp(args.path.stat().st_mtime, timezone.utc).isoformat()
        rows = verifine_events(json.loads(args.path.read_bytes()), at, revision)
        filename = f"verifine-{revision[:16]}"
    else:
        rows = validate_events(read_jsonl(args.path))
        filename = "import-" + hashlib.sha256(args.path.read_bytes()).hexdigest()[:16]
    write_jsonl(inbox / "events" / f"{filename}.jsonl", rows)
    print(f"{args.command}: {len(rows)} accepted events")
    if args.command == "demo":
        print(f"Experiment: {experiment}")


if __name__ == "__main__":
    main()
