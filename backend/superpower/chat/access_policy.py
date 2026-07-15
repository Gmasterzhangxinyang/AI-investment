from __future__ import annotations

from copy import deepcopy
from typing import Any


ETF_DETAIL_HISTORY_ROWS = 30
ETF_LEGACY_HISTORY_ROWS = 8
ETF_DUAL_STRATEGY_HISTORY_ROWS = 400
ETF_SIGNAL_ROWS_PER_BUCKET = 12
ETF_WATCH_ROWS = 12
ETF_RANKING_OUTPUT_ROWS = 10
ETF_DIAGNOSTIC_ROWS = 60
TL_BACKEND_HISTORY_ROWS = 30
TL_DISPLAY_HISTORY_ROWS = 8
TL_ANALYSIS_HISTORY_ROWS = 30
CB_RANKING_QUERY_ROWS = 30
CB_BUCKET_EVIDENCE_ROWS = 10
CB_ANALYSIS_UNIVERSE_ROWS = 30
DAILY_SUMMARY_ROWS = 24
DATA_QUALITY_ROWS = 50
SOURCE_MANIFEST_ROWS = 20
AGENT_AUDIT_ROWS = 30
AI_COMMITTEE_ROWS = 4
RISK_SUMMARY_ROWS = 20
CHAT_MEMORY_STORED_TURNS = 8
CHAT_MEMORY_PROMPT_TURNS = 4


_POLICY: dict[str, Any] = {
    "version": "1.0",
    "architecture": "白名单只读工具先取数和计算，再把裁剪后的证据包交给 AI；AI 不直接连接数据库。",
    "allowed_sources": [
        "最新 dashboard 日报、ETF/TL/可转债结果和数据质检",
        "SQLite 中已入库的资产档案、ETF/TL 日频行情、可转债快照和运行记录",
        "当前策略参数、策略插件输出和规则说明",
        "当前会话的短期记忆",
    ],
    "denied_sources": [
        "互联网、新闻、行情终端和未入库外部数据",
        "任意本地文件、系统目录和数据库原始 SQL",
        "交易账户、下单接口和写库权限",
        "自行修改策略、评分、排名或交易信号",
    ],
    "limits": {
        "etf_universe": "可扫描当前已入库 ETF 全量；单次排序最多展示10只",
        "etf_detail": f"单只ETF最多向回答提供最近{ETF_DETAIL_HISTORY_ROWS}个交易日",
        "etf_strategy_comparison": f"双策略最多用最近{ETF_DUAL_STRATEGY_HISTORY_ROWS}个交易日计算；AI只看到计算结论，不看到全部原始行",
        "etf_signals": f"建仓、平仓各最多{ETF_SIGNAL_ROWS_PER_BUCKET}条；关注池最多{ETF_WATCH_ROWS}条",
        "etf_diagnostics": f"最多{ETF_DIAGNOSTIC_ROWS}条历史诊断汇总",
        "tl": f"单次问答读取并提供最近{TL_ANALYSIS_HISTORY_ROWS}个交易日；页面展示条数不限制问答分析范围",
        "convertible_bond": f"单次问答读取并提供最多{CB_ANALYSIS_UNIVERSE_ROWS}只精简排序记录；页面仍可只展示Top10",
        "daily_and_quality": f"日报摘要最多{DAILY_SUMMARY_ROWS}项，质检最多{DATA_QUALITY_ROWS}项",
        "memory": f"浏览器只保留最近{CHAT_MEMORY_STORED_TURNS}轮，AI提示最多使用最近{CHAT_MEMORY_PROMPT_TURNS}轮",
    },
}


def chat_access_scope(coverage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the single public contract for chat data permissions and limits."""
    payload = deepcopy(_POLICY)
    payload["coverage"] = coverage or {}
    return payload
