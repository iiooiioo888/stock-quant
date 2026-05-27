"""
集中式 SQLite Schema 定義 — 所有表與索引的唯一來源
"""

from __future__ import annotations

# ── 核心行情 ──────────────────────────────────────────────

DDL_DAILY_KLINE = """
CREATE TABLE IF NOT EXISTS daily_kline (
    code        TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    turnover    REAL,
    market      TEXT    DEFAULT 'a_share',
    PRIMARY KEY (code, date)
)
"""

DDL_REALTIME_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS realtime_snapshot (
    code        TEXT    PRIMARY KEY,
    name        TEXT,
    price       REAL,
    change_pct  REAL,
    volume      REAL,
    amount      REAL,
    high        REAL,
    low         REAL,
    open        REAL,
    prev_close  REAL,
    updated_at  TEXT
)
"""

DDL_MINUTE_KLINE = """
CREATE TABLE IF NOT EXISTS minute_kline (
    code        TEXT    NOT NULL,
    datetime    TEXT    NOT NULL,
    period      TEXT    NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    PRIMARY KEY (code, datetime, period)
)
"""

# ── 信號 / 回測 / 預警 ────────────────────────────────────

DDL_ALERT_LOG = """
CREATE TABLE IF NOT EXISTS alert_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL,
    rule_type   TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    price       REAL,
    triggered_at TEXT   NOT NULL
)
"""

DDL_BACKTEST_RESULTS = """
CREATE TABLE IF NOT EXISTS backtest_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    params          TEXT,
    total_return_pct REAL,
    sharpe_ratio    REAL,
    max_drawdown_pct REAL,
    annual_return_pct REAL,
    sortino_ratio   REAL,
    calmar_ratio    REAL,
    var_95          REAL,
    cvar_95         REAL,
    total_trades    INTEGER,
    win_rate_pct    REAL,
    initial_cash    REAL,
    final_value     REAL,
    created_at      TEXT NOT NULL
)
"""

DDL_SIGNAL_LOG = """
CREATE TABLE IF NOT EXISTS signal_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    signal          TEXT NOT NULL,
    price           REAL,
    strength        REAL,
    params          TEXT,
    triggered_at    TEXT NOT NULL
)
"""

DDL_STRATEGY_LEADERBOARD = """
CREATE TABLE IF NOT EXISTS strategy_leaderboard (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT    NOT NULL,
    source          TEXT    NOT NULL DEFAULT 'builtin',
    code            TEXT    NOT NULL,
    total_return_pct REAL,
    sharpe_ratio    REAL,
    sortino_ratio   REAL,
    calmar_ratio    REAL,
    max_drawdown_pct REAL,
    win_rate_pct    REAL,
    total_trades    INTEGER,
    annual_return_pct REAL,
    var_95          REAL,
    rank            INTEGER,
    params          TEXT,
    evaluated_at    TEXT    NOT NULL
)
"""

# ── 用戶系統 ──────────────────────────────────────────────

DDL_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT DEFAULT 'user',
    settings        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL
)
"""

DDL_USER_WATCHLISTS = """
CREATE TABLE IF NOT EXISTS user_watchlists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    name            TEXT NOT NULL,
    codes           TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
"""

DDL_USER_ALERT_RULES = """
CREATE TABLE IF NOT EXISTS user_alert_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    code            TEXT NOT NULL,
    rule_type       TEXT NOT NULL,
    params          TEXT NOT NULL,
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
"""

# ── 擴展市場數據 ──────────────────────────────────────────

DDL_SECTOR_DATA = """
CREATE TABLE IF NOT EXISTS sector_data (
    sector_name TEXT NOT NULL,
    sector_type TEXT NOT NULL,
    code        TEXT NOT NULL,
    stock_name  TEXT,
    update_date TEXT,
    PRIMARY KEY (sector_name, sector_type, code)
)
"""

