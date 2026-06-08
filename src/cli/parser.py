import argparse

from src.cli.helpers import add_alloc_arg


def build_parser():
    parser = argparse.ArgumentParser(
        prog="stock-quant",
        description="📈 stock-quant — A股量化回測 + 實時盯盤預警系統",
        epilog="示例:\n"
        "  python main.py serve --port 8080\n"
        "  python main.py download 000001 600519\n"
        "  python main.py backtest 600519 macd\n"
        "  python main.py optimize 600519 --method optuna\n"
        '  python main.py portfolio --alloc "dual_ma:000001,macd:600519"\n'
        "  python main.py config show -v\n"
        "  python main.py strategy list",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve
    p_serve = subparsers.add_parser("serve", help="啟動 Web 服務")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--workers", type=int, default=None)
    p_serve.add_argument("--reload", action="store_true")

    # download
    p_dl = subparsers.add_parser("download", help="下載歷史數據")
    p_dl.add_argument("codes", nargs="*", help="股票代碼")
    p_dl.add_argument("--incremental", action="store_true", help="增量下載")
    p_dl.add_argument("--force", action="store_true", help="強制重新下載全部")

    # seed — 預載常見數據
    p_seed = subparsers.add_parser("seed", help="預載常見數據（藍籌/指數/目錄）")
    p_seed.add_argument(
        "--profile",
        choices=("quick", "standard", "full"),
        default="standard",
        help="quick | standard（默認）| full",
    )
    p_seed.add_argument("--force", action="store_true", help="強制重新下載日 K")
    p_seed.add_argument(
        "--no-download", action="store_true", help="僅寫目錄，不下載 K 線"
    )
    p_seed.add_argument(
        "--sync-universe", action="store_true", help="從行情源同步股票庫"
    )
    p_seed.add_argument("--with-backtest", action="store_true", help="生成示範回測")

    # backtest
    p_bt = subparsers.add_parser(
        "backtest",
        help="策略回測",
        epilog="可用策略: dual_ma, macd, bollinger, kdj, rsi, grid, turtle, dual_thrust, "
        "momentum, mean_reversion, volume_price, breakout, composite, vwap, "
        "envelope, parabolic_sar, obv, bollinger_squeeze, adx_trend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_bt.add_argument("code", help="股票代碼")
    p_bt.add_argument("strategy", nargs="?", default="dual_ma")
    p_bt.add_argument(
        "--slippage",
        type=float,
        default=0.0,
        help="滑點百分比（默認 0.0，如 0.1 表示 0.1%%）",
    )
    p_bt.add_argument("--no-t1", action="store_true", help="禁用 T+1 限制（默認啟用）")
    p_bt.add_argument(
        "--no-limit", action="store_true", help="禁用漲跌停限制（默認啟用）"
    )

    # optimize
    p_opt = subparsers.add_parser("optimize", help="參數優化")
    p_opt.add_argument("code", help="股票代碼")
    p_opt.add_argument("strategy", nargs="?", default="all")
    p_opt.add_argument("--method", choices=["grid", "optuna"], default="grid")
    p_opt.add_argument(
        "--objective", choices=["sharpe", "return", "calmar"], default="sharpe"
    )
    p_opt.add_argument("--trials", type=int, default=100)

    # portfolio
    p_pf = subparsers.add_parser("portfolio", help="組合回測")
    add_alloc_arg(p_pf)

    # monitor
    p_mon = subparsers.add_parser("monitor", help="實時盯盤")

    # walkforward
    p_wf = subparsers.add_parser("walkforward", help="Walk-Forward 分析")
    p_wf.add_argument("code", help="股票代碼")
    p_wf.add_argument("strategy", nargs="?", default="dual_ma")
    p_wf.add_argument("--train-days", type=int, default=750)
    p_wf.add_argument("--test-days", type=int, default=250)
    p_wf.add_argument("--step-days", type=int, default=250)
    p_wf.add_argument(
        "--objective", choices=["sharpe", "return", "calmar"], default="sharpe"
    )
    p_wf.add_argument("--trials", type=int, default=50)

    # auto-optimize
    p_ao = subparsers.add_parser("auto-optimize", help="自動參數優化")
    p_ao.add_argument("--method", choices=["grid", "optuna"], default="optuna")
    p_ao.add_argument(
        "--objective", choices=["sharpe", "return", "calmar"], default="sharpe"
    )
    p_ao.add_argument("--trials", type=int, default=50)

    # heatmap
    p_hm = subparsers.add_parser("heatmap", help="參數熱力圖")
    p_hm.add_argument("code", help="股票代碼")
    p_hm.add_argument("strategy", help="策略名稱")
    p_hm.add_argument("param_x", help="X 軸參數")
    p_hm.add_argument("param_y", help="Y 軸參數")
    p_hm.add_argument("--grid-size", type=int, default=10, help="網格大小")
    p_hm.add_argument(
        "--objective",
        choices=["sharpe", "return", "calmar", "win_rate"],
        default="sharpe",
    )

    # screen
    p_scr = subparsers.add_parser("screen", help="股票篩選")
    p_scr.add_argument("codes", nargs="*", help="股票代碼")
    p_scr.add_argument("--ma-bullish", action="store_true", help="MA 多頭排列")
    p_scr.add_argument("--volume-surge", type=float, help="成交量暴增倍數")
    p_scr.add_argument("--above-ma", type=int, help="站上 N 日均線")
    p_scr.add_argument("--near-high", type=float, help="接近 52 週新高百分比")
    p_scr.add_argument("--price-change", type=float, help="N 日漲幅百分比")

    # dynamic-portfolio
    p_dp = subparsers.add_parser("dynamic-portfolio", help="動態權重組合回測")
    p_dp.add_argument("--window", type=int, default=60, help="滾動窗口天數")
    p_dp.add_argument("--freq", type=int, default=20, help="權重調整頻率（天）")
    add_alloc_arg(p_dp)

    # kelly
    p_kelly = subparsers.add_parser("kelly", help="Kelly 公式最優倉位")
    p_kelly.add_argument("--limit", type=float, default=0.5, help="Kelly 比例上限")
    add_alloc_arg(p_kelly)

    # degradation
    p_deg = subparsers.add_parser("degradation", help="策略衰退檢測")
    p_deg.add_argument("--lookback", type=int, default=30, help="回看天數")
    p_deg.add_argument("--threshold", type=int, default=5, help="連續跑輸天數閾值")
    add_alloc_arg(p_deg)

    # arbitrate
    p_arb = subparsers.add_parser("arbitrate", help="信號衝突仲裁")
    add_alloc_arg(p_arb)

    # risk-parity
    p_rp = subparsers.add_parser("risk-parity", help="風險平價組合")
    add_alloc_arg(p_rp)

    # mvo
    p_mvo = subparsers.add_parser("mvo", help="均值-方差優化 (Markowitz)")
    p_mvo.add_argument(
        "--objective",
        choices=["max_sharpe", "min_variance", "max_return"],
        default="max_sharpe",
    )
    p_mvo.add_argument("--simulations", type=int, default=5000, help="蒙特卡羅模擬次數")
    add_alloc_arg(p_mvo)

    # vol-target
    p_vt = subparsers.add_parser("vol-target", help="波動率目標組合")
    p_vt.add_argument("--target", type=float, default=0.15, help="目標年化波動率")
    p_vt.add_argument("--lookback", type=int, default=20, help="波動率計算窗口")
    add_alloc_arg(p_vt)

    # max-diversification
    p_md = subparsers.add_parser("max-diversification", help="最大分散化組合")
    add_alloc_arg(p_md)

    # anti-correlation
    p_ac = subparsers.add_parser("anti-correlation", help="反相關組合")
    add_alloc_arg(p_ac)

    # regime-switch
    p_rs = subparsers.add_parser("regime-switch", help="市場狀態切換組合")
    p_rs.add_argument(
        "--method",
        choices=["volatility", "trend"],
        default="volatility",
        help="狀態判定方法",
    )
    p_rs.add_argument("--lookback", type=int, default=60, help="狀態判定窗口天數")
    add_alloc_arg(p_rs)

    # voting-portfolio
    p_vp = subparsers.add_parser("voting-portfolio", help="投票式組合回測")
    p_vp.add_argument("--min-votes", type=int, default=2, help="最低同意票數（默認 2）")
    add_alloc_arg(p_vp)

    # momentum-of-momentum
    p_mm = subparsers.add_parser("momentum-of-momentum", help="動量的動量組合回測")
    p_mm.add_argument(
        "--lookback", type=int, default=60, help="動量計算回看天數（默認 60）"
    )
    add_alloc_arg(p_mm)

    # adaptive-regime
    p_ar = subparsers.add_parser("adaptive-regime", help="自適應市場狀態組合回測")
    add_alloc_arg(p_ar)

    # black-litterman
    p_bl = subparsers.add_parser("black-litterman", help="Black-Litterman 模型組合")
    add_alloc_arg(p_bl)

    # hrp
    p_hrp = subparsers.add_parser("hrp", help="層次風險平價 (HRP) 組合")
    add_alloc_arg(p_hrp)

    # cvar
    p_cvar = subparsers.add_parser("cvar", help="CVaR 優化組合")
    p_cvar.add_argument(
        "--alpha", type=float, default=0.05, help="VaR 顯著性水平（默認 0.05）"
    )
    add_alloc_arg(p_cvar)

    # multi-timeframe
    p_mtf = subparsers.add_parser("multi-timeframe", help="多時間框架信號確認")
    p_mtf.add_argument(
        "--windows", default="5,20,60", help="時間窗口（逗號分隔，默認 5,20,60）"
    )
    add_alloc_arg(p_mtf)

    # dynamic-rebalance
    p_dr = subparsers.add_parser("dynamic-rebalance", help="動態再平衡觸發")
    p_dr.add_argument(
        "--threshold", type=float, default=5.0, help="權重偏移觸發閾值 %%（默認 5.0）"
    )
    p_dr.add_argument(
        "--vol-window", type=int, default=20, help="波動率計算窗口（默認 20）"
    )
    add_alloc_arg(p_dr)

    # sector-limit
    p_sl = subparsers.add_parser("sector-limit", help="板塊敞口限制")
    p_sl.add_argument(
        "--max-pct", type=float, default=40.0, help="單板塊最大佔比 %%（默認 40.0）"
    )
    add_alloc_arg(p_sl)

    # config
    p_cfg = subparsers.add_parser("config", help="查看/驗證配置")
    cfg_sub = p_cfg.add_subparsers(dest="config_action")
    p_cfg_show = cfg_sub.add_parser("show", help="顯示當前配置")
    p_cfg_show.add_argument("-v", "--verbose", action="store_true", help="顯示詳細信息")
    cfg_sub.add_parser("validate", help="驗證配置完整性")

    # strategy
    p_strat = subparsers.add_parser("strategy", help="策略管理")
    strat_sub = p_strat.add_subparsers(dest="strategy_action")

    # strategy create
    p_strat_create = strat_sub.add_parser("create", help="創建策略模板")
    p_strat_create.add_argument("name", help="策略名稱（英文）")
    p_strat_create.add_argument("filepath", nargs="?", help="輸出路徑（可選）")

    # strategy list
    strat_sub.add_parser("list", help="列出所有策略")

    # strategy leaderboard
    p_strat_lb = strat_sub.add_parser("leaderboard", help="策略排行榜")
    p_strat_lb.add_argument("--codes", nargs="*", help="股票代碼（默認 watchlist）")
    p_strat_lb.add_argument(
        "--sort-by",
        choices=["sharpe", "return", "drawdown", "win_rate"],
        default="sharpe",
    )
    p_strat_lb.add_argument("--limit", type=int, default=20, help="顯示條數")

    # report（增強報告）
    p_rpt = subparsers.add_parser("report", help="增強回測報告")
    rpt_sub = p_rpt.add_subparsers(dest="report_action")

    # report full
    p_rpt_full = rpt_sub.add_parser("full", help="全面回測報告")
    p_rpt_full.add_argument("code", help="股票代碼")
    p_rpt_full.add_argument("strategy", nargs="?", default="dual_ma", help="策略名稱")

    # report comparison
    p_rpt_cmp = rpt_sub.add_parser("comparison", help="多股對比報告")
    p_rpt_cmp.add_argument("codes", nargs="+", help="股票代碼列表")
    p_rpt_cmp.add_argument("--strategy", default="dual_ma", help="策略名稱")

    # report strategy
    p_rpt_strat = rpt_sub.add_parser("strategy", help="策略分析報告")
    p_rpt_strat.add_argument("strategy_name", help="策略名稱")
    p_rpt_strat.add_argument("codes", nargs="*", help="股票代碼（默認 watchlist）")

    # monte-carlo
    p_mc = subparsers.add_parser("monte-carlo", help="蒙特卡羅模擬")
    p_mc.add_argument("code", help="股票代碼")
    p_mc.add_argument("strategy", nargs="?", default="dual_ma", help="策略名稱")
    p_mc.add_argument("--simulations", type=int, default=1000, help="模擬次數")
    p_mc.add_argument("--days", type=int, default=252, help="模擬天數")

    # rolling-metrics
    p_rm = subparsers.add_parser("rolling-metrics", help="滾動性能指標")
    p_rm.add_argument("code", help="股票代碼")
    p_rm.add_argument("--window", type=int, default=60, help="滾動窗口天數")

    # export
    p_exp = subparsers.add_parser("export", help="導出數據")
    p_exp.add_argument("type", choices=["backtest", "trades"], help="導出類型")
    p_exp.add_argument("--id", type=int, help="回測結果 ID")
    p_exp.add_argument("--code", help="股票代碼")
    p_exp.add_argument("--strategy", help="策略名稱")
    p_exp.add_argument(
        "--format", choices=["csv", "json"], default="csv", help="導出格式"
    )
    p_exp.add_argument("--output", "-o", help="輸出文件路徑")

    # signals
    p_sig = subparsers.add_parser("signals", help="實時交易信號")
    p_sig.add_argument(
        "action",
        choices=["compute", "history", "strength", "ranking", "heatmap", "backtest"],
        help="操作類型",
    )
    p_sig.add_argument(
        "codes", nargs="*", help="股票代碼 (compute 模式) 或目標代碼 (history/strength)"
    )
    p_sig.add_argument("--code", help="股票代碼 (history/strength)")
    p_sig.add_argument("--days", type=int, default=30, help="歷史天數 (history 模式)")
    p_sig.add_argument("--strategy", help="策略名稱過濾")

    # risk（風險管理）
    p_risk = subparsers.add_parser("risk", help="風險管理")
    risk_sub = p_risk.add_subparsers(dest="risk_action")

    # risk position-size
    p_risk_ps = risk_sub.add_parser("position-size", help="計算倉位大小")
    p_risk_ps.add_argument("--capital", type=float, default=100000, help="總資金")
    p_risk_ps.add_argument("--atr", type=float, default=0, help="ATR 值")
    p_risk_ps.add_argument("--code", help="股票代碼（自動計算 ATR）")
    p_risk_ps.add_argument(
        "--method",
        choices=["atr", "fixed", "kelly", "volatility", "drawdown"],
        default="atr",
        help="計算方法",
    )
    p_risk_ps.add_argument(
        "--fraction", type=float, default=0.1, help="固定比例（fixed 方法）"
    )
    p_risk_ps.add_argument(
        "--win-rate", type=float, default=0.5, help="勝率（kelly 方法）"
    )
    p_risk_ps.add_argument(
        "--max-risk", type=float, default=0.02, help="每筆最大風險比例"
    )

    # risk budget-check
    p_risk_bc = risk_sub.add_parser("budget-check", help="風險預算檢查")
    p_risk_bc.add_argument(
        "--max-portfolio-risk", type=float, default=0.15, help="組合最大風險"
    )
    p_risk_bc.add_argument(
        "--max-single-risk", type=float, default=0.05, help="單持倉最大風險"
    )

    # risk drawdown
    p_risk_dd = risk_sub.add_parser("drawdown", help="回撤保護分析")
    p_risk_dd.add_argument("--nav-file", help="CSV 文件路徑（含 date,nav 列）")
    p_risk_dd.add_argument("--max-dd", type=float, default=20.0, help="最大回撤百分比")
    p_risk_dd.add_argument("--code", help="股票代碼（用於模擬分析）")

    # scheduler（定時任務）
    p_sched = subparsers.add_parser("scheduler", help="定時任務 (APScheduler)")
    sched_sub = p_sched.add_subparsers(dest="scheduler_action")
    sched_sub.add_parser("list", help="列出任務目錄與狀態")
    sched_sub.add_parser("setup", help="按 config 註冊默認任務")
    p_sched_run = sched_sub.add_parser("run", help="立即執行一次")
    p_sched_run.add_argument("job_id", nargs="?", help="任務 ID，如 incremental_update")
    p_sched_en = sched_sub.add_parser("enable", help="啟用任務")
    p_sched_en.add_argument("job_id", nargs="?", help="任務 ID（省略則啟用全套）")
    p_sched_dis = sched_sub.add_parser("disable", help="禁用任務")
    p_sched_dis.add_argument("job_id", nargs="?", help="任務 ID（省略則全部禁用）")

    # user（多用戶管理）
    p_user = subparsers.add_parser("user", help="用戶管理")
    user_sub = p_user.add_subparsers(dest="user_action")

    # user create
    p_user_create = user_sub.add_parser("create", help="創建用戶")
    p_user_create.add_argument("username", help="用戶名")
    p_user_create.add_argument("password", help="密碼")
    p_user_create.add_argument(
        "--role", choices=["admin", "user"], default="user", help="角色（默認 user）"
    )

    # user list
    user_sub.add_parser("list", help="列出所有用戶")

    # user reset-password
    p_user_reset = user_sub.add_parser("reset-password", help="重置用戶密碼")
    p_user_reset.add_argument("username", help="用戶名")
    p_user_reset.add_argument(
        "new_password", nargs="?", default=None, help="新密碼（不提供則交互輸入）"
    )

    # stock-universe（股票庫）
    p_univ = subparsers.add_parser("stock-universe", help="股票庫（按市值前 N）")
    univ_sub = p_univ.add_subparsers(dest="universe_action")
    p_univ_sync = univ_sub.add_parser("sync", help="同步多市場基本資料入庫")
    p_univ_sync.add_argument(
        "--max",
        type=int,
        default=None,
        help="入庫數量上限（默認 SQ_STOCK_UNIVERSE_MAX_COUNT=20000）",
    )
    univ_sub.add_parser("stats", help="查看股票庫統計")
    p_univ_list = univ_sub.add_parser("list", help="列出股票庫")
    p_univ_list.add_argument(
        "--market", default="all", help="a_share/hk_stock/us_stock/all"
    )
    p_univ_list.add_argument("--limit", type=int, default=20)
    p_univ_list.add_argument("--keyword", default=None)

    # ops（運維健檢，對齊 docs/runbooks）
    p_ops = subparsers.add_parser("ops", help="運維健檢（無需 Cursor API key）")
    ops_sub = p_ops.add_subparsers(dest="ops_action")
    p_ops_check = ops_sub.add_parser(
        "check", help="本機 SOP 健檢（DB/管線/索引/數據源）"
    )
    p_ops_check.add_argument("--json", action="store_true", help="輸出 JSON")
    p_ops_check.add_argument("--verbose", action="store_true", help="附完整快照")
    p_ops_check.add_argument(
        "--ci",
        action="store_true",
        help="CI 模式：僅 critical 時非零退出碼",
    )
    p_ops_probe = ops_sub.add_parser(
        "probe", help="HTTP 探活 /api/health/sop（服務已啟動）"
    )
    p_ops_probe.add_argument(
        "--url",
        default="http://127.0.0.1:8000/api/health/sop",
        help="SOP 端點 URL",
    )
    p_ops_probe.add_argument(
        "--timeout", type=float, default=10.0, help="HTTP 逾時（秒）"
    )
    p_ops_probe.add_argument("--json", action="store_true", help="輸出 JSON")
    p_ops_probe.add_argument(
        "--ci",
        action="store_true",
        help="CI 模式：僅 critical 時非零退出碼",
    )

    return parser
