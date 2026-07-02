from __future__ import annotations


RULEBOOK = [
    "系统的 ETF、TL、可转债信号均由确定性代码生成；LLM 只允许解释、归纳、复核和提示风险，不得新增或改写交易信号。",
    "ETF 建仓回答必须区分建仓候选、关注池和平仓提示。关注池不是建仓候选，必须说明未满足条件。",
    "ETF 建仓条件A：标的未持仓，MA5 今日上穿 MA10，MACD柱较前一交易日改善，成交量相对前60日均量倍数达到配置阈值。MA5高于MA20只作为增强项，不是硬性替代条件。",
    "ETF 建仓条件B：标的未持仓，DIF 今日上穿 DEA，MA5 高于 MA10，收盘价高于 MA20，且成交量相对前60日均量倍数达到配置阈值。",
    "ETF 关注池只表示趋势或MACD接近确认但条件不完整，尤其量能未确认时不得说成买入或建仓。",
    "ETF 平仓提示只针对用户持有仓位；条件为收盘跌破MA10且放量，或收盘跌破MA5且明显放量。若当前持仓为空，应说明无持仓侧平仓提示。",
    "ETF 规则解释必须使用 MA5/MA10、MA5/MA20、成交量相对前60个交易日均量倍数、DIF/DEA、MACD柱、触发原因和 score 等字段；不得用主观强弱代替规则。",
    "TL 只输出日频状态：不做交易、关注交易、模型触发建仓候选。30年国债期货 TL 不做平仓提示。",
    "TL 不做交易条件：周线层面红柱T日短于T-1日、绿柱T日长于T-1日，或红转绿阶段。",
    "TL 关注条件：周线层面红柱T日长于T-1日、绿柱T日短于T-1日，或绿转红阶段；日线MACD柱改善也只能形成关注或辅助判断。",
    "TL 建仓条件：周线关注条件且近2周J值曾低于20并在T周回升，或日线关注条件且近3日J值曾低于5并在T日回升；若周线不做交易硬否决开启，则不能升级为建仓。",
    "TL 建仓解释必须拆开周线 MACD、周线 KDJ、日线 MACD、日线 KDJ。周线近2周 J 未低于20，或日线近3日 J 未低于5时，不能说低位条件满足。",
    "TL 若 buy_signal 为 False，只能表述为关注或观察，不能升级成建仓候选。",
    "可转债先做风险排除再打分：100元以下、140元及以上、已发强赎公告、正股ST、BBB+及以下评级、高YTM异常等标的默认不进入正常排序；具体阈值以配置为准。",
    "可转债打分字段包括强赎状态、信用评级、转债价格、到期收益率、基本面增长、剩余期限、转股溢价率、存续规模、未转股比例和行业分散；AI不得只按单一价格或溢价率解释排名。",
    "数据缺失、样本不足、字段为空、可转债文件未上传等情况必须明说，不能用模型猜测补齐。",
    "输出不得承诺收益、不得给出保证性赚钱表述、不得越过规则直接建议交易。",
]


def rules_for_intent(intent_name: str) -> list[str]:
    common = [RULEBOOK[0], RULEBOOK[15], RULEBOOK[16]]
    if intent_name.startswith("etf"):
        return common + RULEBOOK[1:7]
    if intent_name.startswith("tl"):
        return common + RULEBOOK[7:13]
    if intent_name.startswith("convertible"):
        return common + RULEBOOK[13:15]
    if intent_name in {"asset_list", "database_inventory"}:
        return common + [
            "数据库盘点问题必须优先使用 SQLite asset_master 和表行数；不得只列关注池。",
            "列出标的名称时必须区分 ETF、TL、可转债，并尽量给出代码。",
        ]
    return RULEBOOK
