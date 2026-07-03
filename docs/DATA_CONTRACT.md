# Data Contract

This document describes the source data fields used by ingestion and the normalized fields consumed by strategy, dashboard, SQLite, PDF export, and chat.

## Source Files

Configured paths live in `configs/data_sources.json`:

```text
data/wind/current/01_ETF清单和日频公式.xlsx
data/wind/current/02_TL日频公式.xlsx
data/wind/current/03_可转债数据.xlsx
```

Missing one source Excel must not stop the full workflow. The missing module degrades to empty outputs with data quality warnings. Only a frontend refresh with all configured core source files missing is rejected before starting the CLI.

## ETF Market Data

ETF uses a Wind wide table normalized to one row per `date/code`.

Required normalized fields:

```text
date
name
code
开盘价
收盘价
最低价
最高价
成交量（万股）
```

Optional fields used when present:

```text
成交额（亿元）
成交额(亿元）
份额变化（亿份）
```

The split local template may also include the control sheet `ETF清单和持仓`. When present, these fields are used:

```text
是否纳入
ETF代码
ETF名称
持仓状态
买入日期
持仓数量
备注
```

## TL Market Data

TL uses a Wind wide table normalized to one row per date. `code` and `name` are optional for source data; when absent, downstream TL logic falls back to `TL.CFE` and `30年国债期货TL`.

Required normalized fields:

```text
date
开盘价
收盘价
最低价
最高价
成交量
```

Optional fields:

```text
name
code
成交额（亿元）
成交额(亿元）
持仓量
持仓量变化
```

## Convertible Bonds

Convertible-bond ingestion accepts the split local template or ordinary first-row headers. These fields are used after normalization.

Core required fields:

```text
bond_code
bond_name
price
```

Risk, scoring, and display fields:

```text
enabled
date
remaining_years
conversion_premium_rate
ytm
stock_code
stock_name
deducted_profit_growth
profit_growth_acceleration
profit_growth_23_vs_22
profit_growth_24_vs_23
profit_growth_25_vs_24
latest_half_profit_growth
stock_price
conversion_price
redemption_trigger_ratio
redemption_triggered
redemption_announcement_date
no_redemption_announcement_date
issue_size
remaining_size
unconverted_ratio
maturity_date
bond_rating
sw_l1
sw_l2
deducted_profit_2022
deducted_profit_2023
deducted_profit_2024
deducted_profit_2025
deducted_profit_h1_2025
deducted_profit_h1_2026
maturity_redemption_price
notes
```

Common source aliases include:

```text
转债代码 -> bond_code
转债名称 -> bond_name
转债价格 / 价格 -> price
转股溢价率 -> conversion_premium_rate
到期收益率 -> ytm
债项评级 -> bond_rating
申万一级行业 -> sw_l1
申万二级行业 -> sw_l2
```

## Positions

`configs/positions.csv` or the ETF control sheet can provide position state:

```text
asset_type
code
name
status
entry_date
entry_price
position_size
notes
```

Supported `status` values:

```text
holding
closed
flat
watch
```

## Dashboard Alignment

`outputs/latest/dashboard.json` must keep the stable top-level contract documented in `docs/DASHBOARD_SCHEMA.md`:

```text
run_info
data_quality
etf
tl
convertible_bond
report_summary
```

Every strategy row exposed to the dashboard should carry explainable evidence fields where applicable:

```text
action
reason
metrics
rule_hits
risk_notes
confidence
data_quality
```

Convertible-bond rows additionally carry candidate-quality fields:

```text
qualification
score_grade
eligible_for_top
not_top_reason
quality_notes
```

`convertible_bond.top10` is a compatibility field and must contain only `qualified[:10]`; weak-watch and risk-watch rows are not used to fill the Top table.
