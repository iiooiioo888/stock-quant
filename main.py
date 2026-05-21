#!/usr/bin/env python3
"""
stock-quant 主入口

用法:
  python main.py serve              # 啟動 Web 服務
  python main.py serve --port 8080  # 自定義端口
  python main.py download           # 下載歷史數據
  python main.py download 000001 600519
  python main.py backtest 000001    # 回測
  python main.py backtest 000001 macd
  python main.py backtest 000001 all
  python main.py optimize 000001   # 參數優化
  python main.py portfolio          # 組合回測
  python main.py monitor            # 實時盯盤
  python main.py config show        # 查看配置
  python main.py strategy list      # 列出策略

實作位於 src/cli/（命令按領域拆分，run.py 統一分發）。
"""
from src.cli.run import main

if __name__ == "__main__":
    main()
