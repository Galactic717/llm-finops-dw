# PostgreSQL performance at one million rows

The benchmark uses PostgreSQL 16.16 in Docker Desktop. It generates one million synthetic events, with 250 tenants across 180 days and rows physically ordered by date. Its query returns 30 daily observations for a single tenant. Each observation sums the trailing seven calendar days of costs and computes an exact p95 for the same interval.

| Physical layout | Median of 5 warm runs | Relative to heap |
| --- | ---: | ---: |
| Heap scan | 1,121.521 ms | 1.00× |
| BRIN on event date | 71.978 ms | 15.58× |
| Composite B-tree on tenant and event date with included metrics | 2.110 ms | 531.53× |
| Monthly partitions with B-tree and BRIN | 2.801 ms | 400.40× |

The BRIN-only variant benefits from physical date correlation. Tenant and date selectivity drive the composite index result. The partitioned layout prunes months and adds planning overhead for this narrow workload. All four variants returned the same result hash. These timings characterize the published query and dataset on one machine.

```powershell
uv run --locked --no-sync python -m analysis.benchmark --rows 1000000 --repeats 5
```

The implementation warms the query, captures `EXPLAIN (ANALYZE, BUFFERS)` in text and JSON, disables JIT and parallel query workers for the temporary workload, and verifies that all physical layouts return identical results. The checked-in [plans and timings](plans/) come from the local verification.
