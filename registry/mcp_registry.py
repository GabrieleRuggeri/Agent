import os
from dataclasses import dataclass

import psycopg


@dataclass(frozen=True)
class McpServerRecord:
    name: str
    url: str
    transport: str


def is_registry_configured() -> bool:
    return bool(os.environ.get("POSTGRES_HOST") and os.environ.get("POSTGRES_PASSWORD"))


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ.get("POSTGRES_PORT", "5432"),
        user=os.environ.get("POSTGRES_USER", "agentic"),
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ.get("POSTGRES_DB", "agentic"),
    )


def register_server(name: str, url: str, transport: str = "streamable-http") -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mcp_servers (name, url, transport)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    url = EXCLUDED.url,
                    transport = EXCLUDED.transport,
                    last_heartbeat = NOW()
                """,
                (name, url, transport),
            )
        conn.commit()


def deregister_server(name: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mcp_servers WHERE name = %s", (name,))
        conn.commit()


def discover_servers() -> list[McpServerRecord]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, url, transport
                FROM mcp_servers
                ORDER BY registered_at
                """
            )
            rows = cur.fetchall()

    return [McpServerRecord(name=row[0], url=row[1], transport=row[2]) for row in rows]
