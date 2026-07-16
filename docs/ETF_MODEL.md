# ETF 模型与公式

ETF 信号由确定性代码生成。当前默认策略是 `trend_pullback_v2` 2.0.0；`legacy_v1` 1.0.0 作为可切换插件和历史对照保留。AI 不能改变任何状态、信号、评分或排名。

## 1. 插件与生效方式

| 插件 | 当前用途 |
| --- | --- |
| `trend_pullback_v2` | 当前实时默认；拆分中期趋势与短期入场，过滤假反转和过热追涨。 |
| `legacy_v1` | 保留原 MA5/MA10、MACD、量能规则；可切换，也参与诊断对照。 |

操作路径：`策略参数 → ETF 当前策略 → 保存 → 一键刷新`。保存只修改配置；刷新成功后，新的策略 ID、版本和配置哈希才进入 dashboard、SQLite 和报告。刷新失败继续展示上一版结果。

## 2. 输入与基础指标

必要行情：日期、代码、名称、开高低收、成交量；成交额和份额变化在模板提供时使用。持仓状态来自 ETF 控制表或 `configs/positions.csv`。

### 均线

```text
MA_N(t) = mean(Close(t-N+1), ..., Close(t))
```

当前计算 MA5、MA10、MA20、MA60。

### 前 60 日量能倍数

为了避免当日成交量污染基准：

```text
VolMA60(t) = mean(Volume(t-60), ..., Volume(t-1))
VolRatio60(t) = Volume(t) / VolMA60(t)
```

实现使用 `volume.shift(1).rolling(60, min_periods=20).mean()`。

### MACD

```text
DIF = EMA12(Close) - EMA26(Close)
DEA = EMA9(DIF)
MACDHist = DIF - DEA
```

系统柱值不乘 2。正值称红柱，负值称绿柱。

### MA20 斜率

默认回看 5 个交易日：

```text
MA20Slope = MA20(t) / MA20(t-5) - 1
```

绝对值不超过 `0.003` 视为近似走平；高于区间视为向上，低于区间视为向下。

### 周 MACD

日线按已发生数据聚合成周线。当前交易周只使用截至报告日的数据，不读取未来交易日。系统识别红柱加强/减弱、绿柱缩短/扩大和红绿切换。

## 3. 当前默认：中期趋势模块

输出枚举：

```text
do_not_participate
trend_not_confirmed
trend_confirmed
data_unavailable
```

### 3.1 硬否决

出现以下任一明显不利条件时为 `do_not_participate`：

- MA20 继续向下；
- 周 MACD 绿柱扩大；
- 周 MACD 红柱走弱达到策略定义的不利状态。

这用于过滤“长期下跌后突然放量长阳”的假反转。单日上涨和放量不能覆盖中期硬否决。

### 3.2 趋势确认

没有硬否决后，确认项包括：

- 收盘价高于 MA20；
- MA5 高于 MA20；
- MA20 走平或向上；
- 周 MACD 有利；
- 日 MACD 为红柱确认。

共同满足时为 `trend_confirmed`。趋势确认是中期安全垫，不等于短期可以立即建仓。

## 4. 当前默认：密切观察与短期入场

输出枚举：

```text
no_entry
close_watch
overheated_do_not_chase
waiting_confirmation
waiting_pullback
can_enter
data_unavailable
```

### 4.1 密切观察

客户核心规则：

```text
MA5 已在 MA10 上方
且日 MACD 绿柱缩短或转红
=> close_watch
```

系统同时提示周 MACD 是否绿柱缩短/红柱加长，以及 MA20 是否走平。`close_watch` 只是观测状态，可与中期未确认同时存在，不能升级为建仓候选。

### 4.2 趋势确认日

“趋势确认日（设置日）”是中期趋势第一次转为 `trend_confirmed` 的交易日，不固定指前一天。系统记录当日收盘、高点、成交量和均线，默认最多保留 10 个交易日用于等待确认。

