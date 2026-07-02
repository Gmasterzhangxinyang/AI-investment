from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

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
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        return path


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)

