# Warehouse contract

An event is one policy assignment, model request, or workflow run. The source establishes the grain. The warehouse retains that grain under a globally unique event ID and records it as a Bronze JSONB observation before modeling it in Silver and Gold.

| Source | Grain | Data kind | Timing | USD |
| --- | --- | --- | --- | --- |
| Verstak | Terminal workflow run | Observed | Creation to completion, including queueing | Reported workflow ledger cost |
| VeriFine | Serving or evaluation request | Observed | Evaluation elapsed time and optional TTFT | Unknown. Historical estimates are not billed charges |
| llama.cpp | Local synthetic-probe HTTP request | Live | Client-observed end-to-end latency | Unknown. No electricity accounting |
| Demo | One randomized routing assignment | Synthetic | Simulated request latency | Simulated effective policy cost, including both legs on fallback |

## Ingestion

Validated files live under `data/inbox/{events,prices,scores}`. `prepare` validates each record, removes exact duplicates, rejects conflicting keys, and writes a deterministic batch. A PostgreSQL transaction loads the entire batch under an advisory lock. A retry inserts zero rows. Conflicting updates abort the batch. Use a new event ID when source observations are genuinely distinct.

Each simulator configuration has its own experiment ID. The analyst can supply that ID to the analysis CLI. The default BI dashboards use the bundled 90-day reference experiment, `routing-demo-42`.

- All timestamps carry UTC offsets and are stored in UTC. A sibling report's modification timestamp is a fallback for evaluation records without request timestamps. Use `--at` when the actual measurement time is known.
- Token counts may be missing, as can latency on failed requests. Unknown usage or prices remain SQL `NULL`.
- No imported prompts, predictions containing free text, tenant names, source credentials, or workflow payloads go into the committed artifacts. Locally imported workflow identifiers are pseudonymous data.
- Spend is grouped by provenance and cost basis. Use Gold fact rows when recomputing p95 for a larger cohort. Percentiles from daily aggregates cannot be averaged into an overall p95.

## Tariffs

Prices are USD per input or output token. Consecutive equal observations are compressed to a single SCD Type 2 version. Each interval is valid from its first observation to the next price change, with the end excluded. Historical facts before a model's first observed price keep an unknown catalog cost. Model removal or availability changes need a separate availability feed.

The OpenRouter catalog provides list prices. Effective-time tariff cost excludes ancillary items such as per-request fees, provider-side discounts, caching, and multimodal charges. Use charged spend where the data contains it. The dbt operational snapshot tracks the latest visible rate at snapshot time. The Gold SCD2 table reconstructs the observed effective timeline from every retained observation.

## A/B interpretation

The analysis assumes independent, randomized request assignments and a fixed assignment ratio of 50% per arm. Repeated or tenant-randomized production experiments require a design-aware resampling strategy. The Python analysis requires an arm, a ground-truth label, and a charge or cost estimate for every assignment. The A/B mart returns a null mean cost when any assignment in an arm lacks a cost. The SQL routing funnel returns a null correctness share when any assignment in an arm lacks a ground-truth label. Null predictions remain failures. The bootstrap resamples independently within each arm, and savings use the per-assignment mean.

The reported latency comparison conditions on successful requests and is therefore descriptive. The latency forecast uses previous-day or earlier actual p95 at prediction time, so it evaluates one-step-ahead forecasting over the holdout.
