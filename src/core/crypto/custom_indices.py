"""
加密貨幣自定義分析指數 — 組合指標 + 市場情緒 + 資金流向

自創指數：
1. Crypto Fear & Greed Index（恐懼貪婪指數）
2. Altcoin Season Index（山寨幣季指數）
3. DeFi Health Index（DeFi 健康指數）
4. Market Momentum Index（市場動量指數）
5. Whale Activity Index（鯨魚活動指數）
6. Crypto Dominance Index（市佔率指數）
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests
from src.utils.logger import logger

# ============================================================
# 1. 恐懼貪婪指數 (Fear & Greed Index)
# ============================================================


def get_fear_greed_index() -> dict:
    """
    獲取加密貨幣恐懼貪婪指數（0-100）。
    數據來源：alternative.me API

    0-25: 極度恐懼
    25-45: 恐懼
    45-55: 中性
    55-75: 貪婪
    75-100: 極度貪婪
    """
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=7",
            timeout=10,
        )
        data = resp.json().get("data", [])
        if not data:
            return {"error": "無數據"}

        current = data[0]
        history = [
            {
                "date": datetime.fromtimestamp(int(d["timestamp"])).strftime(
                    "%Y-%m-%d"
                ),
                "value": int(d["value"]),
                "label": d["value_classification"],
            }
            for d in data
        ]

        value = int(current["value"])
        label = current["value_classification"]

        # 趨勢判斷
        if len(history) >= 3:
            recent = [h["value"] for h in history[:3]]
            trend = (
                "上升"
                if recent[0] > recent[-1]
                else "下降" if recent[0] < recent[-1] else "平穩"
            )
        else:
            trend = "未知"

        return {
            "index": "fear_greed",
            "name": "恐懼貪婪指數",
            "value": value,
            "label": label,
            "trend": trend,
            "history": history,
            "source": "alternative.me",
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"恐懼貪婪指數獲取失敗: {e}")
        return {"error": str(e)}


# ============================================================
# 2. 山寨幣季指數 (Altcoin Season Index)
# ============================================================


def get_altcoin_season_index(symbols: list[str] = None) -> dict:
    """
    山寨幣季指數 — 比較山寨幣 vs BTC 的表現。

    計算邏輯：
    - 取最近 30 天各幣種漲跌幅
    - 統計跑贏 BTC 的山寨幣比例
    - 比例 > 75% = 山寨幣季
    - 比例 < 25% = BTC 季
    """
    from src.core.db import get_conn

    symbols = symbols or [
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT",
        "DOTUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "UNIUSDT",
        "LTCUSDT",
        "ATOMUSDT",
        "NEARUSDT",
        "SHIBUSDT",
        "TRXUSDT",
    ]

    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    try:
        with get_conn() as conn:
            # BTC 30 天漲跌幅
            btc_row = conn.execute(
                "SELECT MIN(close), MAX(close) FROM daily_kline WHERE code='BTCUSDT' AND date >= ?",
                (cutoff,),
            ).fetchone()
            if not btc_row or not btc_row[0]:
                return {"error": "BTC 數據不足"}

            btc_low, btc_high = btc_row
            btc_change = ((btc_high - btc_low) / btc_low * 100) if btc_low > 0 else 0

            # 各山寨幣 30 天漲跌幅
            altcoins = []
            outperform = 0
            for sym in symbols:
                row = conn.execute(
                    "SELECT MIN(close), MAX(close) FROM daily_kline WHERE code=? AND date >= ?",
                    (sym, cutoff),
                ).fetchone()
                if row and row[0] and row[0] > 0:
                    change = (row[1] - row[0]) / row[0] * 100
                    altcoins.append({"symbol": sym, "change_30d": round(change, 2)})
                    if change > btc_change:
                        outperform += 1

        total = len(altcoins)
        ratio = (outperform / total * 100) if total > 0 else 0

        if ratio >= 75:
            season = "🟢 山寨幣季"
            label = "altcoin_season"
        elif ratio >= 55:
            season = "🟡 偏向山寨幣"
            label = "lean_altcoin"
        elif ratio >= 45:
            season = "⚪ 中性"
            label = "neutral"
        elif ratio >= 25:
            season = "🟡 偏向BTC"
            label = "lean_btc"
        else:
            season = "🔴 BTC季"
            label = "btc_season"

        altcoins.sort(key=lambda x: x["change_30d"], reverse=True)

        return {
            "index": "altcoin_season",
            "name": "山寨幣季指數",
            "value": round(ratio, 1),
            "label": label,
            "season": season,
            "btc_change_30d": round(btc_change, 2),
            "outperform_count": outperform,
            "total_altcoins": total,
            "top_performers": altcoins[:5],
            "worst_performers": altcoins[-5:],
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"山寨幣季指數計算失敗: {e}")
        return {"error": str(e)}


# ============================================================
# 3. DeFi 健康指數
# ============================================================


def get_defi_health_index() -> dict:
    """
    DeFi 健康指數 — 基於 DeFi 代幣的綜合表現。

    組成：
    - LINK (預言機) 25%
    - UNI (DEX) 25%
    - AAVE (借貸) 25%
    - MKR (治理) 25%
    """
    defi_symbols = {
        "LINKUSDT": {"name": "Chainlink", "weight": 0.25, "sector": "預言機"},
        "UNIUSDT": {"name": "Uniswap", "weight": 0.25, "sector": "DEX"},
        "AAVEUSDT": {"name": "Aave", "weight": 0.25, "sector": "借貸"},
        "MKRUSDT": {"name": "Maker", "weight": 0.25, "sector": "治理"},
    }

    try:
        from src.core.crypto.client import get_crypto_realtime

        components = []
        weighted_score = 0

        for sym, info in defi_symbols.items():
            data = get_crypto_realtime(sym)
            if not data or not data.get("price"):
                continue

            change = data.get("change_pct", 0)
            # 歸一化到 0-100（-10% → 0, 0% → 50, +10% → 100）
            score = max(0, min(100, 50 + change * 5))

            components.append(
                {
                    "symbol": sym,
                    "name": info["name"],
                    "sector": info["sector"],
                    "price": data["price"],
                    "change_pct": change,
                    "score": round(score, 1),
                    "weight": info["weight"],
                }
            )
            weighted_score += score * info["weight"]

        if not components:
            return {"error": "DeFi 數據獲取失敗"}

        if weighted_score >= 70:
            health = "🟢 健康"
        elif weighted_score >= 50:
            health = "🟡 中性"
        elif weighted_score >= 30:
            health = "🟠 薄弱"
        else:
            health = "🔴 危險"

        return {
            "index": "defi_health",
            "name": "DeFi 健康指數",
            "value": round(weighted_score, 1),
            "health": health,
            "components": components,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"DeFi 健康指數計算失敗: {e}")
        return {"error": str(e)}


# ============================================================
# 4. 市場動量指數
# ============================================================


def get_market_momentum_index(symbols: list[str] = None) -> dict:
    """
    市場動量指數 — 基於多幣種的 RSI + 成交量變化。

    組成：
    - 平均 RSI (50%)
    - 成交量變化率 (30%)
    - 漲跌比 (20%)
    """
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

    try:
        from src.core.crypto.client import get_crypto_realtime

        rsi_values = []
        volume_changes = []
        up_count = 0
        total = 0

        for sym in symbols:
            data = get_crypto_realtime(sym)
            if not data or not data.get("price"):
                continue

            change = data.get("change_pct", 0)
            # 簡化 RSI 估算：基於漲跌幅
            rsi_est = max(0, min(100, 50 + change * 3))
            rsi_values.append(rsi_est)

            volume = data.get("volume", 0) or data.get("quote_volume", 0)
            volume_changes.append(volume)

            total += 1
            if change > 0:
                up_count += 1

        if not rsi_values:
            return {"error": "數據不足"}

        avg_rsi = sum(rsi_values) / len(rsi_values)
        up_ratio = (up_count / total * 100) if total > 0 else 50

        # 加權計算
        momentum = avg_rsi * 0.5 + up_ratio * 0.2 + 50 * 0.3  # 成交量默認中性

        if momentum >= 70:
            signal = "🟢 強勢上漲"
        elif momentum >= 55:
            signal = "🟡 溫和上漲"
        elif momentum >= 45:
            signal = "⚪ 盤整"
        elif momentum >= 30:
            signal = "🟡 溫和下跌"
        else:
            signal = "🔴 強勢下跌"

        return {
            "index": "market_momentum",
            "name": "市場動量指數",
            "value": round(momentum, 1),
            "signal": signal,
            "avg_rsi": round(avg_rsi, 1),
            "up_ratio": round(up_ratio, 1),
            "up_count": up_count,
            "total": total,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"市場動量指數計算失敗: {e}")
        return {"error": str(e)}


# ============================================================
# 5. 市佔率指數 (Dominance Index)
# ============================================================


def get_dominance_index() -> dict:
    """
    加密貨幣市佔率指數 — BTC/ETH/山寨幣的市佔率。
    數據來源：CoinGecko
    """
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/global",
            timeout=10,
        )
        data = resp.json().get("data", {})

        btc_dominance = data.get("market_cap_percentage", {}).get("btc", 0)
        eth_dominance = data.get("market_cap_percentage", {}).get("eth", 0)
        total_market_cap = data.get("total_market_cap", {}).get("usd", 0)
        total_volume = data.get("total_volume", {}).get("usd", 0)
        active_cryptos = data.get("active_cryptocurrencies", 0)

        alt_dominance = 100 - btc_dominance - eth_dominance

        # 趨勢判斷
        if btc_dominance > 55:
            trend = "BTC 主導"
        elif btc_dominance > 45:
            trend = "BTC 偏強"
        elif eth_dominance > 20:
            trend = "ETH 主導"
        else:
            trend = "山寨幣活躍"

        return {
            "index": "dominance",
            "name": "市佔率指數",
            "btc_dominance": round(btc_dominance, 2),
            "eth_dominance": round(eth_dominance, 2),
            "alt_dominance": round(alt_dominance, 2),
            "trend": trend,
            "total_market_cap_usd": total_market_cap,
            "total_volume_24h_usd": total_volume,
            "active_cryptos": active_cryptos,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"市佔率指數獲取失敗: {e}")
        return {"error": str(e)}


# ============================================================
# 6. 鯉魚活動指數 (基於大額交易)
# ============================================================


def get_whale_activity_index(symbols: list[str] = None) -> dict:
    """
    鯉魚活動指數 — 基於成交量異常放大判斷大戶活動。

    邏輯：
    - 成交量 > 2x 24h 平均 → 鯉魚活躍
    - 成交量 > 3x → 鯉魚極度活躍
    """
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

    try:
        from src.core.crypto.client import get_crypto_realtime

        whale_signals = []
        total_score = 0

        for sym in symbols:
            data = get_crypto_realtime(sym)
            if not data:
                continue

            volume = data.get("quote_volume", 0) or data.get("volume", 0)
            price = data.get("price", 0)
            change = data.get("change_pct", 0)

            # 成交量/市值比（簡化估算）
            # 用成交量/價格作為活躍度指標
            if price > 0:
                activity_ratio = volume / price
            else:
                activity_ratio = 0

            # 歸一化分數
            score = min(100, activity_ratio / 1000)
            total_score += score

            signal = "正常"
            if score > 80:
                signal = "🔴 極度活躍"
            elif score > 60:
                signal = "🟠 高度活躍"
            elif score > 40:
                signal = "🟡 偏高"

            whale_signals.append(
                {
                    "symbol": sym,
                    "price": price,
                    "change_pct": change,
                    "volume_usd": round(volume, 0),
                    "activity_score": round(score, 1),
                    "signal": signal,
                }
            )

        avg_score = total_score / len(whale_signals) if whale_signals else 0

        if avg_score >= 70:
            overall = "🔴 鯉魚極度活躍"
        elif avg_score >= 50:
            overall = "🟠 鯉魚活躍"
        elif avg_score >= 30:
            overall = "🟡 正常偏高"
        else:
            overall = "🟢 平靜"

        return {
            "index": "whale_activity",
            "name": "鯉魚活動指數",
            "value": round(avg_score, 1),
            "signal": overall,
            "components": whale_signals,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"鯉魚活動指數計算失敗: {e}")
        return {"error": str(e)}


# ============================================================
# 統一入口：獲取所有自定義指數
# ============================================================


def get_all_custom_indices() -> dict:
    """獲取所有自定義分析指數。"""
    indices = {}

    for name, fn in [
        ("fear_greed", get_fear_greed_index),
        ("altcoin_season", get_altcoin_season_index),
        ("defi_health", get_defi_health_index),
        ("market_momentum", get_market_momentum_index),
        ("dominance", get_dominance_index),
        ("whale_activity", get_whale_activity_index),
    ]:
        try:
            indices[name] = fn()
        except Exception as e:
            indices[name] = {"error": str(e)}

    return {
        "indices": indices,
        "count": len(indices),
        "updated_at": datetime.now().isoformat(),
    }


def get_index_by_name(name: str) -> dict:
    """按名稱獲取單個指數。"""
    index_map = {
        "fear_greed": get_fear_greed_index,
        "altcoin_season": get_altcoin_season_index,
        "defi_health": get_defi_health_index,
        "market_momentum": get_market_momentum_index,
        "dominance": get_dominance_index,
        "whale_activity": get_whale_activity_index,
    }
    fn = index_map.get(name)
    if not fn:
        return {"error": f"未知指數: {name}，可選: {list(index_map.keys())}"}
    return fn()


if __name__ == "__main__":
    result = get_all_custom_indices()
    for name, data in result["indices"].items():
        if "error" in data:
            print(f"❌ {name}: {data['error']}")
        else:
            print(
                f"✅ {name}: {data.get('value', 'N/A')} - {data.get('label', data.get('signal', data.get('health', '')))}"
            )
