"""
東方財富資金流向 — 直連 HTTP（不依賴 AKShare 包裝層）

接口來源：data.eastmoney.com / push2 / push2his / datacenter-web
"""
from __future__ import annotations

import math
import time
from typing import Any, Optional

from src.core.data_sources import get_session
from src.utils.logger import logger

_PUSH2_HOSTS = (
    "push2.eastmoney.com",
    "82.push2.eastmoney.com",
    "63.push2.eastmoney.com",
    "17.push2.eastmoney.com",
)
_PUSH2HIS_HOSTS = (
    "push2his.eastmoney.com",
    "82.push2his.eastmoney.com",
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/zjlx/",
}
_UT = "b2884a393a59ad64002292a3e90d46a5"


def _get_json(
    path: str,
    params: dict,
    hosts: tuple[str, ...] = _PUSH2_HOSTS,
    timeout: tuple[int, int] = (6, 20),
) -> Optional[dict]:
    session = get_session("eastmoney_flow")
    last_err: Optional[Exception] = None
    for host in hosts:
        url = f"https://{host}{path}"
        try:
            resp = session.get(url, params=params, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data is None:
                continue
            return data
        except Exception as e:
            last_err = e
            logger.debug(f"東財 {host}{path} 失敗: {e}")
    if last_err:
        logger.debug(f"東財請求全部失敗 {path}: {last_err}")
    return None


def _parse_sector_flow_item(item: dict) -> dict:
    name = str(item.get("f14") or "").strip()
    if not name:
        return {}
    change_raw = item.get("f3")
    change_pct = float(change_raw) if change_raw is not None else 0.0
    return {
        "name": name,
        "code": str(item.get("f12") or ""),
        "change_pct": change_pct,
        "main_net": float(item.get("f62") or 0),
        "main_net_pct": float(item.get("f184") or 0),
        "super_large_net": float(item.get("f66") or 0),
        "large_net": float(item.get("f72") or 0),
        "medium_net": float(item.get("f78") or 0),
        "small_net": float(item.get("f84") or 0),
        "source": "eastmoney_http",
    }


def fetch_sector_fund_flow_rank(
    indicator: str = "今日",
    sector_type: str = "industry",
    max_pages: int = 3,
) -> list[dict]:
    """
    板塊資金流向排名。
    sector_type: industry | concept
    """
    sector_type_map = {"industry": "2", "concept": "3", "region": "1"}
    indicator_map = {
        "今日": ("f62", "1", "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124"),
        "5日": ("f164", "5", "f12,f14,f2,f109,f164,f165,f166,f167,f168,f169,f170,f171,f172,f173,f257,f258,f124"),
    }
    if indicator not in indicator_map:
        indicator = "今日"
    fid0, stat, fields = indicator_map[indicator]
    fs_t = sector_type_map.get(sector_type, "2")

    params = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "ut": _UT,
        "fltt": "2",
        "invt": "2",
        "fid0": fid0,
        "fs": f"m:90 t:{fs_t}",
        "stat": stat,
        "fields": fields,
    }

    data = _get_json("/api/qt/clist/get", params)
    if not data or not data.get("data"):
        return []

    total = int(data["data"].get("total") or 0)
    pages = min(max_pages, max(1, math.ceil(total / 100)))
    items: list[dict] = []

    for page in range(1, pages + 1):
        if page > 1:
            params["pn"] = str(page)
            data = _get_json("/api/qt/clist/get", params)
            if not data or not data.get("data"):
                break
        diff = data["data"].get("diff") or []
        for row in diff:
            if not isinstance(row, dict):
                continue
            parsed = _parse_sector_flow_item(row)
            if parsed:
                items.append(parsed)

    if items:
        logger.info(f"東財 HTTP 板塊資金({sector_type}/{indicator}): {len(items)} 條")
    return items


def fetch_market_fund_flow() -> list[dict]:
    """大盤資金流向（上證+深證合併日 K）"""
    params = {
        "lmt": "0",
        "klt": "101",
        "secid": "1.000001",
        "secid2": "0.399001",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut": _UT,
        "_": int(time.time() * 1000),
    }
    data = _get_json("/api/qt/stock/fflow/daykline/get", params, hosts=_PUSH2HIS_HOSTS)
    if not data or not data.get("data"):
        return []

    klines = data["data"].get("klines") or []
    result = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 12:
            continue
        result.append({
            "code": "market",
            "date": parts[0],
            "close": float(parts[11] or 0),
            "change_pct": float(parts[10] or 0),
            "main_net": float(parts[1] or 0),
            "small_net": float(parts[2] or 0),
            "mid_net": float(parts[3] or 0),
            "big_net": float(parts[4] or 0),
            "super_net": float(parts[5] or 0),
            "source": "eastmoney_http",
        })

    if result:
        logger.info(f"東財 HTTP 大盤資金: {len(result)} 條")
    return result


def _fetch_north_flow_one(symbol_key: str, mutual_type: str, days: int) -> list[dict]:
    """datacenter 滬股通/深股通歷史"""
    params = {
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "pageSize": str(min(days + 5, 200)),
        "pageNumber": "1",
        "reportName": "RPT_MUTUAL_DEAL_HISTORY",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(MUTUAL_TYPE="00{mutual_type}")',
    }
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    session = get_session("eastmoney_flow")
    try:
        resp = session.get(url, params=params, headers=_HEADERS, timeout=(6, 25))
        resp.raise_for_status()
        payload = resp.json()
        rows = (payload.get("result") or {}).get("data") or []
    except Exception as e:
        logger.debug(f"北向 {symbol_key} datacenter 失敗: {e}")
        return []

    label = symbol_key
    result = []
    for row in rows:
        date = str(row.get("TRADE_DATE") or "")[:10]
        net = row.get("NET_DEAL_AMT")
        if net is None:
            net = row.get("FUND_INFLOW") or 0
        try:
            main_net = float(net)
        except (TypeError, ValueError):
            main_net = 0.0
        # datacenter 原始單位為元；若數值偏小則按萬元換算
        if 0 < abs(main_net) < 1e7:
            main_net = main_net * 10000.0
        result.append({
            "code": label,
            "date": date,
            "close": 0,
            "change_pct": 0,
            "main_net": main_net,
            "super_net": 0,
            "big_net": 0,
            "mid_net": 0,
            "small_net": 0,
            "source": "eastmoney_datacenter",
        })

    result.sort(key=lambda x: x["date"])
    if len(result) > days:
        result = result[-days:]
    return result


