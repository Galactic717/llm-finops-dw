import argparse
import os

import httpx

from ingestion.warehouse import grant_bi

APP = "LLM FinOps | Routing"
EMAIL = "finops@example.test"
FILTER = "[[AND tenant_id = {{tenant}}]]"
DEMO = "data_kind = 'synthetic' AND experiment_id = 'routing-demo-42'"
TAG = {"tenant": {"id": "f64cd6ba-02c8-4a92-bf55-5fce138e6600",
                  "name": "tenant", "display-name": "Demo tenant", "type": "text",
                  "required": False}}
CARDS = {
    "Simulated policy spend": ("scalar", f"""
        SELECT round(sum(cost_usd), 2) AS usd FROM gold.fct_llm_runs
        WHERE {DEMO} {FILTER}
    """, (0, 0, 8, 3)),
    "Assigned requests": ("scalar", f"""
        SELECT count(*) AS requests FROM gold.fct_llm_runs
        WHERE {DEMO} {FILTER}
    """, (8, 0, 8, 3)),
    "Successful request p95": ("scalar", f"""
        SELECT round((percentile_cont(.95) WITHIN GROUP (ORDER BY latency_ms))::numeric)
        AS latency_ms FROM gold.fct_llm_runs
        WHERE {DEMO} AND status = 'ok' {FILTER}
    """, (16, 0, 8, 3)),
    "Daily spend by routing policy": ("line", f"""
        SELECT event_date, arm, round(sum(cost_usd), 4) AS usd
        FROM gold.fct_llm_runs WHERE {DEMO} {FILTER}
        GROUP BY event_date, arm ORDER BY event_date, arm
    """, (0, 3, 12, 7)),
    "Routing trade-offs": ("table", f"""
        SELECT arm, count(*) AS assigned, round(1000 * avg(cost_usd), 2) AS usd_per_1k,
               round(100 * avg(fallback::int), 2) AS fallback_pct,
               round(100.0 * count(*) FILTER (WHERE prediction = ground_truth)
                             / NULLIF(count(ground_truth), 0), 2) AS accuracy_pct,
               round((percentile_cont(.95) WITHIN GROUP (ORDER BY latency_ms)
                      FILTER (WHERE status = 'ok'))::numeric) AS p95_success_ms
        FROM gold.fct_llm_runs WHERE {DEMO} {FILTER}
        GROUP BY arm ORDER BY arm
    """, (12, 3, 12, 7)),
    "Spend by workflow": ("bar", f"""
        SELECT workflow, round(sum(cost_usd), 2) AS usd
        FROM gold.fct_llm_runs WHERE {DEMO} {FILTER}
        GROUP BY workflow ORDER BY usd DESC
    """, (0, 10, 12, 6)),
    "p95 latency by weekday and policy": ("bar", f"""
        SELECT to_char(event_date, 'Dy') AS weekday, arm,
               round((percentile_cont(.95) WITHIN GROUP (ORDER BY latency_ms))::numeric) AS latency_ms
        FROM gold.fct_llm_runs WHERE {DEMO} AND status = 'ok' {FILTER}
        GROUP BY 1, arm, extract(isodow FROM event_date) ORDER BY extract(isodow FROM event_date), arm
    """, (12, 10, 12, 6)),
}
PROVENANCE_CARD = ("table", """
    SELECT data_kind, source, cost_basis, count(*) AS requests, count(cost_usd) AS priced,
           count(latency_ms) AS timed,
           round((percentile_cont(.95) WITHIN GROUP (ORDER BY latency_ms))::numeric, 1) AS p95_ms
    FROM gold.fct_llm_runs GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
""", (0, 0, 24, 8))


def request(client: httpx.Client, method: str, path: str, **kwargs):
    response = client.request(method, "/api/" + path, **kwargs)
    if response.is_error:
        raise RuntimeError(f"Metabase {method} {path}: {response.status_code} {response.text[:500]}")
    return response.json() if response.content else None


