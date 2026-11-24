import argparse
import hashlib
import json
from pathlib import Path
from statistics import median

from ingestion.files import write_json, write_text
from ingestion.warehouse import ROOT, connect

QUERY = ROOT / "sql" / "benchmark" / "query.sql"


def benchmark(rows: int, repeats: int, output: Path) -> dict:
    if rows < 10_000 or repeats < 2:
        raise ValueError("Use at least 10,000 rows and two repetitions")
    metrics = {}
    signatures = set()
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(15455344)")
        conn.execute("SET LOCAL jit=off")
        conn.execute("SET LOCAL max_parallel_workers_per_gather=0")
        conn.execute("""
            CREATE TEMP TABLE benchmark_heap (
                tenant_id integer, event_date date, cost_usd numeric, latency_ms double precision
            ) ON COMMIT DROP
        """)
        conn.execute("""
            INSERT INTO benchmark_heap
            SELECT 1 + mod(i / 180, 250), DATE '2026-01-01' + mod(i, 180)::int,
                   (10 + mod(i, 1000))::numeric / 100000,
                   (180 + mod(i * 7919, 22000)) / 10.0
            FROM generate_series(1, %s::bigint) AS i
            ORDER BY mod(i, 180), i
        """, (rows,))
        conn.execute("ANALYZE benchmark_heap")

        def measured(label: str, relation: str) -> None:
            earlier_query = QUERY.read_text(encoding="utf-8").replace("{{ relation }}", relation)
            data = conn.execute(earlier_query).fetchall()
            signatures.add(hashlib.sha256(repr(data).encode()).hexdigest())
            samples = []
            for repeat in range(1, repeats + 1):
                payload = conn.execute(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + earlier_query
                ).fetchone()[0]
                samples.append(payload[0]["Execution Time"])
                write_json(output / f"{label}-{repeat}.json", payload)
            plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + earlier_query).fetchall()
            write_text(output / f"{label}.txt", "\n".join(line for (line,) in plan) + "\n")
            metrics[label] = {"samples_ms": samples, "median_ms": median(samples)}

        measured("01_heap", "benchmark_heap")
        conn.execute("CREATE INDEX ON benchmark_heap USING brin (event_date) WITH (pages_per_range=16)")
        measured("02_brin", "benchmark_heap")
        conn.execute("CREATE INDEX ON benchmark_heap (tenant_id, event_date) INCLUDE (cost_usd, latency_ms)")
        measured("03_composite", "benchmark_heap")
        conn.execute("""
            CREATE TEMP TABLE benchmark_partitioned (LIKE benchmark_heap INCLUDING DEFAULTS)
            PARTITION BY RANGE (event_date) ON COMMIT DROP
        """)
        for month in range(1, 7):
            conn.execute(f"""
                CREATE TEMP TABLE benchmark_m{month} PARTITION OF benchmark_partitioned
                FOR VALUES FROM ('2026-{month:02}-01') TO ('2026-{month + 1:02}-01')
                ON COMMIT DROP
            """)
        conn.execute("INSERT INTO benchmark_partitioned SELECT * FROM benchmark_heap")
        conn.execute("CREATE INDEX ON benchmark_partitioned USING brin (event_date) WITH (pages_per_range=16)")
        conn.execute("CREATE INDEX ON benchmark_partitioned (tenant_id, event_date) INCLUDE (cost_usd, latency_ms)")
        conn.execute("ANALYZE benchmark_partitioned")
        measured("04_partitioned", "benchmark_partitioned")
        version = conn.execute("SHOW server_version").fetchone()[0]
    if len(signatures) != 1:
        raise RuntimeError("Benchmark query changed results across layouts")
    baseline = metrics["01_heap"]["median_ms"]
    for variant in metrics.values():
        variant["speedup_vs_heap"] = baseline / variant["median_ms"]
    metrics = {"postgres_version": version, "rows": rows, "repeats": repeats,
               "result_sha256": signatures.pop(), "variants": metrics}
    write_json(output / "summary.json", metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run actual PostgreSQL plan experiments")
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("output/benchmark"))
    args = parser.parse_args()
    print(json.dumps(benchmark(args.rows, args.repeats, args.output), indent=2))


if __name__ == "__main__":
    main()
