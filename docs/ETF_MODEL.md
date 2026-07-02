# ETF 判断逻辑、模型与公式

本文档描述当前系统 ETF 板块的确定性规则。ETF 信号由代码生成，AI 只负责解释证据，不参与新增标的、修改信号或承诺收益。

## 1. 输入数据

ETF 模块读取 Wind Excel 中的日频宽表，并标准化为逐日逐标的行情。

必要字段：

- 日期
- ETF 代码
- ETF 名称
- 开盘价
- 最高价
- 最低价
- 收盘价
- 成交量（万股）
- 成交额（亿元），如模板提供
- 份额变化（亿份），如模板提供

客户持仓状态来自 ETF 控制表或 `configs/positions.csv`：

- `holding`：客户当前持有，系统才允许给出平仓提示。
- `closed` / `flat` / `watch`：不再给平仓提示，重新进入建仓筛选或关注池。

## 2. 基础指标公式

### 2.1 均线

对每只 ETF 按日期升序计算：

```text
MA_N(t) = mean(Close(t-N+1), ..., Close(t))
```

当前使用：

- `MA5`
- `MA10`
- `MA20`
- `MA60`

### 2.2 成交量倍数

系统使用前 60 个交易日均量作为基准，并且为了避免当日成交量污染均量，基准均量会向前移动 1 日：

```text
VolMA60(t) = mean(Volume(t-60), ..., Volume(t-1))
VolRatio60(t) = Volume(t) / VolMA60(t)
```

代码实现中 `VolMA60` 使用 `volume.shift(1).rolling(60, min_periods=20).mean()`，因此在历史不足 60 日但已有 20 日以上时也可以给出初步量能判断。

### 2.3 MACD

```text
EMA12(t) = EMA(Close, span=12)
EMA26(t) = EMA(Close, span=26)
DIF(t) = EMA12(t) - EMA26(t)
DEA(t) = EMA(DIF, span=9)
MACDHist(t) = DIF(t) - DEA(t)
```

当前系统使用的是 `DIF - DEA` 作为 MACD 柱，不乘以 2。

### 2.4 KDJ

```text
Low9(t) = min(Low(t-8), ..., Low(t))
High9(t) = max(High(t-8), ..., High(t))
RSV(t) = (Close(t) - Low9(t)) / (High9(t) - Low9(t)) * 100
```

初始：

```text
K(0) = 50
D(0) = 50
```

递推：

```text
K(t) = 2/3 * K(t-1) + 1/3 * RSV(t)
D(t) = 2/3 * D(t-1) + 1/3 * K(t)
J(t) = 3 * K(t) - 2 * D(t)
```

ETF 当前主要使用 MA、MACD、量能，KDJ 主要进入标的详情展示。

## 3. 建仓判断

建仓信号在 T 日收盘后生成。若产生信号，回测成交价使用 T+1 开盘价。

当前有两类建仓触发。

### 3.1 均线上穿类建仓

条件：

```text
MA5(t-1) <= MA10(t-1)
MA5(t) > MA10(t)
MACDHist(t) > MACDHist(t-1)
VolRatio60(t) >= BuyVolumeThreshold
```

默认：

```text
BuyVolumeThreshold = 1.1
```

如果同时满足：

```text
MA5(t) > MA20(t)
```

系统会在触发原因中增加：

```text
MA5同时高于MA20（增强项）
```

注意：`MA5 > MA20` 不是硬条件，只是增强项。

### 3.2 MACD 金叉类建仓

条件：

```text
DIF(t-1) <= DEA(t-1)
DIF(t) > DEA(t)
MA5(t) > MA10(t)
Close(t) > MA20(t)
VolRatio60(t) >= BuyVolumeThreshold
```

触发原因：

```text
MACD金叉
```

## 4. 平仓判断

平仓信号在 T 日收盘后生成。只有客户状态为 `holding` 的 ETF 才会输出平仓提示。

### 4.1 跌破 MA10 平仓

```text
Close(t) < MA10(t)
VolRatio60(t) >= SellMA10VolumeThreshold
```

默认：

```text
SellMA10VolumeThreshold = 1.2
```

触发原因：

```text
收盘跌破MA10且放量
```

### 4.2 跌破 MA5 平仓

```text
Close(t) < MA5(t)
VolRatio60(t) >= SellMA5VolumeThreshold
```

默认：

```text
SellMA5VolumeThreshold = 1.5
```

触发原因：

