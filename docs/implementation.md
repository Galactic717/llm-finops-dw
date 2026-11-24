# Implementation plan

1. Define a versioned event contract and test malformed data, idempotent IDs, and public source units. Capture sanitized telemetry using the running Verstak database, VeriFine reports and an existing llama.cpp model.
2. Load validated inputs transactionally into PostgreSQL 16. Build dbt staging, price history, facts and marts. Verify effective-time joins, unknown costs, tenant identities, and experiment filters in PostgreSQL.
3. Produce and exercise 16 SQL examples and a reproducible million-row before/after benchmark.
4. Execute a randomized demo analysis and a chronological quantile model. Run the Delta Bronze, Silver, and Gold notebooks using a local Spark session and package them for Databricks.
5. Start Airflow and Metabase in Compose. Export portable BI data and the editable Power BI project. Track external artifacts and account-bound verification separately.

Event IDs are immutable. Reject conflicting duplicate IDs. Use UTC timestamps and per-token USD for prices. Keep synthetic, imported, and live cohorts distinguishable at every aggregation. Use unknown for missing price or usage. Benchmark and experiment targets are hypotheses.
