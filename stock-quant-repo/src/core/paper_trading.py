"""
模擬交易（Paper Trading）引擎

在不連接真實券商的情況下，模擬實時交易流程：
  - 實時行情接入（或模擬行情）
  - 信號計算 → 風控檢查 → 虛擬下單
  - 持倉管理、盈虧追蹤
  - 交易日誌持久化

核心類:
  PaperTradingEngine — 模擬交易引擎
"""
import json
import sqlite3
from datetime import datetime
from typing import Optional

from src.core.db import get_conn, load_daily_kline
from src.core.risk_pipeline import RiskPipeline, TradeSignal, TradeOrder, SignalType, OrderSide
from src.core.signals import SignalEngine
from src.core.risk_manager import calculate_volatility, calculate_atr
from src.config import settings
from src.utils.logger import logger


# ============================================================
# 交易日誌數據庫
# ============================================================

def _init_paper_tables():
    """初始化模擬交易相關表"""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                code TEXT NOT NULL,
                side TEXT NOT NULL,
                shares INTEGER NOT NULL,
                price REAL NOT NULL,
                value REAL NOT NULL,
                commission REAL DEFAULT 0,
                stamp_tax REAL DEFAULT 0,
                strategy TEXT,
                signal_strength REAL DEFAULT 0,
                risk_status TEXT DEFAULT 'approved',
                pnl REAL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_sessions (
                id TEXT PRIMARY KEY,
                name TEXT,
                initial_capital REAL NOT NULL,
                current_capital REAL NOT NULL,
                nav REAL NOT NULL,
                total_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                started_at TEXT NOT NULL,
                stopped_at TEXT,
                config TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                session_id TEXT NOT NULL,
                code TEXT NOT NULL,
                shares INTEGER NOT NULL,
                avg_cost REAL NOT NULL,
                current_price REAL NOT NULL,
                value REAL NOT NULL,
                unrealized_pnl REAL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_id, code)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_nav_history (
                session_id TEXT NOT NULL,
                nav REAL NOT NULL,
                cash REAL NOT NULL,
                invested REAL NOT NULL,
                drawdown_pct REAL DEFAULT 0,
                recorded_at TEXT NOT NULL
            )
        """)


# ============================================================
# PaperTradingEngine
# ============================================================

class PaperTradingEngine:
    """
    模擬交易引擎。

    用法:
        engine = PaperTradingEngine(capital=100000, name="測試")
        engine.start()

        # 每個交易週期調用
        engine.tick()

        # 查看狀態
        engine.get_status()

        # 停止
        engine.stop()
    """

    def __init__(
        self,
        capital: float = None,
        name: str = "默認模擬盤",
        session_id: str = None,
        sizing_method: str = "atr",
        min_signal_strength: float = 10.0,
        poll_interval_sec: int = 60,
    ):
        self.capital = capital or settings.backtest_cash
        self.name = name
        self.session_id = session_id or f"paper_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.sizing_method = sizing_method
        self.min_signal_strength = min_signal_strength
        self.poll_interval_sec = poll_interval_sec

        self._pipeline: Optional[RiskPipeline] = None
        self._signal_engine: Optional[SignalEngine] = None
        self._running = False
        self._trade_count = 0
        self._total_pnl = 0.0
        self._peak_nav = self.capital
        self._max_drawdown = 0.0
        self._wins = 0
        self._losses = 0

        _init_paper_tables()

    def start(self):
        """啟動模擬交易"""
        self._pipeline = RiskPipeline(
            total_capital=self.capital,
            sizing_method=self.sizing_method,
            min_signal_strength=self.min_signal_strength,
        )
        self._signal_engine = SignalEngine()
        self._signal_engine.update_weights_from_backtest()
        self._running = True

        # 持久化 session
        self._save_session()
        logger.info(f"📋 模擬交易啟動: {self.session_id} | 資金: ¥{self.capital:,.0f}")

    def stop(self):
        """停止模擬交易"""
        self._running = False
        self._save_session()
        logger.info(f"📋 模擬交易停止: {self.session_id} | 總盈虧: ¥{self._total_pnl:,.2f}")

    def tick(self) -> list[dict]:
        """
        執行一個交易週期:
          1. 獲取最新行情
          2. 計算信號
          3. 過風控管道
          4. 執行虛擬交易
          5. 記錄日誌

        返回:
            本次執行的交易列表
        """
        if not self._running:
            return []

        try:
            from src.core.realtime import fetch_realtime

            # 獲取行情
            codes = settings.watchlist
            df = fetch_realtime(codes)

            current_prices = {}
            if not df.empty:
                for _, row in df.iterrows():
                    code = str(row.get("code", ""))
                    price = float(row.get("price", 0))
                    if code and price > 0:
                        current_prices[code] = price

            # 如果實時行情不可用，從最新 K 線取
            if not current_prices:
                for code in codes:
                    kdf = load_daily_kline(code)
                    if not kdf.empty:
                        current_prices[code] = float(kdf.iloc[-1]["close"])

            if not current_prices:
                return []

            # 計算信號
            raw_signals = self._signal_engine.compute_signals(codes)

            # 過風控管道
            position_vols = {}
            for code in current_prices:
                position_vols[code] = calculate_volatility(code)

            orders = self._pipeline.process_signals(
                raw_signals, current_prices, position_vols,
            )

            # 執行交易
            executed = []
            for order in orders:
                if order.risk_status in ("approved", "reduced"):
                    self._execute_trade(order)
                    executed.append(order.to_dict() if hasattr(order, 'to_dict') else {
                        "code": order.code,
                        "side": order.side.value,
                        "shares": order.shares,
                        "price": order.price,
                        "strategy": order.strategy,
                        "status": order.risk_status,
                    })

            # 記錄淨值
            self._record_nav()

            return executed

        except Exception as e:
            logger.error(f"模擬交易 tick 失敗: {e}")
            return []

    def _execute_trade(self, order: TradeOrder):
        """執行虛擬交易"""
        commission = order.shares * order.price * settings.backtest_commission
        stamp = order.shares * order.price * settings.backtest_stamp_tax if order.side == OrderSide.SELL else 0

        # 更新管道持倉
        self._pipeline.execute_order(order)

        # 計算盈虧（賣出時）
        pnl = 0.0
        if order.side == OrderSide.SELL:
            pos = self._pipeline.portfolio.positions.get(order.code)
            # 從 paper_positions 查成本
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT avg_cost FROM paper_positions WHERE session_id = ? AND code = ?",
                    (self.session_id, order.code),
                ).fetchone()
            if row:
                avg_cost = row[0]
                pnl = (order.price - avg_cost) * order.shares - commission - stamp
                self._total_pnl += pnl
                if pnl > 0:
                    self._wins += 1
                else:
                    self._losses += 1

        self._trade_count += 1

        # 持久化交易記錄
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO paper_trades
                (session_id, code, side, shares, price, value, commission, stamp_tax,
                 strategy, signal_strength, risk_status, pnl, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.session_id, order.code, order.side.value,
                order.shares, order.price, order.position_value,
                round(commission, 2), round(stamp, 2),
                order.strategy, order.signal_strength,
                order.risk_status, round(pnl, 2), now,
            ))

            # 更新持倉表
            if order.side == OrderSide.BUY:
                conn.execute("""
                    INSERT INTO paper_positions (session_id, code, shares, avg_cost, current_price, value, unrealized_pnl, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                    ON CONFLICT(session_id, code) DO UPDATE SET
                        shares = paper_positions.shares + ?,
                        avg_cost = (paper_positions.avg_cost * paper_positions.shares + ? * ?) / (paper_positions.shares + ?),
                        current_price = ?,
                        value = (paper_positions.shares + ?) * ?,
                        updated_at = ?
                """, (
                    self.session_id, order.code, order.shares, order.price, order.price,
                    order.position_value, now,
                    order.shares, order.price, order.shares, order.shares,
                    order.price, order.shares, order.price, now,
                ))
            elif order.side == OrderSide.SELL:
                conn.execute("""
                    UPDATE paper_positions SET
                        shares = shares - ?,
                        current_price = ?,
                        value = (shares - ?) * ?,
                        unrealized_pnl = (? - avg_cost) * (shares - ?),
                        updated_at = ?
                    WHERE session_id = ? AND code = ?
                """, (
                    order.shares, order.price, order.shares, order.price,
                    order.price, order.shares, now,
                    self.session_id, order.code,
                ))
                # 刪除零持倉
                conn.execute(
                    "DELETE FROM paper_positions WHERE session_id = ? AND code = ? AND shares <= 0",
                    (self.session_id, order.code),
                )

        logger.info(
            f"📋 模擬{'買入' if order.side == OrderSide.BUY else '賣出'}: "
            f"{order.code} {order.shares}股 @ ¥{order.price:.2f} "
            f"({order.strategy}) {'盈虧: ¥' + f'{pnl:.2f}' if pnl else ''}"
        )

    def _record_nav(self):
        """記錄當前淨值"""
        if not self._pipeline:
            return

        state = self._pipeline.get_state()
        nav = state["nav"]
        cash = state["cash"]
        invested = state["invested"]

        # 更新最大回撤
        if nav > self._peak_nav:
            self._peak_nav = nav
        if self._peak_nav > 0:
            dd = (self._peak_nav - nav) / self._peak_nav * 100
            if dd > self._max_drawdown:
                self._max_drawdown = dd

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO paper_nav_history (session_id, nav, cash, invested, drawdown_pct, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (self.session_id, round(nav, 2), round(cash, 2), round(invested, 2),
                  round(self._max_drawdown, 2), now))

    def _save_session(self):
        """保存/更新 session 信息"""
        nav = self._pipeline.get_state()["nav"] if self._pipeline else self.capital
        win_rate = self._wins / (self._wins + self._losses) * 100 if (self._wins + self._losses) > 0 else 0

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        config = json.dumps({
            "sizing_method": self.sizing_method,
            "min_signal_strength": self.min_signal_strength,
            "watchlist": settings.watchlist,
        }, ensure_ascii=False)

        with get_conn() as conn:
            conn.execute("""
                INSERT INTO paper_sessions
                (id, name, initial_capital, current_capital, nav, total_trades,
                 total_pnl, win_rate, max_drawdown, status, started_at, config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    current_capital = ?, nav = ?, total_trades = ?,
                    total_pnl = ?, win_rate = ?, max_drawdown = ?,
                    status = ?, stopped_at = ?
            """, (
                self.session_id, self.name, self.capital, round(nav, 2), round(nav, 2),
                self._trade_count, round(self._total_pnl, 2), round(win_rate, 2),
                round(self._max_drawdown, 2),
                "active" if self._running else "stopped", now, config,
                round(nav, 2), round(nav, 2), self._trade_count,
                round(self._total_pnl, 2), round(win_rate, 2),
                round(self._max_drawdown, 2),
                "active" if self._running else "stopped",
                now if not self._running else None,
            ))

    # ------ 查詢接口 ------

    def get_status(self) -> dict:
        """獲取模擬盤狀態"""
        pipeline_state = self._pipeline.get_state() if self._pipeline else {}
        nav = pipeline_state.get("nav", self.capital)
        win_rate = self._wins / (self._wins + self._losses) * 100 if (self._wins + self._losses) > 0 else 0

        return {
            "session_id": self.session_id,
            "name": self.name,
            "status": "active" if self._running else "stopped",
            "initial_capital": self.capital,
            "nav": round(nav, 2),
            "cash": round(pipeline_state.get("cash", self.capital), 2),
            "invested": round(pipeline_state.get("invested", 0), 2),
            "total_pnl": round(self._total_pnl, 2),
            "total_return_pct": round((nav / self.capital - 1) * 100, 2),
            "total_trades": self._trade_count,
            "win_rate_pct": round(win_rate, 2),
            "max_drawdown_pct": round(self._max_drawdown, 2),
            "positions": pipeline_state.get("positions", {}),
        }

    def get_trade_log(self, limit: int = 100) -> list[dict]:
        """獲取交易日誌"""
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM paper_trades WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (self.session_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_nav_history(self) -> list[dict]:
        """獲取淨值歷史"""
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM paper_nav_history WHERE session_id = ? ORDER BY recorded_at",
                (self.session_id,),
            ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# 管理接口
# ============================================================

def list_paper_sessions() -> list[dict]:
    """列出所有模擬盤 session"""
    _init_paper_tables()
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM paper_sessions ORDER BY started_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_paper_session(session_id: str) -> Optional[dict]:
    """獲取單個 session 詳情"""
    _init_paper_tables()
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM paper_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_paper_session(session_id: str) -> bool:
    """刪除 session 及相關數據"""
    with get_conn() as conn:
        conn.execute("DELETE FROM paper_trades WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM paper_positions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM paper_nav_history WHERE session_id = ?", (session_id,))
        cursor = conn.execute("DELETE FROM paper_sessions WHERE id = ?", (session_id,))
    return cursor.rowcount > 0
