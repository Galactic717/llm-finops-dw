# DAX measures

`bi/powerbi.py` is the source for the model measures.

```dax
Requests = COUNTROWS('Requests')
Spend USD = SUM('Requests'[Policy Spend])
Cost per 1k = 1000 * DIVIDE([Spend USD], COUNT('Requests'[Policy Spend]))
```

Cost per 1,000 uses assignments with known cost as its denominator.

```dax
p95 latency =
VAR Eligible =
    FILTER('Requests', 'Requests'[Status] = "ok" && NOT ISBLANK('Requests'[Latency ms]))
RETURN IF(COUNTROWS(Eligible) > 0, PERCENTILEX.INC(Eligible, 'Requests'[Latency ms], 0.95))

MoM savings =
VAR PriorSpend = CALCULATE([Spend USD], DATEADD('Calendar'[Date], -1, MONTH))
RETURN DIVIDE(PriorSpend - [Spend USD], PriorSpend)
```

Use complete calendar months when interpreting month-over-month savings. The denominator becomes blank when prior spend is unavailable or zero.

```dax
Hybrid savings =
VAR AllCloud = CALCULATE([Cost per 1k], REMOVEFILTERS('Models'), REMOVEFILTERS('Requests'[Model]), 'Requests'[Policy] = "all_cloud")
VAR Hybrid = CALCULATE([Cost per 1k], REMOVEFILTERS('Models'), REMOVEFILTERS('Requests'[Model]), 'Requests'[Policy] = "hybrid")
RETURN DIVIDE(AllCloud - Hybrid, AllCloud)
```

The comparison retains date, tenant, and workflow filters. The final model is a routing outcome, so the savings measure always includes both successful local routes and cloud fallbacks.
