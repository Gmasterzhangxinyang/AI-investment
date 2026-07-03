# 可转债判断逻辑、模型与公式

本文档描述当前系统可转债板块的风险过滤、打分模型和候选资格分层逻辑。可转债排序由确定性规则生成，AI 只解释原因，不改写排名。

## 1. 输入数据

可转债模块读取客户最新版 v2 可转债 Excel。

核心字段：

- 日期
- 转债代码
- 转债名称
- 价格
- 剩余期限
- 转股溢价率
- 到期收益率
- 正股代码
- 正股名称
- 债项评级
- 申万一级行业
- 申万二级行业
- 正股价格
- 最新转股价
- 触发赎回比例
- 赎回公告日
- 不强赎提示公告日
- 发行规模
- 存续规模
- 未转股票比例
- 2022 至 2025 扣非净利润
- 半年度扣非净利润
- 三年平均扣非净利润增长率
- 2025 年扣非增速较三年均值的变化
- 2025 年扣非净利润增速

异常日期处理：

- 无效日期、空日期、类似 Excel 异常日期会被视为无有效公告。

百分比字段处理：

如果字段看起来是小数格式，例如 `0.35` 表示 35%，系统会自动转换为百分数：

```text
if abs(percent_field).quantile(0.75) <= 1.5 and max(abs(percent_field)) <= 5:
    percent_field = percent_field * 100
```

## 2. 总体流程

```text
读取数据
  -> 标准化字段
  -> 识别强赎状态
  -> 识别信用与基本面风险
  -> 硬过滤
  -> 分项打分
  -> 风险扣分
  -> 综合评分
  -> 排名
  -> 候选资格分层
  -> 合格候选中做行业分散
  -> Top候选
```

## 3. 关键参数

当前默认参数：

```text
price_limit = 140
min_price = 100
top_n = 10
high_ytm_hard_exclude = 15
severe_negative_ytm_hard_exclude = -5
high_premium_penalty_threshold = 35
high_premium_hard_exclude = 50
min_remaining_size_hard_exclude = 0.5
max_per_industry_l1 = 2
max_per_industry_l2 = 2
no_redemption_valid_days = 180
exclude_st_stock = true
exclude_unresolved_redemption_trigger = true
```

评级硬排除列表：

```text
A, A-, BBB+, BBB, BBB-, BB+, BB, BB-, B+, B, B-, CCC, CC, C, D
```

因此：

- `A+` 当前不是硬排除，但会被标记为偏低评级风险。
- `A` 及以下会硬排除。
- `BBB+` 及以下会硬排除。

## 4. 强赎风险判断

### 4.1 强赎触发价

触发比例标准化：

```text
TriggerRatioNormalized =
  TriggerRatio if TriggerRatio <= 10
  else TriggerRatio / 100
```

强赎触发价：

```text
RedemptionTriggerPrice = ConversionPrice * TriggerRatioNormalized
```

是否触发强赎价：

```text
RedemptionTriggered =
  StockPrice >= RedemptionTriggerPrice
```

如果 Excel 已提供是否触发字段，系统会与上述计算结果合并：

```text
RedemptionTriggered = ExcelTriggered or ComputedTriggered
```

### 4.2 强赎状态

已发布赎回公告：

```text
has_redeem_announcement == True
```

状态：

```text
已发强赎公告，剔除
```

未触发强赎价：

```text
redemption_triggered == False
```

状态：

```text
未触发强赎价
```

触发强赎价但有有效不强赎公告：

```text
redemption_triggered == True
has_no_redeem_announcement == True
no_redeem_is_stale == False
```

状态：

```text
触发强赎价但有不强赎公告，观察
```

不强赎公告过期：

```text
report_date - no_redemption_announcement_date > no_redemption_valid_days
```

状态：

```text
触发强赎价，不强赎公告可能过期
```

触发但未见有效公告：

```text
触发强赎价，未见有效公告
```

## 5. 硬过滤规则

转债会先经过硬过滤。硬过滤后的标的才进入打分。

### 5.1 价格过滤

```text
if price is missing:
    exclude = 价格缺失
elif price < min_price:
    exclude = 价格低于100元
elif price >= price_limit:
    exclude = 价格不低于140元
```

客户强调 100 元以下通常可能隐含信用风险，因此当前低于 100 直接剔除。

### 5.2 强赎公告过滤

