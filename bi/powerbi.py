import argparse
import base64
import io
import json
import zlib
from pathlib import Path

import pandas as pd

from bi.export import FACT_QUERY, fetch_frame
from ingestion.files import write_json
from ingestion.warehouse import connect

FABRIC = "https://developer.microsoft.com/json-schemas/fabric"
PROJECT_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"
REPORT = "LLM FinOps.Report"
MODEL = "LLM FinOps.SemanticModel"
FACT = "Requests"
TEXT = ("string", "text")
DATE = ("dateTime", "date")
NUMBER = ("double", "number")
MEASURES = [
    {"name": "Requests", "expression": "COUNTROWS('Requests')", "formatString": "#,0"},
    {"name": "Spend USD", "expression": "SUM('Requests'[Policy Spend])", "formatString": "$#,0.00"},
    {"name": "Cost per 1k", "expression": "1000 * DIVIDE([Spend USD], COUNT('Requests'[Policy Spend]))",
     "formatString": "$#,0.00"},
    {"name": "p95 latency", "expression": """
VAR Eligible = FILTER('Requests', 'Requests'[Status] = "ok" && NOT ISBLANK('Requests'[Latency ms]))
RETURN IF(COUNTROWS(Eligible) > 0, PERCENTILEX.INC(Eligible, 'Requests'[Latency ms], 0.95))
""".strip(), "formatString": '#,0 "ms"'},
    {"name": "MoM savings", "expression": """
VAR PriorSpend = CALCULATE([Spend USD], DATEADD('Calendar'[Date], -1, MONTH))
RETURN DIVIDE(PriorSpend - [Spend USD], PriorSpend)
""".strip(), "formatString": "0.0%"},
    {"name": "Hybrid savings", "expression": """
VAR AllCloud = CALCULATE([Cost per 1k], REMOVEFILTERS('Models'), REMOVEFILTERS('Requests'[Model]), 'Requests'[Policy] = "all_cloud")
VAR Hybrid = CALCULATE([Cost per 1k], REMOVEFILTERS('Models'), REMOVEFILTERS('Requests'[Model]), 'Requests'[Policy] = "hybrid")
RETURN DIVIDE(AllCloud - Hybrid, AllCloud)
""".strip(), "formatString": "0.0%"},
]


def embedded_query(frame: pd.DataFrame, columns: dict, use_csv: Path | None) -> list[str]:
    if use_csv is None:
        csv = frame.to_csv(index=False, lineterminator="\n").encode()
        buffer = io.BytesIO()
        compression = zlib.compressobj(level=9, wbits=-zlib.MAX_WBITS)
        buffer.write(compression.compress(csv))
        buffer.write(compression.flush())
        content = base64.b64encode(buffer.getvalue()).decode()
        chunks = [json.dumps(content[i:i + 8000]) for i in range(0, len(content), 8000)]
        binary = ("Binary.Decompress(Binary.FromText(Text.Combine({\n        "
                  + ",\n        ".join(chunks)
                  + "\n    }), BinaryEncoding.Base64), Compression.Deflate)")
    else:
        escaped_path = use_csv.as_posix().replace('"', '""')
        binary = f'File.Contents("{escaped_path}")'
    type_names = {"text": "type text", "date": "type date", "number": "type number"}
    type_changes = ", ".join('{"' + name + '", ' + type_names[typ[1]] + '}'
                             for name, typ in columns.items())
    return [
        "let",
        f'    Source = Csv.Document({binary}, [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        f'    Typed = Table.TransformColumnTypes(Headers, {{{type_changes}}}, "en-US")',
        "in",
        "    Typed",
    ]


def table(name: str, frame: pd.DataFrame, columns: dict, data_file: Path | None = None) -> dict:
    fields = []
    for col, (semantic_type, _) in columns.items():
        field = {"name": col, "dataType": semantic_type, "sourceColumn": col, "summarizeBy": "none"}
        if semantic_type == "dateTime":
            field["formatString"] = "yyyy-MM-dd"
        fields.append(field)
    return {
        "name": name, "columns": fields,
        "partitions": [{"name": name, "mode": "import",
                        "source": {"type": "m", "expression": embedded_query(frame, columns, data_file)}}],
    }


def schema(family: str, version: str) -> str:
    return f"{FABRIC}/item/report/definition/{family}/{version}/schema.json"


def projection(entity: str, field: str, measure: bool = False) -> dict:
    return {
        "field": {
            "Measure" if measure else "Column": {
                "Expression": {"SourceRef": {"Entity": entity}}, "Property": field
            }
        },
        "queryRef": f"{entity}.{field}",
        "nativeQueryRef": field,
        "active": True,
    }


def chart(name: str, kind: str, title: str, geometry: tuple, roles: dict, z: int) -> dict:
    x, y, width, height = geometry
    result = {
        "$schema": schema("visualContainer", "2.0.0"),
        "name": name,
        "position": {"x": x, "y": y, "width": width, "height": height, "z": z, "tabOrder": z},
        "visual": {
            "visualType": kind,
            "query": {"queryState": {key: {"projections": items} for key, items in roles.items()}},
            "visualContainerObjects": {"title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": "'" + title.replace("'", "''") + "'"}}},
            }}]},
            "drillFilterOtherVisuals": True,
        },
    }
    hidden_label = [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}]
    if kind == "card":
        result["visual"]["objects"] = {"categoryLabels": hidden_label}
    if kind == "slicer" and name != "datefilter":
        result["visual"]["objects"] = {
            "header": hidden_label,
            "data": [{"properties": {"mode": {"expr": {"Literal": {"Value": "'Dropdown'"}}}}}],
        }
    return result


