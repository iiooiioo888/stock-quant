"""
儀表盤全球掛牌目錄 — A股 / 港股 / 美股 / 外匯 / 商品 / 加密 / ETF / 電力公用

從 global_market 同步主流可交易標的，並映射 TradingView / IB 符號。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.core.global_market import (
    COMMODITIES,
    ETFS,
    FOREX_YAHOO,
    HK_STOCKS,
    INDICES,
    US_STOCKS,
)

# ---------------------------------------------------------------------------
# 擴展：A股龍頭、電力公用、加密、外匯補充、利率
# ---------------------------------------------------------------------------

A_SHARE_LEADERS: dict[str, str] = {
    "600519.SS": "貴州茅台",
    "601318.SS": "中國平安",
    "600900.SS": "長江電力",
    "600886.SS": "國投電力",
    "600795.SS": "國電電力",
    "000858.SZ": "五糧液",
    "000333.SZ": "美的集團",
    "000001.SZ": "平安銀行",
    "300750.SZ": "寧德時代",
    "601012.SS": "隆基綠能",
}

POWER_UTILITIES: dict[str, str] = {
    # 美股電力 / 公用事業
    "NEE": "NextEra 電力",
    "DUK": "杜克能源",
    "SO": "南方公司",
    "D": "Dominion 能源",
    "AEP": "美國電力",
    "EXC": "Exelon",
    "XEL": "Xcel 能源",
    "SRE": "Sempra 能源",
    "ED": "聯合愛迪生",
    "PCG": "Pacific Gas",
    "EIX": "愛迪生國際",
    "WEC": "WEC 能源",
    "ES": "Eversource",
    "AWK": "American Water",
    # 港股公用
    "0002.HK": "中電控股",
    "0003.HK": "香港中華煤氣",
    "0836.HK": "華潤電力",
    "2688.HK": "新奧能源",
    # ETF
    "XLU": "公用事業 ETF",
    "XLE": "能源板塊 ETF",
}

CRYPTO_SYMBOLS: dict[str, str] = {
    "BTC-USD": "比特幣",
    "ETH-USD": "以太坊",
    "SOL-USD": "Solana",
    "BNB-USD": "幣安幣",
    "XRP-USD": "瑞波幣",
    "DOGE-USD": "狗狗幣",
    "ADA-USD": "Cardano",
    "AVAX-USD": "Avalanche",
}

FOREX_EXTRA: dict[str, str] = {
    "USDCNH=X": "美元/離岸人民幣",
    "USDHKD=X": "美元/港元",
    "USDSGD=X": "美元/新加坡元",
}

RATES: dict[str, str] = {
    "^TNX": "美國10年債收益率",
    "^FVX": "美國5年債收益率",
    "^IRX": "美國13周債",
}

COMMODITY_TV: dict[str, str] = {
    "GC=F": "TVC:GOLD",
    "SI=F": "TVC:SILVER",
    "CL=F": "TVC:USOIL",
    "BZ=F": "TVC:UKOIL",
    "HG=F": "COMEX:HG1!",
    "NG=F": "NYMEX:NG1!",
    "ZC=F": "CBOT:ZC1!",
    "ZS=F": "CBOT:ZS1!",
}

# 美股 NYSE 掛牌（其餘默認 NASDAQ）
_US_NYSE = frozenset({
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK",
    "WMT", "PG", "HD", "COST", "KO", "PEP", "MCD", "NKE", "TGT", "LOW", "TJX",
    "CAT", "BA", "HON", "UPS", "RTX", "GE", "MMM", "XOM", "CVX", "COP", "SLB",
    "DIS", "T", "VZ", "TMUS", "BABA", "NIO", "XPEV", "BIDU", "NEE", "DUK", "SO",
    "D", "AEP", "EXC", "XEL", "SRE", "ED", "PCG", "EIX", "WEC", "ES", "AWK",
    "XLU", "XLE", "SPY", "DIA", "GLD", "SLV", "USO", "TLT", "XLF", "EEM", "FXI",
})

# 頂欄固定展示（跨資產類別）
_TOPBAR_SYMBOLS = frozenset({
    "000001.SS", "399006.SZ", "^HSI", "^GSPC", "^IXIC", "^N225",
    "EURUSD=X", "USDCNH=X", "BTC-USD", "ETH-USD", "GC=F", "CL=F",
    "0700.HK", "AAPL", "NVDA", "XOM", "NEE", "XLU",
})


@dataclass(frozen=True)
class MarketInstrument:
    symbol: str
    name: str
    group: str
    tv: str = ""
    scanner: str = "america"
    ib: Optional[dict[str, Any]] = None
    topbar: bool = False
    asset_class: str = ""  # index | stock | forex | crypto | commodity | etf | rate


GROUP_LABELS: dict[str, str] = {
    "asia": "亞太指數",
    "a_share": "A股龍頭",
    "hk_stock": "港股",
    "us": "美歐指數",
    "us_stock": "美股",
    "europe": "歐洲指數",
    "forex": "外匯",
    "crypto": "加密貨幣",
    "commodities": "商品 · 石油/金屬/農產",
    "etf": "ETF",
    "utilities": "電力 · 公用事業 · 能源",
    "rates": "利率 · 債券",
}

GROUP_ORDER: list[str] = [
    "asia", "a_share", "hk_stock", "us", "us_stock", "europe",
    "forex", "crypto", "commodities", "utilities", "etf", "rates",
]

VALID_SCOPES = frozenset(["all", "topbar", "custom", *GROUP_ORDER])


def _hk_tv(symbol: str) -> str:
    code = symbol.upper().replace(".HK", "").lstrip("0") or "0"
    return f"HKEX:{code}"


def _us_tv(symbol: str) -> str:
    sym = symbol.upper().replace(".", "-")
    if sym in _US_NYSE or sym.replace("-", ".") in _US_NYSE:
        return f"NYSE:{sym.replace('-', '.')}"
    return f"NASDAQ:{sym.replace('-', '.')}"


def _forex_tv(symbol: str) -> str:
    pair = symbol.upper().replace("=X", "")
    return f"FX:{pair}"


def _crypto_tv(symbol: str) -> str:
    base = symbol.upper().replace("-USD", "").replace("-USDT", "")
    return f"BINANCE:{base}USDT"


def _ib_stock(symbol: str, currency: str = "USD", exchange: str = "SMART") -> dict:
    sym = symbol.split(".")[0].upper()
    return {"secType": "STK", "symbol": sym, "exchange": exchange, "currency": currency}


def _ib_a_share(sym: str) -> dict:
    """A 股 IB 合約（滬深）。"""
    code = sym.split(".")[0]
    if sym.upper().endswith(".SS"):
        return {"secType": "STK", "symbol": code, "exchange": "SSE", "currency": "CNY"}
    return {"secType": "STK", "symbol": code, "exchange": "SZSE", "currency": "CNY"}


def _ib_forex(pair: str) -> dict:
    # EURUSD=X → EUR.USD
    p = pair.upper().replace("=X", "")
    if len(p) >= 6:
        return {
            "secType": "CASH",
            "symbol": p[:3],
            "currency": p[3:6],
            "exchange": "IDEALPRO",
        }
    return {"secType": "CASH", "symbol": "EUR", "currency": "USD", "exchange": "IDEALPRO"}


def _make(
    symbol: str,
    name: str,
    group: str,
    *,
    tv: str = "",
    scanner: str = "america",
    ib: Optional[dict] = None,
    asset_class: str = "stock",
    topbar: Optional[bool] = None,
) -> MarketInstrument:
    tb = topbar if topbar is not None else symbol in _TOPBAR_SYMBOLS
    return MarketInstrument(
        symbol=symbol,
        name=name,
        group=group,
        tv=tv,
        scanner=scanner,
        ib=ib,
        topbar=tb,
        asset_class=asset_class,
    )


def _build_catalog() -> list[MarketInstrument]:
    out: list[MarketInstrument] = []
    seen: set[str] = set()

    def add(inst: MarketInstrument):
        key = inst.symbol.upper()
        if key in seen:
            return
        seen.add(key)
        out.append(inst)

    # --- 亞太指數 ---
    asia_syms = {
        "000001.SS", "399001.SZ", "399006.SZ", "^HSI", "^N225", "^KS11", "^STI", "^AXJO",
    }
    for sym, name in INDICES.items():
        if sym in asia_syms:
            tv = {"000001.SS": "SSE:000001", "399001.SZ": "SZSE:399001", "399006.SZ": "SZSE:399006",
                  "^HSI": "HKEX:HSI", "^N225": "TVC:NI225", "^KS11": "KRX:KOSPI",
                  "^STI": "SGX:STI", "^AXJO": "ASX:XJO"}.get(sym, "")
            scanner = "china" if sym.endswith((".SS", ".SZ")) else {
                "^HSI": "hongkong", "^N225": "japan", "^KS11": "korea",
            }.get(sym, "cfd")
            add(_make(sym, name, "asia", tv=tv, scanner=scanner, asset_class="index"))

    # --- 美指 ---
    us_idx = {"^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"}
    us_tv = {"^GSPC": "TVC:SPX", "^IXIC": "TVC:NDX", "^DJI": "TVC:DJI", "^RUT": "TVC:RUT", "^VIX": "TVC:VIX"}
    for sym, name in INDICES.items():
        if sym in us_idx:
            add(_make(sym, name, "us", tv=us_tv.get(sym, ""), scanner="cfd", asset_class="index"))

    # --- 歐指 ---
    eu_idx = {"^FTSE", "^GDAXI", "^FCHI"}
    eu_tv = {"^FTSE": "TVC:UKX", "^GDAXI": "XETR:DAX", "^FCHI": "EURONEXT:PX1"}
    eu_scan = {"^FTSE": "uk", "^GDAXI": "germany", "^FCHI": "france"}
    for sym, name in INDICES.items():
        if sym in eu_idx:
            add(_make(sym, name, "europe", tv=eu_tv.get(sym, ""), scanner=eu_scan.get(sym, "cfd"), asset_class="index"))

    # --- A股龍頭 ---
    for sym, name in A_SHARE_LEADERS.items():
        code = sym.split(".")[0]
        exch = "SSE" if sym.endswith(".SS") else "SZSE"
        add(_make(
            sym, name, "a_share",
            tv=f"{exch}:{code}", scanner="china",
            ib=_ib_a_share(sym),
            asset_class="stock",
        ))

    # --- 港股 ---
    for sym, name in HK_STOCKS.items():
        add(_make(
            sym, name, "hk_stock",
            tv=_hk_tv(sym), scanner="hongkong",
            ib=_ib_stock(sym, currency="HKD", exchange="SEHK"),
            asset_class="stock",
        ))

    # --- 美股 ---
    for sym, name in US_STOCKS.items():
        add(_make(
            sym, name, "us_stock",
            tv=_us_tv(sym), scanner="america",
            ib=_ib_stock(sym),
            asset_class="stock",
        ))

    # --- 外匯 ---
    all_fx = {**FOREX_YAHOO, **FOREX_EXTRA}
    for sym, name in all_fx.items():
        add(_make(
            sym, name, "forex",
            tv=_forex_tv(sym), scanner="forex",
            ib=_ib_forex(sym),
            asset_class="forex",
        ))

    # --- 加密 ---
    for sym, name in CRYPTO_SYMBOLS.items():
        add(_make(
            sym, name, "crypto",
            tv=_crypto_tv(sym), scanner="crypto",
            asset_class="crypto",
        ))

    # --- 商品 ---
    for sym, name in COMMODITIES.items():
        add(_make(
            sym, name, "commodities",
            tv=COMMODITY_TV.get(sym, f"TVC:{sym.replace('=F', '')}"),
            scanner="cfd",
            asset_class="commodity",
        ))

    # --- 電力 / 公用 / 能源（補充不在 US_STOCKS 的） ---
    for sym, name in POWER_UTILITIES.items():
        if sym.endswith(".HK"):
            add(_make(sym, name, "utilities", tv=_hk_tv(sym), scanner="hongkong",
                      ib=_ib_stock(sym, currency="HKD", exchange="SEHK"), asset_class="stock"))
        elif sym in ETFS or sym.startswith("X"):
            add(_make(sym, name, "utilities", tv=_us_tv(sym), scanner="america",
                      ib=_ib_stock(sym), asset_class="etf"))
        elif sym not in US_STOCKS:
            add(_make(sym, name, "utilities", tv=_us_tv(sym), scanner="america",
                      ib=_ib_stock(sym), asset_class="stock"))

    # --- ETF ---
    for sym, name in ETFS.items():
        if sym in seen:
            continue
        add(_make(sym, name, "etf", tv=_us_tv(sym), scanner="america",
                  ib=_ib_stock(sym), asset_class="etf"))

    # --- 利率 ---
    for sym, name in RATES.items():
        add(_make(sym, name, "rates", tv=f"TVC:{sym.lstrip('^')}", scanner="cfd", asset_class="rate"))

    return out


MARKET_INSTRUMENTS: list[MarketInstrument] = _build_catalog()
TOPBAR_INSTRUMENTS = [i for i in MARKET_INSTRUMENTS if i.topbar]
HOME_INDICES = [(i.symbol, i.name) for i in MARKET_INSTRUMENTS if i.group in ("asia", "us")][:8]


def lookup_instrument(symbol: str) -> Optional[MarketInstrument]:
    sym = str(symbol).strip().upper()
    for inst in MARKET_INSTRUMENTS:
        if inst.symbol.upper() == sym:
            return inst
    return None


def instruments_by_group() -> dict[str, list[MarketInstrument]]:
    out: dict[str, list[MarketInstrument]] = {}
    for inst in MARKET_INSTRUMENTS:
        out.setdefault(inst.group, []).append(inst)
    return out


def catalog_summary() -> dict:
    by_group = instruments_by_group()
    by_asset: dict[str, int] = {}
    for inst in MARKET_INSTRUMENTS:
        ac = inst.asset_class or "other"
        by_asset[ac] = by_asset.get(ac, 0) + 1
    return {
        "total": len(MARKET_INSTRUMENTS),
        "topbar": len(TOPBAR_INSTRUMENTS),
        "groups": {g: len(by_group.get(g, [])) for g in GROUP_ORDER if g in by_group},
        "asset_classes": by_asset,
        "group_order": GROUP_ORDER,
        "group_labels": GROUP_LABELS,
    }
