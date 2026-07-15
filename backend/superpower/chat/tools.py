from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from superpower.db import DatabaseRepository
from superpower.skills.etf_rotation_strategy.config import normalize_etf_config
from superpower.skills.etf_rotation_strategy.contracts import ETFHistory, ETFPositionState
from superpower.skills.etf_rotation_strategy.registry import default_registry
from superpower.skills.convertible_bond_ranking.handler import rank_convertible_bonds
from superpower.skills.technical_indicators.etf import add_etf_indicators
from superpower.tools.excel_reader import parse_convertible_bond_excel
from superpower.tools.frame import records

from .schemas import ChatIntent, ToolResult
from .access_policy import (
    AGENT_AUDIT_ROWS,
    AI_COMMITTEE_ROWS,
    CB_ANALYSIS_UNIVERSE_ROWS,
    CB_BUCKET_EVIDENCE_ROWS,
    CB_RANKING_QUERY_ROWS,
    DAILY_SUMMARY_ROWS,
    DATA_QUALITY_ROWS,
    ETF_DETAIL_HISTORY_ROWS,
    ETF_DIAGNOSTIC_ROWS,
    ETF_DUAL_STRATEGY_HISTORY_ROWS,
    ETF_LEGACY_HISTORY_ROWS,
    ETF_SIGNAL_ROWS_PER_BUCKET,
    ETF_WATCH_ROWS,
    RISK_SUMMARY_ROWS,
    SOURCE_MANIFEST_ROWS,
    TL_ANALYSIS_HISTORY_ROWS,
    TL_BACKEND_HISTORY_ROWS,
    TL_DISPLAY_HISTORY_ROWS,
    chat_access_scope,
)
from .strategy_knowledge import build_rule_contract


