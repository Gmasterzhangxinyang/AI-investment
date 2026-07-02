from __future__ import annotations

from pathlib import Path

from .connection import get_connection

SCHEMA_VERSION = 1


def ensure_database(root_dir: Path) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_connection(root_dir) as connection:
        connection.executescript(schema_sql)
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        if current < SCHEMA_VERSION:
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
