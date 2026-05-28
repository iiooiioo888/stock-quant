"""
股票主題包 — 恒生科技、滬深300 核心等一鍵篩選。

符號與資產庫 catalog 一致（如 600519.SS、0700.HK、AAPL）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePack:
    id: str
    label: str
    description: str
    symbols: frozenset[str]


def _s(*codes: str) -> frozenset[str]:
    return frozenset(c.strip().upper() for c in codes if c)


# 恒生科技指數主要成分（與本地 HK 庫交集；可隨指數調整擴充）
_HSTECH = _s(
    "0700.HK", "9988.HK", "3690.HK", "9618.HK", "1810.HK", "1024.HK", "9999.HK",
    "9888.HK", "9626.HK", "2015.HK", "9868.HK", "1211.HK", "2269.HK", "0981.HK",
    "1347.HK", "0285.HK", "0763.HK", "0992.HK", "2382.HK", "6690.HK", "9961.HK",
    "0175.HK", "2020.HK", "9992.HK", "3692.HK", "1177.HK", "1093.HK",
)

# 滬深300 核心權重（代表型龍頭，非完整 300 成分）
_CSI300_CORE = _s(
    "600519.SS", "601318.SS", "600036.SS", "000858.SZ", "300750.SZ", "601012.SS",
    "000333.SZ", "601888.SS", "600900.SS", "601166.SS", "601398.SS", "601288.SS",
    "601328.SS", "600276.SS", "002594.SZ", "300059.SZ", "600030.SS", "601688.SS",
    "000001.SZ", "601857.SS", "600028.SS", "601088.SS", "601225.SS", "600031.SS",
    "601668.SS", "601390.SS", "600048.SS", "000002.SZ", "688981.SS", "688012.SS",
    "603501.SS", "688111.SS", "300124.SZ", "002415.SZ", "600887.SS", "603288.SS",
    "002352.SZ", "601728.SS", "600050.SS", "601211.SS", "600104.SS", "601633.SS",
    "002714.SZ", "688036.SS", "002460.SZ", "300274.SZ", "600588.SS", "600570.SS",
)

# 創業板 / 成長
_CHINEXT_CORE = _s(
    "300750.SZ", "300059.SZ", "300015.SZ", "300274.SZ", "300124.SZ", "300122.SZ",
    "002594.SZ", "300014.SZ", "688981.SS", "688012.SS", "688111.SS", "688036.SS",
)

# 高股息央企能源
_DIVIDEND_CN = _s(
    "601088.SS", "601225.SS", "601857.SS", "600028.SS", "600900.SS", "600886.SS",
    "600795.SS", "601398.SS", "601288.SS", "601939.SS", "601328.SS", "601166.SS",
    "601728.SS", "600050.SS",
)

# 美股科技七巨頭 + 半導體
_US_MAG7 = _s("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA")

_US_SEMIS = _s(
    "NVDA", "AMD", "INTC", "AVGO", "QCOM", "TXN", "AMAT", "MU", "LRCX", "KLAC",
    "TSM", "ASML", "MRVL", "ON", "NXPI", "ARM", "SMCI",
)

# 中概 / ADR
_US_CHINA = _s(
    "BABA", "JD", "PDD", "NIO", "LI", "XPEV", "BIDU", "BILI", "IQ", "TME",
    "FUTU", "TIGR", "KC", "MNSO",
)

# 恒指藍籌（金融+地產+能源）
_HSI_BLUE = _s(
    "0700.HK", "0005.HK", "1299.HK", "2318.HK", "0939.HK", "1398.HK", "3988.HK",
    "0388.HK", "0941.HK", "0857.HK", "0883.HK", "0386.HK", "0016.HK", "1109.HK",
    "0823.HK", "0002.HK", "0003.HK", "2628.HK",
)

THEME_PACKS: dict[str, ThemePack] = {
    "hstech": ThemePack(
        "hstech",
        "恒生科技",
        "港股科技與平台龍頭（恒生科技指數代表成分）",
        _HSTECH,
    ),
    "csi300": ThemePack(
        "csi300",
        "滬深300核心",
        "滬深300 高權重龍頭（精選核心，非完整 300 檔）",
        _CSI300_CORE,
    ),
    "chinext": ThemePack(
        "chinext",
        "創業成長",
        "創業板與硬科技成長代表",
        _CHINEXT_CORE,
    ),
    "dividend_cn": ThemePack(
        "dividend_cn",
        "A股高股息",
        "央企能源、大行與公用高股息標的",
        _DIVIDEND_CN,
    ),
    "us_mag7": ThemePack(
        "us_mag7",
        "美股七巨頭",
        "Magnificent 7 大型科技",
        _US_MAG7,
    ),
    "us_semis": ThemePack(
        "us_semis",
        "美股半導體",
        "半導體設計、設備與代工鏈",
        _US_SEMIS,
    ),
    "us_china": ThemePack(
        "us_china",
        "中概ADR",
        "美股上市的中國概念股",
        _US_CHINA,
    ),
    "hsi_blue": ThemePack(
        "hsi_blue",
        "恒指藍籌",
        "恒生指數金融、地產、能源與電訊藍籌",
        _HSI_BLUE,
    ),
}

THEME_PACK_ORDER: list[str] = [
    "hstech", "csi300", "hsi_blue", "chinext", "dividend_cn",
    "us_mag7", "us_semis", "us_china",
]


def themes_for_symbol(symbol: str) -> list[str]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return []
    out: list[str] = []
    for tid in THEME_PACK_ORDER:
        pack = THEME_PACKS.get(tid)
        if pack and sym in pack.symbols:
            out.append(tid)
    return out


def theme_packs_payload() -> list[dict]:
    return [
        {
            "id": p.id,
            "label": p.label,
            "description": p.description,
            "count": len(p.symbols),
        }
        for pid in THEME_PACK_ORDER
        if (p := THEME_PACKS.get(pid))
    ]


def count_themes_in_catalog(symbols: list[str]) -> dict[str, int]:
    counts = {tid: 0 for tid in THEME_PACK_ORDER}
    for sym in symbols:
        for tid in themes_for_symbol(sym):
            counts[tid] = counts.get(tid, 0) + 1
    return counts
