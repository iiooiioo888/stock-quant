# 10. CLI 命令

## 10.1 概述

CLI 入口為 `main.py`，通過 `src/cli/run.py` 分發到 50+ 個命令處理函數。

```bash
python main.py <command> [options]
```

---

## 10.2 核心命令

### 服務管理

```bash
# 啟動 Web 服務
python main.py serve
python main.py serve --port 8000 --host 0.0.0.0

# 啟動實時監控
python main.py monitor
```

### 數據管理

```bash
# 下載單只股票歷史數據
python main.py download --code 600519 --start 2020-01-01 --end 2024-12-31

# 批量下載自選股
python main.py download --all

# 增量更新
python main.py download --incremental

# 填充演示數據
python main.py seed
```

---

## 10.3 回測命令

```bash
# 基礎回測
python main.py backtest --code 600519 --strategy macd --cash 100000

# 指定日期範圍
python main.py backtest --code 600519 --strategy dual_ma \
  --start 2020-01-01 --end 2024-12-31 --cash 100000

# 自定義策略參數
python main.py backtest --code 600519 --strategy macd \
  --params fast=8,slow=21,signal=7

# 高級回測（含風控）
python main.py backtest --code 600519 --strategy bollinger \
  --stop-loss 0.05 --take-profit 0.15 --trailing-stop 0.03
```

---

## 10.4 優化命令

```bash
# 參數優化
python main.py optimize --code 600519 --strategy macd --trials 100

# Walk-Forward 分析
python main.py walkforward --code 600519 --strategy macd

# 全自動優化（跨股票共識推薦）
python main.py auto-optimize --codes 600519,000858,002714
```

---

## 10.5 組合分析命令

```bash
# 組合回測
python main.py portfolio --codes 600519,000858,002714 --method risk_parity

# 支持的方法
# equal_weight, preset, efficient_frontier, dynamic_weight, kelly,
# risk_parity, mvo, volatility_target, max_diversification,
# anti_correlation, regime_switch, black_litterman, hrp, cvar,
# multi_timeframe, dynamic_rebalance, sector_limit, voting
```

---

## 10.6 信號與報告

```bash
# 查看實時信號
python main.py signals
python main.py signals --code 600519

# 生成每日報告
python main.py report full
python main.py report comparison --codes 600519,000858
python main.py report strategy --strategy macd

# 策略排行榜
python main.py strategy leaderboard
```

---

## 10.7 策略管理

```bash
# 列出所有策略
python main.py strategy list

# 創建新策略模板
python main.py strategy create --name my_strategy

# 查看策略排行榜
python main.py strategy leaderboard
```

---

## 10.8 用戶管理

```bash
# 創建用戶
python main.py user create --username test --password test123

# 列出用戶
python main.py user list

# 重置密碼
python main.py user reset-password --username test
```

---

## 10.9 股票池管理

```bash
# 同步股票池
python main.py stock-universe sync

# 查看統計
python main.py stock-universe stats

# 列出股票
python main.py stock-universe list --market A --limit 50
```

---

## 10.10 定時任務管理

```bash
# 列出定時任務
python main.py scheduler list

# 設置定時任務
python main.py scheduler setup

# 手動運行任務
python main.py scheduler run --name daily_report

# 啟用/禁用任務
python main.py scheduler enable --name daily_report
python main.py scheduler disable --name daily_report
```

---

## 10.11 風險管理

```bash
# 計算倉位
python main.py risk position-size --code 600519 --capital 100000

# 風險預算檢查
python main.py risk budget-check --portfolio 600519,000858

# 回撤保護
python main.py risk drawdown-protect
```

---

## 10.12 配置管理

```bash
# 查看當前配置
python main.py config show

# 更新配置
python main.py config set --key SQ_BACKTEST_DEFAULT_CASH --value 200000
```

---

## 10.13 導出

```bash
# 導出回測結果
python main.py export --format csv --type backtest

# 導出信號
python main.py export --format json --type signals
```
