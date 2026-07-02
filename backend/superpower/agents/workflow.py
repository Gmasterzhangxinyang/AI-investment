from __future__ import annotations

from superpower.runtime.agent import BaseAgent

from .ai_committee_agent import AIResearchCommitteeAgent
from .backtest_agent import BacktestAgent
from .config_agent import ConfigAgent
from .convertible_bond_agent import ConvertibleBondAgent
from .data_agent import DataAgent
from .etf_agent import ETFAgent
from .explanation_agent import ExplanationAgent
from .indicator_agent import IndicatorAgent
from .portfolio_agent import PortfolioAgent
from .qa_agent import QAAgent
from .report_agent import ReportAgent
from .risk_agent import RiskAgent
from .source_agent import SourceArchiveAgent
from .tl_agent import TLAgent


def build_daily_workflow() -> list[BaseAgent]:
    return [
        ConfigAgent(),
        SourceArchiveAgent(),
        DataAgent(),
        PortfolioAgent(),
        QAAgent(),
        IndicatorAgent(),
        ETFAgent(),
        TLAgent(),
        ConvertibleBondAgent(),
        BacktestAgent(),
        RiskAgent(),
        AIResearchCommitteeAgent(),
        ExplanationAgent(),
        ReportAgent(),
    ]
