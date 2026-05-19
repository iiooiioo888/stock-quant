"""
實時交易信號引擎 — 基於 19 種策略計算實時買賣信號
"""
import sqlite3
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.core.backtest import STRATEGIES, prepare_data, run_backtest
from src.core.db import load_daily_kline, get_conn
from src.config import settings
from src.utils.logger import logger


class SignalEngine:
    """
    實時信號計算引擎。
    對監控列表中的每隻股票，用所有 13 種策略計算最新一根 K 線的買賣信號。
    """

    def __init__(self):
        # 策略權重（基於最近回測的夏普比率），初始等權
        self._strategy_weights: dict[str, float] = {name: 1.0 for name in STRATEGIES}

    def compute_signals(self, codes: list[str] = None) -> list[dict]:
        """
        計算指定股票列表的實時信號。
        返回: [{"code": "600519", "strategy": "macd", "signal": "buy", "price": 1800.0, ...}, ...]
        """
        if codes is None:
            codes = settings.watchlist

        all_signals = []
        for code in codes:
            try:
                signals = self._compute_single(code)
                all_signals.extend(signals)
            except Exception as e:
                logger.debug(f"信號計算失敗 {code}: {e}")

        # 持久化到數據庫
        if all_signals:
            _save_signals(all_signals)

        return all_signals

    def _compute_single(self, code: str) -> list[dict]:
        """對單隻股票計算所有策略的信號"""
        df = load_daily_kline(code)
        if df.empty or len(df) < 30:
            return []

        # 準備 Backtrader 數據
        bt_df = df.copy()
        bt_df["date"] = pd.to_datetime(bt_df["date"])
        bt_df = bt_df.set_index("date")
        bt_df = bt_df[["open", "high", "low", "close", "volume"]]
        bt_df.columns = ["Open", "High", "Low", "Close", "Volume"]

        signals = []
        latest_price = float(df.iloc[-1]["close"])
        triggered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for strategy_name, strategy_cls in STRATEGIES.items():
            try:
                signal = self._run_strategy_on_bar(
                    bt_df, strategy_cls, strategy_name, code, latest_price, triggered_at
                )
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"策略 {strategy_name} 在 {code} 上失敗: {e}")

        return signals

    def _run_strategy_on_bar(
        self, df: pd.DataFrame, strategy_cls, strategy_name: str,
        code: str, price: float, triggered_at: str
    ) -> dict | None:
        """
        用 Backtrader 跑策略到最後一根 K 線，判斷是否有信號。
        為了效率，只取最後 200 根 K 線。
        """
        if len(df) > 200:
            df = df.tail(200)

        data = bt.feeds.PandasData(dataname=df)
        cerebro = bt.Cerebro()
        cerebro.adddata(data)
        cerebro.addstrategy(strategy_cls)
        cerebro.broker.setcash(100000)
        cerebro.broker.setcommission(commission=0.0)

        # 添加信號觀察器
        signal_result = {"type": None}

        class SignalObserver(bt.Analyzer):
            """捕獲策略在最後一根 K 線的操作"""
            def notify_order(self, order):
                if order.status == order.Completed:
                    # 判斷是否是最後一根 K 線的訂單
                    if order.isbuy():
                        signal_result["type"] = "buy"
                    elif order.issell():
                        signal_result["type"] = "sell"

        cerebro.addanalyzer(SignalObserver, _name="sigobs")
        results = cerebro.run()
        strat = results[0]

        signal_type = signal_result["type"]
        if signal_type is None:
            # 沒有觸發交易，檢查是否持有（hold）或空倉
            has_position = strat.position.size > 0
            signal_type = "hold" if has_position else "hold"
            # hold 信號也記錄（用於歷史回顧），但強度為 0
            return {
                "code": code,
                "strategy": strategy_name,
                "signal": "hold",
                "price": price,
                "strength": 0.0,
                "params": "{}",
                "triggered_at": triggered_at,
            }

        # 計算信號強度（基於策略權重）
        weight = self._strategy_weights.get(strategy_name, 1.0)
        base_strength = 50.0 if signal_type == "buy" else -50.0
        strength = base_strength * weight

        return {
            "code": code,
            "strategy": strategy_name,
            "signal": signal_type,
            "price": price,
            "strength": round(strength, 2),
            "params": "{}",
            "triggered_at": triggered_at,
        }

    def update_weights_from_backtest(self, code: str = None):
        """
        用最近回測結果更新策略權重（夏普比率作為權重）。
        如果未指定 code，用 watchlist 中第一個。
        """
        if code is None:
            code = settings.watchlist[0] if settings.watchlist else None
        if not code:
            return

        from src.core.db import get_backtest_history
        for strategy_name in STRATEGIES:
            try:
                history = get_backtest_history(code=code, strategy=strategy_name, limit=5)
                if history:
                    # 用最近回測的夏普比率作為權重
                    avg_sharpe = np.mean([h.get("sharpe_ratio", 0) or 0 for h in history])
                    # 正規化到 [0.2, 3.0] 範圍，避免極端值
                    weight = max(0.2, min(3.0, 1.0 + avg_sharpe))
                    self._strategy_weights[strategy_name] = weight
            except Exception:
                pass

    @property
    def weights(self) -> dict:
        """返回當前策略權重"""
        return dict(self._strategy_weights)


