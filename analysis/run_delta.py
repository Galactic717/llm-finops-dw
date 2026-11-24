import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from ingestion.files import write_json


def run(batch: Path, lake: Path, evidence: Path | None = None) -> None:
    builder = (SparkSession.builder.master("local[2]").appName("llm-finops-dw")
               .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
               .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
               .config("spark.jars.ivySettings", str(Path("databricks/ivysettings.xml").resolve()))
               .config("spark.sql.shuffle.partitions", "4")
               .config("spark.ui.enabled", "false")
               .config("spark.databricks.delta.snapshotPartitions", "4"))
    spark = configure_spark_with_delta_pip(builder).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    namespace = {"spark": spark, "batch_root": batch.resolve().as_uri(),
                 "lake_root": lake.resolve().as_uri()}
    try:
        for path in sorted(Path("databricks").glob("0*.ipynb")):
            print(path.name, flush=True)
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    with redirect_stdout(io.StringIO()) as stream:
                        exec(compile("".join(cell["source"]), str(path), "exec"), namespace)
                    stdout = stream.getvalue()
                    print(stdout, end="", flush=True)
                    cell["execution_count"] = 1
                    cell["outputs"] = [{"name": "stdout", "output_type": "stream",
                                        "text": stdout.splitlines(keepends=True)}]
            if evidence:
                write_json(evidence / path.name, notebook)
        gold = lake.resolve().as_uri() + "/gold"
        facts = spark.read.format("delta").load(gold + "/fct_llm_runs")
        daily = spark.read.format("delta").load(gold + "/mart_finops_daily")
        details = facts.groupBy("data_kind", "source").count().orderBy("data_kind", "source").collect()
        if facts.count() != daily.agg(F.sum("runs")).first()[0]:
            raise RuntimeError("Gold daily mart does not reconcile to Delta event count")
        write_json(lake / "verification.json", {
            "spark": spark.version, "delta_facts": facts.count(),
            "source_counts": [row.asDict() for row in details],
        })
    finally:
        spark.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the three portable Delta notebooks")
    parser.add_argument("batch", type=Path)
    parser.add_argument("--lake", type=Path, default=Path("output/delta"))
    parser.add_argument("--evidence", type=Path, help="Directory for executed notebook copies")
    args = parser.parse_args()
    run(args.batch, args.lake, args.evidence)


if __name__ == "__main__":
    main()