def initialize(base_url: str, public_demo: bool) -> tuple[str, str, str | None]:
    grant_bi()
    password = os.getenv("FINOPS_METABASE_ADMIN_PASSWORD", "FinOpsLocalDemo!16")
    with httpx.Client(base_url=base_url, timeout=60) as client:
        properties = request(client, "GET", "session/properties")
        if not properties.get("has-user-setup") and (token := properties.get("setup-token")):
            request(client, "POST", "setup", json={
                "token": token,
                "user": {"first_name": "FinOps", "last_name": "Local", "email": EMAIL, "password": password},
                "prefs": {"site_name": "LLM FinOps Warehouse", "site_locale": "en",
                          "allow_tracking": False},
            })
        session = request(client, "POST", "session", json={"username": EMAIL, "password": password})
        client.headers["X-Metabase-Session"] = session["id"]

        databases = request(client, "GET", "database")["data"]
        database = next((db for db in databases if db["name"] == "FinOps Gold"), None)
        if database is None:
            database = request(client, "POST", "database", json={
                "engine": "postgres", "name": "FinOps Gold", "is_full_sync": True,
                "details": {"host": "warehouse", "port": 5432, "dbname": "finops",
                            "user": "finops_read", "ssl": False,
                            "password": os.getenv("FINOPS_METABASE_PASSWORD", "finops_read")},
            })

        items = request(client, "GET", "collection/root/items", params={"limit": 1000})["data"]

        def dashboard(name, description, cards, filter_tenant):
            dash = next((item for item in items
                         if item["model"] == "dashboard" and item["name"] == name), None)
            if dash is None:
                dash = request(client, "POST", "dashboard", json={"name": name, "description": description})
            saved = request(client, "GET", f"dashboard/{dash['id']}")
            existing = {card["card_id"]: card["id"] for card in saved["dashcards"]}
            attachments = []
            for index, (label, (display, query, geometry)) in enumerate(cards.items(), 1):
                settings = {}
                if display in {"line", "bar"}:
                    settings = {
                        "graph.dimensions": (["event_date", "arm"] if "event_date, arm" in query
                                             else ["weekday", "arm"] if "AS weekday" in query
                                             else ["workflow"]),
                        "graph.metrics": ["latency_ms" if "AS weekday" in query else "usd"],
                    }
                spec = {"name": label, "display": display, "visualization_settings": settings,
                        "dataset_query": {"type": "native", "database": database["id"],
                                          "native": {"query": query.strip(),
                                                     "template-tags": TAG if filter_tenant else {}}}}
                card = next((item for item in items
                             if item["model"] == "card" and item["name"] == label), None)
                card = request(client, "PUT", f"card/{card['id']}", json=spec) if card else request(
                    client, "POST", "card", json=spec
                )
                result = request(client, "POST", f"card/{card['id']}/query", json={"parameters": []})
                if result.get("status") != "completed" or not result["data"]["rows"]:
                    raise RuntimeError(f"Card {label!r} returned no usable rows: {result.get('error')}")
                column, row, width, height = geometry
                attachments.append({
                    "id": existing.get(card["id"], -index), "card_id": card["id"], "row": row,
                    "col": column, "size_x": width, "size_y": height, "series": [],
                    "parameter_mappings": (
                        [{"parameter_id": "demo_tenant", "card_id": card["id"],
                          "target": ["variable", ["template-tag", "tenant"]]}] if filter_tenant else []
                    ),
                })
            parameters = [{"name": "Demo tenant", "slug": "tenant", "id": "demo_tenant",
                           "type": "string/=", "sectionId": "string"}] if filter_tenant else []
            return request(client, "PUT", f"dashboard/{dash['id']}", json={
                "dashcards": attachments, "parameters": parameters,
            })

        main = dashboard(APP, "90-day synthetic experiment. Figures represent modeled policy cost.",
                         CARDS, True)
        telemetry = dashboard("LLM FinOps | Telemetry coverage",
                              "Request timing and cost coverage by source and provenance.",
                              {"Telemetry provenance and coverage": PROVENANCE_CARD}, False)
        public_url = None
        if public_demo:
            request(client, "PUT", "setting/enable-public-sharing", json={"value": True})
            uuid = main.get("public_uuid") or request(
                client, "POST", f"dashboard/{main['id']}/public_link"
            )["uuid"]
            public_url = f"{base_url}/public/dashboard/{uuid}"
        return f"{base_url}/dashboard/{main['id']}", f"{base_url}/dashboard/{telemetry['id']}", public_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and verify the FinOps Metabase dashboards")
    parser.add_argument("--base-url", default="http://127.0.0.1:3006")
    parser.add_argument("--public-demo", action="store_true",
                        help="Enable a local anonymous link to the synthetic dashboard")
    args = parser.parse_args()
    for url in initialize(args.base_url.rstrip("/"), args.public_demo):
        if url:
            print(url)


if __name__ == "__main__":
    main()