### 4.3 过热保护

默认阈值：

| 条件 | 当前值 |
| --- | ---: |
| 单日涨幅 | 4% |
| 阳线实体占振幅 | 60% |
| 量能倍数 | 1.8 |
| 收盘高于 MA5 偏离 | 3% |
| 冷却期 | 3 个交易日 |

涨幅、实体、量能和 MA5 偏离共同显示明显过热时为 `overheated_do_not_chase`。这类信号只提示不追涨，不能写成建仓。

### 4.4 突破确认

中期趋势已确认后，后续交易日需要：

- 收盘突破趋势确认日高点；
- 日 MACD 保持红柱；
- 收盘相对 MA5 的偏离低于默认 3%；
- 当日不属于过热状态。

满足后才可能进入 `can_enter`。

MA5 偏离计算：

```text
MA5Distance = Close / MA5 - 1
```

### 4.5 回踩确认

也可以不追突破，等待价格回踩 MA5、MA10 或突破位。默认支撑容忍度 0.5%，盘中最大假跌破 1%，并要求收盘重新站稳、成交量较设置日缩小且日 MACD 未破坏。

## 5. 持仓退出

只有 `holding` ETF 检查退出。v2 当前复用已验证的原策略退出口径：

```text
Close < MA10 and VolRatio60 >= 1.2
or
Close < MA5 and VolRatio60 >= 1.2
```

未持仓、已平仓和观察状态不会生成平仓提示。

## 6. 排名评分

```text
Score = TrendScore * 0.35
      + MACDScore * 0.25
      + VolumeScore * 0.25
      + ShareChangeScore * 0.15
```

份额变化缺失时使用中性值。评分用于相对排序，不会替代 `medium_status`、`short_entry_status` 和持仓路径。

## 7. `legacy_v1` 保留规则

原策略两类建仓：

```text
规则 A：MA5 当日上穿 MA10 + MACD 柱改善 + VolRatio60 >= 1.1
规则 B：DIF 当日上穿 DEA + MA5 > MA10 + Close > MA20 + VolRatio60 >= 1.1
```

MA5 高于 MA20 在规则 A 中是增强项，不是硬条件。原策略不划分中期趋势，所以 `medium_status=not_applicable`。启用原策略时，前端隐藏 v2 专属的中期/短期列，仅保留原策略信号与风险辅助。

## 8. 历史表现诊断

v2 对状态转折事件统计：

- 1/3/5/10/20 日后收益分布；
- 期间最大有利波动和最大不利波动；
- 10 日假反转次数；
- 突破确认与回踩确认分组。

这些数据回答“历史上相同状态之后通常怎样”，不是完整交易系统回测。兼容层虽仍保留 T 日收盘信号、T+1 开盘执行的交易证据，但当前没有组合资金曲线、仓位管理、滑点、年化收益、Sharpe 或正式样本外验证。

## 9. 输出字段

每只 ETF 至少包含：

```text
strategy_id, strategy_version, config_hash
medium_status, medium_reason
short_entry_status, short_entry_reason
weekly_macd_state, weekly_macd_confirmation_check
ma20_slope_5d, ma20_slope_state, ma20_flat_check
ma5_ma10_signal, ma5_ma20_status
close, ma5, ma10, ma20, ma60
vol_ratio60, macd_hist, dif, dea
rule_hits, risk_notes, score
```

页面上的“趋势确认”“密切观察”“过热不追”“等待回踩”“可考虑入场”必须直接来自这些确定性字段，AI 不得自行转换状态。

## 10. 边界

- 模型适合 5 至 20 个交易日的中短期趋势观察，不是次日涨跌预测器。
- 趋势确认不等于必涨，短期入场也不保证收益。
- 历史诊断只能检查规则表现，不能证明绝对收益。
- 当前不接入实时盘中行情、新闻或账户交易。
