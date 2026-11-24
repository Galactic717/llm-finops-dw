WITH calendar AS (
    SELECT DATE '2026-04-15' + i AS event_date
    FROM generate_series(0, 29) AS i
)

SELECT c.event_date, s.cost, s.p95
FROM calendar AS c
CROSS JOIN
    LATERAL (
        SELECT
            round(sum(cost_usd), 8) AS cost,
            round(cast(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS NUMERIC), 6) AS p95
        FROM {{ relation }}
        WHERE tenant_id = 25 AND event_date BETWEEN c.event_date - 6 AND c.event_date
    ) AS s
ORDER BY c.event_date;