class ResearchToolbox:
    """Read-only tools exposed to the chat agent."""

    def __init__(self, dashboard: dict[str, Any], repository: DatabaseRepository | None = None) -> None:
        self.dashboard = dashboard
        self.repository = repository

    def collect(self, intent: ChatIntent) -> list[ToolResult]:
        if intent.name in {"conversation", "external_data_unavailable", "clarification"}:
            return []
        if intent.name == "chat_data_scope":
            return [self.get_chat_data_scope()]
        if intent.name == "etf_ranking":
            return [self.get_etf_ranking(intent.entities)]
        if intent.name == "etf_strategy_comparison":
            return [self.get_rule_contract(), self.get_etf_strategy_comparison(intent.entities)]
        if intent.name in {"database_inventory", "asset_list"}:
            return [self.get_data_map(), self.get_daily_summary(), self.get_database_inventory()]
        if intent.name in {"strategy_params", "strategy_comparison", "strategy_stability", "historical_diagnostics"}:
            tools = [self.get_rule_contract()]
            if intent.name != "strategy_params":
                tools.append(self.get_strategy_diagnostics())
            return tools
        if intent.name in {"etf_entry", "etf_exit", "etf_detail"}:
            tools = [
                self.get_rule_contract(),
                self.get_etf_signals(intent.entities),
                self.get_etf_watchlist(intent.entities),
            ]
            if intent.name == "etf_detail" and intent.entities.get("code"):
                tools.append(self.get_etf_single_asset(intent.entities["code"]))
            return tools
        if intent.name == "tl_timing":
            return [self.get_rule_contract(), self.get_tl_state()]
        if intent.name == "convertible_bond":
            tools = [self.get_rule_contract(), self.get_convertible_top10()]
            if intent.entities.get("code"):
                tools.append(self.get_convertible_detail(intent.entities["code"]))
            return tools
        if intent.name == "data_quality":
            return [self.get_data_map(), self.get_data_quality()]
        if intent.name == "agent_audit":
            return [self.get_data_map(), self.get_agent_audit()]

        tools: list[ToolResult] = [self.get_daily_summary(), self.get_rule_contract(), self.get_data_map(), self.get_research_snapshot()]
        if intent.name in {"daily_report", "risk_review"}:
            tools.extend([self.get_etf_signals(intent.entities), self.get_etf_watchlist(intent.entities)])
        if intent.name in {"tl_timing", "daily_report", "risk_review"}:
            tools.append(self.get_tl_state())
        if intent.name in {"convertible_bond", "daily_report", "risk_review"}:
            tools.append(self.get_convertible_top10())
        if intent.name == "convertible_bond" and intent.entities.get("code"):
            tools.append(self.get_convertible_detail(intent.entities["code"]))
        if intent.name in {"data_quality", "daily_report", "risk_review"}:
            tools.append(self.get_data_quality())
        if intent.name == "agent_audit":
            tools.append(self.get_agent_audit())
        if intent.name == "risk_review":
            tools.append(self.get_risk_summary())
        return tools

    def get_data_map(self) -> ToolResult:
        """Compact map of available local data so the LLM can reason about coverage."""
        run_info = self.dashboard.get("run_info") or {}
        report_date = self.dashboard.get("reportDate") or run_info.get("trade_date") or "--"
        status = self.dashboard.get("data_quality", {}).get("overall_status") or run_info.get("status") or "--"
        cb = self.dashboard.get("convertible_bond") or {}
        etf = self.dashboard.get("etf") or {}
        table_counts: dict[str, Any] = {}
        latest_run: dict[str, Any] | None = None
        asset_counts: dict[str, int] = {}
        if self.repository is not None:
            db_status = self.repository.status()
            table_counts = db_status.get("tableCounts") or {}
            latest_run = db_status.get("latestRun") or {}
            assets = self.repository.list_assets()
            asset_counts = {
                "ETF": len([item for item in assets if item.get("asset_type") == "ETF"]),
                "TL": len([item for item in assets if item.get("asset_type") == "TL"]),
                "CONVERTIBLE": len([item for item in assets if item.get("asset_type") == "CONVERTIBLE"]),
            }
        modules = {
            "daily_report": bool(self.dashboard.get("summary")),
            "etf": {
                "status": etf.get("status") or "ok",
                "buy_candidates": len(self.dashboard.get("etfBuyCandidates", [])),
                "watchlist": len(self.dashboard.get("etfWatchlist", [])),
                "sell_alerts": len(self.dashboard.get("etfSellAlerts", [])),
                "all_signals": len((etf.get("all_signals") or self.dashboard.get("etfAllSignals") or [])),
            },
            "tl": {
                "today_rows": len(self.dashboard.get("tlToday", [])),
                "recent_rows": len(self.dashboard.get("tlRecent", [])),
            },
            "convertible_bond": {
                "status": cb.get("status") or "ok",
                "qualified": len(cb.get("qualified") or []),
                "weak_watch": len(cb.get("weak_watch") or []),
                "risk_watch": len(cb.get("risk_watch") or []),
                "excluded": len(cb.get("excluded") or self.dashboard.get("cbExcluded") or []),
                "top10": len(cb.get("top10") or self.dashboard.get("cbTop10") or []),
                "quality_message": (cb.get("summary") or {}).get("quality_message") or "",
            },
        }
        return ToolResult(
            tool="get_data_map",
            title="Local data map",
            source="dashboard.run_info + dashboard modules + sqlite status",
            summary=f"本地数据地图：报告日期 {report_date}，数据状态 {status}，SQLite 表计数 {len(table_counts)} 项。",
            data={
                "report_date": report_date,
                "run_status": run_info.get("status") or "--",
                "data_quality_status": status,
                "modules": modules,
                "asset_counts": asset_counts,
                "sqlite_table_counts": table_counts,
                "latest_run": latest_run,
                "data_boundary": [
                    "只能回答 dashboard、SQLite、策略参数和本地 Excel 入库后的数据。",
                    "如果某标的或某日期没有入库，必须明确说没有数据。",
                    "可以解释规则、指出缺口、给出人工复核清单，但不能新增交易信号。",
                ],
            },
        )

    def get_chat_data_scope(self) -> ToolResult:
        coverage = self.repository.research_coverage() if self.repository is not None else {}
        policy = chat_access_scope(coverage)
        return ToolResult(
            tool="get_chat_data_scope",
            title="AI问答数据权限",
            source="chat.access_policy + sqlite research coverage",
            summary="AI 不直接访问数据库，只能读取后端白名单工具生成的裁剪证据包。",
            data=policy,
        )

    def get_research_snapshot(self) -> ToolResult:
        """A compact research worksheet for professional Q&A."""
        etf = self.dashboard.get("etf") or {}
        cb = self.dashboard.get("convertible_bond") or {}
        etf_rows = etf.get("all_signals") or self.dashboard.get("etfAllSignals") or []
        etf_sorted = sorted(etf_rows, key=lambda row: self._safe_float(row.get("score")), reverse=True)
        etf_weak = sorted(etf_rows, key=lambda row: self._safe_float(row.get("score")))
        cb_ranked = cb.get("ranked_candidates") or cb.get("candidates") or self.dashboard.get("cbRanked") or []
        cb_excluded = cb.get("excluded") or self.dashboard.get("cbExcluded") or []
        tl_today = self.dashboard.get("tlToday", [])
        risk_rows = self.dashboard.get("riskSummary", [])
        quality_rows = self.dashboard.get("dataQuality", [])
        warnings = [
            row
            for row in quality_rows
            if str(row.get("status", "")).upper() not in {"OK", "INFO", "SUCCESS", "PASS"}
        ][:8]
        top_etf = [self._compact_etf_row(row) for row in etf_sorted[:8]]
        weak_etf = [self._compact_etf_row(row) for row in etf_weak[:5]]
        cb_watch = [self._compact_cb_row(row) for row in (cb.get("weak_watch") or [])[:8]]
        cb_risk = [self._compact_cb_row(row) for row in (cb.get("risk_watch") or cb_ranked)[:8]]
        cb_excluded_sample = [self._compact_cb_row(row) for row in cb_excluded[:8]]
        tl_row = tl_today[0] if tl_today else {}
        summary = (
            f"研究快照：ETF全量 {len(etf_rows)} 只，"
            f"可转债合格 {len(cb.get('qualified') or [])} 只、弱观察 {len(cb.get('weak_watch') or [])} 只、"
            f"风险观察 {len(cb.get('risk_watch') or [])} 只，TL状态 {tl_row.get('display_status') or tl_row.get('state') or '--'}。"
        )
        return ToolResult(
            tool="get_research_snapshot",
            title="Professional research snapshot",
            source="dashboard.etf.all_signals + dashboard.tlToday + dashboard.convertible_bond + dashboard.riskSummary",
            summary=summary,
            data={
                "research_lens": [
                    "ETF：高分只代表相对强弱，必须再看是否触发建仓/平仓规则。",
                    "TL：先看周线硬约束，再看日线改善；没有低位反弹条件就不能升级。",
                    "可转债：先看候选资格分层，再看评分；高风险分层不进入 Top 候选。",
                    "风险：数据质量 WARN 和风控提示会降低结论置信度。",
                ],
                "etf_strength_leaders": top_etf,
                "etf_weak_tail": weak_etf,
                "tl_state": {
                    "display_status": tl_row.get("display_status") or tl_row.get("state"),
                    "reason": tl_row.get("reason"),
                    "weekly_macd_reason": tl_row.get("weekly_macd_reason"),
                    "weekly_kdj_threshold_check": tl_row.get("weekly_kdj_threshold_check"),
                    "daily_macd_reason": tl_row.get("daily_macd_reason"),
                    "daily_kdj_threshold_check": tl_row.get("daily_kdj_threshold_check"),
                },
                "convertible_bond_quality": {
                    "summary": cb.get("summary") or {},
                    "qualified": [self._compact_cb_row(row) for row in (cb.get("qualified") or [])[:8]],
                    "weak_watch": cb_watch,
                    "risk_watch": cb_risk,
                    "excluded_sample": cb_excluded_sample,
                },
                "risk_summary": risk_rows[:8],
                "data_quality_warnings": warnings,
            },
        )

    def get_rule_contract(self) -> ToolResult:
        params = self._load_strategy_params()
        contract = build_rule_contract(params)
        active_etf = contract["etf_strategy"]["active_strategy"]
        return ToolResult(
            tool="get_rule_contract",
            title="Rule contract",
            source="configs.strategy_params + deterministic strategy handlers",
            summary=(
                f"交易信号由确定性规则生成；当前ETF策略 {active_etf}，LLM 只能解释证据。"
                f" ETF买入量能阈值 {params.get('etf', {}).get('buy_volume_ratio_min', '--')}，"
                f"TL周线J阈值 {params.get('tl', {}).get('weekly_j_low_threshold', '--')}，"
                f"TL日线J阈值 {params.get('tl', {}).get('daily_j_low_threshold', '--')}。"
            ),
            data=contract,
        )

    def get_strategy_diagnostics(self) -> ToolResult:
        etf = self.dashboard.get("etf") or {}
        diagnostics = etf.get("historical_diagnostics") or []
        compact = [
            {
                key: row.get(key)
                for key in (
                    "strategy_id",
                    "strategy_version",
                    "state_type",
                    "entry_route",
                    "horizon",
                    "event_count",
                    "complete_horizon_count",
                    "sample_count",
                    "positive_return_rate",
                    "positive_rate",
                    "mean_return",
                    "average_return",
                    "mean_maximum_adverse_excursion",
                    "average_max_adverse_excursion",
                    "false_reversal_10d_count",
                    "false_reversal_10d_rate",
                    "false_reversal_count",
                    "false_reversal_rate",
                    "state_flip_frequency",
                    "diagnostic_note",
                )
                if key in row
            }
            for row in diagnostics[:ETF_DIAGNOSTIC_ROWS]
        ]
        return ToolResult(
            tool="get_strategy_diagnostics",
            title="ETF historical diagnostics",
            source="dashboard.etf.historical_diagnostics",
            summary=f"ETF历史诊断共 {len(diagnostics)} 条汇总；它用于回看信号后表现，不等同于完整组合回测。",
            data={
                "rows": compact,
                "boundary": [
                    "这是信号事件诊断，不包含完整仓位、资金占用、交易成本和组合净值。",
                    "样本之间可能重叠，不能把正收益比例直接当成实盘胜率。",
                    "没有足够样本时只能说证据不足，不能判定某策略稳定或更优。",
                ],
            },
        )

    def get_database_inventory(self) -> ToolResult:
        if self.repository is None:
            return ToolResult(
                tool="get_database_inventory",
                title="Database inventory",
                source="dashboard only",
                summary="未配置 SQLite Repository，无法列出数据库全量资产。",
                data={},
            )
        inventory = self.repository.database_inventory()
        assets = inventory["assets"]
        counts = inventory["assetCounts"]
        return ToolResult(
            tool="get_database_inventory",
            title="Database inventory",
            source="sqlite.asset_master + sqlite table counts",
            summary=f"数据库资产共 {len(assets)} 个：ETF {counts['ETF']} 个，TL {counts['TL']} 个，可转债 {counts['CONVERTIBLE']} 个。",
            data={
                "assetCounts": counts,
                "assets": assets,
                "tableCounts": inventory["status"]["tableCounts"],
                "latestRun": inventory["status"]["latestRun"],
            },
        )

    def get_daily_summary(self) -> ToolResult:
        rows = self.dashboard.get("summary", [])
        report_date = self.dashboard.get("reportDate", "--")
        return ToolResult(
            tool="get_daily_summary",
            title="Daily summary",
            source=f"dashboard.summary[{report_date}]",
            summary=f"日报日期 {report_date}，摘要指标 {len(rows)} 项。",
            data=rows[:DAILY_SUMMARY_ROWS],
        )

    def _load_strategy_params(self) -> dict[str, Any]:
        root_dir = getattr(self.repository, "root_dir", None)
        if root_dir is None:
            return {}
        path = root_dir / "configs" / "strategy_params.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _load_data_sources(self) -> dict[str, Any]:
        root_dir = getattr(self.repository, "root_dir", None)
        if root_dir is None:
            return {}
        path = root_dir / "configs" / "data_sources.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def get_etf_signals(self, entities: dict[str, str]) -> ToolResult:
        data = {
            "buy_candidates": [
                self._compact_etf_row(row)
                for row in self._filter_rows(self.dashboard.get("etfBuyCandidates", []), entities)[:ETF_SIGNAL_ROWS_PER_BUCKET]
            ],
            "sell_alerts": [
                self._compact_etf_row(row)
                for row in self._filter_rows(self.dashboard.get("etfSellAlerts", []), entities)[:ETF_SIGNAL_ROWS_PER_BUCKET]
            ],
        }
        return ToolResult(
            tool="get_etf_signals",
            title="ETF signals",
            source="dashboard.etfBuyCandidates + dashboard.etfSellAlerts",
            summary=f"ETF 建仓候选 {len(data['buy_candidates'])} 条，平仓提示 {len(data['sell_alerts'])} 条。",
            data=data,
        )

    def get_etf_watchlist(self, entities: dict[str, str]) -> ToolResult:
        rows = self._filter_rows(self.dashboard.get("etfWatchlist", []), entities)
        history = self._filter_rows(self.dashboard.get("etfDetailHistory", []), entities)
        return ToolResult(
            tool="get_etf_watchlist",
            title="ETF watchlist",
            source="dashboard.etfWatchlist + dashboard.etfDetailHistory",
            summary=f"ETF 关注池 {len(rows)} 条，匹配历史 {len(history)} 条。",
            data={
                "watchlist": [self._compact_etf_row(row) for row in rows[:ETF_WATCH_ROWS]],
                "history": [self._compact_etf_row(row) for row in history[-ETF_WATCH_ROWS:]],
            },
        )

    def get_etf_ranking(self, entities: dict[str, str]) -> ToolResult:
        metric = str(entities.get("metric") or "")
        direction = str(entities.get("direction") or "desc")
        try:
            limit = min(max(int(entities.get("limit") or 3), 1), 10)
        except (TypeError, ValueError):
            limit = 3
        metric_labels = {
            "score": "强弱分",
            "close": "收盘价",
            "vol_ratio60": "量能倍数（相对60日均量）",
            "share_change": "份额变化",
        }
        rows = (self.dashboard.get("etf") or {}).get("all_signals") or self.dashboard.get("etfAllSignals") or []
        valid_rows = [row for row in rows if metric and self._safe_float(row.get(metric)) != float("-inf")]
        sorted_rows = sorted(valid_rows, key=lambda row: self._safe_float(row.get(metric)), reverse=direction != "asc")
        compact_rows = []
        for index, row in enumerate(sorted_rows[:limit], start=1):
            compact = self._compact_etf_row(row)
            compact["rank"] = index
            compact["metric"] = metric
            compact["metric_value"] = row.get(metric)
            compact_rows.append(compact)
        label = metric_labels.get(metric, "未指定指标")
        summary = (
            f"ETF 全量 {len(rows)} 只，按{label}{'升序' if direction == 'asc' else '降序'}返回 {len(compact_rows)} 只。"
            if metric
            else f"ETF 全量 {len(rows)} 只；用户尚未指定排序指标。"
        )
        return ToolResult(
            tool="get_etf_ranking",
            title="ETF 指标排序",
            source="dashboard.etf.all_signals",
            summary=summary,
            data={
                "metric": metric,
                "metric_label": label,
                "direction": direction,
                "total": len(rows),
                "rows": compact_rows,
                "supported_metrics": metric_labels,
            },
        )

    def get_etf_strategy_comparison(self, entities: dict[str, str]) -> ToolResult:
        code = str(entities.get("code") or "").strip()
        name = str(entities.get("name") or "").strip()
        if self.repository is None:
            return self._etf_comparison_unavailable(code, name, "SQLite Repository 未配置")
        if not code:
            asset = self.repository.resolve_asset(name)
            code = str((asset or {}).get("code") or "")
            name = str((asset or {}).get("name") or name)
        if not code:
            return self._etf_comparison_unavailable(code, name, "没有识别到 ETF 代码")

        rows = self.repository.get_market_history(code, limit=ETF_DUAL_STRATEGY_HISTORY_ROWS)
        if not rows:
            return self._etf_comparison_unavailable(code, name, "SQLite 没有该 ETF 的日频历史")
        if not name:
            name = str(rows[0].get("name") or code)
        params = normalize_etf_config(self._load_strategy_params())
        frame = self._etf_strategy_frame(rows, code, name)
        if frame.empty:
            return self._etf_comparison_unavailable(code, name, "ETF 日频历史缺少开高低收和成交量")

        frame = add_etf_indicators(
            frame,
            "成交量（万股）",
            params["strategy_profiles"]["trend_pullback_v2"]["medium_trend"],
        )
        history = ETFHistory(
            code=code,
            name=name,
            rows=frame,
            as_of=pd.Timestamp(frame.iloc[-1]["date"]),
        )
        dashboard_signal = self._dashboard_etf_signal(code) or {}
        position = ETFPositionState(is_holding=str(dashboard_signal.get("position_status") or "") == "持仓中")
        registry = default_registry()
        decisions = []
        for strategy_id in ("legacy_v1", "trend_pullback_v2"):
            strategy = registry.create(strategy_id)
            decision = strategy.evaluate(history, position, params["strategy_profiles"][strategy_id])
            fields = dict(decision.compatibility_fields)
            decisions.append(
                {
                    "strategy_id": strategy_id,
                    "strategy_version": decision.strategy_version,
                    "display_name": "原策略 v1" if strategy_id == "legacy_v1" else "趋势回踩 2.0",
                    "medium_status": str(decision.medium_status),
                    "short_entry_status": str(decision.short_entry_status),
                    "buy_candidate": bool(decision.buy_candidate),
                    "watch_candidate": bool(decision.watch_candidate),
                    "sell_alert": bool(decision.sell_alert),
                    "score": decision.score,
                    "medium_reason": decision.medium_reason,
                    "short_entry_reason": decision.short_entry_reason,
                    "rule_hits": list(decision.rule_hits),
                    "missing_conditions": list(decision.missing_conditions),
                    "risk_notes": list(decision.risk_notes),
                    "metrics": dict(decision.metrics),
                    "ma20_slope_state": fields.get("ma20_slope_state"),
                    "weekly_macd_state": fields.get("weekly_macd_state"),
                    "daily_macd_state": fields.get("daily_macd_state"),
                    "ma5_above_ma10": fields.get("ma5_above_ma10"),
                    "ma5_crossed_ma10_today": fields.get("ma5_crossed_ma10_today"),
                }
            )
        return ToolResult(
            tool="get_etf_strategy_comparison",
            title="ETF 双策略对照",
            source="sqlite.market_daily_indicators + configs.strategy_params + ETF strategy plugins",
            summary=f"{name}（{code}）使用同一份 {len(frame)} 日历史分别运行原策略 v1 和趋势回踩 2.0。",
            data={
                "available": True,
                "name": name,
                "code": code,
                "as_of": str(pd.Timestamp(frame.iloc[-1]["date"]).date()),
                "history_rows": len(frame),
                "position_status": "持仓中" if position.is_holding else "未持仓/已平仓",
                "decisions": decisions,
            },
        )

    def _etf_strategy_frame(self, rows: list[dict[str, Any]], code: str, name: str) -> pd.DataFrame:
        normalized = []
        for row in reversed(rows):
            payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
            normalized.append(
                {
                    "date": row.get("trade_date"),
                    "code": code,
                    "name": row.get("name") or name,
                    "开盘价": row.get("open"),
                    "最高价": row.get("high"),
                    "最低价": row.get("low"),
                    "收盘价": row.get("close"),
                    "成交量（万股）": row.get("volume"),
                    "份额变化（亿份）": payload.get("fund_share_change"),
                }
            )
        frame = pd.DataFrame(normalized)
        if frame.empty:
            return frame
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        required = ["date", "开盘价", "最高价", "最低价", "收盘价", "成交量（万股）"]
        return frame.dropna(subset=required).drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)

    def _etf_comparison_unavailable(self, code: str, name: str, reason: str) -> ToolResult:
        return ToolResult(
            tool="get_etf_strategy_comparison",
            title="ETF 双策略对照",
            source="sqlite.market_daily_indicators + ETF strategy plugins",
            summary=f"无法完成 {name or code or '该ETF'} 的双策略对照：{reason}。",
            data={"available": False, "name": name, "code": code, "reason": reason, "decisions": []},
        )

    def get_etf_single_asset(self, code: str) -> ToolResult:
        if self.repository is None:
            return ToolResult(
                tool="get_etf_single_asset",
                title="ETF single asset",
                source="dashboard only",
                summary=f"未配置 SQLite Repository，无法按 {code} 查询单标的全量指标。",
                data={},
            )
        dashboard_signal = self._dashboard_etf_signal(code)
        asset = self.repository.resolve_asset(code)
        latest_bar = self.repository.get_latest_market_bar(code) or self.repository.get_etf_latest_bar(code)
        signals = self.repository.get_etf_signals(code, latest_bar.get("trade_date") if latest_bar else None)
        history = self.repository.get_market_history(code, limit=ETF_DETAIL_HISTORY_ROWS) or self.repository.get_etf_history(
            code, limit=ETF_LEGACY_HISTORY_ROWS
        )
        if latest_bar is None:
            summary = f"SQLite 未找到 {code} 的 ETF 日频指标。"
        else:
            summary = (
                f"{latest_bar.get('name', code)} 最新日期 {latest_bar.get('trade_date')}，"
                f"收盘 {latest_bar.get('close')}，MA5 {latest_bar.get('ma5')}，MA10 {latest_bar.get('ma10')}，"
                f"量能倍数 {latest_bar.get('vol_ratio60')}，MACD柱 {latest_bar.get('macd_hist')}。"
            )
        compact_asset = {key: asset.get(key) for key in ("code", "name", "asset_type") if asset and key in asset}
        return ToolResult(
            tool="get_etf_single_asset",
            title="ETF single asset",
            source="dashboard.etf.all_signals + sqlite.asset_master + sqlite.market_daily_indicators + sqlite.etf_daily_signals",
            summary=summary,
            data={
                "asset": compact_asset,
                "dashboard_signal": self._compact_etf_row(dashboard_signal or {}),
                "latest_bar": self._compact_market_row(latest_bar or {}),
                "signals": [self._compact_etf_row(row) for row in signals[:8]],
                "history": [self._compact_market_row(row) for row in history[:ETF_DETAIL_HISTORY_ROWS]],
            },
        )

    def get_tl_state(self) -> ToolResult:
        rows = self.dashboard.get("tlToday", [])
        recent = self.dashboard.get("tlRecent", [])
        history = []
        if self.repository is not None:
            history = self.repository.get_market_history("TL.CFE", limit=TL_BACKEND_HISTORY_ROWS)
        state = rows[0].get("state", "--") if rows else "--"
        return ToolResult(
            tool="get_tl_state",
            title="TL timing",
            source="dashboard.tlToday + dashboard.tlRecent + sqlite.market_daily_indicators",
            summary=f"TL 当前状态 {state}。",
            data={
                "today": [self._compact_tl_row(row) for row in rows[:1]],
                "recent": [self._compact_tl_row(row) for row in recent[:TL_DISPLAY_HISTORY_ROWS]],
                "history": [self._compact_market_row(row) for row in history[:TL_ANALYSIS_HISTORY_ROWS]],
            },
        )

    def get_convertible_top10(self) -> ToolResult:
        cb = self.dashboard.get("convertible_bond") or {}
        rows = cb.get("top10") or self.dashboard.get("cbTop10", [])
        summary = cb.get("summary") or {}
        ranked = self.repository.get_convertible_rankings(limit=CB_RANKING_QUERY_ROWS) if self.repository is not None else []
        raw_rows = self._agent_metric("convertible-bond-agent", "metric_cb_rows")
        candidates = self._agent_metric("convertible-bond-agent", "metric_cb_candidates")
        top10_count = self._agent_metric("convertible-bond-agent", "metric_cb_top10")
        quality_message = summary.get("quality_message") or ""
        return ToolResult(
            tool="get_convertible_top10",
            title="Convertible bond top10",
            source="dashboard.convertible_bond.top10 + sqlite.convertible_bond_snapshots",
            summary=(
                f"可转债原始有效行 {raw_rows if raw_rows is not None else '--'} 条，"
                f"风控后候选 {candidates if candidates is not None else len(ranked)} 条，"
                f"合格Top候选当前 {top10_count if top10_count is not None else len(rows)} 条。"
                f"{quality_message}"
            ),
            data={
                "as_of": (ranked[0].get("report_date") if ranked else self.dashboard.get("reportDate")),
                "raw_rows": raw_rows,
                "ranked_candidates": candidates if candidates is not None else len(ranked),
                "top10_count": top10_count if top10_count is not None else len(rows),
                "database_ranked_count": len(ranked),
                "top10": [self._compact_cb_row(row) for row in rows[:CB_BUCKET_EVIDENCE_ROWS]],
                "qualified": [self._compact_cb_row(row) for row in (cb.get("qualified") or rows)[:CB_BUCKET_EVIDENCE_ROWS]],
                "weak_watch": [self._compact_cb_row(row) for row in (cb.get("weak_watch") or [])[:CB_BUCKET_EVIDENCE_ROWS]],
                "risk_watch": [self._compact_cb_row(row) for row in (cb.get("risk_watch") or [])[:CB_BUCKET_EVIDENCE_ROWS]],
                "summary": summary,
                "analysis_universe": [self._compact_cb_row(row) for row in ranked[:CB_ANALYSIS_UNIVERSE_ROWS]],
            },
        )

    def get_convertible_detail(self, code: str) -> ToolResult:
        dashboard_row = self._dashboard_convertible_row(code)
        source_row = dashboard_row or self._source_convertible_row(code)
        if self.repository is None:
            return ToolResult(
                tool="get_convertible_detail",
                title="Convertible bond detail",
                source="dashboard only",
                summary=self._convertible_detail_summary(code, None, source_row),
                data={"asset": None, "snapshot": None, "dashboard_row": dashboard_row, "source_row": source_row},
            )
        asset = self.repository.resolve_asset(code)
        snapshot = self.repository.get_convertible_snapshot(code)
        summary = self._convertible_detail_summary(code, snapshot, source_row)
        return ToolResult(
            tool="get_convertible_detail",
            title="Convertible bond detail",
            source="sqlite.asset_master + sqlite.convertible_bond_snapshots + dashboard.convertible_bond + configured Wind CB file",
            summary=summary,
            data={"asset": asset, "snapshot": snapshot, "dashboard_row": dashboard_row, "source_row": source_row},
        )

    def get_data_quality(self) -> ToolResult:
        rows = self.dashboard.get("dataQuality", [])
        warn_rows = [row for row in rows if str(row.get("status", "")).upper() not in {"OK", "INFO", "SUCCESS"}]
        return ToolResult(
            tool="get_data_quality",
            title="Data quality",
            source="dashboard.dataQuality + dashboard.sourceManifest",
            summary=f"数据质检 {len(rows)} 项，其中需关注 {len(warn_rows)} 项。",
            data={
                "quality": rows[:DATA_QUALITY_ROWS],
                "total_count": len(rows),
                "warning_count": len(warn_rows),
                "warning_rows": warn_rows[:DATA_QUALITY_ROWS],
                "manifest": self.dashboard.get("sourceManifest", [])[:SOURCE_MANIFEST_ROWS],
            },
        )

    def get_agent_audit(self) -> ToolResult:
        rows = self.dashboard.get("agentAudit", [])
        return ToolResult(
            tool="get_agent_audit",
            title="Agent audit",
            source="dashboard.agentAudit + dashboard.aiCommitteeReviews",
            summary=f"Agent 审计 {len(rows)} 项。",
            data={
                "agent_audit": rows[:AGENT_AUDIT_ROWS],
                "ai_committee": self.dashboard.get("aiCommitteeReviews", [])[:AI_COMMITTEE_ROWS],
            },
        )

    def get_risk_summary(self) -> ToolResult:
        rows = self.dashboard.get("riskSummary", [])
        return ToolResult(
            tool="get_risk_summary",
            title="Risk summary",
            source="dashboard.riskSummary",
            summary=f"风控摘要 {len(rows)} 项。",
            data=rows[:RISK_SUMMARY_ROWS],
        )

    def _compact_etf_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": row.get("name"),
            "code": row.get("code"),
            "position_status": row.get("position_status"),
            "display_action": row.get("display_action") or row.get("action"),
            "score": row.get("score"),
            "close": row.get("close"),
            "share_change": row.get("share_change"),
            "ma5": row.get("ma5"),
            "ma10": row.get("ma10"),
            "ma20": row.get("ma20"),
            "ma60": row.get("ma60"),
            "volume_ratio_60": row.get("vol_ratio60") or row.get("volume_ratio_60"),
            "vol_ratio60": row.get("vol_ratio60") or row.get("volume_ratio_60"),
            "macd_hist": row.get("macd_hist"),
            "dif": row.get("dif") or (row.get("metrics") or {}).get("dif"),
            "dea": row.get("dea") or (row.get("metrics") or {}).get("dea"),
            "metrics": {
                "dif": row.get("dif") or (row.get("metrics") or {}).get("dif"),
                "dea": row.get("dea") or (row.get("metrics") or {}).get("dea"),
            },
            "signal_type": row.get("signal_type"),
            "action": row.get("action"),
            "date": row.get("date") or row.get("trade_date"),
            "reason": row.get("signal_reason") or row.get("reason") or row.get("missing_condition"),
            "signal_reason": row.get("signal_reason") or row.get("reason") or row.get("missing_condition"),
            "missing_condition": row.get("missing_condition"),
            "watch_type": row.get("watch_type"),
            "ma5_ma10_signal": row.get("ma5_ma10_signal"),
            "ma5_ma20_status": row.get("ma5_ma20_status"),
            "volume_check": row.get("volume_check"),
            "strategy_id": row.get("strategy_id"),
            "strategy_version": row.get("strategy_version"),
            "medium_status": row.get("medium_status"),
            "medium_reason": row.get("medium_reason"),
            "short_entry_status": row.get("short_entry_status"),
            "short_entry_reason": row.get("short_entry_reason"),
            "weekly_macd_confirmation_check": row.get("weekly_macd_confirmation_check"),
            "ma20_flat_check": row.get("ma20_flat_check"),
            "risk_overlay_level": row.get("risk_overlay_level"),
            "risk_overlay_summary": row.get("risk_overlay_summary"),
            "risk_overlay_flags": row.get("risk_overlay_flags"),
            "risk_overlay_ma20_state": row.get("risk_overlay_ma20_state"),
            "risk_overlay_weekly_macd_state": row.get("risk_overlay_weekly_macd_state"),
            "risk_notes": row.get("risk_notes"),
        }

    def _compact_cb_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "rank": row.get("rank"),
            "name": row.get("name") or row.get("bond_name"),
            "code": row.get("code") or row.get("bond_code"),
            "qualification": row.get("qualification"),
            "eligible_for_top": row.get("eligible_for_top"),
            "score": row.get("score"),
            "score_grade": row.get("score_grade"),
            "price": row.get("price"),
            "premium_rate": row.get("premium_rate") or row.get("conversion_premium_rate"),
            "ytm": row.get("ytm"),
            "remaining_size": row.get("remaining_size"),
            "risk_level": row.get("risk_level"),
            "reason": row.get("not_top_reason") or row.get("excluded_reason") or row.get("reason") or row.get("rank_reason"),
            "quality_notes": row.get("quality_notes") or row.get("risk_notes"),
            "stock_daily_return": row.get("stock_daily_return"),
            "bond_daily_return": row.get("bond_daily_return"),
            "stock_bond_relative_gap": self._relative_gap(row),
            "conversion_premium_change": row.get("conversion_premium_change"),
            "auxiliary_score": row.get("auxiliary_score", row.get("dynamic_score")),
            "auxiliary_state": row.get("auxiliary_state") or row.get("dynamic_state"),
            "auxiliary_note": row.get("auxiliary_note") or row.get("dynamic_note"),
            "auxiliary_data_quality": row.get("auxiliary_data_quality") or row.get("dynamic_data_quality"),
        }

    def _relative_gap(self, row: dict[str, Any]) -> float | None:
        try:
            stock = row.get("stock_daily_return")
            bond = row.get("bond_daily_return")
            if stock in (None, "") or bond in (None, ""):
                return None
            return round(float(stock) - float(bond), 4)
        except (TypeError, ValueError):
            return None

    def _compact_tl_row(self, row: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "date",
            "name",
            "code",
            "state",
            "display_status",
            "action",
            "buy_signal",
            "attention_signal",
            "no_trade_signal",
            "reason",
            "weekly_macd_condition",
            "weekly_macd_reason",
            "weekly_kdj_threshold_check",
            "weekly_kdj_rebound",
            "daily_macd_condition",
            "daily_macd_reason",
            "daily_kdj_threshold_check",
            "daily_kdj_rebound",
            "fund_share_change_daily",
            "fund_share_daily_level",
            "fund_share_5d_sum",
            "fund_share_5d_valid_days",
            "fund_flow_state",
            "fund_flow_relation",
            "fund_flow_note",
            "fund_flow_data_quality",
            "rule_hits",
            "risk_notes",
        )
        compact = {key: row.get(key) for key in keys if key in row}
        compact.update(
            {
                "close": row.get("close", row.get("收盘价")),
                "ma5": row.get("ma5"),
                "ma10": row.get("ma10"),
                "ma20": row.get("ma20"),
                "ma60": row.get("ma60"),
                "vol_ratio60": row.get("vol_ratio60"),
                "macd_hist": row.get("macd_hist"),
                "kdj_j": row.get("kdj_j"),
                "week_macd_hist": row.get("week_macd_hist"),
                "week_kdj_j": row.get("week_kdj_j"),
                "metrics": row.get("metrics") if isinstance(row.get("metrics"), dict) else {},
            }
        )
        return compact

    def _compact_market_row(self, row: dict[str, Any]) -> dict[str, Any]:
        keys = ("trade_date", "date", "name", "code", "close", "ma5", "ma10", "ma20", "ma60", "vol_ratio60", "macd_hist", "dif", "dea", "kdj_j")
        return {key: row.get(key) for key in keys if key in row}

    def _safe_float(self, value: Any) -> float:
        try:
            if value is None or value == "":
                return float("-inf")
            return float(value)
        except (TypeError, ValueError):
            return float("-inf")

    def _filter_rows(self, rows: list[dict[str, Any]], entities: dict[str, str]) -> list[dict[str, Any]]:
        code = entities.get("code")
        name = entities.get("name")
        if not code and not name:
            return rows
        filtered = []
        for row in rows:
            if code and str(row.get("code", "")).upper() == code.upper():
                filtered.append(row)
            elif name and str(row.get("name", "")) == name:
                filtered.append(row)
        return filtered

    def _dashboard_etf_signal(self, code: str) -> dict[str, Any] | None:
        target = code.upper()
        for row in (self.dashboard.get("etf") or {}).get("all_signals", []):
            if str(row.get("code", "")).upper() == target:
                return row
        for key in ("etfBuyCandidates", "etfSellAlerts", "etfWatchlist"):
            for row in self.dashboard.get(key, []):
                if str(row.get("code", "")).upper() == target:
                    return row
        return None

    def _dashboard_convertible_row(self, code: str) -> dict[str, Any] | None:
        target = str(code or "").strip().upper()
        if not target:
            return None
        cb = self.dashboard.get("convertible_bond") or {}
        buckets = [
            ("qualified", cb.get("qualified") or []),
            ("top10", cb.get("top10") or self.dashboard.get("cbTop10", []) or []),
            ("weak_watch", cb.get("weak_watch") or []),
            ("risk_watch", cb.get("risk_watch") or []),
            (
                "ranked_candidates",
                (cb.get("candidates") or []) + (cb.get("ranked_candidates") or []) + (self.dashboard.get("cbRanked", []) or []),
            ),
            ("excluded", (cb.get("excluded") or []) + (self.dashboard.get("cbExcluded", []) or [])),
        ]
        for bucket, rows in buckets:
            for row in rows:
                row_code = str(row.get("bond_code") or row.get("code") or "").strip().upper()
                if row_code != target:
                    continue
                item = dict(row)
                item.setdefault("qualification", "qualified" if bucket == "top10" else bucket)
                item.setdefault("detail_source", "dashboard")
                return item
        return None

    def _source_convertible_row(self, code: str) -> dict[str, Any] | None:
        root_dir = getattr(self.repository, "root_dir", None)
        if root_dir is None:
            return None
        sources = self._load_data_sources()
        cb_file = sources.get("convertible_bond_file")
        if not cb_file:
            return None
        path = Path(cb_file)
        if not path.is_absolute():
            path = root_dir / path
        if not path.exists():
            return None
        target = str(code or "").strip().upper()
        try:
            cb_data = parse_convertible_bond_excel(path)
            ranked, excluded = rank_convertible_bonds(cb_data, self._load_strategy_params(), include_excluded=True)
        except Exception:
            return None
        for bucket, frame in (("ranked_candidates", ranked), ("excluded", excluded)):
            if frame.empty or "bond_code" not in frame:
                continue
            hits = frame[frame["bond_code"].astype(str).str.upper() == target]
            if hits.empty:
                continue
            item = records(hits.head(1))[0]
            item.setdefault("qualification", "excluded" if bucket == "excluded" else item.get("qualification") or bucket)
            item.setdefault("detail_source", "configured_wind_cb_file")
            return item
        return None

    def _convertible_detail_summary(self, code: str, snapshot: dict[str, Any] | None, row: dict[str, Any] | None) -> str:
        if row:
            name = row.get("bond_name") or row.get("name") or code
            reason = row.get("not_top_reason") or row.get("excluded_reason") or row.get("rank_reason") or "--"
            qualification = row.get("qualification") or "--"
            return (
                f"{name} 当前分层 {qualification}，评分 {row.get('score', '--')}，"
                f"价格 {row.get('price', '--')}，转股溢价率 {row.get('conversion_premium_rate', '--')}，"
                f"YTM {row.get('ytm', '--')}，未入合格Top原因 {reason}。"
            )
        if snapshot:
            payload = snapshot.get("payload_json") or {}
            return (
                f"{snapshot.get('bond_name', code)} 排名 {snapshot.get('rank')}，评分 {snapshot.get('score')}，"
                f"价格 {snapshot.get('price')}，强赎状态 {payload.get('redemption_status', '--')}，"
                f"风险提示 {payload.get('risk_flags', '--')}。"
            )
        return f"当前最新 dashboard、SQLite 和配置的 Wind 可转债文件都没有找到 {code} 的可转债详情。"

    def _agent_metric(self, agent_name: str, metric_name: str) -> Any:
        for row in self.dashboard.get("agentAudit", []) or []:
            if row.get("agent") == agent_name:
                return row.get(metric_name)
        return None
