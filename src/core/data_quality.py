"""
數據質量保障模塊

提供數據完整性校驗、異常值檢測、除權因子驗證等功能。
可獨立運行（CLI）或被其他模塊調用。

核心函數:
  validate_stock_data  — 校驗單隻股票數據質量
  validate_all         — 批量校驗所有股票
  repair_data          — 自動修復可修復的問題
"""
from datetime import datetime, timedelta

import pandas as pd

from src.core.db import get_conn, load_all_codes, load_daily_kline
from src.utils.logger import logger

# ============================================================
# 數據質量問題定義
# ============================================================

class DataIssue:
    """數據質量問題"""
    def __init__(self, code: str, issue_type: str, severity: str,
                 description: str, affected_rows: int = 0, auto_fixable: bool = False):
        self.code = code
        self.issue_type = issue_type      # missing_dates, outlier, price_gap, zero_volume, stale_data, negative_price
        self.severity = severity          # critical, warning, info
        self.description = description
        self.affected_rows = affected_rows
        self.auto_fixable = auto_fixable
        self.detected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "affected_rows": self.affected_rows,
            "auto_fixable": self.auto_fixable,
            "detected_at": self.detected_at,
        }


# ============================================================
# 核心校驗函數
# ============================================================

def validate_stock_data(
    code: str,
    check_missing_dates: bool = True,
    check_outliers: bool = True,
    check_price_gaps: bool = True,
    check_volume: bool = True,
    check_staleness: bool = True,
    check_negative: bool = True,
    outlier_threshold: float = 5.0,
    gap_threshold_pct: float = 15.0,
    staleness_days: int = 5,
) -> list[DataIssue]:
    """
    校驗單隻股票的數據質量。

    參數:
        code: 股票代碼
        check_missing_dates: 是否檢查缺失交易日
        check_outliers: 是否檢查價格異常值
        check_price_gaps: 是否檢查價格跳空
        check_volume: 是否檢查異常成交量
        check_staleness: 是否檢查數據過期
        check_negative: 是否檢查負價格
        outlier_threshold: 異常值 Z-score 閾值
        gap_threshold_pct: 跳空百分比閾值
        staleness_days: 過期天數閾值（距最後數據超過 N 個交易日）

    返回:
        DataIssue 列表
    """
    issues = []
    df = load_daily_kline(code)

    if df.empty:
        issues.append(DataIssue(
            code, "no_data", "critical",
            f"{code} 無任何歷史數據", 0, False,
        ))
        return issues

    # 確保 date 列是 datetime
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # --- 1. 負價格 / 零價格 ---
    if check_negative:
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                bad = df[df[col] <= 0]
                if not bad.empty:
                    issues.append(DataIssue(
                        code, "negative_price", "critical",
                        f"{col} 列存在 {len(bad)} 條非正價格",
                        len(bad), False,
                    ))

        # high < low
        if "high" in df.columns and "low" in df.columns:
            inverted = df[df["high"] < df["low"]]
            if not inverted.empty:
                issues.append(DataIssue(
                    code, "inverted_hl", "critical",
                    f"high < low 的異常記錄: {len(inverted)} 條",
                    len(inverted), False,
                ))

    # --- 2. 缺失交易日 ---
    if check_missing_dates and len(df) > 1:
        dates = df["date"].dt.date.tolist()
        expected_dates = _generate_trading_dates(dates[0], dates[-1])
        actual_set = set(dates)
        missing = [d for d in expected_dates if d not in actual_set]

        if missing:
            # 排除長假期（國慶/春節）前後的正常缺失
            missing_filtered = _filter_holiday_gaps(missing)
            if missing_filtered:
                severity = "warning" if len(missing_filtered) < 10 else "critical"
                issues.append(DataIssue(
                    code, "missing_dates", severity,
                    f"缺失 {len(missing_filtered)} 個交易日（排除假期後）",
                    len(missing_filtered), False,
                ))

    # --- 3. 價格異常值（Z-score） ---
    if check_outliers and len(df) > 20:
        df["daily_return"] = df["close"].pct_change()
        returns = df["daily_return"].dropna()

        if len(returns) > 10:
            mean_r = returns.mean()
            std_r = returns.std()
            if std_r > 0:
                df["z_score"] = (returns - mean_r) / std_r
                outliers = df[df["z_score"].abs() > outlier_threshold]
                if not outliers.empty:
                    issues.append(DataIssue(
                        code, "outlier", "warning",
                        f"價格異常波動 (Z>{outlier_threshold}): {len(outliers)} 條",
                        len(outliers), False,
                    ))

    # --- 4. 價格跳空缺口 ---
    if check_price_gaps and len(df) > 1:
        df["gap_pct"] = abs(df["close"].pct_change() * 100)
        big_gaps = df[df["gap_pct"] > gap_threshold_pct]
        if not big_gaps.empty:
            issues.append(DataIssue(
                code, "price_gap", "warning",
                f"單日漲跌 > {gap_threshold_pct}%: {len(big_gaps)} 條（可能除權）",
                len(big_gaps), False,
            ))

    # --- 5. 成交量異常 ---
    if check_volume and "volume" in df.columns and len(df) > 20:
        vol = df["volume"]
        vol_mean = vol.mean()
        vol_std = vol.std()
        if vol_std > 0 and vol_mean > 0:
            vol_z = (vol - vol_mean) / vol_std
            # 零成交量
            zero_vol = df[vol == 0]
            if not zero_vol.empty:
                issues.append(DataIssue(
                    code, "zero_volume", "info",
                    f"零成交量: {len(zero_vol)} 條",
                    len(zero_vol), False,
                ))
            # 異常放量
            extreme_vol = df[vol_z > 8]
            if not extreme_vol.empty:
                issues.append(DataIssue(
                    code, "extreme_volume", "info",
                    f"異常放量 (Z>8): {len(extreme_vol)} 條",
                    len(extreme_vol), False,
                ))

    # --- 6. 數據過期 ---
    if check_staleness:
        last_date = df["date"].max()
        if hasattr(last_date, 'date'):
            last_date = last_date.date()
        today = datetime.now().date()
        # 只在交易日檢查
        if _is_weekday(today):
            days_since = (today - last_date).days
            if days_since > staleness_days:
                issues.append(DataIssue(
                    code, "stale_data", "warning",
                    f"最後數據日期: {last_date}，已 {days_since} 天未更新",
                    0, False,
                ))

    # --- 7. 重複記錄 ---
    if "date" in df.columns:
        dupes = df[df.duplicated(subset=["date"], keep=False)]
        if not dupes.empty:
            issues.append(DataIssue(
                code, "duplicate_dates", "warning",
                f"重複日期記錄: {len(dupes)} 條",
                len(dupes), True,
            ))

    return issues


