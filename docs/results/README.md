# Verification evidence

- [Routing experiment and forecast](routing-demo.json) contains the metrics and confidence intervals from the 90-day synthetic experiment.
- [Delta reconciliation](delta.json) records the PySpark version and fact counts from the same input batch as PostgreSQL.
- [PostgreSQL plans](../../sql/plans/) include the measured execution paths and repeated test results.
- [Metabase screenshot](../../bi/screenshots/metabase-routing.jpg) shows the synthetic dashboard. The tenant filter was tested with an independent subset.
- [Power BI screenshot](../../bi/screenshots/powerbi-routing.jpg) shows the imported model after saving the standalone report. Both BI tools confirmed 5,750 assignments for the same tenant slice.
- [Airflow task states](airflow-run.json) record the five successful tasks from the acceptance run.
