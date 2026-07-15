from __future__ import annotations

import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd


class ArtifactStore:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_dataframe(self, name: str, df: pd.DataFrame) -> Path:
        path = self.output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return path

    def save_json(self, name: str, payload: dict[str, Any]) -> Path:
        path = self.output_dir / f"{name}.json"
        atomic_write_text(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        )
        return path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    """Publish one complete text file without exposing a partially written target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def atomic_copy_file(source: Path, target: Path) -> Path:
    """Copy to the target directory first, then atomically switch the public path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        shutil.copyfile(source, temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)
