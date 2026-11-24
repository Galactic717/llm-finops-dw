import argparse
import statistics
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from ingestion.contracts import validate_events
from ingestion.files import DATA_DIR, now, write_jsonl

PROMPTS = (
    "Classify as invoice, support, or other. Reply with one label. Text: Please reset my password.",
    "Classify as invoice, support, or other. Reply with one label. Text: Invoice 721 totals 75 USD.",
    "Classify as invoice, support, or other. Reply with one label. Text: Tomorrow is a holiday.",
)


def capture(base_url: str, model: str, count: int) -> list[dict]:
    url = urlsplit(base_url)
    if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("The smoke runner requires a loopback HTTP llama.cpp endpoint")
    if count < 1:
        raise ValueError("Count must be positive")
    rows = []
    with httpx.Client(timeout=60, trust_env=False) as client:
        client.get(base_url.rstrip("/") + "/health").raise_for_status()
        for index in range(count):
            started_at = now()
            started = perf_counter()
            model_id = model
            usage = {}
            status = "ok"
            try:
                response = client.post(base_url.rstrip("/") + "/v1/chat/completions", json={
                    "model": model, "messages": [
                        {"role": "user", "content": PROMPTS[index % len(PROMPTS)]}
                    ], "temperature": 0, "max_tokens": 32,
                })
                response.raise_for_status()
                result = response.json()
                usage = result["usage"]
                model_id = result.get("model", model)
                if not result.get("choices"):
                    status = "error"
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                status = "error"
            rows.append(dict(event_id=str(uuid4()), occurred_at=started_at,
                             tenant_id="local-smoke", workflow="classification",
                             model_id=f"llamacpp/{model_id}", data_kind="live", source="llamacpp",
                             status=status, latency_ms=round((perf_counter() - started) * 1000, 3),
                             input_tokens=usage.get("prompt_tokens"),
                             output_tokens=usage.get("completion_tokens")))
    return validate_events(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure an existing llama.cpp model")
    parser.add_argument("--base-url", default="http://127.0.0.1:9941")
    parser.add_argument("--model", default="verifine-qwen-q4")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    rows = capture(args.base_url, args.model, args.count)
    path = args.data_dir / "inbox" / "events" / f"llamacpp-{rows[0]['event_id']}.jsonl"
    write_jsonl(path, rows)
    successful = [row["latency_ms"] for row in rows if row["status"] == "ok"]
    print(f"Stored {len(rows)} events to {path}, {len(successful)} successful")
    if not successful:
        raise SystemExit(1)
    print(f"Median successful latency: {statistics.median(successful):.1f} ms")


if __name__ == "__main__":
    main()
