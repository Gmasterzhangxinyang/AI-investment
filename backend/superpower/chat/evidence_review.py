from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .schemas import ToolResult


@dataclass(frozen=True)
class EvidenceReview:
    passed: bool
    issues: list[str]
    warnings: list[str]
    reviewed_tools: list[str]

    def as_tool_result(self) -> ToolResult:
        status = "通过" if self.passed else "未通过"
        return ToolResult(
            tool="evidence_accuracy_review",
            title="数据准确性审查",
            source="backend deterministic evidence verifier",
            summary=f"数据准确性审查{status}：阻断问题 {len(self.issues)} 项，提醒 {len(self.warnings)} 项。",
            data={
                "passed": self.passed,
                "issues": self.issues,
                "warnings": self.warnings,
                "reviewed_tools": self.reviewed_tools,
            },
        )


class EvidenceAccuracyReviewer:
    """Deterministic checks applied after tool execution and before any AI answer."""

    def review(self, tools: list[ToolResult], requested_tools: list[str], report_date: str) -> EvidenceReview:
        issues: list[str] = []
        warnings: list[str] = []
        reviewed = [tool.tool for tool in tools]

        if requested_tools and not tools:
            issues.append("规划了数据工具，但没有返回任何证据")
        for tool in tools:
            if not tool.source.strip():
                issues.append(f"{tool.tool} 缺少数据来源")
            if not tool.summary.strip():
                warnings.append(f"{tool.tool} 缺少摘要")
            self._review_tool(tool, issues, warnings, report_date)
        self._cross_check_signals(tools, issues, warnings)

        return EvidenceReview(not issues, self._deduplicate(issues), self._deduplicate(warnings), reviewed)

    def _review_tool(self, tool: ToolResult, issues: list[str], warnings: list[str], report_date: str) -> None:
        data = tool.data if isinstance(tool.data, dict) else {}
        if tool.tool == "get_etf_ranking":
            if not data.get("metric"):
                issues.append("ETF排序缺少评价指标")
            self._check_unique_codes(data.get("rows") or [], "ETF排序", issues)
            if data.get("metric") and not data.get("rows"):
                issues.append("ETF排序没有有效结果")
            if len(data.get("rows") or []) > 10:
                issues.append("ETF排序超过单次10只展示上限")
            if any(row.get("metric_value") is None for row in data.get("rows") or [] if isinstance(row, dict)):
                issues.append("ETF排序存在空指标值")
        elif tool.tool == "get_rule_contract":
            if not isinstance(data.get("etf_strategy"), dict):
                issues.append("策略规则缺少ETF策略身份")
        elif tool.tool == "get_strategy_diagnostics":
            rows = data.get("rows") or []
            if len(rows) > 60:
                issues.append("ETF历史诊断超过60条授权上限")
            allowed_horizons = {1, 3, 5, 10, 20}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                horizon = row.get("horizon")
                if horizon is not None:
                    try:
                        valid_horizon = int(horizon) in allowed_horizons
                    except (TypeError, ValueError):
                        valid_horizon = False
                    if not valid_horizon:
                        issues.append("ETF历史诊断包含未授权观察周期")
                        break
        elif tool.tool == "get_etf_signals":
            self._check_unique_codes(data.get("buy_candidates") or [], "ETF建仓候选", issues)
            self._check_unique_codes(data.get("sell_alerts") or [], "ETF平仓提示", issues)
        elif tool.tool == "get_etf_watchlist":
            self._check_unique_codes(data.get("watchlist") or [], "ETF关注池", issues)
        elif tool.tool == "get_etf_single_asset":
            latest = data.get("latest_bar") if isinstance(data.get("latest_bar"), dict) else {}
            if not latest:
                issues.append("单只ETF缺少最新行情")
            self._check_unique_dates(data.get("history") or [], "ETF历史", issues)
            self._check_freshness(latest.get("trade_date"), report_date, "ETF行情", warnings)
        elif tool.tool == "get_etf_strategy_comparison":
            if not data.get("available"):
                issues.append(str(data.get("reason") or "ETF双策略数据不可用"))
            decisions = data.get("decisions") or []
            if data.get("available") and {row.get("strategy_id") for row in decisions} != {"legacy_v1", "trend_pullback_v2"}:
                issues.append("ETF双策略结果不完整")
            self._check_freshness(data.get("as_of"), report_date, "ETF双策略历史", warnings)
        elif tool.tool == "get_tl_state":
            history = data.get("history") or []
            if not data.get("today") and not history:
                issues.append("TL缺少当前状态和历史数据")
            self._check_unique_dates(history, "TL历史", issues)
            if len(history) > 30:
                issues.append("TL问答证据超过30日授权上限")
            if history:
                self._check_freshness(history[0].get("trade_date"), report_date, "TL行情", warnings)
        elif tool.tool == "get_convertible_top10":
            universe = data.get("analysis_universe") or []
            if not universe:
                issues.append("可转债分析池为空")
            if len(universe) > 30:
                issues.append("可转债问答证据超过30只授权上限")
            self._check_unique_codes(universe, "可转债分析池", issues)
            ranks = [row.get("rank") for row in universe if isinstance(row, dict) and row.get("rank") is not None]
            if len(ranks) != len(set(ranks)):
                issues.append("可转债分析池存在重复排名")
            self._check_freshness(data.get("as_of"), report_date, "可转债快照", warnings)
        elif tool.tool == "get_convertible_detail":
            if not any(data.get(key) for key in ("snapshot", "dashboard_row", "source_row")):
                issues.append("指定可转债缺少有效快照")
        elif tool.tool == "get_database_inventory":
            counts = data.get("assetCounts") if isinstance(data.get("assetCounts"), dict) else {}
            if not counts or sum(int(value or 0) for value in counts.values()) <= 0:
                issues.append("数据库资产清单为空")
        elif tool.tool == "get_daily_summary" and not tool.data:
            warnings.append("当前日报摘要为空")
        elif tool.tool == "get_data_quality":
            quality = data.get("quality") or []
            attention = [row for row in quality if str(row.get("status", "")).upper() not in {"OK", "INFO", "SUCCESS"}]
            if attention:
                warnings.append(f"数据质检仍有{len(attention)}项需要关注")

    def _cross_check_signals(self, tools: list[ToolResult], issues: list[str], warnings: list[str]) -> None:
        signal_tool = next((tool for tool in tools if tool.tool == "get_etf_signals" and isinstance(tool.data, dict)), None)
        watch_tool = next((tool for tool in tools if tool.tool == "get_etf_watchlist" and isinstance(tool.data, dict)), None)
        if not signal_tool:
            return
        buys = {str(row.get("code") or "") for row in signal_tool.data.get("buy_candidates", []) if isinstance(row, dict)}
        sells = {str(row.get("code") or "") for row in signal_tool.data.get("sell_alerts", []) if isinstance(row, dict)}
        overlap = (buys & sells) - {""}
        if overlap:
            issues.append("同一ETF同时出现在建仓候选和平仓提示")
        if watch_tool:
            watches = {str(row.get("code") or "") for row in watch_tool.data.get("watchlist", []) if isinstance(row, dict)}
            if (buys & watches) - {""}:
                warnings.append("部分ETF同时出现在建仓候选和关注池，请复核信号分桶")

    def _check_unique_codes(self, rows: list[Any], label: str, issues: list[str]) -> None:
        codes = [str(row.get("code") or row.get("bond_code") or "") for row in rows if isinstance(row, dict)]
        codes = [code for code in codes if code]
        if len(codes) != len(set(codes)):
            issues.append(f"{label}存在重复代码")

    def _check_unique_dates(self, rows: list[Any], label: str, issues: list[str]) -> None:
        dates = [str(row.get("trade_date") or row.get("date") or "") for row in rows if isinstance(row, dict)]
        dates = [value for value in dates if value]
        if len(dates) != len(set(dates)):
            issues.append(f"{label}存在重复日期")

    def _check_freshness(self, value: Any, report_date: str, label: str, warnings: list[str]) -> None:
        observed = self._parse_date(value)
        expected = self._parse_date(report_date)
        if not observed or not expected:
            return
        lag = (expected - observed).days
        if lag > 7:
            warnings.append(f"{label}比报告日期滞后{lag}天")
        elif lag < 0:
            warnings.append(f"{label}日期晚于报告日期")

    def _parse_date(self, value: Any) -> date | None:
        text = str(value or "").strip()[:10]
        for pattern in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    def _deduplicate(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))
