# 投研问答运行时

## 目标

投研问答采用“确定性数据与策略在前，AI 解释在后”的架构。AI 不直接连接数据库、不执行 SQL、不访问任意文件，也不能修改策略、排名、评分或交易信号。

规则层和 AI 层必须明确区分：规则层输出系统正式信号、评分和排名；AI 开启后，研究层基于白名单工具返回的行情、历史指标、规则状态和风险证据独立综合，可以说明赞同或不赞同规则及原因，但不能把自己的判断写回正式信号。前端分别标注“规则查询”和“AI研究分析”。固定回答只用于 AI 关闭或模型失败时的兜底。

当前不是早期“按关键词返回固定日报摘要”的问答。Router 会解析意图与标的；明确问题走快速工具；复杂问题可进入受控 ReAct 主 Agent，由 Agent 在白名单内选择下一项工具、观察结果并检查证据是否足够。

## 三档执行路径

| 路径 | 适用问题 | 执行方式 | 典型速度 |
| --- | --- | --- | --- |
| 规则快速路径 | 收盘价、评分、量能、单标的/多标的当前状态、名单、参数、数据范围 | Router 识别意图 → 白名单工具取数 → 确定性回答 → Guardrail | 本地通常低于 1 秒 |
| AI 快速研究 | 中期趋势、短期入场、“为什么”“怎么看”等对象明确的问题 | 已确定的证据工具取数 → `economy_model` 独立综合 → Guardrail | 取决于模型与网络，不是 SLA |
| 深度 Agent | 跨 ETF/TL/可转债综合风险、复杂排序解释、问题不明确、需要继续选工具的问题 | 主 Agent ReAct → 只读工具 → 证据审查/反思 → 主模型回答 → 最终复核 | 会比日常问答更慢 |

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

当前注册工具包括：`chat_data_scope`、`daily_summary`、`database_inventory`、`strategy_contract`、`strategy_diagnostics`、`etf_ranking`、`etf_signals`、`etf_watchlist`、`etf_single_asset`、`etf_multi_assets`、`etf_strategy_comparison`、`tl_state`、`convertible_rankings`、`convertible_detail`、`data_quality`、`risk_summary`。

主 Agent 每轮只能选择一个动作：继续调用工具、请求必要澄清或结束。工具调用有硬上限，重复调用会被跳过；证据不足时可以重新规划，但不能创造新工具、SQL、路径或市场事实。

页面展示范围不限制问答后台范围。例如 TL 页面可只展示最近 8 日，但问答工具仍读取 30 日；可转债页面展示 Top10，但问答可比较前 30 只。

## 数据准确性

1. Router 先识别问题和标的。
2. ResearchToolbox 或主 Agent 只调用白名单工具。
3. EvidenceAccuracyReviewer 检查日期、资产类别、数量边界、重复记录和证据完整性。
4. OutputGuardrail 禁止把关注池写成建仓、把辅助指标写成交易信号、承诺收益或声称执行未开放动作。
5. 没有数据时必须明确说明，禁止补猜。

一句话中出现多只已入库 ETF 时，Router 会保留完整代码列表，`etf_multi_assets` 会逐只补齐证据。此类当前状态核对即使开启 AI 也走确定性快速路径，避免模型遗漏标的或把 `no_entry` 改写成“进入观察”。

证据审查通过不代表投资结论正确，只表示本轮回答使用的数据来源、日期、数量和资产类型满足系统契约。

质检工具会分别返回完整检查总数、完整提醒总数和裁剪后的展示明细，避免因单次证据包上限导致漏报。

## 降级行为

- AI 未开启：规则支持的问题继续正常回答。
- Key 缺失、模型超时或服务失败：回退到确定性回答，并在 Trace 中记录原因。
- 自然闲聊在 AI 关闭时会提示开启 AI，不会错误返回日报摘要。
- 新闻、实时行情、互联网信息没有接入，系统会明确说明当前不可访问。

## 当前模型配置

模型选择可由前端修改，文档不把模型名当作固定业务规则。当前配置使用 OpenAI；日常解释读取 `economy_model`，深度问答读取 `chat.primary_model`。API Key 只保存在本机 `.env` 或环境变量，不写入 Git 和 `model_config.json`。

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
