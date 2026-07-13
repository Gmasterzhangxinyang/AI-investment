from __future__ import annotations

from pathlib import Path

from .connection import get_connection

SCHEMA_VERSION = 2


def ensure_database(root_dir: Path) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_connection(root_dir) as connection:
        connection.executescript(schema_sql)
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        if current < 2:
            _migrate_convertible_snapshots_v2(connection)
        if current < SCHEMA_VERSION:
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def _migrate_convertible_snapshots_v2(connection: object) -> None:
    existing = {
        row[1]
        for row in connection.execute("PRAGMA table_info(convertible_bond_snapshots)").fetchall()
    }
    columns = {
        "source_date": "TEXT",
        "record_status": "TEXT NOT NULL DEFAULT 'ranked'",
        "base_score": "REAL",
        "base_grade": "TEXT",
        "strategy_id": "TEXT",
        "strategy_version": "TEXT",
        "overlay_id": "TEXT",
        "overlay_version": "TEXT",
        "overlay_enabled": "INTEGER",
        "config_hash": "TEXT",
        "auxiliary_score": "REAL",
        "auxiliary_state": "TEXT",
    }
    for name, declaration in columns.items():
        if name not in existing:
            connection.execute(
                f"ALTER TABLE convertible_bond_snapshots ADD COLUMN {name} {declaration}"
            )
