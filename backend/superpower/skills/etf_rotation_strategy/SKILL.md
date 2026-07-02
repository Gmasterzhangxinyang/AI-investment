---
name: etf-rotation-strategy
description: Generate ETF daily buy candidates, sell alerts, signal reasons, and technical ranking scores.
when_to_use: Use after ETF technical indicators and customer positions are available.
inputs:
  - etf_indicators
  - positions
  - strategy_params
outputs:
  - etf_signal_table
  - etf_buy_candidates
  - etf_sell_alerts
---

Signals are deterministic. Do not use LLM output for buy/sell decisions.

