import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from ingestion.contracts import validate
from ingestion.files import DATA_DIR, read_jsonl, write_json, write_jsonl

KINDS = ("events", "prices", "scores")
KEYS = {
    "events": ("event_id",),
    "prices": ("source", "model_id", "observed_at"),
    "scores": ("source", "model_id", "benchmark", "observed_at", "revision"),
}
ROOT = Path(__file__).resolve().parents[1]


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("FINOPS_DB_HOST", "127.0.0.1"),
        port=os.environ.get("FINOPS_DB_PORT", "55436"),
        dbname=os.environ.get("FINOPS_DB_NAME", "finops"),
        user=os.environ.get("FINOPS_DB_USER", "finops"),
        password=os.environ.get("FINOPS_DB_PASSWORD", "finops"),
        connect_timeout=10,
        options="-c timezone=UTC",
    )


def row_key(row: dict, kind: str) -> str:
    return json.dumps([row[key] for key in KEYS[kind]], ensure_ascii=False, separators=(",", ":"))


def prepare(data_root: Path) -> Path:
    digest = hashlib.sha256()
    collections = {}
    for kind in KINDS:
        records = [row for path in sorted((data_root / "inbox" / kind).glob("*.jsonl"))
                   for row in read_jsonl(path)]
        rows = sorted(validate(records, kind), key=lambda row: row_key(row, kind))
        digest.update(json.dumps([kind, rows], sort_keys=True, ensure_ascii=False).encode())
        collections[kind] = rows
    path = data_root / "batches" / digest.hexdigest()[:24]
    for kind, rows in collections.items():
        write_jsonl(path / f"{kind}.jsonl", rows)
    write_json(path / "manifest.json", {kind: len(rows) for kind, rows in collections.items()})
    return path


def load(path: Path) -> dict[str, int]:
    manifest = json.loads((path / "manifest.json").read_bytes())
    result = {}
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(15455342)")
        conn.execute((ROOT / "sql" / "raw.sql").read_text(encoding="utf-8"))
        for kind in KINDS:
            rows = validate(read_jsonl(path / f"{kind}.jsonl"), kind)
            if len(rows) != manifest[kind]:
                raise ValueError(f"Manifest count differs for {kind}")
            conn.execute("CREATE TEMP TABLE incoming (key text primary key, payload jsonb) "
                         "ON COMMIT DROP")
            with conn.cursor().copy("COPY incoming (key, payload) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row((row_key(row, kind), Jsonb(row)))
            target = sql.Identifier("raw", kind)
            conflict = conn.execute(sql.SQL(
                "SELECT i.key FROM incoming i JOIN {} r USING (key) "
                "WHERE i.payload IS DISTINCT FROM r.payload LIMIT 1"
            ).format(target)).fetchone()
            if conflict:
                raise ValueError(f"Conflicting persisted {kind} key {conflict[0]}")
            result[kind] = conn.execute(sql.SQL(
                "INSERT INTO {} (key, payload) SELECT key, payload FROM incoming "
                "ON CONFLICT (key) DO NOTHING"
            ).format(target)).rowcount
            conn.execute("DROP TABLE incoming")
    return result


def grant_bi() -> None:
    password = os.environ.get("FINOPS_METABASE_PASSWORD", "finops_read")
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(15455342)")
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'finops_read'").fetchone():
            conn.execute("CREATE ROLE finops_read LOGIN")
        conn.execute(sql.SQL("ALTER ROLE finops_read PASSWORD {}").format(sql.Literal(password)))
        conn.execute("GRANT USAGE ON SCHEMA gold TO finops_read")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA gold TO finops_read")
        conn.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO finops_read")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and load a transactional Bronze batch")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    load_command = commands.add_parser("load")
    load_command.add_argument("batch", type=Path)
    commands.add_parser("ingest")
    commands.add_parser("grant-bi")
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(args.data_dir))
    elif args.command == "grant-bi":
        grant_bi()
    else:
        batch = args.batch if args.command == "load" else prepare(args.data_dir)
        print(batch, load(batch))


if __name__ == "__main__":
    main()
