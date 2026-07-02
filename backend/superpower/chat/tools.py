from __future__ import annotations

import json
from typing import Any

from superpower.db import DatabaseRepository

from .schemas import ChatIntent, ToolResult


class ResearchToolbox:
    """Read-only tools exposed to the chat agent."""

    def __init__(self, dashboard: dict[str, Any], repository: DatabaseRepository | None = None) -> None:
        self.dashboard = dashboard
        self.repository = repository

    def collect(self, intent: ChatIntent) -> list[ToolResult]:
        tools: list[ToolResult] = [self.get_daily_summary(), self.get_rule_contract()]
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
                        "把关注池说成买入建议",
                        "把未满足KDJ低位条件说成满足",
                        "承诺收益或保证赚钱",
                    ],
                },
                "strategy_params": params,
                "etf_rules": [
                    "建仓A：未持仓 + MA5今日上穿MA10 + MACD柱较昨日改善 + vol_ratio60达到买入阈值。",
                    "建仓B：未持仓 + DIF今日上穿DEA + MA5高于MA10 + 收盘价高于MA20 + vol_ratio60达到买入阈值。",
                    "MA5高于MA20是增强项，不是替代MA5上穿MA10的硬条件。",
                    "关注池不是买入建议；量能未确认时只能写关注或等待确认。",
                    "平仓只对持仓生效：收盘跌破MA10且放量，或收盘跌破MA5且明显放量。",
                ],
                "tl_rules": [
                    "TL仅输出不做交易、关注交易、建议建仓；不做平仓提示。",
                    "不做交易：周线红柱缩短、绿柱变长，或红转绿阶段。",
                    "关注交易：周线红柱变长、绿柱缩短，或绿转红阶段；日线MACD改善只能作为辅助关注。",
                    "建议建仓：周线关注且近2周J<20后回升，或日线关注且近3日J<5后回升；若周线不做交易硬否决，则不能建仓。",
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
            source="sqlite.asset_master + sqlite.etf_daily_bars + sqlite.etf_daily_signals",
            summary=summary,
            data={"asset": asset, "latest_bar": latest_bar, "signals": signals, "history": history},
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
        rows = self.dashboard.get("cbTop10", [])
        ranked = self.repository.get_convertible_rankings(limit=30) if self.repository is not None else []
        raw_rows = self._agent_metric("convertible-bond-agent", "metric_cb_rows")
        candidates = self._agent_metric("convertible-bond-agent", "metric_cb_candidates")
        top10_count = self._agent_metric("convertible-bond-agent", "metric_cb_top10")
        return ToolResult(
            tool="get_convertible_top10",
            title="Convertible bond top10",
            source="dashboard.cbTop10 + sqlite.convertible_bond_snapshots",
            summary=(
                f"可转债原始有效行 {raw_rows if raw_rows is not None else '--'} 条，"
                f"风控后候选 {candidates if candidates is not None else len(ranked)} 条，"
                f"Top10 当前 {top10_count if top10_count is not None else len(rows)} 条。"
            ),
            data={
                "raw_rows": raw_rows,
                "ranked_candidates": candidates if candidates is not None else len(ranked),
                "top10_count": top10_count if top10_count is not None else len(rows),
                "database_ranked_count": len(ranked),
                "top10": rows[:10],
                "ranked_sample": ranked[:30],
            },
        )

    def get_convertible_detail(self, code: str) -> ToolResult:
        if self.repository is None:
            return ToolResult(
                tool="get_convertible_detail",
                title="Convertible bond detail",
                source="dashboard only",
                summary=f"未配置 SQLite Repository，无法查询 {code} 的可转债详情。",
                data={},
            )
        asset = self.repository.resolve_asset(code)
        snapshot = self.repository.get_convertible_snapshot(code)
        if not snapshot:
            summary = f"SQLite 未找到 {code} 的可转债排序快照。"
        else:
            payload = snapshot.get("payload_json") or {}
            summary = (
                f"{snapshot.get('bond_name', code)} 排名 {snapshot.get('rank')}，评分 {snapshot.get('score')}，"
                f"价格 {snapshot.get('price')}，强赎状态 {payload.get('redemption_status', '--')}，"
                f"风险提示 {payload.get('risk_flags', '--')}。"
            )
        return ToolResult(
            tool="get_convertible_detail",
            title="Convertible bond detail",
            source="sqlite.asset_master + sqlite.convertible_bond_snapshots",
            summary=summary,
            data={"asset": asset, "snapshot": snapshot},
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

    def _agent_metric(self, agent_name: str, metric_name: str) -> Any:
        for row in self.dashboard.get("agentAudit", []) or []:
            if row.get("agent") == agent_name:
                return row.get(metric_name)
        return None
