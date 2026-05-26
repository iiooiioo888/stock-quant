"""
基本面 Point-in-Time (PIT) 對齊 — 避免前視偏差

回測時應使用「發布日 / 公告日」而非「報告期」作為數據可用時間。
若庫表僅有 report_date，應在入庫時補 published_date 或保守滯後（如報告期 + N 日）。
"""
from __future__ import annotations

import pandas as pd


def align_fundamental_pit(
    facts: pd.DataFrame,
    as_of_dates: pd.Series,
    *,
    report_col: str = "report_date",
    published_col: str = "published_date",
    fallback_lag_days: int = 45,
) -> pd.DataFrame:
    """
    對每個 as_of 日期，只保留當時已「可用」的基本面記錄。

    優先 published_col；缺失時對 report_col 加上 fallback_lag_days 作為保守估計。
    """
    if facts.empty or as_of_dates.empty:
        return facts.iloc[0:0].copy()

    df = facts.copy()
    as_of = pd.to_datetime(as_of_dates, errors="coerce").dropna()
    if as_of.empty:
        return df.iloc[0:0].copy()

    if published_col in df.columns:
        avail = pd.to_datetime(df[published_col], errors="coerce")
    elif report_col in df.columns:
        avail = pd.to_datetime(df[report_col], errors="coerce") + pd.Timedelta(days=fallback_lag_days)
    else:
        raise ValueError(f"基本面表需含 {published_col} 或 {report_col}")

    df = df.copy()
    df["_avail"] = avail
    df = df.dropna(subset=["_avail"])
    max_as_of = as_of.max()
    return df[df["_avail"] <= max_as_of].drop(columns=["_avail"])