def score_signal_strength(signals: list[dict]) -> float:
    """
    計算信號強度綜合分數。
    當多個策略一致時，信號更強。
    分數 = 策略信號的加權和（權重 = 最近夏普比率）。
    範圍: -100（強烈賣出）到 +100（強烈買入）。
    """
    if not signals:
        return 0.0

    # 統計買/賣/持有
    buy_count = sum(1 for s in signals if s["signal"] == "buy")
    sell_count = sum(1 for s in signals if s["signal"] == "sell")
    hold_count = sum(1 for s in signals if s["signal"] == "hold")

    # 加權求和
    total_strength = sum(s.get("strength", 0) for s in signals)

    # 正規化到 [-100, 100]
    max_possible = len(signals) * 50.0  # 假設每個策略最大強度 50
    if max_possible > 0:
        normalized = (total_strength / max_possible) * 100
    else:
        normalized = 0.0

    # 一致性加成：策略越一致，信號越強
    active_count = buy_count + sell_count
    if active_count > 0:
        agreement = max(buy_count, sell_count) / len(signals)
        normalized *= (0.5 + 0.5 * agreement)  # 一致性加成 50%-100%

    return round(max(-100.0, min(100.0, normalized)), 2)


def get_historical_signals(
    code: str, start_date: str = None, end_date: str = None,
    strategy: str = None, days: int = 30
) -> list[dict]:
    """
    獲取歷史信號記錄。
    如果數據庫中沒有，則回放歷史 K 線數據重新計算。
    """
    # 先查數據庫
    existing = _load_signals_from_db(code, start_date, end_date, strategy, days)
    if existing:
        return existing

    # 數據庫中沒有，回放計算
    return _replay_historical_signals(code, days, strategy)


def _load_signals_from_db(
    code: str, start_date: str = None, end_date: str = None,
    strategy: str = None, days: int = 30
) -> list[dict]:
    """從數據庫讀取歷史信號"""
    sql = "SELECT * FROM signal_log WHERE code = ?"
    params = [code]

    if start_date:
        sql += " AND triggered_at >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND triggered_at <= ?"
        params.append(end_date)
    if strategy:
        sql += " AND strategy = ?"
        params.append(strategy)

    sql += " ORDER BY triggered_at DESC LIMIT ?"
    # 限制返回量：每個策略每天最多 1 條，乘以天數
    limit = days * len(STRATEGIES) * 2
    params.append(limit)

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    return [dict(r) for r in rows]


