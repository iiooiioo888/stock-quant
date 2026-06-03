"""
股票一句話投資邏輯 / 業務簡介 — 資產詳情頁展示用。
"""
from __future__ import annotations

import re
from typing import Any, Optional

from src.core.stock_sectors import stock_sector, stock_sector_label

# 精選標的：一句話投資邏輯（覆蓋優先於自動生成）
ONE_LINERS: dict[str, str] = {
    "600519.SS": "高端白酒龍頭，品牌護城河深、現金流與定價權強，長期受益消費升級與渠道改革。",
    "601318.SS": "綜合金融集團，保險+銀行+資管協同，受益利率與資本市場週期。",
    "300750.SZ": "全球動力電池龍頭，綁定主流車企產能擴張，關注技術路線與海外市占。",
    "0700.HK": "社交與遊戲生態平台，廣告與金融科技構成第二曲線，監管與版號為主要變數。",
    "9988.HK": "電商與雲計算雙引擎，國內零售基本盤穩固，雲與國際化決定估值彈性。",
    "3690.HK": "本地生活與即時零售龍頭，外賣高頻帶動到店與閃購，競爭格局影響利潤率修復。",
    "AAPL": "硬體+服務閉環生態，iPhone 換機週期與服務收入提升驅動利潤，關注創新與供應鏈。",
    "NVDA": "AI 算力核心供應商，數據中心 GPU 需求為主線，估值反映高成長與競爭加劇風險。",
    "MSFT": "企業軟體與雲（Azure）雙寡頭，Copilot 等 AI 產品化有望抬升 ARPU 與黏性。",
    "TSLA": "電動車與能源存儲品牌，產能、降本與自動駕駛進度決定股價波動區間。",
    "BABA": "中國電商與雲龍頭（美股 ADR），估值受中概情緒與國內消費復甦影響大。",
    "9618.HK": "自營+平台零售，物流與供應鏈為護城河，利潤率修復看消費與競爭。",
    "1810.HK": "智能手機與 IoT 生態，高端化與海外拓展為增長點，硬體毛利為關鍵。",
    "600036.SS": "零售銀行標杆，財富管理與對公質量領先，受益經濟與地產風險出清。",
    "000858.SZ": "濃香型白酒第二梯隊龍頭，品牌與渠道力強，業績與估值跟隨行業景氣。",
    "601012.SS": "光伏矽片龍頭，產能與成本曲線決定週期盈利，關注供需與技術迭代。",
    "688981.SS": "大陸晶圓代工龍頭，國產替代與資本開支週期驅動，設備管制為外部風險。",
    "0981.HK": "先進製程代工標的，國產設備與材料滲透率提升為中長期主題。",
    "1211.HK": "新能源整車龍頭，垂直整合+出海，銷量結構與價格戰影響毛利。",
    "0005.HK": "亞太綜合銀行，息差與財富管理為盈利核心，宏觀利率與信貸周期敏感。",
    "1299.HK": "亞洲保險龍頭，保障+儲蓄型產品組合，新業務價值與利率環境為關鍵。",
}

_SECTOR_THESIS: dict[str, str] = {
    "tech": "科技成長標的，關注研發投入、產品週期與估值倍數。",
    "finance": "金融類資產，盈利與估值受利率、信貸與監管政策影響顯著。",
    "consumer": "消費品牌或渠道，景氣與庫存週期、市占率為核心變數。",
    "healthcare": "醫藥健康，管線、集採與出海授權影響中長期空間。",
    "energy": "能源或資源，價格與資本開支週期主導盈利波動。",
    "semiconductor": "半導體產業鏈，景氣與國產替代為雙主線。",
    "internet": "互聯網平台，用戶時長、變現率與監管為估值錨。",
    "auto": "汽車產業鏈，銷量、價格戰與電動化滲透率為關鍵。",
    "utilities": "公用事業，現金流穩定、股息吸引力高，防禦屬性強。",
    "realestate": "地產及相關，政策與銷售回款決定信用與估值。",
    "industrial": "製造與基建，訂單、原材料與出口需求影響景氣。",
    "materials": "週期品種，供需與全球宏觀為主要驅動。",
    "telecom": "電訊運營，ARPU 與資本開支節奏影響自由現金流。",
    "dividend": "高股息策略標的，關注分紅持續性與估值安全邊際。",
}


def _first_sentence(text: str, max_len: int = 120) -> str:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    if not t:
        return ""
    parts = re.split(r"(?<=[。！？.!?])\s*", t)
    line = (parts[0] if parts else t).strip()
    if len(line) > max_len:
        line = line[: max_len - 1].rstrip() + "…"
    return line


def build_investment_thesis(
    symbol: str,
    name: str = "",
    *,
    group: str = "",
    asset_class: str = "",
    intro: str = "",
    sector: str = "",
) -> str:
    """一句話投資邏輯：精選庫 > 簡介首句 > 行業模板 > 通用。"""
    sym = str(symbol or "").strip().upper()
    if sym in ONE_LINERS:
        return ONE_LINERS[sym]

    intro_line = _first_sentence(intro, 140)
    if intro_line and len(intro_line) >= 12:
        return intro_line

    sec = (sector or stock_sector(sym)).strip() or "other"
    sec_label = stock_sector_label(sec)
    nm = (name or sym).strip()

    if asset_class == "stock" or group in ("a_share", "hk_stock", "us_stock"):
        tpl = _SECTOR_THESIS.get(sec)
        if tpl:
            return f"{nm}：{tpl}"
        if group == "a_share":
            return f"{nm}：A股上市標的，可結合財報、估值與行業景氣做配置研究。"
        if group == "hk_stock":
            return f"{nm}：港股標的，流動性與南向資金為常見定價因子。"
        if group == "us_stock":
            return f"{nm}：美股標的，盈利預期與利率環境為核心宏觀變數。"

    if sec_label and sec_label != "綜合":
        return f"{nm}（{sec_label}）— 詳見下方公司簡介與行情數據。"

    return f"{nm} — 可結合 K 線、估值與基本面欄位進行研究。"


def enrich_detail_thesis(detail: dict[str, Any], inst: Optional[Any] = None) -> dict[str, Any]:
    """為 build_asset_detail 結果附加 investment_thesis。"""
    if not isinstance(detail, dict):
        return detail
    sym = detail.get("symbol", "")
    profile = detail.get("profile") or {}
    sector = ""
    if inst is not None:
        sector = getattr(inst, "sub_class", "") or ""
    thesis = build_investment_thesis(
        sym,
        detail.get("name") or profile.get("name", ""),
        group=detail.get("group", ""),
        asset_class=detail.get("asset_class", ""),
        intro=profile.get("intro", ""),
        sector=sector,
    )
    detail["investment_thesis"] = thesis
    detail["one_liner"] = thesis
    return detail