DDL_SECTOR_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS sector_snapshot (
    sector_name       TEXT NOT NULL,
    sector_type       TEXT NOT NULL,
    change_pct        REAL,
    amount            REAL,
    rise_count        INTEGER,
    fall_count        INTEGER,
    leader            TEXT,
    leader_change_pct REAL,
    snapshot_date     TEXT NOT NULL,
    PRIMARY KEY (sector_name, sector_type, snapshot_date)
)
"""

DDL_CAPITAL_FLOW = """
CREATE TABLE IF NOT EXISTS capital_flow (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    flow_type   TEXT NOT NULL,
    main_net    REAL,
    super_net   REAL,
    big_net     REAL,
    mid_net     REAL,
    small_net   REAL,
    close       REAL,
    change_pct  REAL,
    raw_json    TEXT,
    PRIMARY KEY (code, date, flow_type)
)
"""

DDL_DRAGON_TIGER = """
CREATE TABLE IF NOT EXISTS dragon_tiger (
    code            TEXT NOT NULL,
    name            TEXT,
    date            TEXT NOT NULL,
    close           REAL,
    change_pct      REAL,
    reason          TEXT,
    buy_amount      REAL,
    sell_amount     REAL,
    net_amount      REAL,
    turnover_rate   REAL,
    amount          REAL,
    circulating_mv  REAL,
    raw_json        TEXT,
    PRIMARY KEY (code, date)
)
"""

DDL_FUNDAMENTALS = """
CREATE TABLE IF NOT EXISTS fundamentals (
    code            TEXT NOT NULL,
    name            TEXT,
    update_date     TEXT NOT NULL,
    pe_ttm          REAL,
    pb              REAL,
    roe             REAL,
    eps             REAL,
    bvps            REAL,
    total_mv        REAL,
    circulating_mv  REAL,
    revenue         REAL,
    net_profit      REAL,
    gross_margin    REAL,
    net_margin      REAL,
    debt_ratio      REAL,
    dividend_yield  REAL,
    ps_ttm          REAL,
    revenue_yoy     REAL,
    profit_yoy      REAL,
    raw_json        TEXT,
    PRIMARY KEY (code, update_date)
)
"""

DDL_STOCK_UNIVERSE = """
CREATE TABLE IF NOT EXISTS stock_universe (
    code            TEXT NOT NULL,
    market          TEXT NOT NULL,
    name            TEXT,
    exchange        TEXT,
    industry        TEXT,
    list_date       TEXT,
    price           REAL,
    change_pct      REAL,
    total_mv        REAL,
    circulating_mv  REAL,
    pe_ttm          REAL,
    pb              REAL,
    volume          REAL,
    amount          REAL,
    turnover        REAL,
    rank_mv         INTEGER,
    updated_at      TEXT NOT NULL,
    source          TEXT,
    intro           TEXT,
    extra_json      TEXT,
    PRIMARY KEY (code, market)
)
"""

# ── Polymarket ────────────────────────────────────────────

DDL_POLYMARKET_MARKET_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS polymarket_market_snapshot (
    market_id       TEXT NOT NULL,
    slug            TEXT,
    question        TEXT,
    yes_price       REAL,
    no_price        REAL,
    volume          REAL,
    liquidity       REAL,
    active          INTEGER,
    end_date        TEXT,
    payload_json    TEXT,
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (market_id)
)
"""

DDL_POLYMARKET_PRICE_POINT = """
CREATE TABLE IF NOT EXISTS polymarket_price_point (
    token_id        TEXT NOT NULL,
    ts              INTEGER NOT NULL,
    price           REAL NOT NULL,
    interval        TEXT DEFAULT '1d',
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (token_id, ts, interval)
)
"""

DDL_POLYMARKET_ALERT_RULES = """
CREATE TABLE IF NOT EXISTS polymarket_alert_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    market_key      TEXT NOT NULL,
    name            TEXT,
    question        TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    yes_above       REAL,
    yes_below       REAL,
    prob_change_pct REAL,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(market_key)
)
"""

DDL_POLYMARKET_PROB_STATE = """
CREATE TABLE IF NOT EXISTS polymarket_prob_state (
    market_key      TEXT PRIMARY KEY,
    yes_price       REAL NOT NULL,
    no_price        REAL,
    checked_at      TEXT NOT NULL
)
"""

# ── 模擬交易 ──────────────────────────────────────────────

DDL_PAPER_TRADES = """
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
"""

DDL_PAPER_SESSIONS = """
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
"""

DDL_PAPER_POSITIONS = """
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
"""

DDL_PAPER_NAV_HISTORY = """
CREATE TABLE IF NOT EXISTS paper_nav_history (
    session_id TEXT NOT NULL,
    nav REAL NOT NULL,
    cash REAL NOT NULL,
    invested REAL NOT NULL,
    drawdown_pct REAL DEFAULT 0,
    recorded_at TEXT NOT NULL
)
"""

# ── 任務隊列 ──────────────────────────────────────────────

DDL_TASK_LOG = """
CREATE TABLE IF NOT EXISTS task_log (
    task_id     TEXT PRIMARY KEY,
    task_type   TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    title       TEXT,
    status      TEXT NOT NULL,
    progress    INTEGER DEFAULT 0,
    error       TEXT,
    created_at  TEXT,
    completed_at TEXT,
    params_json TEXT
)
"""

# ── 遷移元數據 ────────────────────────────────────────────

