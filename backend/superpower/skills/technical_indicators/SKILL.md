---
name: technical-indicators
description: Calculate MA, MACD, KDJ, 60-day volume ratio, and related deterministic indicators for ETF and TL market data.
when_to_use: Use after data quality passes and before strategy agents run.
inputs:
  - etf_market_raw
  - tl_market_raw
outputs:
  - etf_indicators
  - tl_indicators
---

Indicator calculations must be deterministic and must not use LLM output.