def validate_all(
    codes: list[str] = None,
    severity_filter: str = None,
) -> dict:
    """
    批量校驗所有股票。

    參數:
        codes: 股票代碼列表，None 時校驗所有
        severity_filter: 只返回指定嚴重級別以上的問題 (critical/warning/info)

    返回:
        {
            "total_stocks": 校驗股票數,
            "stocks_with_issues": 有問題的股票數,
            "total_issues": 問題總數,
            "issues_by_type": {type: count},
            "issues": [{...}, ...],
            "summary": 文字摘要,
        }
    """
    if codes is None:
        codes = load_all_codes()

    all_issues = []
    stocks_with_issues = set()

    for code in codes:
        try:
            issues = validate_stock_data(code)
            if issues:
                stocks_with_issues.add(code)
                all_issues.extend(issues)
        except Exception as e:
            logger.debug(f"校驗 {code} 失敗: {e}")
            all_issues.append(DataIssue(
                code, "validation_error", "warning",
                f"校驗過程出錯: {e}", 0, False,
            ))

    # 按嚴重級別過濾
    if severity_filter:
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        min_level = severity_order.get(severity_filter, 2)
        all_issues = [i for i in all_issues if severity_order.get(i.severity, 2) <= min_level]

    # 統計
    by_type = {}
    for issue in all_issues:
        by_type[issue.issue_type] = by_type.get(issue.issue_type, 0) + 1

    critical_count = sum(1 for i in all_issues if i.severity == "critical")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")

    summary_lines = [
        f"📊 數據質量報告: {len(codes)} 只股票",
        f"   有問題: {len(stocks_with_issues)} 只",
        f"   問題總數: {len(all_issues)} (🔴{critical_count} 🟡{warning_count})",
    ]
    if by_type:
        summary_lines.append("   類型分佈: " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())))

    return {
        "total_stocks": len(codes),
        "stocks_with_issues": len(stocks_with_issues),
        "total_issues": len(all_issues),
        "issues_by_type": by_type,
        "issues": [i.to_dict() for i in all_issues],
        "summary": "\n".join(summary_lines),
    }


