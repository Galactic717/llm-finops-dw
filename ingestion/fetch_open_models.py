import argparse
import os
from pathlib import Path

import httpx

from ingestion.contracts import money, validate
from ingestion.files import DATA_DIR, now, write_json, write_jsonl

OPENROUTER = "https://openrouter.ai/api/v1/models"
HF = "https://datasets-server.huggingface.co/rows"
HF_DATASET = "open-llm-leaderboard/contents"
AA = "https://artificialanalysis.ai/api/v2/language/models/free"
HF_METRICS = ("IFEval", "BBH", "MATH Lvl 5", "GPQA", "MUSR", "MMLU-PRO")


def openrouter_prices(payload: dict, observed_at: str) -> list[dict]:
    result = []
    for model in payload["data"]:
        pricing = model.get("pricing") or {}
        try:
            inp, out = money(pricing["prompt"]), money(pricing["completion"])
        except (KeyError, ValueError):
            continue
        result.append(dict(model_id=model["id"], observed_at=observed_at,
                           input_usd=inp, output_usd=out, source="openrouter"))
    return validate(result, "prices")


def hf_scores(payload: dict, observed_at: str) -> list[dict]:
    return validate([
        dict(source="hf_open_llm_leaderboard", model_id=row["fullname"], benchmark=metric,
             score=row[metric], observed_at=observed_at,
             revision=row.get("eval_name") or str(index))
        for index, row in enumerate(payload["rows"])
        if row.get("fullname") and not row.get("Flagged")
        for metric in HF_METRICS if row.get(metric) is not None
    ], "scores")


def fetch_open_data(root: Path, hf_limit: int, artificial_analysis: bool) -> dict:
    observed = now()
    slug = observed.replace(":", "").replace("+", "_")
    receipt = {}
    with httpx.Client(timeout=35, follow_redirects=True) as client:
        response = client.get(OPENROUTER)
        response.raise_for_status()
        payload = response.json()
        pricing = openrouter_prices(payload, observed)
        if not pricing:
            raise ValueError("OpenRouter returned no usable prices")
        write_json(root / "raw" / slug / "openrouter.json", payload)
        write_jsonl(root / "inbox" / "prices" / f"openrouter-{slug}.jsonl", pricing)
        receipt["openrouter_models"] = len(pricing)

        rows = []
        for offset in range(0, hf_limit, 100):
            response = client.get(HF, params=dict(dataset=HF_DATASET, config="default",
                                                  split="train", offset=offset,
                                                  length=min(100, hf_limit - offset)))
            response.raise_for_status()
            page = response.json()
            rows.extend(item["row"] for item in page["rows"])
            if len(rows) >= page["num_rows_total"]:
                break
        if rows:
            payload = {"rows": rows}
            scores = hf_scores(payload, observed)
            if not scores:
                raise ValueError("Hugging Face returned no usable benchmark rows")
            write_json(root / "raw" / slug / "hf.json", payload)
            write_jsonl(root / "inbox" / "scores" / f"hf-{slug}.jsonl", scores)
            receipt["hf_scores"] = len(scores)

        if artificial_analysis:
            key = os.environ.get("AA_API_KEY")
            if not key:
                raise ValueError("AA_API_KEY is required for the optional Artificial Analysis export")
            response = client.get(AA, headers={"x-api-key": key})
            response.raise_for_status()
            write_json(root / "private" / slug / "artificial-analysis.json", response.json())
            receipt["artificial_analysis"] = "private export"
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect open market and benchmark observations")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--hf-limit", type=int, default=100)
    parser.add_argument("--artificial-analysis", action="store_true")
    args = parser.parse_args()
    if args.hf_limit < 0:
        parser.error("--hf-limit must be >= 0")
    print(fetch_open_data(args.data_dir, args.hf_limit, args.artificial_analysis))


if __name__ == "__main__":
    main()
