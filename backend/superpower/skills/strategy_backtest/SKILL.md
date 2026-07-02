---
name: strategy-backtest
description: Run deterministic ETF/TL strategy diagnostics on the currently available historical data.
when_to_use: Use after indicators and strategy params are ready to quantify signal frequency and basic trade outcomes.
inputs:
  - etf_indicators
  - tl_indicators
  - strategy_params
outputs:
  - backtest_summary
  - backtest_trades
---

This is a production-safety diagnostic, not a promise of future returns. It uses
next-trading-day open prices after signal-day close to avoid look-ahead bias.