```text
if has_redeem_announcement:
    exclude = 已发布强赎公告
```

原因：已发强赎公告后，转债交易逻辑通常会变化，不再按普通可转债性价比模型打分。

### 5.3 评级过滤

```text
if rating_key in hard_exclude_ratings:
    exclude = 债项评级低于风控线
```

### 5.4 正股 ST 过滤

```text
if exclude_st_stock and is_st_stock:
    exclude = 正股ST
```

### 5.5 YTM 过滤

高 YTM 异常：

```text
if ytm >= high_ytm_hard_exclude:
    exclude = 到期收益率异常偏高
```

默认：

```text
high_ytm_hard_exclude = 15
```

严重负 YTM：

```text
if ytm <= severe_negative_ytm_hard_exclude:
    exclude = 到期收益率严重为负
```

默认：

```text
severe_negative_ytm_hard_exclude = -5
```

### 5.6 高溢价过滤

```text
if conversion_premium_rate >= high_premium_hard_exclude:
    exclude = 转股溢价率过高
```

默认：

```text
high_premium_hard_exclude = 50
```

### 5.7 剩余规模过滤

```text
if remaining_size < min_remaining_size_hard_exclude:
    exclude = 存续规模过低
```

默认：

```text
min_remaining_size_hard_exclude = 0.5
```

### 5.8 强赎未明过滤

当前默认：

```text
exclude_unresolved_redemption_trigger = true
```

因此，触发强赎价但未见有效不强赎公告的标的会被硬剔除，不能进入普通 Top 候选。

如果设置为 `false`，以下状态会保留观察但强扣分和提示风险：

```text
触发强赎价，未见有效公告
触发强赎价，不强赎公告可能过期
```

## 6. 分项打分模型

硬过滤后的标的进入分项打分。

当前权重：

```text
fundamental = 0.25
premium = 0.20
ytm = 0.15
term = 0.10
credit = 0.15
redemption = 0.10
scale = 0.05
```

系统会将非负权重归一化：

```text
NormalizedWeight_i = max(Weight_i, 0) / sum(max(Weight_i, 0))
```

综合评分：

```text
Score =
  FundamentalScore * fundamental
  + PremiumScore * premium
  + YTMScore * ytm
  + TermScore * term
  + CreditScore * credit
  + RedemptionScore * redemption
  + ScaleScore * scale
  - RiskPenalty
```

最后截断：

```text
Score = clip(round(Score, 2), 0, 100)
```

## 7. 基本面分

基本面使用三类增长指标：

- `deducted_profit_growth`：三年平均扣非净利润增长率。
- `profit_growth_acceleration`：2025 增速相对三年均值的变化。
- `profit_growth_25_vs_24`：2025 年扣非净利润增速。

先对增长率截尾：

```text
GrowthClipped = clip(Growth, growth_winsor_lower, growth_winsor_upper)
```

默认：

```text
growth_winsor_lower = -100
growth_winsor_upper = 150
```

分别做高者更优的百分位评分：

```text
GrowthScore = HigherBetter(deducted_profit_growth)
AccelerationScore = HigherBetter(profit_growth_acceleration)
LatestScore = HigherBetter(profit_growth_25_vs_24)
```

基本面初始分：

```text
FundamentalScore =
  GrowthScore * 0.35
  + AccelerationScore * 0.25
  + LatestScore * 0.40
```

如果利润基数不稳定：

```text
FundamentalScore = FundamentalScore * 0.72
```

利润基数不稳定的判断：

```text
deducted_profit_2022 <= 0 or abs(deducted_profit_2022) < 1
or deducted_profit_2023 <= 0 or abs(deducted_profit_2023) < 1
or deducted_profit_2024 <= 0 or abs(deducted_profit_2024) < 1
or deducted_profit_h1_2025 <= 0 or abs(deducted_profit_h1_2025) < 1
```

如果最新扣非净利润为负：

```text
FundamentalScore = FundamentalScore * 0.55
```

最新扣非净利润为负的判断：

```text
deducted_profit_2025 < 0
or deducted_profit_h1_2026 < 0
```

最终：

```text
FundamentalScore = clip(fillna(FundamentalScore, 50), 0, 100)
```

## 8. 转股溢价率分

设：

```text
P = conversion_premium_rate
PenaltyLine = high_premium_penalty_threshold = 35
HardExcludeLine = high_premium_hard_exclude = 50
```