def write_report(root: Path) -> None:
    report = root / REPORT / "definition"
    page = "ReportSectionFinOps"
    write_json(root / "LLM FinOps.pbip", {
        "$schema": PROJECT_SCHEMA, "version": "1.0",
        "artifacts": [{"report": {"path": REPORT}}], "settings": {"enableAutoRecovery": True},
    })
    write_json(root / REPORT / "definition.pbir", {
        "$schema": f"{FABRIC}/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{MODEL}"}},
    })
    write_json(report / "version.json", {
        "$schema": schema("versionMetadata", "1.0.0"), "version": "2.0.0",
    })
    write_json(report / "report.json", {
        "$schema": schema("report", "2.0.0"),
        "themeCollection": {"baseTheme": {"name": "CY24SU08", "type": "SharedResources",
                                          "reportVersionAtImport": "5.56"}},
        "settings": {"useStylableVisualContainerHeader": True},
    })
    write_json(report / "pages" / "pages.json", {
        "$schema": schema("pagesMetadata", "1.0.0"), "pageOrder": [page], "activePageName": page,
    })
    page_path = report / "pages" / page
    write_json(page_path / "page.json", {
        "$schema": schema("page", "2.0.0"), "name": page,
        "displayName": "FinOps · Synthetic routing", "displayOption": "FitToPage",
        "width": 1280, "height": 720,
    })
    specs = []
    for index, measure in enumerate(["Requests", "Spend USD", "Cost per 1k", "p95 latency", "Hybrid savings"]):
        specs.append((f"metric{index}", "card", measure, (24 + index * 248, 18, 236, 106),
                      {"Values": [projection(FACT, measure, True)]}))
    specs.extend([
        ("datefilter", "slicer", "Date", (24, 143, 347, 64),
         {"Values": [projection("Calendar", "Date")]}),
        ("tenantfilter", "slicer", "Tenant", (388, 143, 365, 64),
         {"Values": [projection("Tenants", "Tenant")]}),
        ("modelfilter", "slicer", "Final model", (770, 143, 485, 64),
         {"Values": [projection("Models", "Model")]}),
        ("spendtrend", "lineChart", "Daily simulated spend", (24, 226, 735, 246),
         {"Category": [projection("Calendar", "Date")], "Series": [projection(FACT, "Policy")],
          "Y": [projection(FACT, "Spend USD", True)]}),
        ("workflowcost", "barChart", "Cost by workflow", (778, 226, 477, 246),
         {"Category": [projection(FACT, "Workflow")], "Y": [projection(FACT, "Cost per 1k", True)]}),
        ("routingtable", "tableEx", "Routing policies", (24, 490, 1231, 194),
         {"Values": [projection(FACT, "Policy")] + [
             projection(FACT, name, True) for name in ("Requests", "Spend USD", "Cost per 1k", "p95 latency")
         ]}),
    ])
    for index, spec in enumerate(specs):
        write_json(page_path / "visuals" / spec[0] / "visual.json", chart(*spec, z=index * 1000))


def build(root: Path, linked_csv: bool) -> None:
    if (root / MODEL / "definition").exists():
        raise FileExistsError("Use a separate output directory for generated Power BI projects")
    with connect() as conn:
        fact = fetch_frame(conn, FACT_QUERY)
    if fact.empty:
        raise ValueError("The Power BI demo needs synthetic facts")
    fact["Date"] = pd.to_datetime(fact["Date"])
    dates = pd.DataFrame({"Date": pd.date_range(fact["Date"].min(), fact["Date"].max())})
    sources = [
        (FACT, fact, {"Date": DATE, "Tenant": TEXT, "Model": TEXT, "Workflow": TEXT,
                      "Policy": TEXT, "Status": TEXT, "Policy Spend": NUMBER, "Latency ms": NUMBER}),
        ("Calendar", dates, {"Date": DATE}),
        ("Tenants", fact[["Tenant"]].drop_duplicates(), {"Tenant": TEXT}),
        ("Models", fact[["Model"]].drop_duplicates(), {"Model": TEXT}),
    ]
    tables = []
    for name, data, schema_types in sources:
        csv_path = None
        if linked_csv:
            csv_path = (root / "csv" / f"{name}.csv").resolve()
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            data.to_csv(csv_path, index=False)
        tables.append(table(name, data, schema_types, csv_path))
    tables[0]["measures"] = MEASURES
    relationships = [
        {"name": f"Requests-{dimension}", "fromTable": FACT, "fromColumn": key,
         "toTable": dimension, "toColumn": key}
        for dimension, key in [("Calendar", "Date"), ("Tenants", "Tenant"), ("Models", "Model")]
    ]
    write_json(root / MODEL / "definition.pbism", {
        "$schema": f"{FABRIC}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "1.0",
    })
    write_json(root / MODEL / "model.bim", {
        "name": "LLM FinOps", "compatibilityLevel": 1601,
        "model": {"culture": "en-US", "defaultPowerBIDataSourceVersion": "powerBI_V3",
                  "sourceQueryCulture": "en-US", "tables": tables, "relationships": relationships,
                  "annotations": [{"name": "__PBI_TimeIntelligenceEnabled", "value": "0"}]},
    })
    write_report(root)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an editable Power BI project from the warehouse")
    parser.add_argument("--out", type=Path, default=Path("output/powerbi"))
    parser.add_argument("--linked-csv", action="store_true")
    args = parser.parse_args()
    build(args.out, args.linked_csv)
    print(args.out / "LLM FinOps.pbip")


if __name__ == "__main__":
    main()
