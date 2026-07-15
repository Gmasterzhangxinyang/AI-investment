# 投研问答运行时

## 目标

投研问答采用“确定性数据与策略在前，AI 解释在后”的架构。AI 不直接连接数据库、不执行 SQL、不访问任意文件，也不能修改策略、排名、评分或交易信号。

## 三档执行路径

| 路径 | 适用问题 | 执行方式 | 典型速度 |
| --- | --- | --- | --- |
| 规则快速路径 | 收盘价、评分、量能、单标的/多标的当前状态、名单、参数、数据范围 | Router 识别意图 → 白名单工具取数 → 确定性回答 → Guardrail | 本地通常低于 1 秒 |
| AI 快速解释 | “为什么”“怎么理解”“简单分析”等对象明确的问题 | 固定工具包取数 → `economy_model` 解释 → Guardrail | 取决于模型与网络；本机实测约 5 秒，不是 SLA |
| 深度 Agent | 跨 ETF/TL/可转债综合风险、问题不明确、需要继续选工具的问题 | 主 Agent ReAct → 只读工具 → 证据审查/反思 → 主模型回答 → 最终复核 | 会比日常问答更慢 |

日常快速模型来自 `configs/model_config.json` 的 `economy_model`；深度分析模型来自 `chat.primary_model`。前端模型设置会同时显示两者。

## 白名单工具

AI 只能通过 `backend/superpower/chat/tool_registry.py` 暴露的只读工具获得证据：

- 数据范围与数据库资产清单
- 日报摘要和策略规则
- ETF 全量排序、建仓/平仓/关注池
- 单只 ETF 最近 30 个交易日
- 2 至 10 只 ETF 的当前中期趋势、短期入场状态和关键指标；逐只返回，不以页面关注池代替
- 单只 ETF 双策略（最多 400 个交易日）计算结果
- TL 最近 30 个交易日
- 可转债 Top10 展示与前 30 只问答分析池
- 单只可转债详情
- 数据质量和风险摘要

页面展示范围不限制问答后台范围。例如 TL 页面可只展示最近 8 日，但问答工具仍读取 30 日；可转债页面展示 Top10，但问答可比较前 30 只。

## 数据准确性

1. Router 先识别问题和标的。
2. ResearchToolbox 或主 Agent 只调用白名单工具。
3. EvidenceAccuracyReviewer 检查日期、资产类别、数量边界、重复记录和证据完整性。
4. OutputGuardrail 禁止把关注池写成建仓、把辅助指标写成交易信号、承诺收益或声称执行未开放动作。
5. 没有数据时必须明确说明，禁止补猜。

一句话中出现多只已入库 ETF 时，Router 会保留完整代码列表，`etf_multi_assets` 会逐只补齐证据。此类当前状态核对即使开启 AI 也走确定性快速路径，避免模型遗漏标的或把 `no_entry` 改写成“进入观察”。

质检工具会分别返回完整检查总数、完整提醒总数和裁剪后的展示明细，避免因单次证据包上限导致漏报。

## 降级行为

- AI 未开启：规则支持的问题继续正常回答。
- Key 缺失、模型超时或服务失败：回退到确定性回答，并在 Trace 中记录原因。
- 自然闲聊在 AI 关闭时会提示开启 AI，不会错误返回日报摘要。
- 新闻、实时行情、互联网信息没有接入，系统会明确说明当前不可访问。

## 关键实现

```text
backend/superpower/chat/router.py
backend/superpower/chat/tool_registry.py
backend/superpower/chat/tools.py
backend/superpower/chat/access_policy.py
backend/superpower/chat/agent_runtime.py
backend/superpower/chat/evidence_review.py
backend/superpower/chat/orchestrator.py
backend/superpower/chat/guardrails.py
```
