from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .backup import backup_database
from .connection import get_connection
from .migrations import ensure_database


def ingest_dashboard(
    root_dir: Path,
    run_id: str,
    dashboard_path: Path,
    *,
    published_dashboard_path: Path | None = None,
    published_report_path: Path | None = None,
    published_market_indicators_path: Path | None = None,
) -> dict[str, Any]:
    ensure_database(root_dir)
    backup_path = backup_database(root_dir)
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    market_indicator_rows = _load_market_indicator_rows(dashboard)
    stored_dashboard = dict(dashboard)
    if published_report_path is not None:
        stored_dashboard["reportPath"] = str(published_report_path)
    if published_market_indicators_path is not None:
        stored_dashboard["marketIndicatorsPath"] = str(published_market_indicators_path)
    stored_dashboard_path = published_dashboard_path or dashboard_path
    dashboard = stored_dashboard
    report_date = str(dashboard.get("reportDate") or "")
    if not report_date:
        raise ValueError("dashboard missing reportDate")
    normalized_report_date = _fmt_date(report_date)

    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(root_dir) as connection:
        connection.execute("BEGIN")
        try:
            connection.execute(
                """
                INSERT INTO import_runs(run_id, report_date, status, dashboard_path, report_path, started_at, source_manifest_json)
                VALUES (?, ?, 'running', ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  report_date=excluded.report_date,
                  status='running',
                  dashboard_path=excluded.dashboard_path,
                  report_path=excluded.report_path,
                  started_at=excluded.started_at,
                  source_manifest_json=excluded.source_manifest_json,
                  error_message=NULL
                """,
                (
                    run_id,
                    normalized_report_date,
                    str(stored_dashboard_path),
                    str(dashboard.get("reportPath", "")),
                    now,
                    _json(dashboard.get("sourceManifest", [])),
                ),
            )
            _upsert_assets(connection, dashboard, normalized_report_date)
            _upsert_daily_report(connection, run_id, normalized_report_date, stored_dashboard_path, dashboard)
            _upsert_summary(connection, normalized_report_date, dashboard.get("summary", []))
            _upsert_market_indicators(connection, market_indicator_rows)
            _upsert_etf_bars(connection, _etf_bar_rows(dashboard))
            _upsert_etf_signals(connection, dashboard)
            _upsert_tl_signals(connection, dashboard.get("tlToday", []) + dashboard.get("tlRecent", []))
            ranked_convertibles = dashboard.get("cbRanked", []) or dashboard.get("cbTop10", [])
            excluded_convertibles = dashboard.get("cbExcluded", [])
            _upsert_convertibles(
                connection,
                normalized_report_date,
                [dict(row, record_status="ranked") for row in ranked_convertibles]
                + [dict(row, record_status="excluded") for row in excluded_convertibles],
            )
            _upsert_data_quality(connection, run_id, dashboard.get("dataQuality", []))
            _upsert_source_manifest(connection, run_id, dashboard.get("sourceManifest", []))
            _upsert_agent_runs(connection, run_id, dashboard.get("agentAudit", []))
            _upsert_ai_reviews(connection, run_id, dashboard.get("aiCommitteeReviews", []))
            _upsert_risk_summary(connection, normalized_report_date, dashboard.get("riskSummary", []))
            _upsert_backtest(connection, normalized_report_date, dashboard)

            connection.execute(
                "UPDATE import_runs SET status='success', finished_at=?, error_message=NULL WHERE run_id=?",
                (datetime.now().isoformat(timespec="seconds"), run_id),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            connection.execute(
                """
                INSERT INTO import_runs(run_id, report_date, status, dashboard_path, report_path, started_at, finished_at, error_message)
                VALUES (?, ?, 'failed', ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  status='failed',
                  finished_at=excluded.finished_at,
                  error_message=excluded.error_message
                """,
                (
                    run_id,
                    normalized_report_date,
                    str(stored_dashboard_path),
                    str(dashboard.get("reportPath", "")),
                    now,
                    datetime.now().isoformat(timespec="seconds"),
                    str(exc),
                ),
            )
            connection.commit()
            raise

    return {
        "dbPath": str(root_dir / "data" / "research.db"),
        "backupPath": str(backup_path) if backup_path else "",
        "runId": run_id,
        "reportDate": normalized_report_date,
        "status": "success",
    }


def _load_market_indicator_rows(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    path_value = dashboard.get("marketIndicatorsPath")
    if not path_value:
        return []
    path = Path(str(path_value))
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        return []
    canonical = {
        (str(row.get("code")), _fmt_date(row.get("date") or dashboard.get("reportDate"))): row
        for row in (dashboard.get("etf", {}).get("all_signals") or [])
        if row.get("code")
    }
    return [
        {**row, **canonical.get((str(row.get("code")), _fmt_date(row.get("date"))), {})}
        if str(row.get("asset_type")) == "ETF"
        else row
        for row in rows
    ]


def _upsert_assets(connection: Any, dashboard: dict[str, Any], report_date: str) -> None:
    rows: list[tuple[str, str, str]] = []
    for key in ("etfWatchlist", "etfBuyCandidates", "etfSellAlerts", "etfDetailHistory"):
        for row in dashboard.get(key, []):
            if row.get("code"):
                rows.append((str(row["code"]), str(row.get("name", row["code"])), "ETF"))
    for row in dashboard.get("etf", {}).get("all_signals", []):
        if row.get("code"):
            rows.append((str(row["code"]), str(row.get("name", row["code"])), "ETF"))
    for row in dashboard.get("tlToday", []) + dashboard.get("tlRecent", []):
        if row.get("code"):
            rows.append((str(row["code"]), str(row.get("name", row["code"])), "TL"))
    for row in dashboard.get("cbTop10", []) + dashboard.get("cbRanked", []) + dashboard.get("cbExcluded", []):
        code = row.get("bond_code") or row.get("code")
        name = row.get("bond_name") or row.get("name") or code
        if code:
            rows.append((str(code), str(name), "CONVERTIBLE"))

    for code, name, asset_type in sorted(set(rows)):
        aliases = sorted({name, name.replace("ETF", ""), code.split(".")[0]})
        connection.execute(
            """
            INSERT INTO asset_master(code, name, asset_type, aliases_json, first_seen_date, last_seen_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(code) DO UPDATE SET
              name=excluded.name,
              asset_type=excluded.asset_type,
              aliases_json=excluded.aliases_json,
              first_seen_date=COALESCE(asset_master.first_seen_date, excluded.first_seen_date),
              last_seen_date=excluded.last_seen_date,
              updated_at=CURRENT_TIMESTAMP
            """,
            (code, name, asset_type, _json(aliases), _fmt_date(report_date), _fmt_date(report_date)),
        )


def _upsert_daily_report(connection: Any, run_id: str, report_date: str, dashboard_path: Path, dashboard: dict[str, Any]) -> None:
    summary_text = ""
    summaries = dashboard.get("researchSummary", [])
    if summaries:
        summary_text = str(summaries[0].get("content", ""))
    connection.execute(
        """
        INSERT INTO daily_reports(report_date, run_id, report_path, dashboard_path, summary_text, payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(report_date) DO UPDATE SET
          run_id=excluded.run_id,
          report_path=excluded.report_path,
          dashboard_path=excluded.dashboard_path,
          summary_text=excluded.summary_text,
          payload_json=excluded.payload_json,
          created_at=CURRENT_TIMESTAMP
        """,
        (
            _fmt_date(report_date),
            run_id,
            str(dashboard.get("reportPath", "")),
            str(dashboard_path),
            summary_text,
            _json(dashboard),
        ),
    )


def _upsert_summary(connection: Any, report_date: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        item = str(row.get("item", ""))
        if not item:
            continue
        connection.execute(
            """
            INSERT INTO summary_items(report_date, item, value_json)
            VALUES (?, ?, ?)
            ON CONFLICT(report_date, item) DO UPDATE SET value_json=excluded.value_json
            """,
            (_fmt_date(report_date), item, _json(row.get("value"))),
        )


def _upsert_etf_bars(connection: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        code = row.get("code")
        trade_date = _fmt_date(row.get("date"))
        if not code or not trade_date:
            continue
        connection.execute(
            """
            INSERT INTO etf_daily_bars(
              trade_date, code, name, close, ma5, ma10, ma20, ma60, vol_ratio60, dif, dea, macd_hist, kdj_j, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_date, code) DO UPDATE SET
              name=excluded.name, close=excluded.close, ma5=excluded.ma5, ma10=excluded.ma10,
              ma20=excluded.ma20, ma60=excluded.ma60, vol_ratio60=excluded.vol_ratio60,
              dif=excluded.dif, dea=excluded.dea, macd_hist=excluded.macd_hist, kdj_j=excluded.kdj_j,
              payload_json=excluded.payload_json
            """,
            (
                trade_date,
                str(code),
                row.get("name"),
                _num(row.get("close")),
                _num(row.get("ma5")),
                _num(row.get("ma10")),
                _num(row.get("ma20")),
                _num(row.get("ma60")),
                _num(row.get("vol_ratio60")),
                _num(row.get("dif")),
                _num(row.get("dea")),
                _num(row.get("macd_hist")),
                _num(row.get("kdj_j")),
                _json(row),
            ),
        )


def _etf_bar_rows(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    details = [dict(row) for row in dashboard.get("etfDetailHistory", [])]
    canonical = dashboard.get("etf", {}).get("all_signals", [])
    by_key = {
        (str(row.get("code")), _fmt_date(row.get("date"))): row
        for row in details
        if row.get("code")
    }
    for signal in canonical:
        code = str(signal.get("code") or "")
        date = _fmt_date(signal.get("date") or dashboard.get("reportDate"))
        if not code or not date:
            continue
        key = (code, date)
        by_key[key] = {**by_key.get(key, {}), **signal, "date": date}
    return list(by_key.values())


def _upsert_market_indicators(connection: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        asset_type = str(row.get("asset_type", "")).strip()
        code = str(row.get("code", "")).strip()
        trade_date = _fmt_date(row.get("date") or row.get("trade_date"))
        if not asset_type or not code or not trade_date:
            continue
        connection.execute(
            """
            INSERT INTO market_daily_indicators(
              asset_type, trade_date, code, name, open, high, low, close, volume, amount,
              open_interest, open_interest_change, ma5, ma10, ma20, ma60, vol_ratio60,
              dif, dea, macd_hist, kdj_k, kdj_d, kdj_j, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_type, trade_date, code) DO UPDATE SET
              name=excluded.name, open=excluded.open, high=excluded.high, low=excluded.low,
              close=excluded.close, volume=excluded.volume, amount=excluded.amount,
              open_interest=excluded.open_interest, open_interest_change=excluded.open_interest_change,
              ma5=excluded.ma5, ma10=excluded.ma10, ma20=excluded.ma20, ma60=excluded.ma60,
              vol_ratio60=excluded.vol_ratio60, dif=excluded.dif, dea=excluded.dea,
              macd_hist=excluded.macd_hist, kdj_k=excluded.kdj_k, kdj_d=excluded.kdj_d,
              kdj_j=excluded.kdj_j, payload_json=excluded.payload_json
            """,
            (
                asset_type,
                trade_date,
                code,
                row.get("name"),
                _num(row.get("open")),
                _num(row.get("high")),
                _num(row.get("low")),
                _num(row.get("close")),
                _num(row.get("volume")),
                _num(row.get("amount")),
                _num(row.get("open_interest")),
                _num(row.get("open_interest_change")),
                _num(row.get("ma5")),
                _num(row.get("ma10")),
                _num(row.get("ma20")),
                _num(row.get("ma60")),
                _num(row.get("vol_ratio60")),
                _num(row.get("dif")),
                _num(row.get("dea")),
                _num(row.get("macd_hist")),
                _num(row.get("kdj_k")),
                _num(row.get("kdj_d")),
                _num(row.get("kdj_j")),
                _json(row),
            ),
        )


def _upsert_etf_signals(connection: Any, dashboard: dict[str, Any]) -> None:
    buckets = [
        ("entry", dashboard.get("etfBuyCandidates", [])),
        ("watch", dashboard.get("etfWatchlist", [])),
        ("exit", dashboard.get("etfSellAlerts", [])),
    ]
    for bucket, rows in buckets:
        for row in rows:
            code = row.get("code")
            trade_date = _fmt_date(row.get("date") or dashboard.get("reportDate"))
            if not code or not trade_date:
                continue
            connection.execute(
                """
                INSERT INTO etf_daily_signals(
                  trade_date, code, name, signal_bucket, buy_signal, sell_signal, watch_type,
                  ma5_ma10_signal, ma5_ma20_status, volume_check, missing_condition,
                  suggested_action, signal_reason, score, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date, code, signal_bucket) DO UPDATE SET
                  name=excluded.name, buy_signal=excluded.buy_signal, sell_signal=excluded.sell_signal,
                  watch_type=excluded.watch_type, ma5_ma10_signal=excluded.ma5_ma10_signal,
                  ma5_ma20_status=excluded.ma5_ma20_status, volume_check=excluded.volume_check,
                  missing_condition=excluded.missing_condition, suggested_action=excluded.suggested_action,
                  signal_reason=excluded.signal_reason, score=excluded.score, payload_json=excluded.payload_json
                """,
                (
                    trade_date,
                    str(code),
                    row.get("name"),
                    bucket,
                    _bool(row.get("buy_signal")),
                    _bool(row.get("sell_signal")),
                    row.get("watch_type"),
                    row.get("ma5_ma10_signal"),
                    row.get("ma5_ma20_status"),
                    row.get("volume_check"),
                    row.get("missing_condition"),
                    row.get("suggested_action"),
                    row.get("signal_reason"),
                    _num(row.get("score")),
                    _json(row),
                ),
            )


def _upsert_tl_signals(connection: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        code = row.get("code") or "TL.CFE"
        trade_date = _fmt_date(row.get("date"))
        if not trade_date:
            continue
        connection.execute(
            """
            INSERT INTO tl_daily_signals(
              trade_date, code, name, state, close, macd_hist, kdj_j, week_macd_hist, week_kdj_j,
              buy_signal, attention_signal, no_trade_signal, daily_macd_condition, daily_macd_reason,
              daily_kdj_threshold_check, weekly_macd_condition, weekly_macd_reason, weekly_kdj_threshold_check, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_date, code) DO UPDATE SET
              name=excluded.name, state=excluded.state, close=excluded.close, macd_hist=excluded.macd_hist,
              kdj_j=excluded.kdj_j, week_macd_hist=excluded.week_macd_hist, week_kdj_j=excluded.week_kdj_j,
              buy_signal=excluded.buy_signal, attention_signal=excluded.attention_signal,
              no_trade_signal=excluded.no_trade_signal, daily_macd_condition=excluded.daily_macd_condition,
              daily_macd_reason=excluded.daily_macd_reason, daily_kdj_threshold_check=excluded.daily_kdj_threshold_check,
              weekly_macd_condition=excluded.weekly_macd_condition, weekly_macd_reason=excluded.weekly_macd_reason,
              weekly_kdj_threshold_check=excluded.weekly_kdj_threshold_check, payload_json=excluded.payload_json
            """,
            (
                trade_date,
                str(code),
                row.get("name"),
                row.get("state"),
                _num(row.get("收盘价")),
                _num(row.get("macd_hist")),
                _num(row.get("kdj_j")),
                _num(row.get("week_macd_hist")),
                _num(row.get("week_kdj_j")),
                _bool(row.get("buy_signal")),
                _bool(row.get("attention_signal")),
                _bool(row.get("no_trade_signal")),
                row.get("daily_macd_condition"),
                row.get("daily_macd_reason"),
                row.get("daily_kdj_threshold_check"),
                row.get("weekly_macd_condition"),
                row.get("weekly_macd_reason"),
                row.get("weekly_kdj_threshold_check"),
                _json(row),
            ),
        )


def _upsert_convertibles(connection: Any, report_date: str, rows: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM convertible_bond_snapshots WHERE report_date=?", (_fmt_date(report_date),))
    for index, row in enumerate(rows, start=1):
        code = row.get("bond_code") or row.get("code")
        if not code:
            continue
        connection.execute(
            """
            INSERT INTO convertible_bond_snapshots(
              report_date, source_date, bond_code, bond_name, record_status, rank, price,
              remaining_years, conversion_premium_rate, ytm, deducted_profit_growth, score,
              base_score, base_grade, strategy_id, strategy_version, overlay_id, overlay_version,
              overlay_enabled, config_hash, auxiliary_score, auxiliary_state, rank_reason, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date, bond_code) DO UPDATE SET
              source_date=excluded.source_date, bond_name=excluded.bond_name,
              record_status=excluded.record_status, rank=excluded.rank, price=excluded.price,
              remaining_years=excluded.remaining_years, conversion_premium_rate=excluded.conversion_premium_rate,
              ytm=excluded.ytm, deducted_profit_growth=excluded.deducted_profit_growth,
              score=excluded.score, base_score=excluded.base_score, base_grade=excluded.base_grade,
              strategy_id=excluded.strategy_id, strategy_version=excluded.strategy_version,
              overlay_id=excluded.overlay_id, overlay_version=excluded.overlay_version,
              overlay_enabled=excluded.overlay_enabled, config_hash=excluded.config_hash,
              auxiliary_score=excluded.auxiliary_score, auxiliary_state=excluded.auxiliary_state,
              rank_reason=excluded.rank_reason, payload_json=excluded.payload_json
            """,
            (
                _fmt_date(report_date),
                _fmt_date(row.get("source_date") or row.get("date")),
                str(code),
                row.get("bond_name") or row.get("name"),
                row.get("record_status") or "ranked",
                int(row.get("rank") or index),
                _num(row.get("price")),
                _num(row.get("remaining_years")),
                _num(row.get("conversion_premium_rate")),
                _num(row.get("ytm")),
                _num(row.get("deducted_profit_growth")),
                _num(row.get("score")),
                _num(row.get("base_score")),
                row.get("base_grade") or row.get("score_grade"),
                row.get("strategy_id"),
                row.get("strategy_version"),
                row.get("overlay_id"),
                row.get("overlay_version"),
                int(bool(row.get("overlay_enabled"))) if row.get("overlay_enabled") is not None else None,
                row.get("config_hash"),
                _num(row.get("auxiliary_score")),
                row.get("auxiliary_state"),
                row.get("rank_reason"),
                _json(row),
            ),
        )


def _upsert_data_quality(connection: Any, run_id: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        item = str(row.get("item", ""))
        if not item:
            continue
        connection.execute(
            """
            INSERT OR REPLACE INTO data_quality_checks(run_id, item, status, detail, note, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, item, str(row.get("status", "")), row.get("detail"), row.get("note"), _json(row)),
        )


def _upsert_source_manifest(connection: Any, run_id: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        source_type = str(row.get("source_type", ""))
        if not source_type:
            continue
        connection.execute(
            """
            INSERT OR REPLACE INTO source_manifests(
              run_id, source_type, path, exists_flag, size_bytes, modified_at, sha256, archive_path, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_type,
                row.get("path"),
                _bool(row.get("exists")),
                int(row.get("size_bytes") or 0),
                row.get("modified_at"),
                row.get("sha256"),
                row.get("archive_path"),
                _json(row),
            ),
        )


def _upsert_agent_runs(connection: Any, run_id: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        agent = str(row.get("agent", ""))
        if not agent:
            continue
        connection.execute(
            """
            INSERT OR REPLACE INTO agent_runs(
              run_id, agent, status, message, started_at, finished_at, duration_ms, metric_role, metric_skill, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                agent,
                row.get("status"),
                row.get("message"),
                row.get("started_at"),
                row.get("finished_at"),
                int(row.get("duration_ms") or 0),
                row.get("metric_role"),
                row.get("metric_skill"),
                _json(row),
            ),
        )


def _upsert_ai_reviews(connection: Any, run_id: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        role = str(row.get("role", ""))
        if not role:
            continue
        connection.execute(
            """
            INSERT OR REPLACE INTO ai_reviews(
              run_id, role, title, llm_used, provider, model, reason, review, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                role,
                row.get("title"),
                _bool(row.get("llm_used")),
                row.get("provider"),
                row.get("model"),
                row.get("reason"),
                row.get("review"),
                _json(row),
            ),
        )


def _upsert_risk_summary(connection: Any, report_date: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        item = str(row.get("item", ""))
        if not item:
            continue
        connection.execute(
            """
            INSERT INTO risk_summary(report_date, item, value_json, level, payload_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(report_date, item) DO UPDATE SET
              value_json=excluded.value_json, level=excluded.level, payload_json=excluded.payload_json
            """,
            (_fmt_date(report_date), item, _json(row.get("value")), row.get("level"), _json(row)),
        )


def _upsert_backtest(connection: Any, report_date: str, dashboard: dict[str, Any]) -> None:
    for row in dashboard.get("backtestSummary", []):
        item = str(row.get("item", ""))
        if not item:
            continue
        connection.execute(
            """
            INSERT INTO backtest_summary(report_date, item, value_json, level, note, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date, item) DO UPDATE SET
              value_json=excluded.value_json, level=excluded.level, note=excluded.note, payload_json=excluded.payload_json
            """,
            (_fmt_date(report_date), item, _json(row.get("value")), row.get("level"), row.get("note"), _json(row)),
        )

    for row in dashboard.get("backtestTrades", []):
        code = row.get("code")
        entry_signal_date = _fmt_date(row.get("entry_signal_date"))
        if not code or not entry_signal_date:
            continue
        connection.execute(
            """
            INSERT INTO backtest_trades(
              report_date, code, entry_signal_date, name, entry_date, entry_price, exit_signal_date,
              exit_date, exit_price, holding_days, gross_return, net_return, entry_reason, exit_reason, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date, code, entry_signal_date) DO UPDATE SET
              name=excluded.name, entry_date=excluded.entry_date, entry_price=excluded.entry_price,
              exit_signal_date=excluded.exit_signal_date, exit_date=excluded.exit_date, exit_price=excluded.exit_price,
              holding_days=excluded.holding_days, gross_return=excluded.gross_return, net_return=excluded.net_return,
              entry_reason=excluded.entry_reason, exit_reason=excluded.exit_reason, payload_json=excluded.payload_json
            """,
            (
                _fmt_date(report_date),
                str(code),
                entry_signal_date,
                row.get("name"),
                _fmt_date(row.get("entry_date")),
                _num(row.get("entry_price")),
                _fmt_date(row.get("exit_signal_date")),
                _fmt_date(row.get("exit_date")),
                _num(row.get("exit_price")),
                int(row.get("holding_days") or 0),
                _num(row.get("gross_return")),
                _num(row.get("net_return")),
                row.get("entry_reason"),
                row.get("exit_reason"),
                _json(row),
            ),
        )


def _fmt_date(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if "T" in text:
        return text.split("T", 1)[0]
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> int:
    return 1 if bool(value) else 0
