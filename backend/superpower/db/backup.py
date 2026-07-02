from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .connection import default_db_path


def backup_database(root_dir: Path) -> Path | None:
    source = default_db_path(root_dir)
    if not source.exists():
        return None
    backup_dir = root_dir / "data" / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"research-{stamp}.db"
    shutil.copy2(source, target)
    return target