def fetch_north_flow(days: int = 30) -> list[dict]:
    """北向資金：滬股通 + 深股通"""
    sh = _fetch_north_flow_one("沪股通", "1", days)
    time.sleep(0.3)
    sz = _fetch_north_flow_one("深股通", "3", days)
    combined = sh + sz
    if combined:
        logger.info(f"東財 datacenter 北向資金: {len(combined)} 條")
    return combined


def fetch_sector_fund_flow_akshare(indicator: str = "今日") -> list[dict]:
    """AKShare 備選（包裝層仍為東財源）"""
    try:
        import akshare as ak

        df = ak.stock_sector_fund_flow_rank(indicator=indicator)
        if df is None or df.empty:
            return []
        result = []
        for _, row in df.iterrows():
            name = str(row.get("名称", "") or row.get("行业", ""))
            if not name:
                continue
            result.append({
                "name": name,
                "change_pct": float(row.get("今日涨跌幅", row.get("阶段涨跌幅", 0)) or 0),
                "main_net": float(row.get("今日主力净流入-净额", row.get("主力净流入-净额", 0)) or 0),
                "main_net_pct": float(row.get("今日主力净流入-净占比", row.get("主力净流入-净占比", 0)) or 0),
                "super_large_net": float(row.get("今日超大单净流入-净额", row.get("超大单净流入-净额", 0)) or 0),
                "large_net": float(row.get("今日大单净流入-净额", row.get("大单净流入-净额", 0)) or 0),
                "medium_net": float(row.get("今日中单净流入-净额", row.get("中单净流入-净额", 0)) or 0),
                "small_net": float(row.get("今日小单净流入-净额", row.get("小单净流入-净额", 0)) or 0),
                "source": "akshare",
            })
        return result
    except Exception as e:
        logger.debug(f"AKShare 板塊資金失敗: {e}")
        return []


def fetch_market_fund_flow_akshare() -> list[dict]:
    try:
        import akshare as ak

        df = ak.stock_market_fund_flow()
        if df is None or df.empty:
            return []
        result = []
        for _, row in df.iterrows():
            result.append({
                "code": "market",
                "date": str(row.get("日期", "")),
                "close": float(row.get("上证指数", row.get("上证-收盘价", 0)) or 0),
                "change_pct": float(row.get("上证指数-涨跌幅", row.get("上证-涨跌幅", 0)) or 0),
                "main_net": float(row.get("主力净流入-净额", 0) or 0),
                "super_net": float(row.get("超大单净流入-净额", 0) or 0),
                "big_net": float(row.get("大单净流入-净额", 0) or 0),
                "mid_net": float(row.get("中单净流入-净额", 0) or 0),
                "small_net": float(row.get("小单净流入-净额", 0) or 0),
                "source": "akshare",
            })
        return result
    except Exception as e:
        logger.debug(f"AKShare 大盤資金失敗: {e}")
        return []


def fetch_north_flow_akshare(days: int = 30) -> list[dict]:
    try:
        import akshare as ak

        if hasattr(ak, "stock_hsgt_hist_em"):
            result = []
            for label, sym in [("沪股通", "沪股通"), ("深股通", "深股通")]:
                df = ak.stock_hsgt_hist_em(symbol=sym)
                if df is None or df.empty:
                    continue
                tail = df.tail(days)
                for _, row in tail.iterrows():
                    net_col = "当日成交净买额" if "当日成交净买额" in tail.columns else None
                    main_net = float(row.get(net_col, 0) or 0) if net_col else 0
                    result.append({
                        "code": label,
                        "date": str(row.get("日期", "")),
                        "close": 0,
                        "change_pct": 0,
                        "main_net": main_net * 1e8 if abs(main_net) < 1e6 else main_net,
                        "super_net": 0,
                        "big_net": 0,
                        "mid_net": 0,
                        "small_net": 0,
                        "source": "akshare",
                    })
                time.sleep(0.3)
            if result:
                return result
    except Exception as e:
        logger.debug(f"AKShare 北向 hist 失敗: {e}")

    try:
        if hasattr(ak, "stock_hsgt_north_net_flow_in_em"):
            result = []
            for label, sym in [("沪股通", "沪股通"), ("深股通", "深股通")]:
                df = ak.stock_hsgt_north_net_flow_in_em(symbol=sym)
                if df is None or df.empty:
                    continue
                tail = df.tail(days)
                for _, row in tail.iterrows():
                    main_net = 0.0
                    for col in tail.columns:
                        if "净流入" in str(col) or "净买" in str(col):
                            main_net = float(row.get(col, 0) or 0)
                            break
                    result.append({
                        "code": label,
                        "date": str(row.get("日期", row.get("date", ""))),
                        "close": 0,
                        "change_pct": 0,
                        "main_net": main_net,
                        "super_net": 0,
                        "big_net": 0,
                        "mid_net": 0,
                        "small_net": 0,
                        "source": "akshare",
                    })
            return result
    except Exception as e:
        logger.debug(f"AKShare 北向 north_net 失敗: {e}")
    return []
