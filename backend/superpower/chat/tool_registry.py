from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from superpower.db import DatabaseRepository

from .schemas import ToolResult
from .tools import ResearchToolbox


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    arguments: dict[str, str]


class ResearchToolRegistry:
    """Explicit read-only tool surface available to the AI planner."""

    MAX_TOOL_CALLS = 5

    SPECS = (
        AgentToolSpec("chat_data_scope", "查询投研问答允许访问的数据范围和单次上限", {}),
        AgentToolSpec("daily_summary", "查询当前日报摘要和信号数量", {}),
        AgentToolSpec("database_inventory", "查询已入库资产数量、名单和数据库状态", {}),
        AgentToolSpec("strategy_contract", "查询当前ETF、TL和可转债的确定性策略规则与参数", {}),
        AgentToolSpec("strategy_diagnostics", "查询ETF两套策略的历史信号诊断汇总；不是完整回测", {}),
        AgentToolSpec(
            "etf_ranking",
            "按当前横截面指标排序全部已入库ETF；指标不明确时应先追问",
            {"metric": "score|close|vol_ratio60|share_change", "direction": "asc|desc", "limit": "1-10"},
        ),
        AgentToolSpec("etf_signals", "查询ETF建仓候选和平仓提示", {"code": "可选ETF代码", "name": "可选ETF名称"}),
        AgentToolSpec("etf_watchlist", "查询ETF关注池和匹配历史", {"code": "可选ETF代码", "name": "可选ETF名称"}),
        AgentToolSpec(
            "etf_single_asset",
            "查询单只ETF最新指标和最近30个交易日；必须提供代码或可解析名称",
            {"code": "ETF代码", "name": "ETF名称"},
        ),
        AgentToolSpec(
            "etf_multi_assets",
            "一次查询2至10只ETF的当前中期趋势、短期入场状态和最新关键指标",
            {"codes": "用|分隔的ETF代码", "names": "用|分隔的ETF名称"},
        ),
        AgentToolSpec(
            "etf_strategy_comparison",
            "用最多400日历史运行单只ETF的原策略和2.0，返回当前判断对照",
            {"code": "ETF代码", "name": "ETF名称"},
        ),
        AgentToolSpec("tl_state", "查询TL当前状态和最近30个交易日历史", {}),
        AgentToolSpec("convertible_rankings", "查询可转债Top10展示和前30只问答分析池", {}),
        AgentToolSpec(
            "convertible_detail",
            "查询指定可转债最新完整快照；必须提供代码或可解析名称",
            {"code": "转债代码", "name": "转债名称"},
        ),
        AgentToolSpec("data_quality", "查询源文件、数据质量和需要处理的问题", {}),
        AgentToolSpec("risk_summary", "查询当前组合风险摘要", {}),
    )

    def __init__(self, toolbox: ResearchToolbox, repository: DatabaseRepository) -> None:
        self.toolbox = toolbox
        self.repository = repository
        self._specs = {item.name: item for item in self.SPECS}

    def public_specs(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.SPECS]

    def has_tool(self, name: str) -> bool:
        return name in self._specs

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        if name not in self._specs:
            raise ValueError(f"未授权的投研工具：{name}")
        args = self._clean_arguments(arguments or {})
        entities = self._resolve_entities(args)

        if name == "chat_data_scope":
            return self.toolbox.get_chat_data_scope()
        if name == "daily_summary":
            return self.toolbox.get_daily_summary()
        if name == "database_inventory":
            return self.toolbox.get_database_inventory()
        if name == "strategy_contract":
            return self.toolbox.get_rule_contract()
        if name == "strategy_diagnostics":
            return self.toolbox.get_strategy_diagnostics()
        if name == "etf_ranking":
            return self.toolbox.get_etf_ranking(self._ranking_arguments(args))
        if name == "etf_signals":
            return self.toolbox.get_etf_signals(entities)
        if name == "etf_watchlist":
            return self.toolbox.get_etf_watchlist(entities)
        if name == "etf_single_asset":
            code = self._required_code(entities, "ETF")
            return self.toolbox.get_etf_single_asset(code)
        if name == "etf_multi_assets":
            codes = args.get("codes") or entities.get("codes") or ""
            if not codes:
                raise ValueError("多ETF查询需要至少两个标的代码")
            return self.toolbox.get_etf_multi_assets(codes)
        if name == "etf_strategy_comparison":
            if not entities.get("code") and not entities.get("name"):
                raise ValueError("ETF双策略对照需要标的名称或代码")
            return self.toolbox.get_etf_strategy_comparison(entities)
        if name == "tl_state":
            return self.toolbox.get_tl_state()
        if name == "convertible_rankings":
            return self.toolbox.get_convertible_top10()
        if name == "convertible_detail":
            code = self._required_code(entities, "CONVERTIBLE")
            return self.toolbox.get_convertible_detail(code)
        if name == "data_quality":
            return self.toolbox.get_data_quality()
        if name == "risk_summary":
            return self.toolbox.get_risk_summary()
        raise ValueError(f"工具尚未实现：{name}")

    def _resolve_entities(self, arguments: dict[str, str]) -> dict[str, str]:
        entities = {key: value for key, value in arguments.items() if key in {"code", "name", "codes", "names"} and value}
        query = entities.get("code") or entities.get("name")
        if not query:
            return entities
        asset = self.repository.resolve_asset(query)
        if asset:
            entities.update(
                {
                    "code": str(asset.get("code") or entities.get("code") or ""),
                    "name": str(asset.get("name") or entities.get("name") or ""),
                    "asset_type": str(asset.get("asset_type") or ""),
                }
            )
        return entities

    def _required_code(self, entities: dict[str, str], asset_type: str) -> str:
        code = str(entities.get("code") or "")
        if not code:
            raise ValueError("没有识别到标的代码")
        actual_type = str(entities.get("asset_type") or "")
        if actual_type and actual_type != asset_type:
            raise ValueError("标的类型与所选工具不匹配")
        return code

    def _ranking_arguments(self, arguments: dict[str, str]) -> dict[str, str]:
        metric = arguments.get("metric", "")
        if metric not in {"score", "close", "vol_ratio60", "share_change"}:
            raise ValueError("ETF排序需要明确且受支持的指标")
        direction = arguments.get("direction", "desc")
        if direction not in {"asc", "desc"}:
            direction = "desc"
        try:
            limit = min(max(int(arguments.get("limit", "3")), 1), 10)
        except ValueError:
            limit = 3
        return {"metric": metric, "direction": direction, "limit": str(limit)}

    def _clean_arguments(self, arguments: dict[str, Any]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key in ("code", "name", "codes", "names", "metric", "direction", "limit"):
            value = arguments.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                cleaned[key] = text[:120]
        return cleaned
