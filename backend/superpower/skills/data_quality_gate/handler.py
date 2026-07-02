from __future__ import annotations

from datetime import datetime

import pandas as pd

from superpower.runtime.context import AgentContext


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        etf = context.get("etf_market_raw")
        tl = context.get("tl_market_raw")
        cb = context.maybe("cb_data", pd.DataFrame())
        positions = context.maybe("positions", pd.DataFrame())
        source_manifest = context.maybe("source_manifest", pd.DataFrame())
        ingestion_warnings = context.maybe("data_ingestion_warnings", pd.DataFrame())
        etf_template_universe = context.maybe("etf_template_universe", pd.DataFrame())
        universe = context.maybe("universe", context.maybe("universe_config", {}))
        min_symbols = int(universe.get("expected_min_symbols", 1))

        etf_symbols = etf[["name", "code"]].drop_duplicates().shape[0] if {"name", "code"}.issubset(etf.columns) else 0
        etf_days = int(etf["date"].nunique()) if "date" in etf.columns else 0
        tl_days = int(tl["date"].nunique()) if "date" in tl.columns else 0
        etf_latest = etf["date"].max() if "date" in etf.columns and not etf.empty else pd.NaT
        tl_latest = tl["date"].max() if "date" in tl.columns and not tl.empty else pd.NaT
        today = pd.Timestamp(datetime.now().date())

        checks: list[dict[str, object]] = []
        checks.extend(_source_checks(source_manifest))
        checks.extend(_ingestion_warning_checks(ingestion_warnings))
        checks.extend(
            [
                _check("ETF有效标的数", "ERROR" if etf_symbols < min_symbols else "OK", etf_symbols, f"最低要求{min_symbols}"),
                _check("ETF目标标的范围", "WARN" if etf_symbols < 30 else "OK", etf_symbols, "客户目标30-50只；当前少于30只时可先跑，但不建议视作完整覆盖"),
                _check("ETF有效交易日", _history_status(etf_days), etf_days, "正式回测建议至少3-5年，当前少于120日只适合流程验证"),
                _check("ETF最新日期", _freshness_status(etf_latest, today), _date_text(etf_latest), "若不是上一交易日附近，需确认 Wind 是否刷新"),
                _check("TL有效交易日", _history_status(tl_days), tl_days, "正式回测建议至少3-5年，当前少于120日只适合流程验证"),
                _check("TL最新日期", _freshness_status(tl_latest, today), _date_text(tl_latest), "若不是上一交易日附近，需确认 Wind 是否刷新"),
                _check(
                    "ETF/TL最新日期一致",
                    "WARN" if _date_text(etf_latest) != _date_text(tl_latest) else "OK",
                    f"ETF={_date_text(etf_latest)} TL={_date_text(tl_latest)}",
                    "两者不一致时报告仍可出，但需人工复核",
                ),
            ]
        )
        checks.extend(_required_field_checks("ETF", etf, ["开盘价", "收盘价", "最低价", "最高价", "成交量（万股）"]))
        checks.extend(_required_field_checks("TL", tl, ["开盘价", "收盘价", "最低价", "最高价", "成交量"]))
        checks.extend(_market_value_checks("ETF", etf, "成交量（万股）"))
        checks.extend(_market_value_checks("TL", tl, "成交量"))
        checks.extend(_position_checks(positions, etf_template_universe))
        checks.extend(_cb_checks(cb))

        report = pd.DataFrame(checks)
        fail_count = int(report["status"].isin(["FAIL", "ERROR"]).sum())
        context.put("data_quality_report", report)
        return {
            "checks": len(report),
            "fail_count": fail_count,
            "warn_count": int((report["status"] == "WARN").sum()),
        }


def _check(item: str, status: str, detail: object, note: str = "") -> dict[str, object]:
    return {"item": item, "status": status, "detail": detail, "note": note}


