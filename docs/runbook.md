# Local operations

| Component | Local connection |
| --- | --- |
| PostgreSQL warehouse | `127.0.0.1:55436/finops` |
| Airflow | `http://127.0.0.1:8086` |
| Metabase | `http://127.0.0.1:3006` |
| Optional llama.cpp smoke endpoint | `http://127.0.0.1:9941` |

## Check pipeline state

Start the Airflow web server and scheduler with `docker compose up -d --wait airflow-web airflow-scheduler`. Sign in as `admin` using the local default password `admin`. Unpause `llm_finops_daily` to enable the daily schedule.

```powershell
docker compose ps
docker compose exec -T airflow-scheduler airflow dags list-runs -d llm_finops_daily -o json
docker compose exec -T airflow-scheduler airflow dags list-import-errors
```

`llm_finops_daily` fetches public prices and a Hugging Face result page, validates the accumulated inbox, loads Bronze, runs the snapshot and SQL models, and executes all dbt data tests. Add new local telemetry to the inbox to include it in the next run. Airflow retains task logs in its Compose volume.

## Run a development bootstrap

```powershell
./scripts/demo.ps1 -Offline
```

This path needs Docker images and Python packages but makes no requests to pricing or benchmark endpoints. For a clean deployment on a different machine, use a fresh Docker Compose project. Existing runs and source observations stay in PostgreSQL on a normal restart.

## Audit generated artifacts

- `output/analysis` holds `routing.json` and `p95_predictions.csv` from the routing analysis. The executed notebook HTML is a [release download](https://github.com/Galactic717/llm-finops-dw/releases/latest).
- `output/bi` holds Excel and CSV exports from the local warehouse.
- `bi/powerbi` holds the editable, synthetic-only Power BI source.
- `output/delta` holds local Delta tables and `verification.json`.
- `data/raw` preserves source snapshots for replay. Keep `data/private` and all raw or observed telemetry local unless you have approved it for release.

Common local database settings are `FINOPS_DB_HOST`, `FINOPS_DB_PORT`, `FINOPS_DB_NAME`, `FINOPS_DB_USER`, and `FINOPS_DB_PASSWORD`. The default passwords are for these loopback services. `FINOPS_METABASE_PASSWORD` controls the warehouse role used by the BI service.
