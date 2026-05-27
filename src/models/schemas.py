"""
API 數據模型 — Pydantic schemas
"""
from pydantic import BaseModel, Field
from typing import Optional


# ====== 通用 ======

class ApiResponse(BaseModel):
    """統一 API 響應"""
    success: bool = True
    message: str = ""
    data: Optional[dict | list] = None


# ====== 股票 ======

class StockInfo(BaseModel):
    code: str
    name: str = ""
    price: float = 0
    change_pct: float = 0
    volume: float = 0


class WatchlistUpdate(BaseModel):
    codes: list[str]


# ====== 回測 ======

class BacktestRequest(BaseModel):
    code: str
    strategy: str = "dual_ma"
    params: Optional[dict] = None
    cash: float = 100000
    commission: float = 0.001


class BacktestAdvancedRequest(BaseModel):
    """進階回測請求 — 支持滑點、T+1、漲跌停控制"""
    code: str
    strategy: str = "dual_ma"
    params: Optional[dict] = None
    cash: float = 100000
    commission: float = 0.001
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    benchmark: bool = False
    slippage_pct: float = 0.0        # 滑點百分比（默認 0.0）
    enable_t1: bool = True            # 啟用 T+1 限制（默認 True）
    enable_limit: bool = True         # 啟用漲跌停限制（默認 True）


class BacktestResult(BaseModel):
    code: str
    strategy: str
    initial_cash: float
    final_value: float
    total_return_pct: float
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: float
    total_trades: int
    won_trades: int
    lost_trades: int
    win_rate_pct: float


# ====== 優化 ======

class OptimizeRequest(BaseModel):
    code: str
    strategy: str = "all"
    method: str = "grid"  # grid / optuna
    objective: str = "sharpe"  # sharpe / return / calmar / win_rate
    n_trials: int = 100
    top_n: int = 10


class OptimizeResult(BaseModel):
    strategy: str
    code: str
    params: dict
    score: float
    total_return_pct: float
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: float
    total_trades: int
    win_rate_pct: float


# ====== 組合 ======

class PortfolioAllocation(BaseModel):
    strategy: str
    code: str
    params: Optional[dict] = None
    weight: Optional[float] = None


class PortfolioRequest(BaseModel):
    allocations: list[PortfolioAllocation]
    weights: Optional[list[float]] = None
    rebalance: str = "none"
    rebalance_freq_days: int = 20
    cash: float = 100000
    plot: bool = False


class PortfolioResult(BaseModel):
    portfolio: dict
    sub_strategies: list[dict]
    weights: list[float]
    rebalance: str


# ====== 預警 ======

class AlertRule(BaseModel):
    code: str
    name: str = ""
    price_above: Optional[float] = None
    price_below: Optional[float] = None
    change_pct: Optional[float] = None


class AlertLog(BaseModel):
    id: int
    code: str
    rule_type: str
    message: str
    price: Optional[float] = None
    triggered_at: str


# ====== 系統 ======

class SystemStatus(BaseModel):
    version: str
    uptime: str
    db_size_mb: float
    total_stocks: int
    total_alerts: int
    last_update: Optional[str] = None


class HealthCheck(BaseModel):
    status: str = "ok"
    version: str
    database: str = "ok"
    uptime: str