分段：

```text
if P <= 0:
    PremiumScore = 95
elif 0 < P <= 15:
    PremiumScore = 100 - P / 15 * 8
elif 15 < P <= 30:
    PremiumScore = 88 - (P - 15) / 15 * 18
elif 30 < P <= PenaltyLine:
    PremiumScore = 68 - (P - 30) / (PenaltyLine - 30) * 18
elif PenaltyLine < P < HardExcludeLine:
    PremiumScore = 42 - (P - PenaltyLine) / (HardExcludeLine - PenaltyLine) * 32
else:
    PremiumScore = 0
```

最终：

```text
PremiumScore = clip(fillna(PremiumScore, 50), 0, 100)
```

## 9. YTM 质量分

设：

```text
Y = ytm
HighYTMHardExclude = 15
```

分段：

```text
if Y < -8:
    YTMScore = 10
elif -8 <= Y < 0:
    YTMScore = 35 + (Y + 8) / 8 * 40
elif 0 <= Y <= 3:
    YTMScore = 82 + Y / 3 * 18
elif 3 < Y <= 8:
    YTMScore = 82 - (Y - 3) / 5 * 25
elif 8 < Y < HighYTMHardExclude:
    YTMScore = 45 - (Y - 8) / (HighYTMHardExclude - 8) * 25
```

最终：

```text
YTMScore = clip(fillna(YTMScore, 50), 0, 100)
```

说明：

- YTM 为负不是一定硬排除，但会降低 YTMScore，并进入风险扣分。
- YTM 异常高不是简单高收益机会，达到硬排除阈值会直接剔除。

## 10. 剩余期限分

剩余期限采用低者更优的百分位评分：

```text
TermScore = LowerBetter(remaining_years)
```

含义：

- 剩余期限更短，回收现金流更近，期限风险相对更低。
- 当前只作为评分项，不作为单独硬过滤。

## 11. 信用分

评级基础分：

```text
AAA = 100
AA+ = 92
AA = 84
AA- = 74
A+ = 62
A = 50
A- = 42
BBB+ = 34
BBB = 28
BBB- = 22
其他更低评级 = 更低分
```

价格和 YTM 调整：

```text
if price < 105:
    CreditScore -= 12
elif price < 110:
    CreditScore -= 6

if ytm > 8:
    CreditScore -= 18
elif ytm > 3:
    CreditScore -= 8
```

最终：

```text
CreditScore = clip(CreditScore, 0, 100)
```

## 12. 强赎状态分

```text
if redemption_status == "未触发强赎价":
    RedemptionScore = 100
elif redemption_status == "触发强赎价但有不强赎公告，观察":
    RedemptionScore = 68
elif redemption_status == "触发强赎价，不强赎公告可能过期":
    RedemptionScore = 42
elif redemption_status == "触发强赎价，未见有效公告":
    RedemptionScore = 25
else:
    RedemptionScore = 0
```

## 13. 规模分

```text
SizeScore = HigherBetter(remaining_size)
RatioScore = PercentileScore(unconverted_ratio, ascending=True)
ScaleScore = SizeScore * 0.7 + RatioScore * 0.3
```

最终：

```text
ScaleScore = clip(fillna(ScaleScore, 50), 0, 100)
```

## 14. 风险扣分

### 14.1 负 YTM 扣分

```text
if ytm < 0:
    severity = clip(abs(ytm) / 5, 0.25, 1)
    RiskPenalty += negative_ytm_penalty * severity
```

默认：

```text
negative_ytm_penalty = 28
```

### 14.2 高溢价扣分

```text
if premium > high_premium_penalty_threshold:
    severity = min((premium - high_premium_penalty_threshold) / (high_premium_hard_exclude - high_premium_penalty_threshold), 1)
    RiskPenalty += min(high_premium_penalty, high_premium_penalty * (0.5 + severity))
```

默认：

```text
high_premium_penalty = 28
```

### 14.3 业绩扣分

```text
if profit_growth_25_vs_24 < 0:
    RiskPenalty += negative_growth_penalty

if profit_growth_acceleration < 0:
    RiskPenalty += negative_acceleration_penalty

if latest_profit_negative:
    RiskPenalty += negative_profit_penalty
elif growth_base_unstable:
    RiskPenalty += unstable_growth_base_penalty
```

默认：

