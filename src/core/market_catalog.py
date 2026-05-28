"""
儀表盤全球掛牌目錄 — A股 / 港股 / 美股 / 外匯 / 商品 / 加密 / ETF / 電力公用

從 global_market 同步主流可交易標的，並映射 TradingView / IB 符號。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TypedDict

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
    # 金融/保險/券商
    "600036.SS": "招商銀行",
    "601166.SS": "興業銀行",
    "601398.SS": "工商銀行",
    "601939.SS": "建設銀行",
    "600030.SS": "中信證券",
    "601688.SS": "華泰證券",
    "601601.SS": "中國太保",
    # 消費/醫藥
    "600887.SS": "伊利股份",
    "603288.SS": "海天味業",
    "600276.SS": "恒瑞醫藥",
    "300015.SZ": "愛爾眼科",
    # 科技/製造
    "600703.SS": "三安光電",
    "603986.SS": "兆易創新",
    "002594.SZ": "比亞迪",
    "601899.SS": "紫金礦業",
    # 白酒/食品飲料
    "000568.SZ": "瀘州老窖",
    "002304.SZ": "洋河股份",
    "600809.SS": "山西汾酒",
    "600600.SS": "青島啤酒",
    "000596.SZ": "古井貢酒",
    # 家電/消費電子
    "000651.SZ": "格力電器",
    "002415.SZ": "海康威視",
    "002475.SZ": "立訊精密",
    "000725.SZ": "京東方A",
    # 醫藥生物
    "600196.SS": "復星醫藥",
    "000963.SZ": "華東醫藥",
    "300122.SZ": "智飛生物",
    "600161.SS": "天壇生物",
    # TMT/互聯網/軟硬件
    "002230.SZ": "科大訊飛",
    "600570.SS": "恒生電子",
    "300059.SZ": "東方財富",
    "600588.SS": "用友網絡",
    # 新能源/車/材料
    "300274.SZ": "陽光電源",
    "002466.SZ": "天齊鋰業",
    "002460.SZ": "贛鋒鋰業",
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
    asset_class: str = ""  # index | stock | forex | crypto | commodity | etf | rate | structured | money_market | derivative | carbon | alternative
    sub_class: str = ""  # e.g. ABS, MBS, CMBS, CLO, IRS, TRS, Repo, NCD, CCER, CEA...
    market: str = "exchange"  # exchange | interbank | otc | registry
    exchange: str = ""  # SSE/SZSE/HKEX/NYSE/NASDAQ/SHFE/CFFEX/... (if applicable)
    currency: str = ""  # CNY/HKD/USD...
    settlement: str = ""  # T+0/T+1/OTC/physical/cash...
    regulator: str = ""  # CSRC/PBOC/NAFMII/NFRA/SAC/CBIRC... (string tag)
    detail_supported: bool = True  # whether /api/assets/detail is expected to work


class PriceSource(TypedDict, total=False):
    id: str
    name: str
    url: str
    kind: str  # price | valuation | registry | disclosure
    authority: str  # official | licensed | authoritative
    auth: str  # public | login | institution
    note: str


PRICE_SOURCES: dict[str, PriceSource] = {
    # 交易所/集中市場（官方）
    "SSE": {"id": "SSE", "name": "上交所", "url": "https://www.sse.com.cn", "kind": "price", "authority": "official", "auth": "public"},
    "SZSE": {"id": "SZSE", "name": "深交所", "url": "https://www.szse.cn", "kind": "price", "authority": "official", "auth": "public"},
    "BSE": {"id": "BSE", "name": "北交所", "url": "https://www.bse.cn", "kind": "price", "authority": "official", "auth": "public"},
    "SHFE": {"id": "SHFE", "name": "上期所", "url": "https://www.shfe.com.cn", "kind": "price", "authority": "official", "auth": "public"},
    "CFFEX": {"id": "CFFEX", "name": "中金所", "url": "https://www.cffex.com.cn", "kind": "price", "authority": "official", "auth": "public"},
    "DCE": {"id": "DCE", "name": "大商所", "url": "https://www.dce.com.cn", "kind": "price", "authority": "official", "auth": "public"},
    "CZCE": {"id": "CZCE", "name": "郑商所", "url": "https://www.czce.com.cn", "kind": "price", "authority": "official", "auth": "public"},
    "HKEX": {"id": "HKEX", "name": "港交所", "url": "https://www.hkex.com.hk", "kind": "price", "authority": "official", "auth": "public"},

    # 銀行間/估值（權威）
    "CHINAMONEY": {"id": "CHINAMONEY", "name": "中國貨幣網", "url": "https://www.chinamoney.com.cn", "kind": "price", "authority": "official", "auth": "public"},
    "CHINABOND": {"id": "CHINABOND", "name": "中國債券信息網(中債)", "url": "https://www.chinabond.com.cn", "kind": "valuation", "authority": "authoritative", "auth": "public"},

    # 監管/登記/披露（官方/權威）
    "CHINAWEALTH": {"id": "CHINAWEALTH", "name": "中國理財網(登記查詢)", "url": "https://www.chinawealth.com.cn", "kind": "registry", "authority": "official", "auth": "public"},
    "IACHINA": {"id": "IACHINA", "name": "保險行業協會(產品公示)", "url": "https://www.iachina.cn", "kind": "disclosure", "authority": "authoritative", "auth": "public"},
    "AMAC": {"id": "AMAC", "name": "基金業協會(備案/管理人)", "url": "https://www.amac.org.cn", "kind": "registry", "authority": "official", "auth": "public"},

    # 貴金屬（官方）
    "SGE": {"id": "SGE", "name": "上海黃金交易所", "url": "https://www.sge.com.cn", "kind": "price", "authority": "official", "auth": "public"},
}


def _ps(*ids: str) -> list[PriceSource]:
    out: list[PriceSource] = []
    for i in ids:
        s = PRICE_SOURCES.get(i)
        if s:
            out.append(s)
    return out


def map_price_sources(inst: MarketInstrument) -> tuple[list[PriceSource], str]:
    """
    依資產元資料產生「可查價/可估值」的權威渠道映射（不做抓取，只做合規入口與口徑提示）。
    回傳：(sources, pricing_note)
    """
    g = (inst.group or "").strip()
    ac = (inst.asset_class or "").strip()
    mkt = (inst.market or "").strip() or "exchange"

    # 交易所產品：以交易所官方為首選入口
    if mkt == "exchange":
        ex = (inst.exchange or "").strip()
        if ex:
            return _ps(ex), "交易所產品：以交易所官方口徑為準；個人實時成交價通常在券商端查看。"
        # fallback by group
        if g in ("a_share",):
            return _ps("SSE", "SZSE"), "A股：交易所官方披露為準；實時行情以持牌券商端為准。"
        if g in ("hk_stock",):
            return _ps("HKEX"), "港股：交易所披露/行情為準；實時行情以持牌券商端為准。"
        if g in ("commodities",):
            return _ps("SHFE", "DCE", "CZCE", "CFFEX"), "期貨/商品：交易所或期貨公司持牌渠道。"
        return _ps("SSE", "SZSE", "HKEX"), "交易所產品：以交易所/持牌交易端口徑為準。"

    # 銀行間：價格/利率在 ChinaMoney，估值在 ChinaBond
    if mkt == "interbank":
        return _ps("CHINAMONEY", "CHINABOND"), "銀行間市場：交易/利率口徑可參考中國貨幣網；估值口徑以中債為準。"

    # OTC：多為機構協議定價；提供權威信息入口 + 口徑提示
    if mkt == "otc":
        # structured / derivatives: generally institution-only pricing
        if ac in ("derivative", "structured", "money_market"):
            return _ps("CHINAMONEY", "CHINABOND"), "OTC/協議定價：多需機構報價或交易對手報價；此處提供權威市場信息/估值入口。"
        return _ps("CHINAMONEY"), "OTC：多為協議定價，請以持牌機構/交易對手報價為準。"

    # registry/disclosure type assets
    if mkt == "registry":
        if g in ("alternative",):
            return _ps("CHINAMONEY"), "登記/配額類資產：價格視交易機制與合規資格而定；此處提供權威信息入口。"
        return _ps("CHINAMONEY"), "登記/信息類口徑：以官方/權威披露為準。"

    return [], "暫無權威定價來源映射。"

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
    # 機構級/系統級擴展（多為 OTC/登記信息/機構市場口徑）
    "structured": "資產證券化 · 結構化",
    "interbank": "銀行間 · 貨幣市場",
    "otc": "場外衍生品 · 協議定價",
    "crossborder": "跨境互聯互通 · 特殊債",
    "alternative": "另類資產 · 碳資產",
}

GROUP_ORDER: list[str] = [
    "asia", "a_share", "hk_stock", "us", "us_stock", "europe",
    "forex", "crypto", "commodities", "utilities", "etf", "rates",
    "structured", "interbank", "otc", "crossborder", "alternative",
]

VALID_SCOPES = frozenset(["all", "topbar", "custom", *GROUP_ORDER])

ASSET_CLASS_LABELS: dict[str, str] = {
    "index": "指數",
    "stock": "股票",
    "forex": "外匯",
    "crypto": "加密",
    "commodity": "商品",
    "etf": "ETF",
    "rate": "利率",
    "structured": "結構化",
    "money_market": "貨幣市場",
    "derivative": "衍生品",
    "carbon": "碳資產",
    "alternative": "另類",
    "other": "其他",
}


def derive_l2(inst: MarketInstrument) -> tuple[str, str]:
    """二級分類：以 asset_class 為主（穩定、可跨 group 共用）。"""
    key = (inst.asset_class or "other").strip() or "other"
    return key, ASSET_CLASS_LABELS.get(key, key)


def derive_l3(inst: MarketInstrument) -> tuple[str, str]:
    """
    三級分類：同一套 key 在不同 asset_class 下含義不同。
    - stock/etf: 交易所（SSE/SZSE/HKEX/NYSE/NASDAQ）
    - index: 分區（由 group 近似）
    - commodity: 能源/貴金屬/工業金屬/農產（依符號粗分）
    - forex: 報價幣別（USD/CNH/HKD/SGD...）
    - crypto: 以計價幣別（USD/USDT 等，這裡預設 USD）
    - rate: 國別（目前主要為 US）
    """
    ac = (inst.asset_class or "other").strip() or "other"
    sym = (inst.symbol or "").upper()

    if ac in ("stock", "etf"):
        # A 股
        if sym.endswith(".SS"):
            return "SSE", "上交所"
        if sym.endswith(".SZ"):
            return "SZSE", "深交所"
        # 港股
        if sym.endswith(".HK"):
            return "HKEX", "港交所"
        # 美股：簡化為 NYSE / NASDAQ（與 TV/IB 一致）
        us_sym = sym.replace(".", "-")
        if us_sym in _US_NYSE or us_sym.replace("-", ".") in _US_NYSE:
            return "NYSE", "NYSE"
        return "NASDAQ", "NASDAQ"

    if ac == "forex":
        # EURUSD=X → USD
        pair = sym.replace("=X", "")
        if len(pair) >= 6:
            quote = pair[3:6]
            return quote, quote
        return "USD", "USD"

    if ac == "crypto":
        # BTC-USD / ETH-USD → USD
        if sym.endswith("-USD"):
            return "USD", "USD"
        if sym.endswith("-USDT"):
            return "USDT", "USDT"
        return "USD", "USD"

    if ac == "commodity":
        base = sym.replace("=F", "")
        if base in ("CL", "BZ", "NG"):
            return "energy", "能源"
        if base in ("GC", "SI"):
            return "precious", "貴金屬"
        if base in ("HG",):
            return "industrial", "工業金屬"
        if base in ("ZC", "ZS"):
            return "agri", "農產"
        return "other", "其他"

    if ac == "rate":
        return "US", "美國"

    if ac == "index":
        # 用 group 做近似分區（避免引入新的資料依賴）
        if inst.group in ("asia", "a_share", "hk_stock"):
            return "asia", "亞太"
        if inst.group in ("us", "us_stock"):
            return "us", "美國"
        if inst.group in ("europe",):
            return "europe", "歐洲"
        return "global", "全球"

    return "other", "其他"


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
    sub_class: str = "",
    market: str = "exchange",
    exchange: str = "",
    currency: str = "",
    settlement: str = "",
    regulator: str = "",
    detail_supported: bool = True,
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
        sub_class=sub_class,
        market=market,
        exchange=exchange,
        currency=currency,
        settlement=settlement,
        regulator=regulator,
        detail_supported=detail_supported,
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

    # --- 機構級：Asset Universe v1（規則生成，統一元資料；多數不可直接查詳情/定價） ---
    # structured: 200
    abs_types = [
        ("ABS_SUPPLYCHAIN", "企業ABS·供應鏈"),
        ("ABS_LEASING", "企業ABS·融資租賃"),
        ("CMBS", "企業ABS·CMBS"),
        ("MBS", "信貸ABS·MBS"),
        ("CLO", "信貸ABS·CLO"),
    ]
    abs_underlyings = [
        ("receivable", "應收帳款"), ("auto_loan", "車貸"), ("consumer_loan", "消費金融"),
        ("mortgage", "按揭"), ("infrastructure", "基建收益"), ("commercial_property", "商業地產"),
        ("credit_card", "信用卡"), ("sme_loan", "小微貸"), ("green_energy", "綠能資產"),
        ("ip_rights", "知識產權"),
    ]
    abs_tenors = ["3M", "6M", "1Y", "2Y"]
    for sc, scn in abs_types:
        for uk, ucn in abs_underlyings:
            for t in abs_tenors:
                add(_make(
                    f"CN_STRUCT_{sc}_{uk.upper()}_{t}",
                    f"{scn}·{ucn}·{t}（占位）",
                    "structured",
                    asset_class="structured",
                    sub_class=sc,
                    market="otc" if sc in ("ABS_SUPPLYCHAIN", "ABS_LEASING", "CMBS") else "interbank",
                    currency="CNY",
                    settlement="OTC",
                    regulator="PBOC/NAFMII/CSRC",
                    detail_supported=False,
                ))

    # interbank: 300
    mm_products = [
        ("REPO", "回購"), ("NCD", "同業存單"), ("CD", "大額存單"),
        ("CP", "商業票據"), ("IB_LOAN", "同業拆借"),
    ]
    mm_tenors = ["O/N", "7D", "14D", "1M", "2M", "3M", "6M", "9M", "1Y", "2Y"]
    mm_curves = ["R001", "R007", "DR001", "DR007", "SHIBOR"]
    # 5 * 10 * 6 = 300 (每個產品配 6 條曲線/口徑)
    for (k, kn) in mm_products:
        for t in mm_tenors:
            for c in mm_curves + ["NCD"]:
                add(_make(
                    f"CN_IB_{k}_{c}_{t}".replace("/", ""),
                    f"{kn}·{c}·{t}（占位）",
                    "interbank",
                    asset_class="money_market",
                    sub_class=k,
                    market="interbank",
                    currency="CNY",
                    settlement="T+0" if k == "REPO" else "OTC",
                    regulator="PBOC/NAFMII",
                    detail_supported=False,
                ))

    # otc: 400
    # IRS 120 = 3 refs * 2 pay/recv * 20 tenors
    irs_refs = [("FR007", "FR007"), ("SHIBOR3M", "Shibor3M"), ("LPR1Y", "LPR1Y")]
    irs_dirs = [("PAY", "付固定"), ("REC", "收固定")]
    irs_tenors = ["1M", "3M", "6M", "9M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "15Y", "20Y", "25Y", "30Y", "18M", "12M", "8Y", "6Y", "9Y"]
    for r, rcn in irs_refs:
        for d, dcn in irs_dirs:
            for t in irs_tenors:
                add(_make(
                    f"CN_OTC_IRS_{r}_{d}_{t}",
                    f"IRS·{rcn}·{dcn}·{t}（占位）",
                    "otc",
                    asset_class="derivative",
                    sub_class="IRS",
                    market="otc",
                    currency="CNY",
                    settlement="OTC",
                    regulator="PBOC/NAFMII",
                    detail_supported=False,
                ))

    # FX Forwards 100 = 10 pairs * 10 tenors
    fx_pairs = ["USDCNY", "USDCNH", "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDHKD", "USDSGD", "USDCHF", "USDCAD"]
    fx_tenors = ["1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y", "18M", "2Y"]
    for p in fx_pairs:
        for t in fx_tenors:
            add(_make(
                f"CN_OTC_FXFWD_{p}_{t}",
                f"外匯遠期·{p}·{t}（占位）",
                "otc",
                asset_class="derivative",
                sub_class="FX_FWD",
                market="otc",
                currency=p[-3:],  # quote currency (approx)
                settlement="OTC",
                regulator="PBOC/SAFE",
                detail_supported=False,
            ))

    # TRS 100 = 10 underlyings * 10 tenors
    trs_under = ["CSI300", "HSI", "HSTECH", "SPX", "NDX", "US10Y", "GOLD", "OIL", "BTC", "CN_A50"]
    trs_tenors = ["1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y", "18M", "2Y"]
    for u in trs_under:
        for t in trs_tenors:
            add(_make(
                f"CN_OTC_TRS_{u}_{t}",
                f"TRS·{u}·{t}（占位）",
                "otc",
                asset_class="derivative",
                sub_class="TRS",
                market="otc",
                currency="CNY",
                settlement="OTC",
                regulator="CSRC/SAC",
                detail_supported=False,
            ))

    # OTC Options 80 = 8 underlyings * 10 tenors
    opt_under = ["CSI300", "HSI", "HSTECH", "SPX", "NDX", "USDCNH", "GOLD", "OIL"]
    opt_tenors = ["1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y", "18M", "2Y"]
    for u in opt_under:
        for t in opt_tenors:
            add(_make(
                f"CN_OTC_OPT_{u}_{t}",
                f"場外期權·{u}·{t}（占位）",
                "otc",
                asset_class="derivative",
                sub_class="OTC_OPTION",
                market="otc",
                currency="CNY",
                settlement="OTC",
                regulator="CSRC/SAC",
                detail_supported=False,
            ))

    # crossborder: 150 = 5 channels * 5 types * 6 variants
    cb_channels = [
        ("STOCK_CONNECT", "滬深港通"),
        ("BOND_CONNECT", "債券通"),
        ("SWAP_CONNECT", "互換通"),
        ("WEALTH_CONNECT", "跨境理財通"),
        ("GDR", "GDR"),
    ]
    cb_types = [
        ("ELIGIBLE", "合資格標的"),
        ("FLOW", "資金流口徑"),
        ("SETTLEMENT", "結算口徑"),
        ("FX_HEDGE", "匯率對沖"),
        ("REGISTRY", "登記口徑"),
    ]
    cb_variants = ["V1", "V2", "V3", "V4", "V5", "V6"]
    for ck, cn in cb_channels:
        for tk, tn in cb_types:
            for v in cb_variants:
                add(_make(
                    f"CN_CB_{ck}_{tk}_{v}",
                    f"{cn}·{tn}·{v}（占位）",
                    "crossborder",
                    asset_class="other" if ck != "SWAP_CONNECT" else "derivative",
                    sub_class=ck,
                    market="registry",
                    currency="CNY",
                    settlement="OTC",
                    regulator="PBOC/HKMA/CSRC",
                    detail_supported=False,
                ))

    # alternative: 200 = 4 categories * 10 regions * 5 vintages
    alt_cats = [
        ("CEA", "碳配額 CEA", "carbon"),
        ("CCER", "自願減排 CCER", "carbon"),
        ("GEC", "綠證", "alternative"),
        ("DATA_IP", "數據/知產資產", "alternative"),
    ]
    alt_regions = ["NATIONAL", "BJ", "SH", "SZ", "GZ", "TJ", "CQ", "HB", "HN", "SC"]
    alt_vint = ["2022", "2023", "2024", "2025", "2026"]
    for ak, an, ac in alt_cats:
        for r in alt_regions:
            for y in alt_vint:
                add(_make(
                    f"CN_ALT_{ak}_{r}_{y}",
                    f"{an}·{r}·{y}（占位）",
                    "alternative",
                    asset_class=ac,
                    sub_class=ak,
                    market="registry",
                    currency="CNY",
                    settlement="OTC",
                    regulator="MEE/NDRC/NFRA",
                    detail_supported=False,
                ))

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
