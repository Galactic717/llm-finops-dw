import os
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
