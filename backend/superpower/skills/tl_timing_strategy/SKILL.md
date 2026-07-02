---
name: tl-timing-strategy
description: Classify TL daily status as no-trade, attention, or build-position using MACD and KDJ.
when_to_use: Use after TL technical indicators are available.
inputs:
  - tl_indicators
  - strategy_params
outputs:
  - tl_today
  - tl_recent
---

TL 60-minute logic is intentionally out of scope for phase one.

