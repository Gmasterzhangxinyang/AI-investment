<div align="center">

# AI Investment Research Workbench

**本地优先的 ETF、TL、可转债投研工作台**

`Rules First` · `SQLite Evidence` · `ETF / TL / Convertible Bonds` · `Optional AI Chat` · `Port 8766`

</div>

---

## 项目定位

AI Investment Research Workbench 是一个本地化投研辅助系统。它读取本地 Wind Excel 模板，完成数据校验、指标计算、策略筛选、风险识别、日报生成、SQLite 入库和前端展示。

系统的核心原则是：

- 交易信号由确定性规则生成。
- AI 只解释已有证据，不生成、修改或覆盖信号。
- 数据默认保留在本地，真实 Excel、SQLite、日志和输出文件不进入 Git。
- 当 ETF、TL、可转债中的单个 Excel 缺失时，流程降级运行；只有全部核心源文件都缺失时，前端刷新才会直接报错。
- 所有输出保留合规免责声明，不构成投资建议或收益承诺。

## 当前能力

| 模块 | 能力 |
| --- | --- |
| 投研问答 | 默认使用规则证据回答；用户点击 `AI 智能问答` 并确认后，才调用大模型做更自然的解释。 |
| 每日报告 | 今日投研值班台，汇总 ETF、TL、可转债、风险提示、数据质量和可执行检查项。 |
| ETF | 根据持仓状态区分建仓候选、关注池和平仓提示，并展示每只 ETF 的指标、缺口和规则原因。 |
| TL | 对 30 年国债期货 TL 做日频状态诊断：不做交易、关注交易、模型触发建仓候选。 |
| 可转债 | 先硬风控，再打分，再分为合格候选、弱观察候选、风险观察和排除列表；不会强行凑满 Top10。 |
| 标的档案 | 按代码或名称查看 ETF、TL、可转债的单标的指标、状态、风险说明和入库数据。 |
| 数据状态 | 查看源文件、SQLite、dashboard、数据质量和最近运行状态。 |
| 运行审计 | 查看工作流、QA audit、warnings 和可追溯运行信息。 |
| 策略参数 | 本地调整 ETF、TL、可转债阈值和权重；刷新后生效。 |
| 参数说明 | 解释各类策略参数的含义、调高调低影响、调参顺序和边界。 |

## 架构

```text
Wind Excel
  -> SourceArchiveAgent
  -> DataAgent
  -> QAAgent
  -> IndicatorAgent
  -> Strategy Agents
       - ETFAgent
       - TLAgent
       - ConvertibleBondAgent
  -> BacktestAgent
  -> RiskAgent
  -> AIResearchCommitteeAgent
  -> ExplanationAgent
  -> ReportAgent
       - outputs/latest/dashboard.json
       - outputs/latest/report.xlsx
       - outputs/latest/report.pdf
       - data/research.db
       - frontend dashboard
```

工作流采用 Agent + Skill + Tool 结构。Agent 负责治理和审计，Skill 执行业务逻辑，Tool 封装 Excel、PDF、SQLite、LLM、文本安全等通用能力。

大模型只在解释层使用：

- 日报和问答的策略结果来自 `dashboard.json`、SQLite 和配置参数。
- 配置的 LLM provider 不可用、额度不足或超时时，系统回退到本地确定性解释。
- 前端没有独立计算策略，所有页面展示后端生成的证据包。

## 数据输入

默认源文件路径配置在 `configs/data_sources.json`：

```text
data/wind/current/01_ETF清单和日频公式.xlsx
data/wind/current/02_TL日频公式.xlsx
data/wind/current/03_可转债数据.xlsx
```

ETF 持仓状态可来自 ETF 模板中的控制页，也可来自：

```text
configs/positions.csv
```

常用状态：

```text
holding   当前持有，只检查平仓提示
closed    已平仓，重新进入建仓筛选
flat      未持仓，进入建仓筛选和关注池判断
watch     观察中
```

## 快速启动

macOS 文件夹版第一次使用先双击：

```text
初始化环境.command
```

之后日常使用直接双击：

```text
启动AI投研.command
```

脚本会检查 `data/wind/current/` 下的三个 Wind Excel，启动本地服务并自动打开浏览器。更详细的双击启动说明见 `START_HERE.md`。

也可以手动启动：

安装依赖后，在项目根目录运行：

```bash
python serve.py --port 8766
```

打开：

```text
http://127.0.0.1:8766/frontend/
```

`serve.py` 默认端口为 `8766`。如果端口被占用，可以传入其他端口：

```bash
python serve.py --port 8770
```

## 运行日报

使用本地 Wind 文件生成日报、dashboard、SQLite 入库和审计信息：

```bash
PYTHONPATH=backend python -m superpower.cli.run_daily \
  --etf-file data/wind/current/01_ETF清单和日频公式.xlsx \
  --tl-file data/wind/current/02_TL日频公式.xlsx \
  --cb-file data/wind/current/03_可转债数据.xlsx \
  --disable-llm
```

