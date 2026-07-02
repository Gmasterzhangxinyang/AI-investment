---
name: portfolio-state-machine
description: Load customer position records and classify holdings, closed positions, and investable watchlist state.
when_to_use: Use before strategy agents need to distinguish holding versus non-holding assets.
inputs:
  - positions_file
outputs:
  - positions
---

This skill treats holding as customer account holdings, not ETF constituent weights.