def _replay_historical_signals(
    code: str, days: int = 30, strategy: str = None
) -> list[dict]:
    """
    回放歷史 K 線，計算每天的策略信號。
    使用滑動窗口：對每一天，用截止到該天的數據運行策略。
    """
    df = load_daily_kline(code)
    if df.empty or len(df) < 60:
        return []

    # 只回放最近 N 天
    df = df.tail(min(days + 60, len(df)))

    strategies_to_run = {strategy: STRATEGIES[strategy]} if strategy else STRATEGIES
    all_signals = []

    # 取最後 days 根 K 線作為回放目標
    replay_bars = df.tail(days)

    for _, bar in replay_bars.iterrows():
        bar_date = str(bar["date"])
        bar_price = float(bar["close"])

        for strat_name, strat_cls in strategies_to_run.items():
            try:
                # 用截止到當天的數據（含當天）
                idx = df[df["date"] == bar_date].index
                if len(idx) == 0:
                    continue
                end_idx = idx[0]
                window = df.iloc[max(0, end_idx - 199):end_idx + 1]

                if len(window) < 30:
                    continue

                bt_df = window.copy()
                bt_df["date"] = pd.to_datetime(bt_df["date"])
                bt_df = bt_df.set_index("date")
                bt_df = bt_df[["open", "high", "low", "close", "volume"]]
                bt_df.columns = ["Open", "High", "Low", "Close", "Volume"]

                data = bt.feeds.PandasData(dataname=bt_df)
                cerebro = bt.Cerebro()
                cerebro.adddata(data)
                cerebro.addstrategy(strat_cls)
                cerebro.broker.setcash(100000)
                cerebro.broker.setcommission(commission=0.0)

                signal_result = {"type": None}

                class ReplayObserver(bt.Analyzer):
                    def notify_order(self, order):
                        if order.status == order.Completed:
                            signal_result["type"] = "buy" if order.isbuy() else "sell"

                cerebro.addanalyzer(ReplayObserver, _name="sigobs")
                cerebro.run()

                sig = signal_result["type"] or "hold"
                all_signals.append({
                    "code": code,
                    "strategy": strat_name,
                    "signal": sig,
                    "price": bar_price,
                    "strength": 50.0 if sig == "buy" else (-50.0 if sig == "sell" else 0.0),
                    "params": "{}",
                    "triggered_at": bar_date,
                })
            except Exception as e:
                logger.debug(f"回放信號失敗 {code}/{strat_name}/{bar_date}: {e}")

    # 持久化到數據庫
    if all_signals:
        _save_signals(all_signals)

    return all_signals


