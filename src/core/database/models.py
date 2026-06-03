"""SQLAlchemy ORM Models — P6 所有 27 張表的映射。

自動從 schema.py DDL 推導；SQLite 和 PostgreSQL 均適用。
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.orm import relationship

from src.core.database.orm_base import Base

# ── 用戶系統 ──────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(Text, default="user")
    settings = Column(Text, default="{}")
    created_at = Column(Text, nullable=False)

    watchlists = relationship("UserWatchlist", back_populates="user", cascade="all, delete-orphan")
    alert_rules = relationship("UserAlertRule", back_populates="user", cascade="all, delete-orphan")
    likes = relationship("StrategyLike", back_populates="user", cascade="all, delete-orphan")


class StrategyLike(Base):
    __tablename__ = "strategy_likes"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    strategy_key = Column(Text, primary_key=True)
    created_at = Column(Text, nullable=False)

    user = relationship("User", back_populates="likes")


class UserWatchlist(Base):
    __tablename__ = "user_watchlists"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(Text, nullable=False)
    codes = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False)

    user = relationship("User", back_populates="watchlists")


class UserAlertRule(Base):
    __tablename__ = "user_alert_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(Text, nullable=False)
    rule_type = Column(Text, nullable=False)
    params = Column(Text, nullable=False)
    enabled = Column(Integer, default=1)
    created_at = Column(Text, nullable=False)

    user = relationship("User", back_populates="alert_rules")


# ── 核心行情 ──────────────────────────────────────────────

class DailyKline(Base):
    __tablename__ = "daily_kline"
    code = Column(Text, nullable=False, primary_key=True)
    date = Column(Text, nullable=False, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    turnover = Column(Float)
    market = Column(Text, default="a_share")


class RealtimeSnapshot(Base):
    __tablename__ = "realtime_snapshot"
    code = Column(Text, primary_key=True)
    name = Column(Text)
    price = Column(Float)
    change_pct = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    high = Column(Float)
    low = Column(Float)
    open = Column(Float)
    prev_close = Column(Float)
    updated_at = Column(Text)


class MinuteKline(Base):
    __tablename__ = "minute_kline"
    code = Column(Text, nullable=False, primary_key=True)
    datetime = Column(Text, nullable=False, primary_key=True)
    period = Column(Text, nullable=False, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)


# ── 信號 / 回測 / 預警 ────────────────────────────────────

class AlertLog(Base):
    __tablename__ = "alert_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, nullable=False)
    rule_type = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    price = Column(Float)
    triggered_at = Column(Text, nullable=False)


class BacktestResult(Base):
    __tablename__ = "backtest_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, nullable=False)
    strategy = Column(Text, nullable=False)
    params = Column(Text)
    total_return_pct = Column(Float)
    sharpe_ratio = Column(Float)
    max_drawdown_pct = Column(Float)
    annual_return_pct = Column(Float)
    sortino_ratio = Column(Float)
    calmar_ratio = Column(Float)
    var_95 = Column(Float)
    cvar_95 = Column(Float)
    total_trades = Column(Integer)
    win_rate_pct = Column(Float)
    initial_cash = Column(Float)
    final_value = Column(Float)
    created_at = Column(Text, nullable=False)


class SignalLog(Base):
    __tablename__ = "signal_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, nullable=False)
    strategy = Column(Text, nullable=False)
    signal = Column(Text, nullable=False)
    price = Column(Float)
    strength = Column(Float)
    params = Column(Text)
    triggered_at = Column(Text, nullable=False)


class StrategyLeaderboard(Base):
    __tablename__ = "strategy_leaderboard"
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(Text, nullable=False)
    source = Column(Text, nullable=False, default="builtin")
    code = Column(Text, nullable=False)
    total_return_pct = Column(Float)
    sharpe_ratio = Column(Float)
    sortino_ratio = Column(Float)
    calmar_ratio = Column(Float)
    max_drawdown_pct = Column(Float)
    win_rate_pct = Column(Float)
    total_trades = Column(Integer)
    annual_return_pct = Column(Float)
    var_95 = Column(Float)
    rank = Column(Integer)
    params = Column(Text)
    evaluated_at = Column(Text, nullable=False)


# ── 擴展市場數據 ──────────────────────────────────────────

class SectorData(Base):
    __tablename__ = "sector_data"
    sector_name = Column(Text, nullable=False, primary_key=True)
    sector_type = Column(Text, nullable=False, primary_key=True)
    code = Column(Text, nullable=False, primary_key=True)
    stock_name = Column(Text)
    update_date = Column(Text)


class SectorSnapshot(Base):
    __tablename__ = "sector_snapshot"
    sector_name = Column(Text, nullable=False, primary_key=True)
    sector_type = Column(Text, nullable=False, primary_key=True)
    change_pct = Column(Float)
    amount = Column(Float)
    rise_count = Column(Integer)
    fall_count = Column(Integer)
    leader = Column(Text)
    leader_change_pct = Column(Float)
    snapshot_date = Column(Text, nullable=False, primary_key=True)


class CapitalFlow(Base):
    __tablename__ = "capital_flow"
    code = Column(Text, nullable=False, primary_key=True)
    date = Column(Text, nullable=False, primary_key=True)
    flow_type = Column(Text, nullable=False, primary_key=True)
    main_net = Column(Float)
    super_net = Column(Float)
    big_net = Column(Float)
    mid_net = Column(Float)
    small_net = Column(Float)
    close = Column(Float)
    change_pct = Column(Float)
    raw_json = Column(Text)


class DragonTiger(Base):
    __tablename__ = "dragon_tiger"
    code = Column(Text, nullable=False, primary_key=True)
    name = Column(Text)
    date = Column(Text, nullable=False, primary_key=True)
    close = Column(Float)
    change_pct = Column(Float)
    reason = Column(Text)
    buy_amount = Column(Float)
    sell_amount = Column(Float)
    net_amount = Column(Float)
    turnover_rate = Column(Float)
    amount = Column(Float)
    circulating_mv = Column(Float)
    raw_json = Column(Text)


class Fundamental(Base):
    __tablename__ = "fundamentals"
    code = Column(Text, nullable=False, primary_key=True)
    name = Column(Text)
    update_date = Column(Text, nullable=False, primary_key=True)
    pe_ttm = Column(Float)
    pb = Column(Float)
    roe = Column(Float)
    eps = Column(Float)
    bvps = Column(Float)
    total_mv = Column(Float)
    circulating_mv = Column(Float)
    revenue = Column(Float)
    net_profit = Column(Float)
    gross_margin = Column(Float)
    net_margin = Column(Float)
    debt_ratio = Column(Float)
    dividend_yield = Column(Float)
    ps_ttm = Column(Float)
    revenue_yoy = Column(Float)
    profit_yoy = Column(Float)
    raw_json = Column(Text)


class StockUniverse(Base):
    __tablename__ = "stock_universe"
    code = Column(Text, nullable=False, primary_key=True)
    market = Column(Text, nullable=False, primary_key=True)
    name = Column(Text)
    exchange = Column(Text)
    industry = Column(Text)
    list_date = Column(Text)
    price = Column(Float)
    change_pct = Column(Float)
    total_mv = Column(Float)
    circulating_mv = Column(Float)
    pe_ttm = Column(Float)
    pb = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    turnover = Column(Float)
    rank_mv = Column(Integer)
    updated_at = Column(Text, nullable=False)
    source = Column(Text)
    intro = Column(Text)
    extra_json = Column(Text)


# ── 模擬交易 ──────────────────────────────────────────────

class PaperTrade(Base):
    __tablename__ = "paper_trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False)
    code = Column(Text, nullable=False)
    side = Column(Text, nullable=False)
    shares = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    value = Column(Float, nullable=False)
    commission = Column(Float, default=0)
    stamp_tax = Column(Float, default=0)
    strategy = Column(Text)
    signal_strength = Column(Float, default=0)
    risk_status = Column(Text, default="approved")
    pnl = Column(Float, default=0)
    created_at = Column(Text, nullable=False)


class PaperSession(Base):
    __tablename__ = "paper_sessions"
    id = Column(Text, primary_key=True)
    name = Column(Text)
    initial_capital = Column(Float, nullable=False)
    current_capital = Column(Float, nullable=False)
    nav = Column(Float, nullable=False)
    total_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0)
    win_rate = Column(Float, default=0)
    max_drawdown = Column(Float, default=0)
    status = Column(Text, default="active")
    started_at = Column(Text, nullable=False)
    stopped_at = Column(Text)
    config = Column(Text)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    session_id = Column(Text, nullable=False, primary_key=True)
    code = Column(Text, nullable=False, primary_key=True)
    shares = Column(Integer, nullable=False)
    avg_cost = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    value = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, default=0)
    updated_at = Column(Text, nullable=False)


class PaperNavHistory(Base):
    __tablename__ = "paper_nav_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False)
    nav = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    invested = Column(Float, nullable=False)
    drawdown_pct = Column(Float, default=0)
    recorded_at = Column(Text, nullable=False)


# ── 任務隊列 ──────────────────────────────────────────────

class TaskLog(Base):
    __tablename__ = "task_log"
    task_id = Column(Text, primary_key=True)
    task_type = Column(Text, nullable=False)
    params_hash = Column(Text, nullable=False)
    title = Column(Text)
    status = Column(Text, nullable=False)
    progress = Column(Integer, default=0)
    error = Column(Text)
    created_at = Column(Text)
    completed_at = Column(Text)
    params_json = Column(Text)


# ── 用戶資產庫 ─────────────────────────────────────────────

class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"
    id = Column(Text, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    quantity = Column(Float, nullable=False, default=0)
    price = Column(Float, nullable=False, default=0)
    currency = Column(Text, nullable=False, default="MOP")
    fee = Column(Float, nullable=False, default=0)
    executed_at = Column(Text, nullable=False)
    note = Column(Text)
    created_at = Column(Text, nullable=False)


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, primary_key=True)
    symbol = Column(Text, nullable=False, primary_key=True)
    total_qty = Column(Float, nullable=False, default=0)
    avg_cost = Column(Float, nullable=False, default=0)
    currency = Column(Text, nullable=False, default="MOP")
    last_updated = Column(Text, nullable=False)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, primary_key=True)
    snapshot_date = Column(Text, nullable=False, primary_key=True)
    currency = Column(Text, nullable=False, default="MOP", primary_key=True)
    total_net_worth = Column(Float, nullable=False, default=0)
    daily_pnl = Column(Float, nullable=False, default=0)
    fx_rate_to_usd = Column(Float)
    allocation_json = Column(Text)


# ── 匯率 ──────────────────────────────────────────────────

class FxRateDaily(Base):
    __tablename__ = "fx_rates_daily"
    base = Column(Text, nullable=False, default="USD", primary_key=True)
    target = Column(Text, nullable=False, primary_key=True)
    rate = Column(Float, nullable=False)
    date = Column(Text, nullable=False, primary_key=True)


# ── 遷移元數據 ────────────────────────────────────────────

class SchemaMigration(Base):
    __tablename__ = "schema_migrations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    applied_at = Column(Text, nullable=False)
