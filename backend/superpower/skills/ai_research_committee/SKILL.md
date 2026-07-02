---
name: ai-research-committee
description: Run a constrained LLM research committee over deterministic signals, QA, backtest, and risk outputs.
when_to_use: Use after strategy, backtest, and risk agents have produced deterministic artifacts.
inputs:
  - data_quality_report
  - etf_buy_candidates
  - etf_watchlist
  - etf_sell_alerts
  - tl_today
  - cb_top10
  - backtest_summary
  - risk_summary
  - model_config
outputs:
  - ai_committee_reviews
---

The committee can critique, explain, and flag review items, but cannot mutate
signals, scores, risk flags, or source data. When the OpenAI API key is missing,
it emits deterministic fallback reviews with explicit disclosure.