开启 AI 解释时，需要在 `configs/model_config.json` 中启用 LLM。当前默认是 OpenAI；顶层 `provider` 用于日报/复核语言层，`chat.provider` 专门用于前端“AI 智能问答”：

- `openai`：默认问答 provider。可在前端“策略参数 > AI 模型”里查看遮挡后的 Key、点击修改 Key、验证连通、读取账号可用模型并选择模型。
- `opencode`：仅保留为可选底层 provider；当前产品默认不启用。

配置也支持直接填写 `api_key`，但更推荐通过前端遮挡输入或 `.env`/系统环境变量管理，避免密钥进入 Git。

即便 AI 调用失败，日报仍会继续生成。

## 输出文件

```text
outputs/latest/dashboard.json   前端、问答、PDF 和 SQLite 的稳定数据契约
outputs/latest/report.xlsx      每日 Excel 报告
outputs/latest/report.pdf       每日 PDF 报告
outputs/latest/audit.json       QA audit 摘要
logs/                           Agent 运行审计日志
data/research.db                本地 SQLite 研究数据库
```

这些文件是运行产物，不建议提交到 Git。

## 策略口径

### ETF

ETF 根据信号日的指标和持仓状态判断：

- 持仓中：只检查平仓提示。
- 未持仓或已平仓：检查建仓候选和关注池。
- 建仓侧重点：MA5/MA10、MACD、前 60 日量能倍数。
- 平仓侧重点：跌破 MA10 或 MA5，并伴随配置要求的放量。

### TL

TL 只做日频状态诊断：

- `不做交易`
- `关注交易`
- `模型触发建仓候选`

周线不利状态是硬约束；系统不会因为日线短期改善就强行升级为建仓候选。

### 可转债

可转债不再强行凑满 Top10。输出分层为：

- `qualified`: 合格候选，可进入 Top 表。
- `weak_watch`: 弱观察候选，只代表相对排序靠前，不写成推荐。
- `risk_watch`: 风险观察，不进入首页 Top 表。
- `excluded`: 硬排除列表。

兼容字段 `top10` 仍然存在，但只能等于 `qualified[:10]`。

## 测试与检查

```bash
python -m compileall backend/superpower
pytest
```

每日运行检查：

```bash
PYTHONPATH=backend python -m superpower.cli.run_daily \
  --etf-file data/wind/current/01_ETF清单和日频公式.xlsx \
  --tl-file data/wind/current/02_TL日频公式.xlsx \
  --cb-file data/wind/current/03_可转债数据.xlsx \
  --disable-llm
```

QA audit 默认不阻断日报生成；只有传入 `--strict-audit` 时，audit 非 PASS 才会让命令返回非 0。

## 关键配置

| 文件 | 说明 |
| --- | --- |
| `configs/strategy_params.json` | ETF、TL、可转债阈值、权重和风控参数。 |
| `configs/data_sources.json` | Wind Excel 默认路径。 |
| `configs/model_config.json` | LLM 开关、模型和超时设置。 |
| `configs/positions.csv` | ETF 持仓状态。 |
| `configs/universe_etf.json` | ETF 标的范围。 |
| `configs/delivery.json` | 报告输出和运行参数。 |

## 文档入口

| 文档 | 内容 |
| --- | --- |
| `docs/ARCHITECTURE.md` | 系统架构、Agent、Skill、前端和数据流。 |
| `docs/AGENTS.md` | 每个 Agent 的职责、输入输出和 LLM 边界。 |
| `docs/DATA_CONTRACT.md` | Wind Excel、标准化字段、dashboard 和 SQLite 数据契约。 |
| `docs/DASHBOARD_SCHEMA.md` | `outputs/latest/dashboard.json` 稳定结构。 |
| `docs/FRONTEND_GUIDE.md` | 前端页面、端口、刷新和降级行为。 |
| `docs/CLIENT_PRODUCT_GUIDE.md` | 产品使用说明、策略口径和参数解释。 |
| `docs/STRATEGY_LOGIC.md` | ETF、TL、可转债核心规则。 |
| `docs/STRATEGY_PARAMETERS.md` | 参数含义、默认值和调参影响。 |
| `docs/DATA_QUALITY_RULES.md` | 数据质量规则和缺数据降级。 |
| `docs/REPORTING_POLICY.md` | 报告措辞、免责声明和文本安全边界。 |
| `docs/STABILITY_CHECKLIST.md` | 本地运行和发布前检查清单。 |

## 安全边界

系统输出是投研辅助结果，不构成投资建议或收益承诺。任何建仓候选、平仓提示、弱观察、风险观察和历史诊断，都需要结合账户约束、流动性、交易成本、风险偏好和人工复核使用。

LLM 回答必须以本地数据为依据；如果数据库没有某只标的或某个历史日期的数据，系统应明确说明“当前没有数据”，而不是编造结论。
