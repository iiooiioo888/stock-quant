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
    log_format: str = Field(default="text", pattern="^(text|json)$")
    sentry_dsn: Optional[str] = Field(default=None, description="可選 Sentry DSN（SQ_SENTRY_DSN）")

    # ====== 數據庫 ======
    database_url: str = Field(default="", description="PostgreSQL URL; postgresql://user:pass@host:port/dbname")
    db_path: str = str(DATA_DIR / "stock.db")
    sqlite_cache_size_kb: int = Field(default=64000, ge=1024, le=512000)
    sqlite_mmap_size: int = Field(default=268435456, ge=0, le=1073741824)
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=1000, le=60000)

    # ====== 歷史數據 ======
    history_start_date: str = Field(default="20200101", pattern=r"^\d{8}$")
    # True：讀 K 線時本地無數據則自動爬取一次入庫；之後僅讀本地
    local_first_auto_fetch: bool = Field(default=True)

    # ====== 多幣種結算 ======
    default_preferred_currency: str = Field(default="MOP", pattern=r"^(HKD|MOP|USD|CNY)$")

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
    backtest_stamp_tax: float = Field(default=0.0005, ge=0, le=0.1)  # 2023 年後 0.05%，僅賣出收取
    # 生產環境建議 SQ_ALLOW_STRATEGY_UPLOAD=false
    allow_strategy_upload: bool = True
    strategy_upload_max_bytes: int = Field(default=65536, ge=1024, le=512000)
    volume_slippage_enabled: bool = False
    volume_slippage_participation_cap: float = Field(default=0.05, gt=0, le=1.0)

    # ====== 訂閱 / 計費 ======
    billing_dev_upgrade: bool = Field(
        default=True,
        description="開發環境允許 POST /api/billing/checkout 直接升級 Pro（無支付）",
    )
    billing_checkout_enabled: bool = False
    billing_quota_enforce: bool = Field(
        default=True,
        description="是否強制每日回測/優化等配額；測試與 CI 可設 SQ_BILLING_QUOTA_ENFORCE=false",
    )
    stripe_secret_key: Optional[str] = Field(default=None, description="Stripe Secret Key")
    stripe_webhook_secret: Optional[str] = Field(default=None, description="Stripe Webhook Signing Secret")

    # ====== 股票庫 ======
    stock_universe_max_count: int = Field(default=20000, ge=100, le=50000)
    stock_universe_intro_enrich_limit: int = Field(default=500, ge=0, le=20000)
    # False：/api/stock-logo 僅讀既有快取，未命中不背景下載（前端預設用本地 SVG）
    stock_logo_api_enabled: bool = False

    # ====== 數據下載並行 ======
    download_max_workers: int = Field(default=3, ge=1, le=8)
    download_throttle_sec: float = Field(default=0.5, ge=0.1, le=2.0)

    # ====== 資料源開關與限速 ======
    yahoo_enabled: bool = Field(default=True, description="是否啟用 Yahoo Finance（SQ_YAHOO_ENABLED）")
    akshare_enabled: bool = Field(default=True, description="是否啟用 AKShare 備選源（SQ_AKSHARE_ENABLED）")
    yahoo_request_interval: float = Field(
        default=1.0,
        ge=0.2,
        le=10.0,
        description="Yahoo 主動請求最小間隔（秒），SQ_YAHOO_REQUEST_INTERVAL",
    )
    yahoo_max_retries: int = Field(default=3, ge=1, le=10, description="Yahoo 單請求最大重試次數")

    # ====== 任務並行 ======
    task_max_workers: int = Field(default=0, ge=0, le=32)  # 0 = 自動 min(4, CPU-1)
    task_parallel_grid: bool = True
    optimize_parallel_backend: str = "auto"  # auto | joblib | futures（網格搜索並行後端）
    task_grid_workers: int = Field(default=0, ge=0, le=16)  # 0 = 按全局預算自動
    optuna_n_jobs: int = Field(default=0, ge=0, le=16)  # 0 = 按全局預算自動
    multi_strategy_workers: int = Field(default=4, ge=1, le=16)
    optimize_all_workers: int = Field(default=2, ge=1, le=8)  # 僅 optimize_all_parallel=true 時生效
    optimize_all_parallel: bool = False  # 默認策略串行+進程池，避免嵌套爆炸
    task_progress_save_interval_sec: float = Field(default=2.0, ge=0.5, le=30.0)
    task_heavy_max_concurrent: int = Field(default=2, ge=1, le=16)  # Backtrader 等重型任務同時上限
    task_timeout_sec: int = Field(default=1800, ge=60, le=86400)  # 單任務超時熔斷（秒）
    task_watchdog_interval_sec: float = Field(default=60.0, ge=10.0, le=600.0)

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

    # ====== 定時任務 (APScheduler) ======
    scheduler_enabled: bool = True
    scheduler_auto_register: bool = True
    scheduler_job_incremental: bool = True
    scheduler_job_daily_report: bool = True
    scheduler_job_data_quality: bool = True
    scheduler_job_degradation: bool = False
    scheduler_job_correlation: bool = False
    scheduler_job_leaderboard: bool = True
    scheduler_job_daily_download: bool = True  # 每天 09:00 爬取數據
    scheduler_incremental_hour: int = Field(default=8, ge=0, le=23)
    scheduler_incremental_minute: int = Field(default=5, ge=0, le=59)

    # ====== 加密貨幣行情（Binance 等，只讀） ======
    crypto_enabled: bool = True

    # ── 加密貨幣 WebSocket 串流 ──
    crypto_ws_enabled: bool = True
    crypto_ws_streams: list[str] = Field(
        default=["trade", "kline_1m", "ticker", "depth"],
        description="訂閱串流類型：trade / kline_* / ticker / depth",
    )
    crypto_ws_kline_intervals: list[str] = Field(
        default=["1m", "5m", "15m", "1h"],
        description="K 線週期（僅 stream_types 含 kline 時生效）",
    )
    crypto_ws_reconnect_base_sec: int = Field(default=5, ge=1, le=30)
    crypto_ws_reconnect_max_sec: int = Field(default=60, ge=10, le=300)
    crypto_ws_trade_window_size: int = Field(default=10000, ge=1000, le=100000)
    crypto_ws_max_connections: int = Field(default=5, ge=1, le=20)

    # ── 加密貨幣技術指標參數 ──
    crypto_indicator_rsi_period: int = Field(default=14, ge=2, le=100)
    crypto_indicator_macd_fast: int = Field(default=12, ge=2, le=50)
    crypto_indicator_macd_slow: int = Field(default=26, ge=5, le=100)
    crypto_indicator_macd_signal: int = Field(default=9, ge=2, le=50)
    crypto_indicator_bb_period: int = Field(default=20, ge=5, le=100)
    crypto_indicator_bb_std: float = Field(default=2.0, ge=0.5, le=5.0)
    crypto_indicator_ema_periods: list[int] = Field(default=[9, 21, 55, 200])
    crypto_indicator_atr_period: int = Field(default=14, ge=2, le=100)
    crypto_indicator_mfi_period: int = Field(default=14, ge=2, le=100)
    crypto_indicator_stoch_rsi_period: int = Field(default=14, ge=2, le=100)
    crypto_indicator_cci_period: int = Field(default=20, ge=5, le=100)

    # ── 加密貨幣微結構分析 ──
    crypto_micro_large_order_multiplier: float = Field(default=10.0, ge=2.0, le=100.0)
    crypto_micro_depth_levels: int = Field(default=20, ge=5, le=100)

    # ── 加密貨幣告警 ──
    crypto_alerts_enabled: bool = True
    crypto_alert_price_change_pct: float = Field(default=5.0, ge=0.5, le=50.0)
    crypto_alert_volume_surge_multiplier: float = Field(default=5.0, ge=2.0, le=50.0)
    crypto_alert_rsi_overbought: float = Field(default=70.0, ge=50.0, le=95.0)
    crypto_alert_rsi_oversold: float = Field(default=30.0, ge=5.0, le=50.0)
    crypto_alert_cooldown_sec: int = Field(default=300, ge=10, le=3600)
    crypto_alert_large_order_usd: float = Field(default=100000.0, ge=1000.0, le=10000000.0)

    # ── 加密貨幣數據持久化 ──
    crypto_persist_trades: bool = False
    crypto_persist_kline: bool = True
    crypto_kline_max_days: int = Field(default=365, ge=7, le=3650)

    # ── 加密貨幣推送 ──
    crypto_push_interval_sec: int = Field(default=5, ge=1, le=60)
    crypto_push_types: list[str] = Field(
        default=["quotes", "indicators", "alerts", "micro"],
        description="WS 推送的消息類型",
    )

    # ====== TradingView / IB 行情（儀表盤掛牌） ======
    tradingview_enabled: bool = True
    ib_enabled: bool = False
    ib_host: str = "127.0.0.1"
    ib_port: int = Field(default=7497, ge=1, le=65535)
    ib_client_id: int = Field(default=10, ge=0, le=9999)

    # ====== 緩存 ======
    cache_enabled: bool = True
    cache_backtest_ttl: int = Field(default=3600, ge=60, le=86400 * 7)
    cache_optimize_ttl: int = Field(default=7200, ge=60, le=86400 * 7)
    cache_portfolio_ttl: int = Field(default=3600, ge=60, le=86400 * 7)
    cache_walkforward_ttl: int = Field(default=7200, ge=60, le=86400 * 7)
    cache_heatmap_ttl: int = Field(default=3600, ge=60, le=86400 * 7)
    cache_multi_strategy_ttl: int = Field(default=3600, ge=60, le=86400 * 7)
    cache_lru_max_size: int = Field(default=2048, ge=256, le=16384)
    cache_warmup_on_startup: bool = False
    cache_warmup_codes: list[str] = Field(default=[
        "600519",
        "000001",
        "601318",
    ])
    cache_warmup_indicators: bool = True
    numba_enabled: bool = True
    heatmap_parallel: bool = True
    heatmap_max_workers: int = Field(default=4, ge=1, le=16)

    # ====== Celery 任務佇列 ======
    celery_enabled: bool = False
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    db_read_replica_path: str = ""
    prometheus_enabled: bool = True
    runtime_gc_interval_sec: float = Field(default=3600.0, ge=300.0, le=86400.0)



    # ====== Redis 緩存 ======
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False
    redis_password: str = ""

    # ====== WebSocket 安全 ======
    ws_auth_required: bool = False  # 本地/演示可關閉；非演示模式見 effective_ws_auth_required

    # ====== LLM 智能問答（OpenAI 兼容 API） ======
    llm_enabled: bool = True
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_sec: int = Field(default=90, ge=15, le=300)
    llm_max_tool_rounds: int = Field(default=6, ge=1, le=12)
    llm_max_tokens: int = Field(default=2048, ge=256, le=8192)
    llm_temperature: float = Field(default=0.2, ge=0, le=1.5)

    # ====== 安全 ======
    jwt_secret: str = ""  # 留空時由 auth.py 自動生成隨機密鑰並持久化到 data/.jwt_secret
    rate_limit_per_minute: int = Field(default=120, ge=10, le=10000)

    # ====== Web 服務 ======
    web_host: str = "0.0.0.0"
    web_port: int = Field(default=8000, ge=1, le=65535)
    web_workers: int = Field(default=4, ge=1, le=16)
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://localhost:5173"

    # ====== 策略參數（全部 29 個內置策略） ======
    strategy_params: dict = Field(default={
        # --- 趨勢類 ---
        "dual_ma": {"fast": 5, "slow": 20},
        "ema_cross": {"fast": 12, "slow": 26},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "turtle": {"entry_period": 20, "exit_period": 10, "atr_period": 20, "risk_pct": 1.0},
        "breakout": {"period": 60, "atr_period": 20, "atr_multiplier": 2.0},
        "momentum": {"lookback": 20, "hold_period": 5},
        "adx_trend": {"adx_period": 14, "adx_threshold": 25, "di_period": 14},
        "parabolic_sar": {"af_start": 0.02, "af_step": 0.02, "af_max": 0.20},
        "donchian": {"period": 20},
        "supertrend": {"period": 10, "multiplier": 3.0},
        "atr_trail": {"ma_period": 20, "atr_period": 14, "atr_mult": 2.5},
        "triple_ma": {"fast": 5, "mid": 20, "slow": 60},
        "pullback_ma": {"fast": 10, "slow": 50, "trend": 120},
        # --- 均值回歸類 ---
        "bollinger": {"period": 20, "devfactor": 2.0},
        "bollinger_squeeze": {"period": 20, "devfactor": 2.0, "squeeze_threshold": 0.03, "squeeze_lookback": 5},
        "mean_reversion": {"period": 20, "entry_zscore": -2.0, "exit_zscore": 0.0},
        "envelope": {"period": 20, "deviation_pct": 5},
        # --- 振盪指標類 ---
        "rsi": {"period": 14, "overbought": 70, "oversold": 30},
        "kdj": {"period": 9, "period_dfast": 3, "period_dslow": 3, "overbought": 80, "oversold": 20},
        "williams_r": {"period": 14, "overbought": -20, "oversold": -80},
        "cci": {"period": 20, "overbought": 100, "oversold": -100},
        # --- 量價類 ---
        "volume_price": {"price_ma": 20, "volume_ma": 20, "volume_ratio": 2.0},
        "ema_volume": {"fast": 12, "slow": 26, "vol_ma": 20, "vol_ratio": 1.2},
        "vwap": {"period": 20, "deviation_pct": 1.0},
        "obv": {"obv_ma_period": 20, "price_ma_period": 20},
        # --- 日內突破類 ---
        "dual_thrust": {"period": 4, "k_up": 0.5, "k_down": 0.5},
        "grid": {"grid_pct": 3.0, "position_pct": 0.1},
        # --- 組合類 ---
        "composite": {"min_agreement": 3, "ma_fast": 5, "ma_slow": 20, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "rsi_period": 14, "rsi_overbought": 70, "rsi_oversold": 30, "boll_period": 20, "boll_dev": 2.0},
        "macd_rsi": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "rsi_period": 14, "rsi_max": 68, "rsi_min": 35},
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

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if v and not v.startswith(("postgresql://","postgres://")):
            raise ValueError("database_url 必須以 postgresql:// 開頭")
        return v

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

    @property
    def effective_ws_auth_required(self) -> bool:
        """WebSocket 是否要求認證：顯式開啟，或非演示/非 debug 時默認啟用。"""
        if self.ws_auth_required:
            return True
        if self.demo_mode or self.debug:
            return False
        return True

    def get_strategy_defaults(self, strategy_name: str) -> dict:
        """獲取策略默認參數（config 中的值優先）"""
        return self.strategy_params.get(strategy_name, {})

    def summary(self) -> str:
        """返回配置摘要（脫敏）"""
        lines = [
            f"📊 {self.app_name} v{self.app_version}",
            f"   端口: {self.web_port} | Workers: {self.web_workers}",
            f"   數據庫: {'PostgreSQL' if self.database_url else self.db_path}",
            f"   盯盤: {len(self.watchlist)} 只 A股 + {len(self.crypto_watchlist)} 加密 + {len(self.forex_watchlist)} 外匯",
            f"   輪詢: {self.poll_interval_sec}s | 預警冷卻: {self.alert_cooldown_sec}s",
            f"   回測資金: ¥{self.backtest_cash:,.0f} | 佣金: {self.backtest_commission:.1%} | 印花稅: {self.backtest_stamp_tax:.1%}",
            f"   緩存: {'啟用' if self.cache_enabled else '禁用'} | Redis: {'啟用' if self.redis_enabled else '禁用'}",
            f"   CORS: {self.cors_origins}",
            f"   策略: {len(self.strategy_params)} 個已配置",
            f"   預設組合: {', '.join(self.portfolio_presets.keys())}",
        ]
        return "\n".join(lines)

    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def is_public_demo_deployment(self) -> bool:
        """演示模式且 CORS 含非 localhost 域名（公開部署特徵）。"""
        if not self.demo_mode:
            return False
        localhost_markers = ("localhost", "127.0.0.1")
        for origin in self.cors_origin_list():
            low = origin.lower()
            if not any(m in low for m in localhost_markers):
                return True
        return False

    def log_demo_security_warnings(self, logger) -> None:
        """啟動時輸出演示/生產安全配置風險。"""
        if not self.demo_mode:
            if not self.jwt_secret:
                logger.warning(
                    "SQ_JWT_SECRET 未設置，將使用自動生成密鑰；生產環境建議顯式配置。"
                )
            # CORS 警告：非 localhost 部署時提醒用戶
            non_localhost_origins = [
                o for o in self.cors_origin_list()
                if o and 'localhost' not in o.lower() and '127.0.0.1' not in o
            ]
            if non_localhost_origins:
                logger.warning(
                    f"⚠️  CORS 配置警告：檢測到非 localhost 來源 {non_localhost_origins}。"
                    " 若部署在公網，請確保 CORS 配置正確，避免跨域攻擊風險。"
                    " 建議設置 SQ_CORS_ORIGINS 為具體前端域名，例如：https://yourdomain.com"
                )
            return

        if self.is_public_demo_deployment():
            logger.warning(
                "⚠️  公開演示模式：SQ_DEMO_MODE=true 且 CORS 含公網域名。"
                " GET 讀取白名單較寬，請務必設置 SQ_DEMO_ADMIN_PASSWORD 並勿用於私有生產數據。"
            )
        else:
            logger.info("演示模式已啟用（本地/開發）。")

        if not os.environ.get("SQ_DEMO_ADMIN_PASSWORD"):
            logger.warning(
                "SQ_DEMO_ADMIN_PASSWORD 未設置：管理員密碼見 data/.admin_password 或首次啟動日誌。"
            )


# 全局單例
settings = Settings()