def _save_signals(signals: list[dict]):
    """批量保存信號到數據庫"""
    if not signals:
        return
    try:
        with get_conn() as conn:
            conn.executemany(
                """INSERT INTO signal_log (code, strategy, signal, price, strength, params, triggered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (s["code"], s["strategy"], s["signal"],
                     s.get("price"), s.get("strength", 0),
                     s.get("params", "{}"), s["triggered_at"])
                    for s in signals
                ]
            )
        logger.debug(f"保存 {len(signals)} 條信號記錄")
    except Exception as e:
        logger.debug(f"保存信號失敗: {e}")


def get_current_signals_for_codes(codes: list[str] = None) -> list[dict]:
    """
    獲取指定股票列表的最新信號（用於 API /api/signals/current）。
    對每隻股票返回所有策略的最新信號 + 綜合強度分數。
    """
    if codes is None:
        codes = settings.watchlist

    result = []
    for code in codes:
        # 從數據庫取最新信號
        sql = """SELECT * FROM signal_log
                 WHERE code = ? AND triggered_at = (
                     SELECT MAX(triggered_at) FROM signal_log WHERE code = ?
                 )"""
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (code, code)).fetchall()

        if rows:
            signals = [dict(r) for r in rows]
            strength = score_signal_strength(signals)
            result.append({
                "code": code,
                "signals": signals,
                "strength": strength,
                "updated_at": signals[0]["triggered_at"] if signals else None,
            })
        else:
            result.append({
                "code": code,
                "signals": [],
                "strength": 0,
                "updated_at": None,
            })

    return result


def compute_and_push_signals(engine: SignalEngine, codes: list[str] = None) -> list[dict]:
    """
    計算信號並返回推送數據（用於 WebSocket 推送）。
    返回格式: [{"code": "600519", "signals": [...], "strength": 75.0}, ...]
    """
    raw_signals = engine.compute_signals(codes)

    # 按股票分組
    grouped: dict[str, list] = {}
    for s in raw_signals:
        code = s["code"]
        if code not in grouped:
            grouped[code] = []
        grouped[code].append(s)

    result = []
    for code, signals in grouped.items():
        strength = score_signal_strength(signals)
        result.append({
            "code": code,
            "signals": signals,
            "strength": strength,
        })

    return result


# ============================================================
# 信號增強功能 — 回測驗證、熱力圖、綜合排名
# ============================================================

def backtest_signals(
    codes: list[str] = None,
    strategies: list[str] = None,
    days: int = 250,
) -> dict:
    """
    信號回測驗證 — 回放歷史信號，計算跟隨信號交易的實際收益。

    對每個歷史信號，計算前向收益（1d, 3d, 5d, 10d），
    並按策略統計準確率。

    參數:
        codes: 股票代碼列表，None 時用 watchlist
        strategies: 策略名稱列表，None 時用所有策略
        days: 回測天數，默認 250 天

    返回:
        {
            "by_strategy": {
                "macd": {
                    "total_signals": 120,
                    "buy_signals": 60,
                    "sell_signals": 60,
                    "accuracy_1d": 0.55,  # 1 天後方向正確率
                    "accuracy_3d": 0.53,
                    "accuracy_5d": 0.52,
                    "accuracy_10d": 0.50,
                    "avg_return_1d": 0.3,  # 平均 1 天收益%
                    "avg_return_3d": 0.5,
                    "avg_return_5d": 0.8,
                    "avg_return_10d": 1.2,
                    "buy_accuracy_1d": 0.58,  # 買入信號準確率
                    "sell_accuracy_1d": 0.52,  # 賣出信號準確率
                },
                ...
            },
            "overall": { ... },
            "signal_details": [ ... ]
        }
    """
    if codes is None:
        codes = settings.watchlist

    if strategies is None:
        strategies = list(STRATEGIES.keys())

    # 按策略統計
    strategy_stats: dict[str, dict] = {}
    for strat in strategies:
        strategy_stats[strat] = {
            "total_signals": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            # 前向收益累計（用於計算平均值）
            "fwd_returns": {"1d": [], "3d": [], "5d": [], "10d": []},
            # 方向正確次數
            "correct_dir": {"1d": 0, "3d": 0, "5d": 0, "10d": 0},
            # 買入/賣出分開統計
            "buy_returns": {"1d": [], "3d": [], "5d": [], "10d": []},
            "sell_returns": {"1d": [], "3d": [], "5d": [], "10d": []},
        }

    all_details = []

    for code in codes:
        try:
            # 獲取歷史 K 線
            df = load_daily_kline(code)
            if df.empty or len(df) < days + 60:
                continue

            # 只取最近 days 天
            df = df.tail(days + 60).copy()
            df = df.reset_index(drop=True)

            # 獲取歷史信號
            signals = get_historical_signals(code=code, days=days)

            if not signals:
                continue

            # 建立日期到索引的映射
            date_to_idx = {}
            for idx, row in df.iterrows():
                date_str = str(row["date"])[:10]
                date_to_idx[date_str] = idx

            # 對每個信號計算前向收益
            for sig in signals:
                strat_name = sig.get("strategy", "")
                if strat_name not in strategy_stats:
                    continue

                signal_type = sig.get("signal", "hold")
                if signal_type == "hold":
                    continue

                sig_date = str(sig.get("triggered_at", ""))[:10]
                sig_idx = date_to_idx.get(sig_date)
                if sig_idx is None:
                    continue

                stats = strategy_stats[strat_name]
                stats["total_signals"] += 1
                if signal_type == "buy":
                    stats["buy_signals"] += 1
                else:
                    stats["sell_signals"] += 1

                # 計算前向收益
                for days_fwd, key in [(1, "1d"), (3, "3d"), (5, "5d"), (10, "10d")]:
                    fwd_idx = sig_idx + days_fwd
                    if fwd_idx >= len(df):
                        continue

                    entry_price = float(df.iloc[sig_idx]["close"])
                    exit_price = float(df.iloc[fwd_idx]["close"])

                    if entry_price <= 0:
                        continue

                    # 買入信號: 前向收益 = (exit - entry) / entry
                    # 賣出信號: 前向收益 = (entry - exit) / entry（做空方向）
                    if signal_type == "buy":
                        fwd_return = (exit_price - entry_price) / entry_price * 100
                    else:
                        fwd_return = (entry_price - exit_price) / entry_price * 100

                    stats["fwd_returns"][key].append(fwd_return)

                    # 方向正確 = 前向收益 > 0
                    if fwd_return > 0:
                        stats["correct_dir"][key] += 1

                    # 分買賣統計
                    if signal_type == "buy":
                        stats["buy_returns"][key].append(fwd_return)
                    else:
                        stats["sell_returns"][key].append(fwd_return)

                    # 記錄明細（只保留最近 500 條）
                    if len(all_details) < 500:
                        all_details.append({
                            "code": code,
                            "strategy": strat_name,
                            "signal": signal_type,
                            "date": sig_date,
                            "price": float(sig.get("price", 0)),
                            f"return_{key}": round(fwd_return, 2),
                        })

        except Exception as e:
            logger.debug(f"信號回測失敗 {code}: {e}")

    # 匯總結果
    by_strategy = {}
    total_signals = 0
    total_correct = {"1d": 0, "3d": 0, "5d": 0, "10d": 0}
    total_count = {"1d": 0, "3d": 0, "5d": 0, "10d": 0}

    for strat_name, stats in strategy_stats.items():
        n = stats["total_signals"]
        if n == 0:
            continue

        total_signals += n
        strat_result = {
            "total_signals": n,
            "buy_signals": stats["buy_signals"],
            "sell_signals": stats["sell_signals"],
        }

        for key in ["1d", "3d", "5d", "10d"]:
            returns = stats["fwd_returns"][key]
            correct = stats["correct_dir"][key]
            count = len(returns)

            total_correct[key] += correct
            total_count[key] += count

            strat_result[f"accuracy_{key}"] = round(correct / count, 4) if count > 0 else 0
            strat_result[f"avg_return_{key}"] = round(np.mean(returns), 4) if returns else 0

            # 買入/賣出分開的準確率
            buy_rets = stats["buy_returns"][key]
            sell_rets = stats["sell_returns"][key]
            if buy_rets:
                buy_correct = sum(1 for r in buy_rets if r > 0)
                strat_result[f"buy_accuracy_{key}"] = round(buy_correct / len(buy_rets), 4)
            else:
                strat_result[f"buy_accuracy_{key}"] = 0
            if sell_rets:
                sell_correct = sum(1 for r in sell_rets if r > 0)
                strat_result[f"sell_accuracy_{key}"] = round(sell_correct / len(sell_rets), 4)
            else:
                strat_result[f"sell_accuracy_{key}"] = 0

        by_strategy[strat_name] = strat_result

    # 整體統計
    overall = {"total_signals": total_signals}
    for key in ["1d", "3d", "5d", "10d"]:
        overall[f"accuracy_{key}"] = (
            round(total_correct[key] / total_count[key], 4)
            if total_count[key] > 0 else 0
        )

    return {
        "by_strategy": by_strategy,
        "overall": overall,
        "signal_details": all_details,
    }


def signal_heatmap(codes: list[str] = None, days: int = 30) -> dict:
    """
    信號熱力圖 — 生成 codes × dates × signal_strength 的矩陣數據。

    每個單元格為綜合信號強度分數（-100 到 +100）。
    正值越深表示買入信號越強，負值越深表示賣出信號越強。

    參數:
        codes: 股票代碼列表，None 時用 watchlist
        days: 歷史天數，默認 30 天

    返回:
        {
            "codes": ["600519", "000001", ...],
            "dates": ["2024-01-15", "2024-01-16", ...],
            "matrix": [[score, ...], ...],  # codes × dates
            "max_score": 最大分數,
            "min_score": 最小分數,
        }
    """
    if codes is None:
        codes = settings.watchlist

    all_dates = set()
    # 先收集所有日期
    for code in codes:
        try:
            df = load_daily_kline(code)
            if not df.empty:
                recent = df.tail(days)
                for _, row in recent.iterrows():
                    all_dates.add(str(row["date"])[:10])
        except Exception:
            pass

    if not all_dates:
        return {"codes": codes, "dates": [], "matrix": [], "max_score": 0, "min_score": 0}

    sorted_dates = sorted(all_dates)
    # 限制日期數量
    sorted_dates = sorted_dates[-days:]

    # 為每隻股票計算每天的信號強度
    matrix = []
    max_score = -100
    min_score = 100

    for code in codes:
        row_scores = []

        # 獲取歷史信號
        try:
            signals = get_historical_signals(code=code, days=days)
        except Exception:
            signals = []

        # 按日期分組信號
        signals_by_date: dict[str, list] = {}
        for sig in signals:
            sig_date = str(sig.get("triggered_at", ""))[:10]
            if sig_date not in signals_by_date:
                signals_by_date[sig_date] = []
            signals_by_date[sig_date].append(sig)

        for date in sorted_dates:
            day_signals = signals_by_date.get(date, [])
            if day_signals:
                score = score_signal_strength(day_signals)
            else:
                score = 0.0

            row_scores.append(round(score, 1))
            max_score = max(max_score, score)
            min_score = min(min_score, score)

        matrix.append(row_scores)

    return {
        "codes": codes,
        "dates": sorted_dates,
        "matrix": matrix,
        "max_score": round(max_score, 1),
        "min_score": round(min_score, 1),
    }


def composite_signal_ranking(codes: list[str] = None) -> list[dict]:
    """
    綜合信號排名 — 按複合信號強度對所有股票排名。

    聚合所有策略的信號，並根據近期策略準確率加權。

    參數:
        codes: 股票代碼列表，None 時用所有有數據的股票

    返回:
        排名列表，每個元素:
            {
                "rank": 排名,
                "code": 股票代碼,
                "composite_score": 綜合分數 (-100 ~ +100),
                "recommendation": "強烈買入" / "買入" / "持有" / "賣出" / "強烈賣出",
                "signal_count": 有效信號數,
                "strategy_details": {
                    "macd": {"signal": "buy", "strength": 50, "weight": 0.15},
                    ...
                },
                "latest_price": 最新價格,
                "updated_at": 更新時間
            }
    """
    if codes is None:
        # 嘗試獲取所有有數據的股票
        from src.core.db import load_all_codes
        try:
            codes = load_all_codes()
        except Exception:
            codes = settings.watchlist

    if not codes:
        return []

    # 初始化信號引擎並更新權重
    engine = SignalEngine()
    engine.update_weights_from_backtest()
    strategy_weights = engine.weights

    # 計算策略準確率權重（從最近的回測結果）
    accuracy_weights = _compute_accuracy_weights(codes)

    rankings = []

    for code in codes:
        try:
            # 計算實時信號
            raw_signals = engine.compute_signals([code])
            if not raw_signals:
                continue

            # 計算加權綜合分數
            weighted_sum = 0.0
            weight_total = 0.0
            strategy_details = {}

            for sig in raw_signals:
                strat_name = sig.get("strategy", "")
                strength = sig.get("strength", 0)
                signal_type = sig.get("signal", "hold")

                # 組合權重 = 策略權重 × 準確率權重
                strat_weight = strategy_weights.get(strat_name, 1.0)
                acc_weight = accuracy_weights.get(strat_name, 1.0)
                combined_weight = strat_weight * acc_weight

                weighted_sum += strength * combined_weight
                weight_total += abs(combined_weight)

                strategy_details[strat_name] = {
                    "signal": signal_type,
                    "strength": round(strength, 1),
                    "weight": round(combined_weight, 3),
                }

            # 正規化到 [-100, 100]
            if weight_total > 0:
                composite_score = (weighted_sum / weight_total)
            else:
                composite_score = 0.0
            composite_score = max(-100, min(100, composite_score))

            # 判斷推薦操作
            if composite_score > 50:
                recommendation = "強烈買入"
            elif composite_score > 20:
                recommendation = "買入"
            elif composite_score > -20:
                recommendation = "持有"
            elif composite_score > -50:
                recommendation = "賣出"
            else:
                recommendation = "強烈賣出"

            # 獲取最新價格
            latest_price = 0.0
            updated_at = None
            if raw_signals:
                latest_price = raw_signals[0].get("price", 0)
                updated_at = raw_signals[0].get("triggered_at")

            rankings.append({
                "code": code,
                "composite_score": round(composite_score, 1),
                "recommendation": recommendation,
                "signal_count": len(raw_signals),
                "strategy_details": strategy_details,
                "latest_price": latest_price,
                "updated_at": updated_at,
            })

        except Exception as e:
            logger.debug(f"綜合排名計算失敗 {code}: {e}")

    # 按綜合分數排序（買入信號強的在前）
    rankings.sort(key=lambda x: x["composite_score"], reverse=True)

    # 添加排名
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    return rankings


def _compute_accuracy_weights(codes: list[str]) -> dict[str, float]:
    """
    計算各策略的準確率權重。

    通過回放最近 30 天信號，統計每個策略 1 天方向準確率。
    準確率高的策略獲得更高權重。

    返回:
        策略名稱到權重的映射，範圍 [0.5, 2.0]
    """
    try:
        result = backtest_signals(codes=codes[:3], strategies=None, days=30)
        by_strategy = result.get("by_strategy", {})

        weights = {}
        for strat_name, stats in by_strategy.items():
            acc = stats.get("accuracy_1d", 0.5)
            # 將準確率映射到 [0.5, 2.0] 的權重
            # 準確率 50% → 權重 1.0，60% → 1.4，40% → 0.6
            weight = max(0.5, min(2.0, 1.0 + (acc - 0.5) * 4))
            weights[strat_name] = weight

        return weights
    except Exception:
        # 計算失敗時返回等權
        return {name: 1.0 for name in STRATEGIES}
