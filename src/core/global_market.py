"""
全球股票 & 指數數據模塊 — Yahoo Finance（免費，無需 API Key）
支持：美股、港股、日股、歐股、全球指數、ETF、商品期貨
"""

import time
from datetime import datetime

import pandas as pd
import requests

from src.core.yahoo_finance import (
    yahoo_chart as _yahoo_chart,
)
from src.core.yahoo_finance import (
    yahoo_quote as _yahoo_quote,
)
from src.utils.logger import logger

MAX_RETRIES = 3
RETRY_DELAY = 2

# 失敗符號緩存：避免重複嘗試已知失敗的符號
_failed_symbols: dict[str, float] = {}  # {symbol: fail_timestamp}
_FAILED_COOLDOWN = 3600  # 失敗後冷卻 1 小時再重試

# 通用 Session（用於非 Yahoo 數據源）
_http_session = requests.Session()
_http_session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    }
)


# ============================================================
# 備選數據源 1：新浪全球行情（免費，無需 API Key）
# ============================================================
def _sina_global_quote(symbol: str) -> dict:
    """
    新浪全球行情（免費 HTTP 接口）。

    支持格式：
    - 美股: hq.sinajs.cn/list=gb_aapl
    - 港股: hq.sinajs.cn/list=rt_hk00700
    - 外匯: hq.sinajs.cn/list=fx_seurusd
    """
    # 判斷 symbol 類型並構造新浪代碼
    sina_code = _to_sina_code(symbol)
    if not sina_code:
        return {}

    try:
        url = f"https://hq.sinajs.cn/list={sina_code}"
        resp = _http_session.get(url, timeout=8)
        resp.encoding = "gbk"
        text = resp.text.strip()

        if "=" not in text or '""' in text:
            return {}

        data_str = text.split('="')[1].rstrip('";')
        parts = data_str.split(",")

        # 美股格式：gb_aapl
        if sina_code.startswith("gb_"):
            if len(parts) < 18:
                return {}
            name = parts[0]
            price = float(parts[1] or 0)
            change_pct = float(parts[2] or 0)
            change = float(parts[3] or 0)
            prev_close = float(parts[26] or 0) if len(parts) > 26 else price
            open_p = float(parts[5] or 0) if len(parts) > 5 else 0
            high = float(parts[6] or 0) if len(parts) > 6 else 0
            low = float(parts[7] or 0) if len(parts) > 7 else 0
            volume = float(parts[10] or 0) if len(parts) > 10 else 0

            return {
                "symbol": symbol,
                "name": name,
                "price": round(price, 4),
                "change_pct": round(change_pct, 2),
                "change": round(change, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "volume": int(volume),
                "prev_close": round(prev_close, 4),
                "open": round(open_p, 4),
                "currency": "USD",
                "source": "sina",
            }

        # 港股格式：rt_hk00700
        elif sina_code.startswith("rt_hk"):
            if len(parts) < 15:
                return {}
            name = parts[1]
            price = float(parts[6] or 0)
            change_pct = float(parts[8] or 0)
            change = float(parts[7] or 0)
            prev_close = float(parts[3] or 0)
            open_p = float(parts[2] or 0)
            high = float(parts[4] or 0)
            low = float(parts[5] or 0)
            volume = float(parts[11] or 0) if len(parts) > 11 else 0

            return {
                "symbol": symbol,
                "name": name,
                "price": round(price, 4),
                "change_pct": round(change_pct, 2),
                "change": round(change, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "volume": int(volume),
                "prev_close": round(prev_close, 4),
                "open": round(open_p, 4),
                "currency": "HKD",
                "source": "sina",
            }

        # 外匯格式：fx_seurusd
        elif sina_code.startswith("fx_s"):
            if len(parts) < 10:
                return {}
            price = float(parts[1] or 0)
            change_pct = float(parts[2] or 0)
            prev_close = float(parts[3] or 0)
            open_p = float(parts[4] or 0) if len(parts) > 4 else 0
            high = float(parts[5] or 0) if len(parts) > 5 else 0
            low = float(parts[6] or 0) if len(parts) > 6 else 0

            return {
                "symbol": symbol,
                "name": symbol,
                "price": round(price, 6),
                "change_pct": round(change_pct, 2),
                "change": round(price - prev_close, 6) if prev_close else 0,
                "high": round(high, 6),
                "low": round(low, 6),
                "volume": 0,
                "prev_close": round(prev_close, 6),
                "open": round(open_p, 6),
                "source": "sina",
            }

    except Exception as e:
        logger.debug(f"新浪全球行情 {symbol} 失敗: {e}")

    return {}


def _to_sina_code(symbol: str) -> str:
    """將 Yahoo Finance 代碼轉為新浪格式"""
    s = symbol.upper().strip()

    # 港股：0700.HK → rt_hk00700
    if s.endswith(".HK"):
        num = s.replace(".HK", "").zfill(5)
        return f"rt_hk{num}"

    # 外匯：EURUSD=X → fx_seurusd
    if s.endswith("=X"):
        pair = s.replace("=X", "").lower()
        return f"fx_s{pair}"

    # 商品期貨：不支持
    if s.endswith("=F"):
        return ""

    # 指數：不支持大部分
    if s.startswith("^"):
        return ""

    # 美股：AAPL → gb_aapl
    if s.isalpha() or ("-" in s and s.replace("-", "").isalpha()):
        return f"gb_{s.lower()}"

    # A 股
    if s.isdigit() and len(s) == 6:
        if s.startswith("6"):
            return f"sh{s}"
        else:
            return f"sz{s}"

    return ""


# ============================================================
# 備選數據源 2：東方財富全球行情（免費，無需 API Key）
# ============================================================
def _em_global_quote(symbol: str) -> dict:
    """
    東方財富全球行情（push2 接口）。

    支持美股、港股、全球指數。
    secid 格式：105.AAPL (美股), 116.00700 (港股), 100.^GSPC (指數)
    """
    secid = _to_em_secid(symbol)
    if not secid:
        return {}

    try:
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f169,f170,f171",
            "ut": "fa5fd1943c7b386f172d6893dbbd1",
        }
        resp = _http_session.get(url, params=params, timeout=8)
        data = resp.json().get("data", {})

        if not data:
            return {}

        # 東財的價格是整數，需要除以某個因子
        price = data.get("f43", 0)
        prev_close = data.get("f44", 0) or data.get("f60", 0)
        open_p = data.get("f46", 0)
        high = data.get("f44", 0)
        low = data.get("f45", 0)
        change_pct = data.get("f170", 0)
        change = data.get("f169", 0)
        volume = data.get("f47", 0)
        name = data.get("f58", "")

        # 判斷價格因子（美股是美元，需要 /1000）
        if symbol.isalpha() or ("-" in symbol):
            divisor = 1000.0
        else:
            divisor = 100.0

        price_f = price / divisor if price else 0
        prev_f = prev_close / divisor if prev_close else 0

        return {
            "symbol": symbol,
            "name": name,
            "price": round(price_f, 4),
            "change_pct": round(change_pct / 100, 2) if change_pct else 0,
            "change": round(change / divisor, 4) if change else 0,
            "high": round(high / divisor, 4) if high else 0,
            "low": round(low / divisor, 4) if low else 0,
            "volume": int(volume) if volume else 0,
            "prev_close": round(prev_f, 4),
            "open": round(open_p / divisor, 4) if open_p else 0,
            "source": "eastmoney",
        }

    except Exception as e:
        logger.debug(f"東財全球行情 {symbol} 失敗: {e}")

    return {}


def _to_em_secid(symbol: str) -> str:
    """將 Yahoo Finance 代碼轉為東財 secid"""
    s = symbol.upper().strip()

    # 港股：0700.HK → 116.00700
    if s.endswith(".HK"):
        num = s.replace(".HK", "").zfill(5)
        return f"116.{num}"

    # 美股：AAPL → 105.AAPL
    if s.isalpha() or ("-" in s and s.replace("-", "").isalpha()):
        return f"105.{s}"

    # 指數：^GSPC → 100.GSPC（部分支持）
    if s.startswith("^"):
        return f"100.{s[1:]}"

    return ""


# ============================================================
# 備選數據源 3：Twelve Data（免費 800 次/天，無需 Key 有限額）
# ============================================================
_TWELVE_BASE = "https://api.twelvedata.com"


def _twelve_quote(symbol: str) -> dict:
    """
    Twelve Data 實時行情（免費層 800 次/天，8 次/分鐘）。
    支持：美股、外匯、加密貨幣。
    """
    try:
        url = f"{_TWELVE_BASE}/quote"
        params = {"symbol": symbol}
        resp = _http_session.get(url, params=params, timeout=8)
        data = resp.json()

        if data.get("status") == "error":
            return {}

        price = float(data.get("close", 0) or 0)
        if price <= 0:
            return {}

        return {
            "symbol": symbol,
            "name": data.get("name", symbol),
            "price": price,
            "change_pct": round(float(data.get("percent_change", 0) or 0), 2),
            "change": round(float(data.get("change", 0) or 0), 4),
            "high": round(float(data.get("high", 0) or 0), 4),
            "low": round(float(data.get("low", 0) or 0), 4),
            "volume": int(float(data.get("volume", 0) or 0)),
            "prev_close": round(float(data.get("previous_close", 0) or 0), 4),
            "open": round(float(data.get("open", 0) or 0), 4),
            "currency": data.get("currency", "USD"),
            "source": "twelvedata",
        }

    except Exception as e:
        logger.debug(f"Twelve Data {symbol} 失敗: {e}")

    return {}


# ====== 美股熱門 ======
US_STOCKS = {
    # 科技巨頭
    "AAPL": "蘋果",
    "MSFT": "微軟",
    "GOOGL": "谷歌",
    "AMZN": "亞馬遜",
    "NVDA": "英偉達",
    "META": "Meta",
    "TSLA": "特斯拉",
    "NFLX": "Netflix",
    "AMD": "AMD",
    "INTC": "英特爾",
    "CRM": "Salesforce",
    "ADBE": "Adobe",
    "ORCL": "甲骨文",
    "CSCO": "思科",
    "AVGO": "博通",
    "QCOM": "高通",
    "TXN": "德州儀器",
    "NOW": "ServiceNow",
    "INTU": "Intuit",
    "AMAT": "應用材料",
    "MU": "美光",
    "LRCX": "科林研發",
    "KLAC": "科磊",
    "SNOW": "Snowflake",
    "PLTR": "Palantir",
    "COIN": "Coinbase",
    "ABNB": "Airbnb",
    "UBER": "優步",
    "LYFT": "Lyft",
    "DASH": "DoorDash",
    "SPOT": "Spotify",
    "ZM": "Zoom",
    "SHOP": "Shopify",
    "SQ": "Block",
    "PYPL": "PayPal",
    # 中概股
    "BABA": "阿里巴巴(美)",
    "JD": "京東(美)",
    "PDD": "拼多多(美)",
    "NIO": "蔚來(美)",
    "LI": "理想(美)",
    "XPEV": "小鵬(美)",
    "BIDU": "百度(美)",
    "BILI": "嗶哩嗶哩(美)",
    "IQ": "愛奇藝(美)",
    "TME": "騰訊音樂(美)",
    "VIPS": "唯品會(美)",
    "ZTO": "中通快遞(美)",
    "FUTU": "富途(美)",
    "TIGR": "老虎證券(美)",
    "KC": "金山雲(美)",
    "MNSO": "名創優品(美)",
    # 金融
    "BRK-B": "伯克希爾",
    "JPM": "摩根大通",
    "V": "Visa",
    "MA": "Mastercard",
    "BAC": "美國銀行",
    "WFC": "富國銀行",
    "GS": "高盛",
    "MS": "摩根士丹利",
    "C": "花旗",
    "AXP": "美國運通",
    "BLK": "貝萊德",
    "SCHW": "嘉信理財",
    "CME": "芝加哥交易所",
    "ICE": "洲際交易所",
    "SPGI": "標普全球",
    "MCO": "穆迪",
    # 醫療健康
    "UNH": "聯合健康",
    "JNJ": "強生",
    "LLY": "禮來",
    "PFE": "輝瑞",
    "ABBV": "艾伯維",
    "MRK": "默沙東",
    "TMO": "賽默飛",
    "ABT": "雅培",
    "DHR": "丹納赫",
    "BMY": "百時美施貴寶",
    "AMGN": "安進",
    "GILD": "吉利德",
    "ISRG": "直覺外科",
    "MDT": "美敦力",
    "VRTX": "福泰製藥",
    # 消費
    "WMT": "沃爾瑪",
    "PG": "寶潔",
    "HD": "家得寶",
    "COST": "好市多",
    "KO": "可口可樂",
    "PEP": "百事",
    "MCD": "麥當勞",
    "NKE": "耐克",
    "SBUX": "星巴克",
    "TGT": "塔吉特",
    "LOW": "勞氏",
    "TJX": "TJX",
    "CL": "高露潔",
    "EL": "雅詩蘭黛",
    "LULU": "Lululemon",
    # 工業與能源
    "CAT": "卡特彼勒",
    "BA": "波音",
    "HON": "霍尼韋爾",
    "UPS": "UPS",
    "RTX": "雷神",
    "GE": "通用電氣",
    "MMM": "3M",
    "XOM": "埃克森美孚",
    "CVX": "雪佛龍",
    "COP": "康菲石油",
    "SLB": "斯倫貝謝",
    # 通信與媒體
    "DIS": "迪士尼",
    "CMCSA": "康卡斯特",
    "T": "AT&T",
    "VZ": "威瑞森",
    "TMUS": "T-Mobile",
    "WBD": "華納兄弟",
    # 半導體
    "TSM": "台積電(美)",
    "ASML": "阿斯麥(美)",
    "MRVL": "Marvell",
    "ON": "安森美",
    "NXPI": "恩智浦",
    "ARM": "ARM",
    # 新能源
    "ENPH": "Enphase",
    "SEDG": "SolarEdge",
    "FSLR": "第一太陽能",
    "PLUG": "Plug Power",
    "RIVN": "Rivian",
    "LCID": "Lucid",
    # 公用事業/能源/材料
    "NEE": "NextEra 電力",
    "DUK": "杜克能源",
    "SO": "南方公司",
    "AEP": "美國電力",
    "EXC": "Exelon",
    "XEL": "Xcel 能源",
    "SRE": "Sempra 能源",
    "ED": "聯合愛迪生",
    "EIX": "愛迪生國際",
    "PCG": "Pacific Gas",
    "LIN": "林德",
    "APD": "Air Products",
    "FCX": "自由港麥克墨倫",
    "NEM": "紐蒙特",
    # 航太軍工/工業
    "LMT": "洛克希德馬丁",
    "NOC": "諾斯洛普格魯曼",
    "GD": "通用動力",
    "DE": "約翰迪爾",
    "UNP": "聯合太平洋",
    "CSX": "CSX 鐵路",
    "NSC": "諾福克南方",
    # 必需消費/飲料/食品
    "MDLZ": "億滋",
    "KHC": "卡夫亨氏",
    "PM": "菲利普莫里斯",
    "MO": "奧馳亞",
    "CAG": "康尼格拉",
    # 零售/服飾
    "BKNG": "Booking",
    "EBAY": "eBay",
    "ROST": "Ross",
    # REIT（不動產）
    "AMT": "美國塔",
    "PLD": "普洛斯",
    "EQIX": "Equinix",
    "PSA": "Public Storage",
    "O": "Realty Income",
    # 生醫/醫療器械
    "SYK": "史賽克",
    "BSX": "波士頓科學",
    "ZTS": "Zoetis",
    "REGN": "再生元",
    "BIIB": "百健",
    # 其他大型/熱門
    "PBR": "巴西石油(美)",
    "VALE": "淡水河谷(美)",
    # 網安 / 雲 / AI 基建
    "CRWD": "CrowdStrike",
    "PANW": "Palo Alto",
    "FTNT": "Fortinet",
    "SMCI": "超微電腦",
    "DDOG": "Datadog",
    "NET": "Cloudflare",
    "MDB": "MongoDB",
}

# ====== 港股熱門 ======
HK_STOCKS = {
    "0700.HK": "騰訊",
    "9988.HK": "阿里巴巴(港)",
    "9618.HK": "京東(港)",
    "3690.HK": "美團",
    "9999.HK": "網易",
    "1810.HK": "小米",
    "2318.HK": "中國平安(港)",
    "0941.HK": "中國移動",
    "1398.HK": "工商銀行(港)",
    "0005.HK": "匯豐控股",
    "0388.HK": "港交所",
    "1299.HK": "友邦保險",
    "2020.HK": "安踏體育",
    "9961.HK": "攜程(港)",
    "0175.HK": "吉利汽車",
    # 更多恒指/國企藍籌（金融/地產/能源/公用/消費）
    "0939.HK": "建設銀行(港)",
    "3988.HK": "中國銀行(港)",
    "2628.HK": "中國人壽(港)",
    "1336.HK": "新華保險(港)",
    "0267.HK": "中信股份(港)",
    "0857.HK": "中國石油(港)",
    "0883.HK": "中國海洋石油",
    "0386.HK": "中國石油化工",
    "1024.HK": "快手",
    "6690.HK": "海爾智家(港)",
    "1211.HK": "比亞迪股份(港)",
    "2269.HK": "藥明生物",
    "1093.HK": "石藥集團",
    "1177.HK": "中國生物製藥",
    "6862.HK": "海底撈",
    "1113.HK": "長實集團",
    "0016.HK": "新鴻基地產",
    "1109.HK": "華潤置地",
    "0823.HK": "領展房產基金",
    "0002.HK": "中電控股",
    "0003.HK": "香港中華煤氣",
    # 銀行/金融（港股）
    "2388.HK": "中銀香港",
    "3968.HK": "招商銀行(港)",
    "0011.HK": "恒生銀行",
    # 消費/醫藥/製造
    "2319.HK": "蒙牛乳業",
    "1929.HK": "周大福",
    "1038.HK": "長江基建",
    "0669.HK": "創科實業",
    "2015.HK": "理想汽車(港)",
    "9868.HK": "小鵬汽車(港)",
    "9888.HK": "百度(港)",
    "9626.HK": "嗶哩嗶哩(港)",
    "9992.HK": "泡泡瑪特",
    "2618.HK": "京東物流",
    "3692.HK": "翰森製藥",
    # 科技 / 半導體 / 電訊
    "0981.HK": "中芯國際",
    "1347.HK": "華虹半導體",
    "0763.HK": "中興通訊",
    "0762.HK": "中國聯通",
    "0285.HK": "比亞迪電子",
    "0992.HK": "聯想集團",
    # 消費 / 體育 / 航空
    "0231.HK": "李寧",
    "0322.HK": "康師傅",
    "0293.HK": "國泰航空",
    "0288.HK": "萬洲國際",
    "2313.HK": "申洲國際",
    "1876.HK": "百威亞太",
    "0291.HK": "華潤啤酒",
    "0960.HK": "龍湖集團",
    "0836.HK": "華潤電力",
    "2688.HK": "新奧能源",
}

# ====== 全球指數 ======
INDICES = {
    "^GSPC": "標普500",
    "^IXIC": "納斯達克",
    "^DJI": "道瓊斯",
    "^RUT": "羅素2000",
    "^FTSE": "富時100",
    "^GDAXI": "德國DAX",
    "^FCHI": "法國CAC40",
    "^N225": "日經225",
    "^HSI": "恒生指數",
    "000001.SS": "上證綜指",
    "399001.SZ": "深證成指",
    "399006.SZ": "創業板指",
    "^STI": "新加坡海峽",
    "^AXJO": "澳洲ASX200",
    "^KS11": "韓國KOSPI",
    "^HSCE": "恒生國企指數",
    "^HSTECH": "恒生科技指數",
    "^STOXX50E": "歐洲STOXX50",
    "^SPXEW": "標普500等權",
}

# ====== ETF ======
ETFS = {
    "SPY": "標普500 ETF",
    "QQQ": "納斯達克100 ETF",
    "IWM": "羅素2000 ETF",
    "DIA": "道瓊斯 ETF",
    "EEM": "新興市場 ETF",
    "FXI": "中國大盤 ETF",
    "KWEB": "中國互聯網 ETF",
    "GLD": "黃金 ETF",
    "SLV": "白銀 ETF",
    "USO": "原油 ETF",
    "TLT": "20年+美債 ETF",
    "VIXY": "VIX 波動率 ETF",
    "ARKK": "ARK 創新 ETF",
    "SOXX": "半導體 ETF",
    "XLF": "金融板塊 ETF",
    "XLK": "科技板塊 ETF",
    "XLY": "可選消費 ETF",
    "XLP": "必需消費 ETF",
    "XLV": "醫療保健 ETF",
    "XLI": "工業板塊 ETF",
    "XLE": "能源板塊 ETF",
    "XLC": "通信服務 ETF",
    "XLU": "公用事業 ETF",
    "VNQ": "美國REIT ETF",
    "HYG": "高收益債 ETF",
    "LQD": "投資級債 ETF",
    "IEF": "7-10年美債 ETF",
    "SHY": "1-3年美債 ETF",
    "TIP": "抗通膨債 ETF",
}

# ====== 商品期貨 ======
COMMODITIES = {
    "GC=F": "黃金期貨",
    "SI=F": "白銀期貨",
    "CL=F": "WTI 原油",
    "BZ=F": "布倫特原油",
    "HG=F": "銅期貨",
    "NG=F": "天然氣",
    "ZC=F": "玉米期貨",
    "ZS=F": "大豆期貨",
}

# ====== 外匯（Yahoo 格式） ======
FOREX_YAHOO = {
    "USDCNY=X": "美元/人民幣",
    "EURUSD=X": "歐元/美元",
    "GBPUSD=X": "英鎊/美元",
    "USDJPY=X": "美元/日元",
    "USDCHF=X": "美元/瑞郎",
    "AUDUSD=X": "澳元/美元",
    "USDCAD=X": "美元/加元",
    "EURGBP=X": "歐元/英鎊",
    "EURJPY=X": "歐元/日元",
    "GBPJPY=X": "英鎊/日元",
}

# 市場分類映射
MARKET_CATALOG = {
    "us_stock": {"name": "美股", "icon": "🇺🇸", "symbols": US_STOCKS},
    "hk_stock": {"name": "港股", "icon": "🇭🇰", "symbols": HK_STOCKS},
    "index": {"name": "全球指數", "icon": "📈", "symbols": INDICES},
    "etf": {"name": "ETF", "icon": "📦", "symbols": ETFS},
    "commodity": {"name": "商品期貨", "icon": "🛢️", "symbols": COMMODITIES},
    "forex_yahoo": {"name": "外匯(Yahoo)", "icon": "💱", "symbols": FOREX_YAHOO},
}


def get_market_catalog() -> dict:
    """返回完整市場目錄"""
    return MARKET_CATALOG.copy()


def _twelve_time_series(symbol: str, start_date: str = None) -> pd.DataFrame:
    """
    Twelve Data 歷史 K 線（免費 800 次/天）。
    支持美股、外匯、加密貨幣。
    """
    try:
        url = f"{_TWELVE_BASE}/time_series"
        params = {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": 5000,
            "format": "JSON",
        }
        if start_date:
            sd = start_date.replace("-", "")
            if len(sd) == 8:
                params["start_date"] = f"{sd[:4]}-{sd[4:6]}-{sd[6:]}"

        resp = _http_session.get(url, params=params, timeout=30)
        data = resp.json()

        if data.get("status") == "error":
            return pd.DataFrame()

        values = data.get("values", [])
        if not values:
            return pd.DataFrame()

        records = []
        for v in values:
            c = float(v.get("close", 0) or 0)
            if c <= 0:
                continue
            records.append(
                {
                    "date": v.get("datetime", ""),
                    "open": round(float(v.get("open", 0) or 0), 4),
                    "high": round(float(v.get("high", 0) or 0), 4),
                    "low": round(float(v.get("low", 0) or 0), 4),
                    "close": round(c, 4),
                    "volume": int(float(v.get("volume", 0) or 0)),
                    "amount": 0,
                }
            )

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df = df.sort_values("date").reset_index(drop=True)
        logger.info(f"Twelve Data {symbol}: {len(df)} 條記錄")
        return df

    except Exception as e:
        logger.debug(f"Twelve Data {symbol} 失敗: {e}")
        return pd.DataFrame()


def download_global_symbol(symbol: str, start_date: str = None) -> pd.DataFrame:
    """
    下載全球任意標的的歷史數據（多源自動降級）。

    symbol: 代碼（如 AAPL, 0700.HK, ^GSPC, GC=F）
    優先級：Yahoo Finance → Twelve Data
    """
    # 檢查失敗緩存（避免重複嘗試已知失敗的符號）
    now = time.time()
    if symbol in _failed_symbols:
        elapsed = now - _failed_symbols[symbol]
        if elapsed < _FAILED_COOLDOWN:
            logger.debug(
                f"{symbol}: 跳過（{_FAILED_COOLDOWN - elapsed:.0f}s 前失敗，冷卻中）"
            )
            return pd.DataFrame()
        else:
            # 冷卻期過，允許重試
            del _failed_symbols[symbol]
    # 判斷時間範圍
    if start_date:
        start_date = start_date.replace("-", "")
        try:
            sd = datetime.strptime(start_date, "%Y%m%d")
            days = (datetime.now() - sd).days
            if days <= 30:
                range_str = "1mo"
            elif days <= 90:
                range_str = "3mo"
            elif days <= 365:
                range_str = "1y"
            elif days <= 730:
                range_str = "2y"
            elif days <= 1825:
                range_str = "5y"
            else:
                range_str = "max"
        except ValueError:
            range_str = "5y"
    else:
        range_str = "5y"

    # 源 1：Yahoo Finance
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = _yahoo_chart(symbol, range_str=range_str, interval="1d")
            if not df.empty:
                if start_date:
                    sd_str = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
                    df = df[df["date"] >= sd_str]
                logger.info(f"全球標的 {symbol}: {len(df)} 條記錄 (Yahoo)")
                return df
        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"Yahoo {symbol} 失敗(第{attempt}次)，重試... ({e})")
                time.sleep(RETRY_DELAY * attempt)
            else:
                logger.warning(f"Yahoo {symbol} 全部失敗，嘗試備選...")

    # 源 2：Twelve Data（美股/外匯/加密有效）
    if symbol.isalpha() or ("-" in symbol and not symbol[0].isdigit()):
        logger.info(f"{symbol}: 嘗試 Twelve Data 備選...")
        df = _twelve_time_series(symbol, start_date)
        if not df.empty:
            return df

    logger.error(f"全球標的 {symbol}: 所有數據源均失敗")
    _failed_symbols[symbol] = time.time()  # 記錄失敗，冷卻後再重試
    return pd.DataFrame()


