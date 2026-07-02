from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .connection import default_db_path, get_connection
from .migrations import ensure_database


class DatabaseRepository:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        ensure_database(root_dir)

    def status(self) -> dict[str, Any]:
        db_path = default_db_path(self.root_dir)
        with get_connection(self.root_dir) as connection:
            latest_run = self._one(
                connection,
                """
                SELECT run_id, report_date, status, started_at, finished_at, dashboard_path, report_path, error_message
                FROM import_runs
                ORDER BY started_at DESC
                LIMIT 1
                """,
            )
            table_counts = {}
            for table in (
                "asset_master",
                "daily_reports",
                "market_daily_indicators",
                "etf_daily_bars",
                "etf_daily_signals",
                "tl_daily_signals",
                "convertible_bond_snapshots",
                "refresh_jobs",
                "data_quality_checks",
                "agent_runs",
                "chat_traces",
            ):
                table_counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            pragmas = {
                "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
                "user_version": connection.execute("PRAGMA user_version").fetchone()[0],
            }
            latest_chat = self._one(
                connection,
                """
                SELECT trace_id, created_at, llm_used, llm_model
                FROM chat_traces
                ORDER BY created_at DESC
                LIMIT 1
                """,
            )
            chat_summary = self._one(
                connection,
                """
                SELECT COUNT(*) AS total, COALESCE(SUM(llm_used), 0) AS llm_used_count
                FROM chat_traces
                """,
            )
        return {
            "dbPath": str(db_path),
            "exists": db_path.exists(),
            "sizeBytes": db_path.stat().st_size if db_path.exists() else 0,
            "latestRun": latest_run,
            "tableCounts": table_counts,
            "pragmas": pragmas,
            "chatModel": {
                "latest": latest_chat,
                "summary": chat_summary,
            },
        }

    def latest_report_date(self) -> str | None:
        with get_connection(self.root_dir) as connection:
            row = connection.execute("SELECT report_date FROM daily_reports ORDER BY report_date DESC LIMIT 1").fetchone()
            return row["report_date"] if row else None

    def resolve_asset(self, query: str) -> dict[str, Any] | None:
        needle = query.strip()
        if not needle:
            return None
        with get_connection(self.root_dir) as connection:
            row = self._one(
                connection,
                """
                SELECT code, name, asset_type, aliases_json, first_seen_date, last_seen_date
                FROM asset_master
                WHERE code = ? OR name = ? OR aliases_json LIKE ?
                ORDER BY last_seen_date DESC
                LIMIT 1
                """,
                (needle, needle, f"%{needle}%"),
            )
            if row is None:
                rows = [
                    self._decode_row(item)
                    for item in connection.execute(
                        """
                        SELECT code, name, asset_type, aliases_json, first_seen_date, last_seen_date
                        FROM asset_master
                        ORDER BY asset_type, code
                        """
                    ).fetchall()
                ]
                for item in rows:
                    if item is None:
                        continue
                    aliases = item.get("aliases_json") or []
                    candidates = {str(item.get("code", "")), str(item.get("name", "")), *[str(alias) for alias in aliases]}
                    if any(candidate and candidate.lower() in needle.lower() for candidate in candidates):
                        row = item
                        break
        return row

    def list_assets(self, asset_type: str | None = None) -> list[dict[str, Any]]:
        with get_connection(self.root_dir) as connection:
            if asset_type:
                rows = connection.execute(
                    """
                    SELECT code, name, asset_type, aliases_json, first_seen_date, last_seen_date
                    FROM asset_master
                    WHERE asset_type = ?
                    ORDER BY asset_type, code
                    """,
                    (asset_type,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT code, name, asset_type, aliases_json, first_seen_date, last_seen_date
                    FROM asset_master
                    ORDER BY asset_type, code
                    """
                ).fetchall()
            return [item for row in rows if (item := self._decode_row(row)) is not None]

    def get_etf_signal(self, code: str, trade_date: str | None = None) -> dict[str, Any] | None:
        with get_connection(self.root_dir) as connection:
            if trade_date is None:
                row = connection.execute(
                    """
                    SELECT * FROM etf_daily_signals
                    WHERE code = ?
                    ORDER BY trade_date DESC
                    LIMIT 1
                    """,
                    (code,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM etf_daily_signals WHERE code = ? AND trade_date = ? LIMIT 1",
                    (code, trade_date),
                ).fetchone()
            return self._decode_row(row)

    def get_etf_signals(self, code: str, trade_date: str | None = None) -> list[dict[str, Any]]:
        with get_connection(self.root_dir) as connection:
            if trade_date is None:
                row = connection.execute("SELECT MAX(trade_date) AS latest FROM etf_daily_signals").fetchone()
                trade_date = row["latest"] if row else None
            rows = connection.execute(
                """
                SELECT * FROM etf_daily_signals
                WHERE code = ? AND (? IS NULL OR trade_date = ?)
                ORDER BY trade_date DESC, signal_bucket
                """,
                (code, trade_date, trade_date),
            ).fetchall()
            return [item for row in rows if (item := self._decode_row(row)) is not None]

    def get_etf_latest_bar(self, code: str, trade_date: str | None = None) -> dict[str, Any] | None:
        with get_connection(self.root_dir) as connection:
            if trade_date is None:
                row = connection.execute(
                    """
                    SELECT * FROM etf_daily_bars
                    WHERE code = ?
                    ORDER BY trade_date DESC
                    LIMIT 1
                    """,
                    (code,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM etf_daily_bars WHERE code = ? AND trade_date = ? LIMIT 1",
                    (code, trade_date),
                ).fetchone()
            return self._decode_row(row)

    def get_etf_history(self, code: str, limit: int = 8) -> list[dict[str, Any]]:
        with get_connection(self.root_dir) as connection:
            rows = connection.execute(
                """
                SELECT * FROM etf_daily_bars
                WHERE code = ?
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (code, limit),
            ).fetchall()
            return [item for row in rows if (item := self._decode_row(row)) is not None]

    def get_market_history(self, code: str, limit: int = 60) -> list[dict[str, Any]]:
        with get_connection(self.root_dir) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM market_daily_indicators
                WHERE code = ?
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (code, limit),
            ).fetchall()
            return [item for row in rows if (item := self._decode_row(row)) is not None]

    def get_latest_market_bar(self, code: str) -> dict[str, Any] | None:
        with get_connection(self.root_dir) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM market_daily_indicators
                WHERE code = ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (code,),
            ).fetchone()
            return self._decode_row(row)

    def get_convertible_snapshot(self, code: str, report_date: str | None = None) -> dict[str, Any] | None:
        with get_connection(self.root_dir) as connection:
            if report_date:
                row = connection.execute(
                    """
                    SELECT *
                    FROM convertible_bond_snapshots
                    WHERE bond_code = ? AND report_date = ?
                    LIMIT 1
                    """,
                    (code, report_date),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT *
                    FROM convertible_bond_snapshots
                    WHERE bond_code = ?
                    ORDER BY report_date DESC, rank ASC
                    LIMIT 1
                    """,
                    (code,),
                ).fetchone()
            return self._decode_row(row)

    def get_convertible_rankings(self, limit: int = 50) -> list[dict[str, Any]]:
        with get_connection(self.root_dir) as connection:
            latest = connection.execute("SELECT MAX(report_date) AS latest FROM convertible_bond_snapshots").fetchone()
            report_date = latest["latest"] if latest else None
            if not report_date:
                return []
            rows = connection.execute(
                """
                SELECT *
                FROM convertible_bond_snapshots
                WHERE report_date = ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (report_date, limit),
            ).fetchall()
            return [item for row in rows if (item := self._decode_row(row)) is not None]

    def asset_detail(self, code: str, history_limit: int = 80) -> dict[str, Any]:
        asset = self.resolve_asset(code) or {"code": code, "name": code, "asset_type": "UNKNOWN"}
        asset_type = str(asset.get("asset_type", ""))
        detail: dict[str, Any] = {"asset": asset}
        if asset_type in {"ETF", "TL"}:
            detail["latestMarketBar"] = self.get_latest_market_bar(code)
            detail["marketHistory"] = self.get_market_history(code, limit=history_limit)
            if asset_type == "ETF":
                latest = detail["latestMarketBar"] or self.get_etf_latest_bar(code)
                detail["signals"] = self.get_etf_signals(code, latest.get("trade_date") if latest else None)
            if asset_type == "TL":
                detail["tlState"] = self.get_tl_state()
        elif asset_type == "CONVERTIBLE":
            snapshot = self.get_convertible_snapshot(code)
            detail["convertibleSnapshot"] = snapshot
            if snapshot is None:
                detail["convertibleMessage"] = "当前最新报告没有该转债排序快照；通常表示未进入候选池，或已被价格、评级、强赎、YTM、规模等风控条件过滤。"
        return detail

    def database_inventory(self) -> dict[str, Any]:
        status = self.status()
        assets = self.list_assets()
        return {
            "status": status,
            "assets": assets,
            "assetCounts": {
                "ETF": len([item for item in assets if item.get("asset_type") == "ETF"]),
                "TL": len([item for item in assets if item.get("asset_type") == "TL"]),
                "CONVERTIBLE": len([item for item in assets if item.get("asset_type") == "CONVERTIBLE"]),
            },
        }

    def get_tl_state(self, trade_date: str | None = None) -> dict[str, Any] | None:
        with get_connection(self.root_dir) as connection:
            if trade_date is None:
                row = connection.execute("SELECT * FROM tl_daily_signals ORDER BY trade_date DESC LIMIT 1").fetchone()
            else:
                row = connection.execute("SELECT * FROM tl_daily_signals WHERE trade_date = ? LIMIT 1", (trade_date,)).fetchone()
            return self._decode_row(row)

    def create_refresh_job(self, job_id: str, command: list[str], message: str = "Queued") -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        with get_connection(self.root_dir) as connection:
            connection.execute(
                """
                INSERT INTO refresh_jobs(job_id, status, message, command_json, created_at, updated_at, payload_json)
                VALUES (?, 'queued', ?, ?, ?, ?, ?)
                """,
                (job_id, message, json.dumps(command, ensure_ascii=False), now, now, "{}"),
            )
            connection.commit()
        return self.get_refresh_job(job_id) or {"job_id": job_id, "status": "queued"}

    def update_refresh_job(self, job_id: str, **updates: Any) -> dict[str, Any] | None:
        allowed = {
            "status",
            "message",
            "started_at",
            "finished_at",
            "return_code",
            "stdout_tail",
            "stderr_tail",
            "dashboard_path",
            "audit_path",
            "run_id",
            "payload_json",
        }
        fields = [key for key in updates if key in allowed]
        if not fields:
            return self.get_refresh_job(job_id)
        assignments = ", ".join(f"{field}=?" for field in fields)
        values = [updates[field] for field in fields]
        values.extend([datetime.now().isoformat(timespec="seconds"), job_id])
        with get_connection(self.root_dir) as connection:
            connection.execute(
                f"UPDATE refresh_jobs SET {assignments}, updated_at=? WHERE job_id=?",
                tuple(values),
            )
            connection.commit()
        return self.get_refresh_job(job_id)

    def get_refresh_job(self, job_id: str) -> dict[str, Any] | None:
        with get_connection(self.root_dir) as connection:
            row = connection.execute("SELECT * FROM refresh_jobs WHERE job_id = ? LIMIT 1", (job_id,)).fetchone()
            return self._decode_row(row)

    def latest_refresh_job(self) -> dict[str, Any] | None:
        with get_connection(self.root_dir) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM refresh_jobs
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
            return self._decode_row(row)

    def _one(self, connection: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        row = connection.execute(sql, params).fetchone()
        return self._decode_row(row)

    def _decode_row(self, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for key, value in list(item.items()):
            if key.endswith("_json") and isinstance(value, str):
                try:
                    item[key] = json.loads(value)
                except json.JSONDecodeError:
                    pass
        return item