DDL_SCHEMA_MIGRATIONS = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version     INTEGER NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL
)
"""

# 建表順序（尊重外鍵依賴）
TABLE_DDL: list[tuple[str, str]] = [
    ("users", DDL_USERS),
    ("user_watchlists", DDL_USER_WATCHLISTS),
    ("user_alert_rules", DDL_USER_ALERT_RULES),
    ("daily_kline", DDL_DAILY_KLINE),
    ("realtime_snapshot", DDL_REALTIME_SNAPSHOT),
    ("minute_kline", DDL_MINUTE_KLINE),
    ("alert_log", DDL_ALERT_LOG),
    ("backtest_results", DDL_BACKTEST_RESULTS),
    ("signal_log", DDL_SIGNAL_LOG),
    ("strategy_leaderboard", DDL_STRATEGY_LEADERBOARD),
    ("sector_data", DDL_SECTOR_DATA),
    ("sector_snapshot", DDL_SECTOR_SNAPSHOT),
    ("capital_flow", DDL_CAPITAL_FLOW),
    ("dragon_tiger", DDL_DRAGON_TIGER),
    ("fundamentals", DDL_FUNDAMENTALS),
    ("stock_universe", DDL_STOCK_UNIVERSE),
    ("polymarket_market_snapshot", DDL_POLYMARKET_MARKET_SNAPSHOT),
    ("polymarket_price_point", DDL_POLYMARKET_PRICE_POINT),
    ("polymarket_alert_rules", DDL_POLYMARKET_ALERT_RULES),
    ("polymarket_prob_state", DDL_POLYMARKET_PROB_STATE),
    ("paper_trades", DDL_PAPER_TRADES),
    ("paper_sessions", DDL_PAPER_SESSIONS),
    ("paper_positions", DDL_PAPER_POSITIONS),
    ("paper_nav_history", DDL_PAPER_NAV_HISTORY),
    ("task_log", DDL_TASK_LOG),
    ("schema_migrations", DDL_SCHEMA_MIGRATIONS),
]

INDEX_DDL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_daily_code ON daily_kline(code)",
    "CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_kline(date)",
    "CREATE INDEX IF NOT EXISTS idx_daily_code_date ON daily_kline(code, date)",
    "CREATE INDEX IF NOT EXISTS idx_daily_market ON daily_kline(market)",
    "CREATE INDEX IF NOT EXISTS idx_bt_code ON backtest_results(code)",
    "CREATE INDEX IF NOT EXISTS idx_bt_created ON backtest_results(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_bt_code_strategy_created ON backtest_results(code, strategy, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sig_code ON signal_log(code)",
    "CREATE INDEX IF NOT EXISTS idx_sig_triggered ON signal_log(triggered_at)",
    "CREATE INDEX IF NOT EXISTS idx_sig_strategy ON signal_log(strategy)",
    "CREATE INDEX IF NOT EXISTS idx_minute_code ON minute_kline(code)",
    "CREATE INDEX IF NOT EXISTS idx_minute_period ON minute_kline(period)",
    "CREATE INDEX IF NOT EXISTS idx_user_username ON users(username)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_user ON user_watchlists(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_alert_user ON user_alert_rules(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sector_name ON sector_data(sector_name)",
    "CREATE INDEX IF NOT EXISTS idx_sector_code ON sector_data(code)",
    "CREATE INDEX IF NOT EXISTS idx_snapshot_date ON sector_snapshot(snapshot_date)",
    "CREATE INDEX IF NOT EXISTS idx_snapshot_type ON sector_snapshot(sector_type)",
    "CREATE INDEX IF NOT EXISTS idx_cf_code ON capital_flow(code)",
    "CREATE INDEX IF NOT EXISTS idx_cf_date ON capital_flow(date)",
    "CREATE INDEX IF NOT EXISTS idx_cf_type ON capital_flow(flow_type)",
    "CREATE INDEX IF NOT EXISTS idx_dt_code ON dragon_tiger(code)",
    "CREATE INDEX IF NOT EXISTS idx_dt_date ON dragon_tiger(date)",
    "CREATE INDEX IF NOT EXISTS idx_fund_code ON fundamentals(code)",
    "CREATE INDEX IF NOT EXISTS idx_fund_date ON fundamentals(update_date)",
    "CREATE INDEX IF NOT EXISTS idx_universe_market ON stock_universe(market)",
    "CREATE INDEX IF NOT EXISTS idx_universe_rank ON stock_universe(rank_mv)",
    "CREATE INDEX IF NOT EXISTS idx_univ_mv ON stock_universe(total_mv DESC)",
    "CREATE INDEX IF NOT EXISTS idx_pm_snapshot_slug ON polymarket_market_snapshot(slug)",
    "CREATE INDEX IF NOT EXISTS idx_pm_snapshot_fetched ON polymarket_market_snapshot(fetched_at)",
    "CREATE INDEX IF NOT EXISTS idx_pm_price_token_ts ON polymarket_price_point(token_id, ts)",
    "CREATE INDEX IF NOT EXISTS idx_pm_alert_enabled ON polymarket_alert_rules(enabled)",
    "CREATE INDEX IF NOT EXISTS idx_lb_strategy ON strategy_leaderboard(strategy_name)",
    "CREATE INDEX IF NOT EXISTS idx_lb_evaluated ON strategy_leaderboard(evaluated_at)",
    "CREATE INDEX IF NOT EXISTS idx_paper_trades_session ON paper_trades(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_paper_nav_session ON paper_nav_history(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_status ON task_log(status)",
    "CREATE INDEX IF NOT EXISTS idx_task_created ON task_log(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_task_status_created ON task_log(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_task_active ON task_log(created_at DESC) WHERE status IN ('pending', 'running')",
]