def get_global_realtime(symbols: list[str]) -> list[dict]:
    """
    批量獲取全球標的實時行情（多源自動降級）。

    優先級：Yahoo → 新浪 → 東財 → Twelve Data
    """
    results = []
    for sym in symbols:
        q = None

        # 源 1：Yahoo Finance
        q = _yahoo_quote(sym)
        if q and q.get("price", 0) > 0:
            q["source"] = "yahoo"
        else:
            # 源 2：新浪全球行情
            q = _sina_global_quote(sym)
            if q and q.get("price", 0) > 0:
                logger.debug(f"{sym}: 使用新浪備選源")
            else:
                # 源 3：東方財富全球行情
                q = _em_global_quote(sym)
                if q and q.get("price", 0) > 0:
                    logger.debug(f"{sym}: 使用東財備選源")
                else:
                    # 源 4：Twelve Data
                    q = _twelve_quote(sym)
                    if q and q.get("price", 0) > 0:
                        logger.debug(f"{sym}: 使用 Twelve Data 備選源")
                    else:
                        logger.warning(f"{sym}: 所有全球行情源均失敗")
                        continue

        # 查找中文名
        name = ""
        for cat in MARKET_CATALOG.values():
            if sym in cat["symbols"]:
                name = cat["symbols"][sym]
                break
        q["name"] = q.get("name") or name or sym
        results.append(q)
        time.sleep(0.2)

    return results


def detect_global_market(symbol: str) -> str:
    """判斷全球標的所屬市場"""
    symbol = symbol.upper().strip()
    for cat_key, cat in MARKET_CATALOG.items():
        if symbol in [s.upper() for s in cat["symbols"]]:
            return cat_key
    # 啟發式判斷
    if symbol.endswith(".HK"):
        return "hk_stock"
    if symbol.endswith(".SS") or symbol.endswith(".SZ"):
        return "index"
    if symbol.endswith("=X"):
        return "forex_yahoo"
    if symbol.endswith("=F"):
        return "commodity"
    if symbol.startswith("^"):
        return "index"
    # 默認美股
    return "us_stock"