def _source_checks(source_manifest: pd.DataFrame) -> list[dict[str, object]]:
    if source_manifest.empty:
        return [_check("源文件Manifest", "WARN", "未生成", "缺少源文件归档信息")]
    checks = [
        _check("源文件Manifest", "OK", f"{len(source_manifest)}个源文件", "每次运行均记录hash和归档路径"),
    ]
    for _, row in source_manifest.iterrows():
        source_type = row.get("source_type", "UNKNOWN")
        exists = bool(row.get("exists", False))
        status = "OK" if exists else ("WARN" if source_type == "CB" else "ERROR")
        checks.append(
            _check(
                f"{source_type}源文件",
                status,
                row.get("path", ""),
                f"sha256={str(row.get('sha256', ''))[:12]}" if exists else "文件不存在",
            )
        )
    return checks


def _ingestion_warning_checks(warnings: pd.DataFrame) -> list[dict[str, object]]:
    if warnings.empty:
        return []
    checks = []
    for _, row in warnings.iterrows():
        module = row.get("module", "UNKNOWN")
        checks.append(
            _check(
                f"{module}数据接入",
                str(row.get("status", "ERROR")),
                row.get("message", ""),
                str(row.get("path", "")),
            )
        )
    return checks


def _history_status(days: int) -> str:
    if days < 60:
        return "ERROR"
    if days < 120:
        return "WARN"
    return "OK"


def _freshness_status(latest: pd.Timestamp, today: pd.Timestamp) -> str:
    if pd.isna(latest):
        return "ERROR"
    age_days = int((today - pd.Timestamp(latest.date())).days)
    return "WARN" if age_days > 5 else "OK"


def _date_text(value: pd.Timestamp) -> str:
    if pd.isna(value):
        return "暂无"
    return str(pd.Timestamp(value).date())


def _required_field_checks(label: str, frame: pd.DataFrame, required: list[str]) -> list[dict[str, object]]:
    missing = [col for col in required if col not in frame.columns]
    return [_check(f"{label}必要字段", "ERROR" if missing else "OK", "缺失：" + ",".join(missing) if missing else "齐全")]


def _market_value_checks(label: str, frame: pd.DataFrame, volume_field: str) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    if frame.empty:
        return [_check(f"{label}行情行数", "ERROR", 0, "该模块不可用或没有有效交易行")]
    dup_cols = ["date", "code"] if "code" in frame.columns else ["date"]
    duplicates = int(frame.duplicated(dup_cols).sum()) if all(col in frame.columns for col in dup_cols) else 0
    checks.append(_check(f"{label}日期代码重复行", "WARN" if duplicates else "OK", duplicates))
    for col in ["开盘价", "收盘价", "最低价", "最高价", volume_field]:
        if col not in frame.columns:
            continue
        missing = int(frame[col].isna().sum())
        checks.append(_check(f"{label}{col}空值", "WARN" if missing else "OK", missing))
    if {"开盘价", "收盘价"}.issubset(frame.columns):
        negative_price_rows = int(((frame["开盘价"] <= 0) | (frame["收盘价"] <= 0)).sum())
    else:
        negative_price_rows = len(frame)
    checks.append(_check(f"{label}非正价格行", "ERROR" if negative_price_rows else "OK", negative_price_rows))
    if volume_field in frame.columns:
        zero_volume_rows = int((pd.to_numeric(frame[volume_field], errors="coerce").fillna(0) <= 0).sum())
        checks.append(_check(f"{label}零成交量行", "WARN" if zero_volume_rows else "OK", zero_volume_rows, "零成交量行不进入指标均量计算"))
    invalid_trading_rows = int(frame.attrs.get("invalid_trading_rows", 0) or 0)
    checks.append(_check(f"{label}无效交易行过滤数", "WARN" if invalid_trading_rows else "OK", invalid_trading_rows, "open/close/high/low/volume缺失或非正的行不进入指标计算"))
    return checks


def _position_checks(positions: pd.DataFrame, universe: pd.DataFrame) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    if positions.empty:
        return [_check("ETF持仓状态", "WARN", "空表", "客户未填写持仓状态时，系统会默认没有持仓路径")]
    valid = {"holding", "closed", "flat", "watch"}
    invalid = sorted(set(positions["status"].dropna().astype(str)) - valid)
    checks.append(_check("ETF持仓状态枚举", "WARN" if invalid else "OK", ",".join(invalid) if invalid else "合法"))
    duplicates = int(positions.duplicated("code").sum())
    checks.append(_check("ETF持仓重复代码", "WARN" if duplicates else "OK", duplicates))
    if not universe.empty:
        enabled_codes = set(universe["code"].astype(str))
        outside = sorted(set(positions["code"].astype(str)) - enabled_codes)
        checks.append(_check("持仓代码是否在ETF清单内", "WARN" if outside else "OK", ",".join(outside[:8]) if outside else "全部在清单内"))
    if "position_size" in positions.columns:
        conflict = positions[
            (positions["status"].astype(str) == "holding")
            & (
                positions["position_size"].isna()
                | (positions["position_size"].astype(str).str.strip().isin(["", "nan", "None"]))
            )
        ]
        checks.append(_check("持有状态是否填写数量", "WARN" if len(conflict) else "OK", len(conflict), "持有但数量为空时仍可平仓提示，但需客户确认"))
    return checks


