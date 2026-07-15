# Agent Contracts

The system uses Agents as governance and orchestration units, while Skills hold reusable domain execution logic.

An Agent is responsible for:

- declaring its role and objective
- validating required blackboard artifacts before execution
- invoking one approved Skill or custom loader
- verifying expected output artifacts after execution
- writing its contract, quality gates, metrics, and artifacts into the audit trail

Signals remain deterministic. LLM output can explain results but cannot change signal tables, scores, or risk flags.

## Daily Workflow

| Agent | Role | Skill | Key Outputs |
|---|---|---|---|
| ConfigAgent | 配置治理 Agent | custom | `strategy_params`, `universe`, `model_config`, `delivery` |
| SourceArchiveAgent | 数据源归档 Agent | `source-archive` | `source_manifest`, `source_manifest_path` |
| DataAgent | 数据接入 Agent | `wind-excel-ingestion` | `etf_market_raw`, `tl_market_raw` |
| QAAgent | 数据质量 Agent | `data-quality-gate` | `data_quality_report` |
| IndicatorAgent | 指标计算 Agent | `technical-indicators` | `etf_indicators`, `tl_indicators` |
| PortfolioAgent | 组合状态 Agent | `portfolio-state-machine` | `positions` |
| ETFAgent | ETF 趋势筛选 Agent | `etf-rotation-strategy`（兼容性内部名称） | `etf_signal_table`, `etf_buy_candidates`, `etf_watchlist`, `etf_detail_history`, `etf_sell_alerts` |
| TLAgent | TL 择时 Agent | `tl-timing-strategy` | `tl_today`, `tl_recent` |
| ConvertibleBondAgent | 可转债性价比 Agent | `convertible-bond-ranking` | `cb_ranked`, `cb_top10` |
| BacktestAgent | 历史诊断 Agent | `strategy-backtest` | `backtest_summary`, `backtest_trades` |
| RiskAgent | 组合风控 Agent | `portfolio-risk-control` | `risk_summary` |
| AIResearchCommitteeAgent | 证据复核 Agent | `ai-research-committee` | `ai_committee_reviews` |
| ExplanationAgent | 投研解释 Agent | `research-explanation` | `research_summary` |
| ReportAgent | 报告生产 Agent | `report-generation` | `report_path`, `dashboard_json_path` |

## LLM Boundary

Large-model usage is intentionally limited to the review and language layer.

- When `configs/model_config.json` has `llm_enabled=true`, `ai-research-committee` and `research-explanation` call the configured LLM provider through `tools/llm.py`.
- Current default provider is `openai` through the Responses API; `opencode` remains an optional provider but is not the default product path.
- The chat assistant uses a separate `chat` override in `model_config.json`; the frontend `AI 模型` panel can update the OpenAI chat model and masked key without changing deterministic strategy Agents.
- The model can only write explanatory text based on already generated deterministic signal tables.
- It cannot create new ETF/TL signals, change scores, change TL state, or override QA/risk flags.
- If the API key is missing or the request fails, the system falls back to deterministic commentary and records the reason in Agent Audit.
- All strategy Agents are deterministic. This is intentional: LLM is a reporting/research language layer, not a trading decision engine.

## Interactive Research Agent

The frontend chat has a separate bounded runtime from the daily workflow:

- clear factual questions use deterministic tools and do not need a model call;
- focused explanation uses the configured economy model after deterministic tools assemble evidence;
- cross-asset or ambiguous questions may use `ResearchAgentRuntime`, a bounded ReAct supervisor;
- the supervisor has at most 8 iterations, 5 read-only tool calls, and 2 reflection passes;
- every tool result is checked by `EvidenceAccuracyReviewer` before it can support an answer;
- deep final answers are reviewed again, while all answers pass deterministic output guardrails.

This runtime cannot call refresh, write files, write SQLite, browse the web, access accounts, or place orders.

## Evidence Review Layer

`AIResearchCommitteeAgent` runs constrained review roles when LLM is enabled, and deterministic fallback commentary when it is not. This layer is an evidence review and language layer, not a signal generator.

- DataQAAnalyst: reviews freshness, templates, missing fields, and history length.
- StrategyReviewer: checks whether ETF/TL/convertible-bond outputs are explainable from deterministic rules.
- RiskReviewer: reviews QA warnings, historical-diagnostic limitations, and report risk language.
- ReportWriter: drafts a user-facing conclusion from existing tables only.

These roles can critique and explain, but cannot mutate any context artifacts used by strategy or risk.

## TL Agent Contract

TLAgent enforces the configured rule set:

- red MACD histogram is positive, green MACD histogram is negative
- weekly red bar shortening, green bar lengthening, or red-to-green is no-trade
- weekly red bar lengthening, green bar shortening, or green-to-red is attention
- weekly KDJ condition requires previous 2-week J minimum below 20 and current weekly J above that minimum
- daily KDJ condition requires previous 3-day J minimum below 5 and current daily J above that minimum
- weekly no-trade is a hard veto over daily entry tendency
- TL has no sell signal in phase one

## Audit Behavior

Every Agent result includes:

- role
- objective
- skill
- required inputs
- expected outputs
- quality gates
- decision policy
- runtime metrics
- error trace if failed

The `audit_daily.py` script independently recalculates source data, signals, dashboard values, and report row counts after each daily run.