```text
收盘跌破MA5且明显放量
```

## 5. 关注池判断

关注池不是买入建议。它用于展示“接近触发但尚未满足完整建仓条件”的 ETF。

### 5.1 均线已触发，量能未确认

```text
MA5(t-1) <= MA10(t-1)
MA5(t) > MA10(t)
MACDHist(t) > MACDHist(t-1)
VolRatio60(t) < BuyVolumeThreshold
```

动作：

```text
关注，等待放量确认
```

### 5.2 MACD 接近确认，量能未确认

```text
Gap(t) = DIF(t) - DEA(t)
Gap(t-1) = DIF(t-1) - DEA(t-1)
Gap(t) < 0
Gap(t) > Gap(t-1)
Close(t) > MA20(t)
VolRatio60(t) < BuyVolumeThreshold
```

动作：

```text
关注，等待MACD金叉与量能确认
```

### 5.3 趋势改善，量能未确认

```text
MA5(t) > MA10(t)
Close(t) > MA20(t)
MACDHist(t) > MACDHist(t-1)
VolRatio60(t) < BuyVolumeThreshold
```

动作：

```text
跟踪，不追高，等待再次放量
```

## 6. ETF 评分模型

ETF 评分用于排序，不单独决定建仓。建仓必须先满足规则条件。

当前权重：

```text
TrendWeight = 0.35
MACDWeight = 0.25
VolumeWeight = 0.25
ShareChangeWeight = 0.15
```

总分：

```text
ETFScore =
  TrendScore * TrendWeight
  + MACDScore * MACDWeight
  + VolumeScore * VolumeWeight
  + ShareChangeScore * ShareChangeWeight
```

### 6.1 趋势分

```text
TrendScore = 0
if MA5 > MA10: TrendScore += 50
if Close > MA20: TrendScore += 30
if Close > MA60: TrendScore += 20
```

### 6.2 MACD 分

```text
MACDScore = 50 + clip(MACDHist * 3000, -50, 50)
```

取值范围：

```text
0 <= MACDScore <= 100
```

### 6.3 量能分

```text
VolumeScore = min(VolRatio60 / 2 * 100, 100)
```

### 6.4 份额变化分

如果模板中存在 `份额变化（亿份）`：

```text
ShareChangeScore = clip(50 + ShareChange * 5, 0, 100)
```

如果没有该字段：

```text
ShareChangeScore = 50
```

## 7. 回测模型

### 7.1 完整交易回测

信号和交易时点：

```text
T 日收盘后生成信号
T+1 日开盘价模拟成交
```

建仓：

```text
EntrySignalDate = T
EntryDate = T+1
EntryPrice = Open(T+1)
```

平仓：

```text
ExitSignalDate = T
ExitDate = T+1
ExitPrice = Open(T+1)
```

收益：

```text
GrossReturn = ExitPrice / EntryPrice - 1
NetReturn = GrossReturn - 2 * FeeRate
```

当前费用假设：

```text
FeeRate = 0.001
```

即双边合计扣 `0.2%`。

### 7.2 次日方向验证

用于验证“今天按规则给出信号，下一交易日方向是否符合预期”。

建仓信号：

```text
ExpectedDirection = 上涨
NextDayReturn = Close(T+1) / Open(T+1) - 1
Hit = NextDayReturn > 0
```

平仓信号：

```text
ExpectedDirection = 下跌
NextDayReturn = Close(T+1) / Open(T+1) - 1
Hit = NextDayReturn < 0
```

注意：平仓信号更偏风险控制，不一定等同于预测次日下跌。

## 8. 输出结果

ETF 页面输出：

- 建仓候选
- 平仓提示
- 关注池
- 近 30 交易日次日验证
- 完整交易回测
- 标的详情近 8 日指标

主要字段：

- `ma5_ma10_signal`
- `ma5_ma20_status`
- `volume_check`
- `vol_ratio60`
- `macd_hist`
- `score`
- `signal_reason`
- `watch_type`
- `missing_condition`
- `suggested_action`

## 9. 当前边界

- ETF 模块目前是规则模型，不是机器学习模型。
- 建仓、平仓由确定性条件触发，评分只用于排序。
- 只有客户持仓状态为 `holding` 的 ETF 才会输出平仓提示。
- 回测不代表未来收益，只用于验证历史信号表现。
- 当前尚未实现组合级资金曲线、最大回撤、年化收益和 Sharpe。

