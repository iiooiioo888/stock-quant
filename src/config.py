"""
配置管理 — 支持環境變量 + .env 文件 + 默認值
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional


# 項目根目錄
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    """全局配置，優先級: 環境變量 > .env 文件 > 默認值"""

    # ====== 應用 ======
    app_name: str = "stock-quant"
    app_version: str = "1.1.0"
    debug: bool = False
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_dir: str = str(BASE_DIR / "logs")

    # ====== 數據庫 ======
    db_path: str = str(DATA_DIR / "stock.db")

    # ====== 歷史數據 ======
    history_start_date: str = Field(default="20200101", pattern=r"^\d{8}$")

    # ====== 盯盤 ======
    watchlist: list[str] = Field(default=[
        "000001",  # 平安銀行
        "600519",  # 貴州茅台
        "000858",  # 五糧液
        "601318",  # 中國平安
        "000333",  # 美的集團
    ])
    crypto_watchlist: list[str] = Field(default=[
        "BTCUSDT",  # 比特幣
        "ETHUSDT",  # 以太坊
        "SOLUSDT",  # Solana
        "BNBUSDT",  # 幣安幣
        "XRPUSDT",  # 瑞波幣
    ])
    forex_watchlist: list[str] = Field(default=[
        "USDCNY",   # 美元/人民幣
        "EURUSD",   # 歐元/美元
        "GBPUSD",   # 英鎊/美元
        "USDJPY",   # 美元/日元
    ])
    poll_interval_sec: int = Field(default=10, ge=1, le=300)
    alert_cooldown_sec: int = Field(default=300, ge=0)

    # ====== 回測 ======
    backtest_cash: float = Field(default=100000.0, gt=0)
    backtest_commission: float = Field(default=0.001, ge=0, le=0.1)
    backtest_stamp_tax: float = Field(default=0.001, ge=0, le=0.1)

    # ====== 任務並行 ======
    task_max_workers: int = Field(default=0, ge=0, le=32)  # 0 = 自動 min(4, CPU-1)
    task_parallel_grid: bool = True
    task_grid_workers: int = Field(default=0, ge=0, le=16)  # 0 = 按全局預算自動
    optuna_n_jobs: int = Field(default=0, ge=0, le=16)  # 0 = 按全局預算自動
    multi_strategy_workers: int = Field(default=4, ge=1, le=16)
    optimize_all_workers: int = Field(default=2, ge=1, le=8)  # 僅 optimize_all_parallel=true 時生效
    optimize_all_parallel: bool = False  # 默認策略串行+進程池，避免嵌套爆炸
    task_progress_save_interval_sec: float = Field(default=2.0, ge=0.5, le=30.0)

    # ====== 通知 ======
    notify_console: bool = True
    notify_webhook: bool = False
    webhook_url: str = ""
    notify_wechat_work: bool = False
    wechat_work_webhook: str = ""
    notify_dingtalk: bool = False
    dingtalk_webhook: str = ""
    notify_telegram: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ====== 演示模式 ======
    demo_mode: bool = False

    # ====== 緩存 ======
    cache_enabled: bool = True
    cache_backtest_ttl: int = Field(default=3600, ge=60, le=86400 * 7)
    cache_optimize_ttl: int = Field(default=7200, ge=60, le=86400 * 7)
    cache_portfolio_ttl: int = Field(default=3600, ge=60, le=86400 * 7)
    cache_walkforward_ttl: int = Field(default=7200, ge=60, le=86400 * 7)
    cache_heatmap_ttl: int = Field(default=3600, ge=60, le=86400 * 7)
    cache_multi_strategy_ttl: int = Field(default=3600, ge=60, le=86400 * 7)

    # ====== Redis 緩存 ======
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False
    redis_password: str = ""

    # ====== WebSocket 安全 ======
    ws_auth_required: bool = False  # 本地默認免登錄 WS；生產請設 SQ_WS_AUTH_REQUIRED=true

    # ====== 安全 ======
    jwt_secret: str = ""  # 留空時由 auth.py 自動生成隨機密鑰並持久化到 data/.jwt_secret
    rate_limit_per_minute: int = Field(default=120, ge=10, le=10000)

    # ====== Web 服務 ======
    web_host: str = "0.0.0.0"
    web_port: int = Field(default=8000, ge=1, le=65535)
    web_workers: int = Field(default=1, ge=1, le=16)
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://localhost:5173"

    # ====== 策略參數（全部 19 個內置策略） ======
    strategy_params: dict = Field(default={
        # --- 趨勢類 ---
        "dual_ma": {"fast": 5, "slow": 20},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "turtle": {"entry_period": 20, "exit_period": 10, "atr_period": 20, "risk_pct": 1.0},
        "breakout": {"period": 60, "atr_period": 20, "atr_multiplier": 2.0},
        "momentum": {"lookback": 20, "hold_period": 5},
        "adx_trend": {"adx_period": 14, "adx_threshold": 25, "di_period": 14},
        "parabolic_sar": {"af_start": 0.02, "af_step": 0.02, "af_max": 0.20},
        # --- 均值回歸類 ---
        "bollinger": {"period": 20, "devfactor": 2.0},
        "bollinger_squeeze": {"period": 20, "devfactor": 2.0, "squeeze_threshold": 0.03, "squeeze_lookback": 5},
        "mean_reversion": {"period": 20, "entry_zscore": -2.0, "exit_zscore": 0.0},
        "envelope": {"period": 20, "deviation_pct": 5},
        # --- 振盪指標類 ---
        "rsi": {"period": 14, "overbought": 70, "oversold": 30},
        "kdj": {"period": 9, "period_dfast": 3, "period_dslow": 3, "overbought": 80, "oversold": 20},
        # --- 量價類 ---
        "volume_price": {"price_ma": 20, "volume_ma": 20, "volume_ratio": 2.0},
        "vwap": {"period": 20, "deviation_pct": 1.0},
        "obv": {"obv_ma_period": 20, "price_ma_period": 20},
        # --- 日內突破類 ---
        "dual_thrust": {"period": 4, "k_up": 0.5, "k_down": 0.5},
        "grid": {"grid_pct": 3.0, "position_pct": 0.1},
        # --- 組合類 ---
        "composite": {"min_agreement": 3, "ma_fast": 5, "ma_slow": 20, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "rsi_period": 14, "rsi_overbought": 70, "rsi_oversold": 30, "boll_period": 20, "boll_dev": 2.0},
    })

    # ====== 預警規則 ======
    alert_rules: dict = Field(default={
        "000001": {"name": "平安銀行", "price_above": 13.0, "price_below": 10.0, "change_pct": 5.0},
        "600519": {"name": "貴州茅台", "price_above": 1800.0, "price_below": 1500.0, "change_pct": 3.0},
        "000858": {"name": "五糧液", "price_above": 180.0, "price_below": 120.0, "change_pct": 4.0},
        "601318": {"name": "中國平安", "price_above": 60.0, "price_below": 45.0, "change_pct": 4.0},
        "000333": {"name": "美的集團", "price_above": 80.0, "price_below": 55.0, "change_pct": 4.0},
    })

    # ====== 預設組合 ======
    portfolio_presets: dict = Field(default={
        "conservative": {
            "name": "穩健型",
            "desc": "低風險，均線+布林+均值回歸為主",
            "allocations": [
                {"strategy": "dual_ma", "code": "600519", "weight": 0.20},
                {"strategy": "bollinger", "code": "600519", "weight": 0.20},
                {"strategy": "mean_reversion", "code": "000858", "weight": 0.20},
                {"strategy": "dual_ma", "code": "000858", "weight": 0.20},
                {"strategy": "bollinger", "code": "601318", "weight": 0.20},
            ],
            "rebalance": "periodic",
            "rebalance_freq_days": 20,
        },
        "balanced": {
            "name": "均衡型",
            "desc": "多策略多股票分散，含動量和量價",
            "allocations": [
                {"strategy": "dual_ma", "code": "000001", "weight": 0.12},
                {"strategy": "macd", "code": "600519", "weight": 0.12},
                {"strategy": "bollinger", "code": "000858", "weight": 0.12},
                {"strategy": "rsi", "code": "601318", "weight": 0.12},
                {"strategy": "turtle", "code": "600519", "weight": 0.12},
                {"strategy": "momentum", "code": "000333", "weight": 0.12},
                {"strategy": "volume_price", "code": "000001", "weight": 0.12},
                {"strategy": "composite", "code": "600519", "weight": 0.16},
            ],
            "rebalance": "periodic",
            "rebalance_freq_days": 20,
        },
        "aggressive": {
            "name": "激進型",
            "desc": "高波動策略為主，突破+動量+DualThrust",
            "allocations": [
                {"strategy": "dual_thrust", "code": "600519", "weight": 0.20},
                {"strategy": "turtle", "code": "000858", "weight": 0.15},
                {"strategy": "breakout", "code": "000001", "weight": 0.20},
                {"strategy": "momentum", "code": "000333", "weight": 0.20},
                {"strategy": "composite", "code": "600519", "weight": 0.25},
            ],
            "rebalance": "none",
        },
        "trend_follower": {
            "name": "趨勢跟蹤型",
            "desc": "ADX+SAR+突破，強趨勢行情專用",
            "allocations": [
                {"strategy": "adx_trend", "code": "600519", "weight": 0.25},
                {"strategy": "parabolic_sar", "code": "000858", "weight": 0.25},
                {"strategy": "breakout", "code": "000001", "weight": 0.25},
                {"strategy": "turtle", "code": "601318", "weight": 0.25},
            ],
            "rebalance": "none",
        },
        "value_trap_avoider": {
            "name": "量價驗證型",
            "desc": "OBV+VWAP+量價，用成交量驗證趨勢",
            "allocations": [
                {"strategy": "obv", "code": "600519", "weight": 0.25},
                {"strategy": "vwap", "code": "000858", "weight": 0.25},
                {"strategy": "volume_price", "code": "000001", "weight": 0.25},
                {"strategy": "bollinger_squeeze", "code": "601318", "weight": 0.25},
            ],
            "rebalance": "periodic",
            "rebalance_freq_days": 30,
        },
    })

    model_config = {
        "env_prefix": "SQ_",
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
    }

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if v and not v.startswith(("redis://", "rediss://")):
            raise ValueError("redis_url 必須以 redis:// 或 rediss:// 開頭")
        return v

    @field_validator("web_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v < 1 or v > 65535:
            raise ValueError("端口號必須在 1-65535 之間")
        return v

    def get_strategy_defaults(self, strategy_name: str) -> dict:
        """獲取策略默認參數（config 中的值優先）"""
        return self.strategy_params.get(strategy_name, {})

    def summary(self) -> str:
        """返回配置摘要（脫敏）"""
        lines = [
            f"📊 {self.app_name} v{self.app_version}",
            f"   端口: {self.web_port} | Workers: {self.web_workers}",
            f"   數據庫: {self.db_path}",
            f"   盯盤: {len(self.watchlist)} 只 A股 + {len(self.crypto_watchlist)} 加密 + {len(self.forex_watchlist)} 外匯",
            f"   輪詢: {self.poll_interval_sec}s | 預警冷卻: {self.alert_cooldown_sec}s",
            f"   回測資金: ¥{self.backtest_cash:,.0f} | 佣金: {self.backtest_commission:.1%} | 印花稅: {self.backtest_stamp_tax:.1%}",
            f"   緩存: {'啟用' if self.cache_enabled else '禁用'} | Redis: {'啟用' if self.redis_enabled else '禁用'}",
            f"   CORS: {self.cors_origins}",
            f"   策略: {len(self.strategy_params)} 個已配置",
            f"   預設組合: {', '.join(self.portfolio_presets.keys())}",
        ]
        return "\n".join(lines)


# 全局單例
settings = Settings()
