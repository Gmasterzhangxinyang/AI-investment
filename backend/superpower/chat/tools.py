from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from superpower.db import DatabaseRepository
from superpower.skills.convertible_bond_ranking.handler import rank_convertible_bonds
from superpower.tools.excel_reader import parse_convertible_bond_excel
from superpower.tools.frame import records

from .schemas import ChatIntent, ToolResult


class ResearchToolbox:
    """Read-only tools exposed to the chat agent."""

    def __init__(self, dashboard: dict[str, Any], repository: DatabaseRepository | None = None) -> None:
        self.dashboard = dashboard
        self.repository = repository

    def collect(self, intent: ChatIntent) -> list[ToolResult]:
        tools: list[ToolResult] = [
            self.get_daily_summary(),
            self.get_rule_contract(),
            self.get_data_map(),
            self.get_research_snapshot(),
        ]
        if intent.name in {"database_inventory", "asset_list"}:
            tools.append(self.get_database_inventory())
            return tools
        if intent.name in {"etf_entry", "etf_exit", "etf_detail", "daily_report", "risk_review"}:
            tools.extend([self.get_etf_signals(intent.entities), self.get_etf_watchlist(intent.entities)])
        if intent.name == "etf_detail" and intent.entities.get("code"):
            tools.append(self.get_etf_single_asset(intent.entities["code"]))
        if intent.name in {"tl_timing", "daily_report", "risk_review"}:
            tools.append(self.get_tl_state())
        if intent.name in {"convertible_bond", "daily_report"}:
            tools.append(self.get_convertible_top10())
        if intent.name == "convertible_bond" and intent.entities.get("code"):
            tools.append(self.get_convertible_detail(intent.entities["code"]))
        if intent.name in {"data_quality", "daily_report", "risk_review"}:
            tools.append(self.get_data_quality())
        if intent.name in {"agent_audit", "daily_report"}:
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
        return ToolResult(
            tool="get_rule_contract",
            title="Rule contract",
            source="configs.strategy_params + deterministic strategy handlers",
            summary=(
                "交易信号由确定性规则生成；LLM 只能解释证据。"
                f" ETF买入量能阈值 {params.get('etf', {}).get('buy_volume_ratio_min', '--')}，"
                f"TL周线J阈值 {params.get('tl', {}).get('weekly_j_low_threshold', '--')}，"
                f"TL日线J阈值 {params.get('tl', {}).get('daily_j_low_threshold', '--')}。"
            ),
            data={
                "policy": {
                    "signal_owner": "deterministic_code_only",
                    "llm_permission": "explain_only",
                    "llm_forbidden": [
                        "新增交易信号",
                        "把关注池说成建仓候选",
                        "把未满足KDJ低位条件说成满足",
                        "承诺收益或保证赚钱",
                    ],
                },
                "strategy_params": params,
                "etf_rules": [
                    "建仓A：未持仓 + MA5今日上穿MA10 + MACD柱较昨日改善 + vol_ratio60达到买入阈值。",
                    "建仓B：未持仓 + DIF今日上穿DEA + MA5高于MA10 + 收盘价高于MA20 + vol_ratio60达到买入阈值。",
                    "MA5高于MA20是增强项，不是替代MA5上穿MA10的硬条件。",
                    "关注池不是建仓候选；量能未确认时只能写关注或等待确认。",
                    "平仓只对持仓生效：收盘跌破MA10且放量，或收盘跌破MA5且明显放量。",
                ],
                "tl_rules": [
                    "TL仅输出不做交易、关注交易、模型触发建仓候选；不做平仓提示。",
                    "不做交易：周线红柱缩短、绿柱变长，或红转绿阶段。",
                    "关注交易：周线红柱变长、绿柱缩短，或绿转红阶段；日线MACD改善只能作为辅助关注。",
                    "模型触发建仓候选：周线关注且近2周J<20后回升，或日线关注且近3日J<5后回升；若周线不做交易硬否决，则不能建仓。",
                ],
                "convertible_bond_rules": [
                    "先做风控排除，再做综合打分；100元以下、140元及以上、已发强赎公告、正股ST、A/A-及以下评级、高YTM异常等默认不进入正常排序；A+保留为中风险观察。",
                    "负YTM、高转股溢价率、极端业绩增速、利润基数异常必须按配置扣分或硬排除；默认50%以上转股溢价率和-5%以下YTM不进入普通Top10，不能只按单一高增长指标解释为优质。",
                    "强赎状态必须区分：未触发、触发但有不强赎公告、触发且未见有效公告、已发强赎公告。",
                    "综合打分字段包括截尾后的基本面增长、转股溢价率质量、到期收益率质量、剩余期限、信用评级、强赎状态、存续规模、未转股比例和行业分散。",
                    "AI只能解释代码给出的rank、score、risk_flags和rank_reason，不得新增候选或按主观理解改排名。",
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
            data=rows[:24],
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
            "buy_candidates": self._filter_rows(self.dashboard.get("etfBuyCandidates", []), entities),
            "sell_alerts": self._filter_rows(self.dashboard.get("etfSellAlerts", []), entities),
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
            data={"watchlist": rows[:20], "history": history[-30:]},
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
        history = self.repository.get_market_history(code, limit=30) or self.repository.get_etf_history(code, limit=8)
        if latest_bar is None:
            summary = f"SQLite 未找到 {code} 的 ETF 日频指标。"
        else:
            summary = (
                f"{latest_bar.get('name', code)} 最新日期 {latest_bar.get('trade_date')}，"
                f"收盘 {latest_bar.get('close')}，MA5 {latest_bar.get('ma5')}，MA10 {latest_bar.get('ma10')}，"
                f"量能倍数 {latest_bar.get('vol_ratio60')}，MACD柱 {latest_bar.get('macd_hist')}。"
            )
        return ToolResult(
            tool="get_etf_single_asset",
            title="ETF single asset",
            source="dashboard.etf.all_signals + sqlite.asset_master + sqlite.market_daily_indicators + sqlite.etf_daily_signals",
            summary=summary,
            data={"asset": asset, "dashboard_signal": dashboard_signal, "latest_bar": latest_bar, "signals": signals, "history": history},
        )

    def get_tl_state(self) -> ToolResult:
        rows = self.dashboard.get("tlToday", [])
        recent = self.dashboard.get("tlRecent", [])
        history = []
        if self.repository is not None:
            history = self.repository.get_market_history("TL.CFE", limit=30)
        state = rows[0].get("state", "--") if rows else "--"
        return ToolResult(
            tool="get_tl_state",
            title="TL timing",
            source="dashboard.tlToday + dashboard.tlRecent + sqlite.market_daily_indicators",
            summary=f"TL 当前状态 {state}。",
            data={"today": rows[:2], "recent": recent[:12], "history": history},
        )

    def get_convertible_top10(self) -> ToolResult:
        cb = self.dashboard.get("convertible_bond") or {}
        rows = cb.get("top10") or self.dashboard.get("cbTop10", [])
        summary = cb.get("summary") or {}
        ranked = self.repository.get_convertible_rankings(limit=30) if self.repository is not None else []
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
                "raw_rows": raw_rows,
                "ranked_candidates": candidates if candidates is not None else len(ranked),
                "top10_count": top10_count if top10_count is not None else len(rows),
                "database_ranked_count": len(ranked),
                "top10": rows[:10],
                "qualified": cb.get("qualified") or rows[:10],
                "weak_watch": cb.get("weak_watch") or [],
                "risk_watch": cb.get("risk_watch") or [],
                "summary": summary,
                "ranked_sample": ranked[:30],
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
            data={"quality": rows[:50], "manifest": self.dashboard.get("sourceManifest", [])[:20]},
        )

    def get_agent_audit(self) -> ToolResult:
        rows = self.dashboard.get("agentAudit", [])
        return ToolResult(
            tool="get_agent_audit",
            title="Agent audit",
            source="dashboard.agentAudit + dashboard.aiCommitteeReviews",
            summary=f"Agent 审计 {len(rows)} 项。",
            data={"agent_audit": rows[:30], "ai_committee": self.dashboard.get("aiCommitteeReviews", [])[:4]},
        )

    def get_risk_summary(self) -> ToolResult:
        rows = self.dashboard.get("riskSummary", [])
        return ToolResult(
            tool="get_risk_summary",
            title="Risk summary",
            source="dashboard.riskSummary",
            summary=f"风控摘要 {len(rows)} 项。",
            data=rows[:20],
        )

    def _compact_etf_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": row.get("name"),
            "code": row.get("code"),
            "position_status": row.get("position_status"),
            "display_action": row.get("display_action") or row.get("action"),
            "score": row.get("score"),
            "close": row.get("close"),
            "ma5": row.get("ma5"),
            "ma10": row.get("ma10"),
            "ma20": row.get("ma20"),
            "volume_ratio_60": row.get("vol_ratio60") or row.get("volume_ratio_60"),
            "macd_hist": row.get("macd_hist"),
            "reason": row.get("signal_reason") or row.get("reason") or row.get("missing_condition"),
        }

    def _compact_cb_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
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
        }

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
