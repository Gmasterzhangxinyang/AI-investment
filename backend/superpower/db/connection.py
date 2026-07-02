from __future__ import annotations

import sqlite3
from pathlib import Path


def default_db_path(root_dir: Path) -> Path:
    return root_dir / "data" / "research.db"


def get_connection(root_dir: Path, db_path: Path | None = None) -> sqlite3.Connection:
    path = (db_path or default_db_path(root_dir)).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection
