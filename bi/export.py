import argparse
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from ingestion.warehouse import connect

MARTS = ("mart_finops_daily", "mart_ab_routing", "dim_models_scd2", "mart_model_benchmarks")
FACT_QUERY = """
    SELECT event_date AS "Date", tenant_id AS "Tenant", model_id AS "Model",
           workflow AS "Workflow", arm AS "Policy", status AS "Status",
           cast(cost_usd AS double precision) AS "Policy Spend", latency_ms AS "Latency ms"
    FROM gold.fct_llm_runs
    WHERE data_kind = 'synthetic' AND experiment_id = 'routing-demo-42'
    ORDER BY event_date, event_id
"""


def fetch_frame(conn, query: str) -> pd.DataFrame:
    cursor = conn.execute(query)
    return pd.DataFrame(cursor.fetchall(), columns=[d.name for d in cursor.description])


def export(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with connect() as conn, pd.ExcelWriter(root / "llm_finops.xlsx", engine="openpyxl") as book:
        for mart in MARTS:
            frame = fetch_frame(conn, f"SELECT * FROM gold.{mart} ORDER BY 1, 2")
            for name in frame.select_dtypes(include=["datetimetz"]):
                frame[name] = frame[name].dt.tz_convert("UTC").dt.tz_localize(None)
            frame.to_csv(root / f"{mart}.csv", index=False)
            usd_columns = [name for name in frame.columns if "usd" in name]
            for name in usd_columns:
                frame[name] = pd.to_numeric(frame[name])
            sheet = mart.removeprefix("mart_")
            frame.to_excel(book, sheet_name=sheet, index=False)
            worksheet = book.sheets[sheet]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for index, cell in enumerate(worksheet[1], 1):
                worksheet.column_dimensions[get_column_letter(index)].width = min(
                    42, max(15, len(cell.value) + 3)
                )
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="194858")
                if cell.value in usd_columns:
                    for row in worksheet.iter_rows(min_row=2, min_col=index, max_col=index):
                        row[0].number_format = '0.000000000000'
        fact = fetch_frame(conn, FACT_QUERY)
        fact.to_csv(root / "synthetic_fact.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export PostgreSQL marts to CSV and Excel")
    parser.add_argument("--out", type=Path, default=Path("output/bi"))
    args = parser.parse_args()
    export(args.out)


if __name__ == "__main__":
    main()
