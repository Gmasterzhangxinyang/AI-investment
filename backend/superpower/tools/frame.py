from __future__ import annotations

from typing import Any
import json

import pandas as pd


def records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def agent_audit_frame(results: list[Any]) -> pd.DataFrame:
    rows = []
    for result in results:
        row = {
            "agent": result.agent_name,
            "status": result.status,
            "message": result.message,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "duration_ms": result.duration_ms,
            "error": result.error,
        }
        for key, value in result.metrics.items():
            row[f"metric_{key}"] = value
        rows.append(row)
    return pd.DataFrame(rows)
