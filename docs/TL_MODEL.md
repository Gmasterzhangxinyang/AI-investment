# TL 判断逻辑、模型与公式

本文档描述当前系统 30 年国债期货 TL 板块的日频择时规则。TL 当前只做建仓状态诊断，不做平仓提示，也不模拟完整收益。

## 1. 输入数据

TL 模块读取 Wind Excel 中的日频行情。

必要字段：

- 日期
- 合约代码
- 合约名称
- 开盘价
- 最高价
- 最低价
- 收盘价
- 成交量

当前版本不处理 60 分钟数据。若后续客户提供 60 分钟 Wind 数据，可以复用指标层，但需要新增分钟级数据解析、交易时段过滤和分钟级回测。

## 2. 基础指标公式

TL 使用与 ETF 相同的技术指标函数。

### 2.1 均线

```text
MA_N(t) = mean(Close(t-N+1), ..., Close(t))
```

当前计算：

- `MA5`
- `MA10`
- `MA20`
- `MA60`

### 2.2 MACD

```text
EMA12(t) = EMA(Close, span=12)
EMA26(t) = EMA(Close, span=26)
DIF(t) = EMA12(t) - EMA26(t)
DEA(t) = EMA(DIF, span=9)
MACDHist(t) = DIF(t) - DEA(t)
```

系统使用 `MACDHist = DIF - DEA`，不乘以 2。

### 2.3 KDJ

```text
Low9(t) = min(Low(t-8), ..., Low(t))
High9(t) = max(High(t-8), ..., High(t))
RSV(t) = (Close(t) - Low9(t)) / (High9(t) - Low9(t)) * 100
```

```text
K(t) = 2/3 * K(t-1) + 1/3 * RSV(t)
D(t) = 2/3 * D(t-1) + 1/3 * K(t)
J(t) = 3 * K(t) - 2 * D(t)
```

初始值：

```text
K(0) = 50
D(0) = 50
```

## 3. 周线转换

系统会在每个日频 T 日，用截至 T 日的历史数据重新聚合周线，避免使用未来周线数据。

周线聚合规则：

```text
WeekOpen = first(Open)
WeekHigh = max(High)
WeekLow = min(Low)
WeekClose = last(Close)
WeekVolume = sum(Volume)
```

周频周期：

```text
W-FRI
```

即按周五作为周线结束日。

## 4. MACD 柱判断

设：

```text
Hist(t) = MACDHist(t)
Hist(t-1) = MACDHist(t-1)
Delta(t) = Hist(t) - Hist(t-1)
```

当前参数：

```text
macd_hist_min_delta = 0
```

### 4.1 不做交易条件

红转绿：

```text
Hist(t-1) > 0
Hist(t) < 0
```

输出：

```text
红转绿阶段
```

红柱缩短：

```text
Delta(t) < 0
Hist(t-1) > 0
Hist(t) > 0
```

输出：

```text
红柱T日短于T-1日
```

绿柱变长：

```text
Delta(t) < 0
Hist(t-1) <= 0
Hist(t) < 0
```

输出：

```text
绿柱T日长于T-1日
```

其他走弱：

```text
Delta(t) < 0
```

输出：

```text
MACD柱走弱
```

### 4.2 开始关注条件

绿柱缩短：

```text
Delta(t) > 0
Hist(t-1) < 0
Hist(t) < 0
```

输出：

```text
绿柱T日短于T-1日
```

绿转红：

```text
Delta(t) > 0
Hist(t-1) < 0
Hist(t) >= 0
```

输出：

```text
绿转红阶段
```

红柱变长：

```text
Delta(t) > 0
Hist(t-1) >= 0
Hist(t) > 0
```

输出：

```text
红柱T日长于T-1日
```

其他改善：

```text
Delta(t) > 0
```

输出：

```text
MACD柱改善
```

## 5. KDJ 低位反弹判断

### 5.1 周线 KDJ

当前参数：

```text
weekly_kdj_lookback = 2
weekly_j_low_threshold = 20
```

系统取当前周之前近 2 周 J 值最低值：

```text
WeeklyLowJ(t) = min(J(week t-2), J(week t-1))
```

周线 KDJ 反弹成立：

```text
WeeklyLowJ(t) < 20
CurrentWeekJ(t) > WeeklyLowJ(t)
```

输出示例：

```text
周线近2周J值最低值：71.7775，未低于20，KDJ低位反弹条件不满足
```

### 5.2 日线 KDJ

当前参数：

```text
daily_kdj_lookback = 3
daily_j_low_threshold = 5
```

系统取 T 日之前近 3 个交易日 J 值最低值：

```text
DailyLowJ(t) = min(J(t-3), J(t-2), J(t-1))
```

日线 KDJ 反弹成立：

```text
DailyLowJ(t) < 5
J(t) > DailyLowJ(t)
```

## 6. TL 状态模型

### 6.1 周线关注

```text
attention_week = weekly_macd_condition == "attention"
```

### 6.2 周线不做交易

```text
no_trade_week = weekly_macd_condition == "no_trade"
```

### 6.3 日线关注

```text
daily_attention = daily_macd_condition == "attention"
```

### 6.4 原始建仓信号

满足周线关注且周线 KDJ 低位反弹：

```text
attention_week == True
weekly_kdj_rebound == True
```

或满足日线关注且日线 KDJ 低位反弹：

```text
daily_attention == True
daily_kdj_rebound == True
```

因此：

```text
raw_buy_signal =
  (attention_week and weekly_kdj_rebound)
  or (daily_attention and daily_kdj_rebound)
```

### 6.5 周线硬否决

当前参数：

```text
weekly_no_trade_hard_veto = true
```

如果周线满足不做交易，则即使日线出现反弹，也不升级为建议建仓：

```text
buy_signal = raw_buy_signal and not no_trade_week
```

如果关闭该参数：

```text
buy_signal = raw_buy_signal
```

### 6.6 最终状态

```text
if buy_signal:
    state = "建议建仓"
elif no_trade_week and not buy_signal:
    state = "不做交易"
elif attention_week or daily_attention:
    state = "关注交易"
else:
    state = "中性"
```

## 7. 输出结果

TL 页面输出：

- 今日状态
- 近期 20 日状态
- 日线 MACD 判断
- 日线 KDJ 判断
- 周线 MACD 判断
- 周线 KDJ 判断
- 历史状态诊断摘要

主要字段：

- `state`
- `macd_hist`
- `kdj_j`
- `week_macd_hist`
- `week_kdj_j`
- `daily_macd_reason`
- `daily_kdj_threshold_check`
- `weekly_macd_reason`
- `weekly_kdj_threshold_check`
- `buy_signal`
- `attention_signal`
- `no_trade_signal`

## 8. 当前边界

- 当前版本只做日频 TL，不做 60 分钟频率。
- 当前版本只做建仓状态提示，不做平仓提示。
- 当前版本不模拟 TL 收益，因为客户规则没有给出完整平仓条件。
- 周线 MACD 柱需要收盘后才能最终定长短；盘中只能作为观察，不应作为最终信号。
- TL 状态是规则诊断，不等同于收益保证。

