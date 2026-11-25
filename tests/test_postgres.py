import os
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("FINOPS_TEST_POSTGRES"), reason="requires built dbt")


def test_demo_cost_on_both_sides_of_effective_price_boundary():
    from ingestion.warehouse import connect

    with connect() as conn:
        before, after, unmatched = conn.execute("""
            SELECT count(*) FILTER (WHERE p.valid_to IS NOT NULL),
                   count(*) FILTER (WHERE p.valid_to IS NULL AND p.price_version_id IS NOT NULL),
                   count(*) FILTER (WHERE p.price_version_id IS NULL)
            FROM gold.fct_llm_runs r
            LEFT JOIN gold.dim_models_scd2 p USING (price_version_id)
            WHERE r.model_id = 'demo/cloud-frontier'
        """).fetchone()
        assert before > 0 and after > 0 and unmatched == 0


def test_showcase_queries_execute_against_gold_schema():
    from ingestion.warehouse import connect

    paths = sorted(Path("sql/queries").glob("*.sql"))
    assert len(paths) >= 15
    with connect() as conn:
        for path in paths:
            result = conn.execute(path.read_text(encoding="utf-8"))
            assert result.description, path


def test_routing_metrics_require_complete_assignment_coverage():
    from jinja2 import Template

    from ingestion.warehouse import connect

    model = Template(Path("dbt_project/models/marts/mart_ab_routing.sql").read_text())
    routing_mart = model.render(ref=lambda name: f"pg_temp.{name}")
    route_funnel = Path("sql/queries/08_route_funnel.sql").read_text().replace(
        "gold.mart_ab_routing", "pg_temp.mart_ab_routing"
    )
    with connect() as conn:
        conn.execute("""
            CREATE TEMP VIEW fct_llm_runs AS
            SELECT experiment_id, 'observed' AS data_kind, 'hybrid' AS arm,
                   'ok' AS status, false AS fallback, ground_truth, prediction,
                   cost_usd, 100.0::double precision AS latency_ms
            FROM (VALUES
                ('complete', 'yes', 'yes', 0.02), ('complete', 'yes', NULL, 0.00),
                ('unknown-cost', 'yes', 'yes', 0.02), ('unknown-cost', 'yes', NULL, NULL),
                ('unknown-label', 'yes', 'yes', 0.02), ('unknown-label', NULL, NULL, 0.00)
            ) AS assignments(experiment_id, ground_truth, prediction, cost_usd)
        """)
        conn.execute(f"CREATE TEMP VIEW mart_ab_routing AS {routing_mart}")
        rates = conn.execute("""
            SELECT experiment_id, assigned, priced_runs, labels_available, mean_cost_usd
            FROM pg_temp.mart_ab_routing ORDER BY experiment_id
        """).fetchall()
        funnel = conn.execute(route_funnel).fetchall()

    assert rates == [
        ("complete", 2, 2, 2, Decimal("0.01")),
        ("unknown-cost", 2, 1, 2, None),
        ("unknown-label", 2, 2, 1, Decimal("0.01")),
    ]
    assert [row[-1] for row in funnel] == [Decimal("0.5"), Decimal("0.5"), None]


def test_excel_exports_financial_values_as_numbers(tmp_path):
    from openpyxl import load_workbook

    from bi.export import export

    export(tmp_path)
    with (tmp_path / "llm_finops.xlsx").open("rb") as handle:
        workbook = load_workbook(handle, read_only=True)
        sheet = workbook["ab_routing"]
        headers, first, *_ = sheet.iter_rows()
        cost_column = next(index for index, cell in enumerate(headers) if cell.value == "mean_cost_usd")
        assert first[cost_column].data_type == "n"
        workbook.close()