def _cb_checks(cb: pd.DataFrame) -> list[dict[str, object]]:
    if cb.empty:
        return [_check("可转债数据", "WARN", "暂无", "客户第三个Excel未提供或没有有效转债行")]
    checks = [_check("可转债有效行数", "OK", len(cb))]
    for col in [
        "bond_code",
        "bond_name",
        "price",
        "remaining_years",
        "conversion_premium_rate",
        "ytm",
        "deducted_profit_growth",
        "profit_growth_acceleration",
        "stock_price",
        "conversion_price",
        "redemption_trigger_ratio",
        "bond_rating",
        "sw_l1",
        "remaining_size",
    ]:
        missing = int(cb[col].isna().sum()) if col in cb.columns else len(cb)
        checks.append(_check(f"可转债{col}空值", "WARN" if missing else "OK", missing))
    if "price" in cb.columns:
        price = pd.to_numeric(cb["price"], errors="coerce")
        under_100 = int((price < 100).sum())
        risk_pool = int(((price >= 100) & (price < 140)).sum())
        checks.append(_check("100元以下可转债数量", "WARN" if under_100 else "OK", under_100, "客户倾向直接排除，低价通常不是简单便宜"))
        checks.append(_check("100-140元可转债候选池数量", "WARN" if risk_pool == 0 else "OK", risk_pool, "可转债打分只在风控后候选池内排序"))
    if "conversion_premium_rate" in cb.columns:
        premium = pd.to_numeric(cb["conversion_premium_rate"], errors="coerce")
        high_premium = int((premium >= 50).sum())
        checks.append(_check("高转股溢价率转债数量", "WARN" if high_premium else "OK", high_premium, "默认50%以上不进入普通Top10"))
    if "redemption_triggered" in cb.columns:
        triggered = int(cb["redemption_triggered"].fillna(False).astype(bool).sum())
        checks.append(_check("触发强赎价转债数量", "WARN" if triggered else "OK", triggered, "触发后需看强赎公告或不强赎公告"))
    if "redemption_announcement_date" in cb.columns:
        announced = int(cb["redemption_announcement_date"].notna().sum())
        checks.append(_check("已发强赎公告转债数量", "WARN" if announced else "OK", announced, "已发强赎公告标的不进入正常打分"))
    if "no_redemption_announcement_date" in cb.columns:
        no_redeem = int(cb["no_redemption_announcement_date"].notna().sum())
        checks.append(_check("不强赎公告转债数量", "OK", no_redeem, "可继续观察，但需关注公告时效和再次触发"))
    if "ytm" in cb.columns:
        ytm = pd.to_numeric(cb["ytm"], errors="coerce")
        high_ytm = int((ytm >= 15).sum())
        severe_negative_ytm = int((ytm <= -5).sum())
        checks.append(_check("到期收益率异常偏高数量", "WARN" if high_ytm else "OK", high_ytm, "高YTM通常指向信用或兑付风险"))
        checks.append(_check("严重负YTM转债数量", "WARN" if severe_negative_ytm else "OK", severe_negative_ytm, "默认-5%以下不进入普通Top10"))
    if "bond_rating" in cb.columns:
        rating = cb["bond_rating"].astype(str).str.upper().str.replace("STI", "", regex=False).str.strip()
        weak_rating = int(rating.isin({"A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "CC", "C", "D"}).sum())
        checks.append(_check("低评级转债数量", "WARN" if weak_rating else "OK", weak_rating, "默认A/A-及以下不进入正常打分，A+保留为中风险观察"))
    return checks