def repair_data(code: str, dry_run: bool = True) -> list[str]:
    """
    自動修復可修復的數據問題。

    目前支持:
      - 重複日期記錄（保留最後一條）

    參數:
        code: 股票代碼
        dry_run: True 時只報告不實際修復

    返回:
        修復操作列表
    """
    repairs = []
    issues = validate_stock_data(code)

    for issue in issues:
        if issue.issue_type == "duplicate_dates" and issue.auto_fixable:
            if dry_run:
                repairs.append(f"[DRY RUN] 將刪除 {code} 的重複日期記錄")
            else:
                try:
                    with get_conn() as conn:
                        # 保留每組重複日期中 id 最大的記錄
                        conn.execute("""
                            DELETE FROM daily_kline
                            WHERE code = ? AND id NOT IN (
                                SELECT MAX(id) FROM daily_kline WHERE code = ? GROUP BY date
                            )
                        """, (code, code))
                    repairs.append(f"已刪除 {code} 的重複日期記錄")
                except Exception as e:
                    repairs.append(f"刪除重複記錄失敗: {e}")

    return repairs


# ============================================================
# 輔助函數
# ============================================================

def _generate_trading_dates(start, end) -> set:
    """生成指定區間內的所有工作日（排除週末，不排除假期）"""
    dates = set()
    current = start
    while current <= end:
        if current.weekday() < 5:  # 週一到週五
            dates.add(current)
        current += timedelta(days=1)
    return dates


def _filter_holiday_gaps(missing_dates: list) -> list:
    """
    過濾掉可能是長假期（國慶/春節/清明/端午/中秋）的缺失日期。
    如果缺失日期形成連續塊且長度 >= 4 天，可能是假期。
    """
    if not missing_dates:
        return []

    missing_sorted = sorted(missing_dates)
    filtered = []
    current_block = [missing_sorted[0]]

    for i in range(1, len(missing_sorted)):
        if (missing_sorted[i] - missing_sorted[i - 1]).days <= 1:
            current_block.append(missing_sorted[i])
        else:
            # 連續塊結束
            if len(current_block) < 4:
                filtered.extend(current_block)
            current_block = [missing_sorted[i]]

    # 最後一塊
    if len(current_block) < 4:
        filtered.extend(current_block)

    return filtered


def _is_weekday(d) -> bool:
    """判斷是否工作日"""
    if hasattr(d, 'weekday'):
        return d.weekday() < 5
    return True


# ============================================================
# 除權因子檢測
# ============================================================

def detect_split_adjustments(code: str, threshold: float = 0.3) -> list[dict]:
    """
    檢測可能的除權除息事件。
    當日收盤價與次日收盤價的比值顯著偏離 1 時，可能是除權。

    參數:
        code: 股票代碼
        threshold: 觸發閾值（價格變化比例）

    返回:
        疑似除權事件列表
    """
    df = load_daily_kline(code)
    if df.empty or len(df) < 2:
        return []

    df = df.sort_values("date").reset_index(drop=True)
    df["price_ratio"] = df["close"] / df["close"].shift(1)

    events = []
    for idx in range(1, len(df)):
        ratio = df.iloc[idx]["price_ratio"]
        if pd.isna(ratio):
            continue
        # 除權通常導致價格驟降（ratio < 0.7）或驟升（ratio > 1.3，如高送轉）
        if abs(ratio - 1) > threshold:
            events.append({
                "date": str(df.iloc[idx]["date"])[:10],
                "prev_close": round(float(df.iloc[idx - 1]["close"]), 2),
                "close": round(float(df.iloc[idx]["close"]), 2),
                "ratio": round(float(ratio), 4),
                "possible_event": "送股/轉增" if ratio > 1 else "分紅/配股",
            })

    return events
