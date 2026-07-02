# Data Contract

## ETF market data

Required fields:

```text
date
name
code
开盘价
收盘价
最低价
最高价
成交量（万股）
成交额(亿元）
份额变化（亿份）
```

## TL market data

Required fields:

```text
date
name
code
开盘价
收盘价
最低价
最高价
成交量
成交额(亿元）
持仓量
持仓量变化
```

## Positions

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

`status` values:

```text
holding
closed
watch
```

## Convertible bonds, phase two

```text
date
bond_code
bond_name
price
premium_rate
ytm
remaining_years
stock_code
stock_name
deducted_np_growth
```