```text
negative_growth_penalty = 10
negative_acceleration_penalty = 5
negative_profit_penalty = 14
unstable_growth_base_penalty = 10
```

### 14.4 极端增长率扣分

```text
if abs(deducted_profit_growth) > 150
or abs(profit_growth_acceleration) > 150
or abs(profit_growth_25_vs_24) > 150:
    RiskPenalty += extreme_growth_penalty
```

默认：

```text
extreme_growth_penalty = 6
```

### 14.5 强赎状态扣分

```text
if redemption_status == "触发强赎价，未见有效公告":
    RiskPenalty += 12
elif redemption_status == "触发强赎价，不强赎公告可能过期":
    RiskPenalty += 8
elif redemption_status == "触发强赎价但有不强赎公告，观察":
    RiskPenalty += 4
```

### 14.6 剩余规模偏小扣分

```text
if remaining_size < 2:
    RiskPenalty += 5
```

## 15. 风险提示

系统会生成 `risk_flags`：

- 触发强赎价相关状态。
- 转股溢价率偏高。
- 2025 扣非增速为负。
- 2025 增速低于三年均值。
- 最新扣非净利润为负。
- 利润基数异常。
- 增长率极端，评分已截尾。
- 到期收益率为负。
- 存续规模偏小。
- A+、A、A- 等偏低评级提示。

风险等级：

```text
无明显 risk_flags -> 低
有少量 risk_flags -> 中
多项 risk_flags 或重大风险 -> 高
```

## 16. 排序与行业分散

候选池先按以下顺序排序：

```text
score DESC
credit_score DESC
redemption_score DESC
conversion_premium_rate ASC
```

然后做行业分散：

```text
max_per_industry_l1 = 2
max_per_industry_l2 = 2
```

即同一申万一级行业最多 2 只，同一申万二级行业最多 2 只。

输出：

```text
合格候选
弱观察候选
风险观察
排除列表
```

兼容字段 `cbTop10` 仍保留，但只等于 `qualified[:10]`。如果合格候选不足 10 只，不会从弱观察或风险观察中补足。

## 17. 候选资格分层

评分完成后，系统不会直接强制取前 10 名，而是先分层：

```text
qualified   合格候选，可进入 Top 候选表
weak_watch  弱观察候选，仅代表相对排序靠前，不构成高质量候选
risk_watch  风险观察，不进入 Top 候选表
excluded    硬排除列表
```

分数等级：

```text
A: score >= 70
B: 55 <= score < 70
C: 40 <= score < 55
D: 25 <= score < 40
E: score < 25
```

只有同时满足以下条件，才可进入 `qualified`：

```text
score >= 50
risk_level != 高
conversion_premium_rate <= 35
ytm >= -3
remaining_size >= 5
没有“最新扣非净利润为负”
没有“增长率极端，评分已截尾”
```

如果 `qualified` 不足 10 只，Top 表只展示实际合格数量。若 `qualified` 为 0，页面显示“今日无合格可转债 Top 候选”，并说明候选池整体质量偏弱。

## 18. 输出结果

可转债页面输出：

- 合格候选 Top
- 弱观察候选
- 风险观察
- 候选池全量排序
- 可转债质检与风险
- 标的档案详情

主要字段：

- `rank`
- `bond_code`
- `bond_name`
- `price`
- `remaining_years`
- `conversion_premium_rate`
- `ytm`
- `bond_rating`
- `sw_l1`
- `sw_l2`
- `redemption_status`
- `remaining_size`
- `deducted_profit_growth`
- `profit_growth_acceleration`
- `profit_growth_25_vs_24`
- `growth_score`
- `premium_score`
- `ytm_score`
- `credit_score`
- `redemption_score`
- `scale_score`
- `risk_penalty`
- `score`
- `score_grade`
- `qualification`
- `eligible_for_top`
- `not_top_reason`
- `quality_notes`
- `risk_level`
- `risk_flags`
- `rank_reason`

## 18. 当前边界

- 当前可转债模型是单日截面排序，不是历史收益回测。
- 强赎判断当前基于快照字段和当日正股价格，不包含最近 20/30 个交易日连续触发次数。
- 公告文本没有直接联网抓取，依赖客户 Excel 中的公告日期字段。
- 低价格、高 YTM、评级、ST、强赎等风险优先于打分。
- 模型不承诺收益，只用于筛选、排序和风险解释。
