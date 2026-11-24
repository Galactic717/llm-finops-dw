# Databricks and local Delta Lake

The three notebooks process the same prepared JSONL batch in Bronze, Silver, and Gold. They write actual Delta transaction logs and Parquet data, with UTC timestamps and explicit schemas.

## Local verification with Docker

From the repository root.

```powershell
$batch = uv run --locked --no-sync python -m ingestion.warehouse prepare
docker build -t llm-finops-delta:local -f databricks/Dockerfile .
docker run --rm --mount "type=bind,source=$($PWD.Path),target=/opt/finops" llm-finops-delta:local ($batch -replace '\\','/')
```

The default location is `output/delta`. Review `verification.json` for fact counts and source reconciliation.
Add `--evidence output/databricks` to the Docker command for executed notebook copies. Render those copies to HTML with `uv run --group analysis jupyter nbconvert --to html output/databricks/*.ipynb`.

## Databricks Free Edition

1. Create a Unity Catalog volume and upload `events.jsonl`, `prices.jsonl`, and `scores.jsonl` from a prepared batch to an `input` folder. To create a synthetic-only batch, generate demo inputs with the global `--data-dir data/databricks-demo` option and use the same option with `warehouse prepare`.
2. Import the three `.ipynb` files as workspace notebooks.
3. Attach serverless compute. Set the first notebook's `batch_root` widget to the input folder under your volume and set `lake_root` in all three notebooks to an output folder in the same volume.
4. Execute them in numeric order. Review the printed row counts and inspect the fact using `spark.read.format("delta").load(f"{lake_root}/gold/fct_llm_runs")`.

The cloud steps need a Databricks workspace. The local verification covers PySpark and Delta execution. [Databricks Free Edition](https://docs.databricks.com/aws/en/getting-started/free-edition)
