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
  - etf_watchlist
  - etf_strategy_run
---

Signals are deterministic. Do not use LLM output for buy/sell decisions.

ETF strategies are plugins selected by `etf.active_strategy`. `legacy_v1` preserves the original rules; `trend_pullback_v2` emits separate medium-trend and short-entry states. Switching an installed strategy requires save + refresh, not code changes. Historical state diagnostics are descriptive and are not an executable P&L backtest.

Current repository default: `trend_pullback_v2`. Do not describe `legacy_v1` as the live default unless the saved configuration explicitly selects it.

The skill ID keeps its historical `etf-rotation-strategy` name for compatibility, but the current product is trend screening and signal ranking, not an automatic portfolio-rotation engine.
