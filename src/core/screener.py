"""
股票篩選器 — 基於 AKShare 數據的條件篩選
"""

import akshare as ak

from src.core.db import load_daily_kline
from src.utils.logger import logger


def get_stock_list(market: str = "all") -> list[dict]:
    """
    獲取 A 股股票列表（來自 AKShare）。

    Args:
        market: "all", "sh" (上海), "sz" (深圳)

    Returns:
        [{"code": "000001", "name": "平安銀行", "market": "sz"}, ...]
    """
    try:
        df = ak.stock_info_a_code_name()
        if df.empty:
            return []

        results = []
        for _, row in df.iterrows():
            code = str(row.get("code", ""))
            name = str(row.get("name", ""))

            if market == "sh" and not code.startswith("6"):
                continue
            if market == "sz" and not code.startswith(("0", "3")):
                continue

            mkt = "sh" if code.startswith("6") else "sz"
            results.append({"code": code, "name": name, "market": mkt})

        return results
    except Exception as e:
        logger.error(f"獲取股票列表失敗: {e}")
        return []


def screen_stocks(
    codes: list[str] = None,
    filters: dict = None,
) -> list[dict]:
    """
    篩選股票。

    Args:
        codes: 股票代碼列表，為 None 時從數據庫獲取所有
        filters: 篩選條件
            - price_change_ndays: {"days": 5, "min_pct": 5}
            - volume_surge: {"days": 5, "ratio": 2.0}
            - ma_bullish: True/False
            - above_ma: {"period": 20}
            - near_52w_high: {"pct": 5}

    Returns:
        [{"code": "000001", "name": "...", "filters_passed": [...], "data": {...}}]
    """
    if filters is None:
        filters = {}

    if codes is None:
        from src.core.db import load_all_codes

        codes = load_all_codes()

    results = []
    for code in codes:
        try:
            result = _check_stock(code, filters)
            if result:
                results.append(result)
        except Exception as e:
            logger.debug(f"篩選 {code} 失敗: {e}")

    logger.info(f"篩選完成: {len(results)}/{len(codes)} 只股票通過")
    return results


def _check_stock(code: str, filters: dict) -> dict | None:
    """檢查單只股票是否滿足所有篩選條件"""
    df = load_daily_kline(code)
    if df.empty or len(df) < 60:
        return None

    df = df.sort_values("date").reset_index(drop=True)
    passed_filters = []
    data_info = {}

    # 價格變化 N 日
    if "price_change_ndays" in filters:
        cfg = filters["price_change_ndays"]
        days = cfg.get("days", 5)
        min_pct = cfg.get("min_pct", 5)
        if len(df) >= days + 1:
            old_price = float(df.iloc[-(days + 1)]["close"])
            new_price = float(df.iloc[-1]["close"])
            change_pct = (new_price - old_price) / old_price * 100
            data_info["price_change"] = round(change_pct, 2)
            if change_pct >= min_pct:
                passed_filters.append(f"price_change_{days}d: {change_pct:.1f}%")
            else:
                return None
        else:
            return None

    # 成交量暴增
    if "volume_surge" in filters:
        cfg = filters["volume_surge"]
        days = cfg.get("days", 5)
        ratio = cfg.get("ratio", 2.0)
        if len(df) >= days + 1:
            recent_vol = float(df.iloc[-1]["volume"])
            avg_vol = df["volume"].iloc[-(days + 1) : -1].mean()
            if avg_vol > 0:
                vol_ratio = recent_vol / avg_vol
                data_info["volume_ratio"] = round(vol_ratio, 2)
                if vol_ratio >= ratio:
                    passed_filters.append(f"volume_surge: {vol_ratio:.1f}x")
                else:
                    return None
            else:
                return None
        else:
            return None

    # MA 多頭排列
    if "ma_bullish" in filters and filters["ma_bullish"]:
        if len(df) >= 60:
            from src.core.indicators.fast_indicators import compute_sma

            closes = df["close"].astype(float).to_numpy()
            ma5 = float(compute_sma(closes, 5)[-1])
            ma10 = float(compute_sma(closes, 10)[-1])
            ma20 = float(compute_sma(closes, 20)[-1])
            ma60 = float(compute_sma(closes, 60)[-1])

            if ma5 > ma10 > ma20 > ma60:
                passed_filters.append("ma_bullish: MA5>MA10>MA20>MA60")
                data_info["ma5"] = round(float(ma5), 2)
                data_info["ma10"] = round(float(ma10), 2)
                data_info["ma20"] = round(float(ma20), 2)
                data_info["ma60"] = round(float(ma60), 2)
            else:
                return None
        else:
            return None

    # 站上均線
    if "above_ma" in filters:
        cfg = filters["above_ma"]
        period = cfg.get("period", 20)
        if len(df) >= period:
            from src.core.indicators.fast_indicators import compute_sma

            closes = df["close"].astype(float).to_numpy()
            ma = float(compute_sma(closes, period)[-1])
            current_price = float(df.iloc[-1]["close"])
            data_info[f"ma{period}"] = round(float(ma), 2)
            data_info["current_price"] = round(current_price, 2)
            if current_price > ma:
                passed_filters.append(
                    f"above_ma{period}: {current_price:.2f} > {ma:.2f}"
                )
            else:
                return None
        else:
            return None

    # 接近 52 週新高
    if "near_52w_high" in filters:
        cfg = filters["near_52w_high"]
        pct = cfg.get("pct", 5)
        if len(df) >= 250:
            year_data = df.tail(250)
        else:
            year_data = df

        high_52w = float(year_data["high"].max())
        current_price = float(df.iloc[-1]["close"])
        diff_pct = (high_52w - current_price) / high_52w * 100
        data_info["high_52w"] = round(high_52w, 2)
        data_info["diff_from_high"] = round(diff_pct, 2)

        if diff_pct <= pct:
            passed_filters.append(f"near_52w_high: {diff_pct:.1f}% from {high_52w:.2f}")
        else:
            return None

    if not passed_filters:
        return None

    # 獲取股票名稱
    name = code
    try:
        from src.config import settings

        rule = settings.alert_rules.get(code, {})
        name = rule.get("name", code)
    except Exception:
        pass

    return {
        "code": code,
        "name": name,
        "filters_passed": passed_filters,
        "data": data_info,
    }
