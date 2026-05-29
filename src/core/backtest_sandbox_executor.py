"""
沙箱回測執行器

在安全隔離環境中執行用戶上傳的自定義策略：
- 動態載入已驗證的策略源碼
- 使用 strategy_base.UserStrategy 基類
- 與正式回測數據隔離（不污染生產記錄）
- 支持滑點、手續費、止損/止盈等進階控制
"""
import importlib.util
import sys
import types
from typing import Optional
from src.utils.logger import logger


def load_strategy_from_code(strategy_code: str, class_name: str = "MyStrategy"):
    """
    從源碼字符串動態載入策略類
    
    Args:
        strategy_code: 用戶提供的策略源碼
        class_name: 策略類名（默認 MyStrategy，也可自動檢測）
    
    Returns:
        策略類對象
    
    Raises:
        ImportError: 載入失敗
    """
    from src.core.strategy_sandbox import validate_strategy_source
    
    # 再次驗證（防禦性編程）
    validation = validate_strategy_source(strategy_code)
    if not validation.ok:
        raise ImportError(f"策略源碼校驗失敗：{validation.error}")
    
    # 嘗試自動檢測類名
    if class_name == "MyStrategy":
        import re
        match = re.search(r'class\s+(\w+)\s*\(\s*UserStrategy\s*\)', strategy_code)
        if match:
            class_name = match.group(1)
    
    # 創建模組規範
    spec = importlib.util.spec_from_loader(
        name="user_strategy_module",
        loader=None,
        origin="<sandbox>",
    )
    module = importlib.util.module_from_spec(spec)
    
    # 準備安全的執行環境
    safe_globals = {
        "__name__": "user_strategy_module",
        "__doc__": "用戶策略模組（沙箱環境）",
    }
    
    # 注入允許的依賴
    try:
        import numpy as np
        safe_globals["np"] = np
    except ImportError:
        pass
    
    try:
        import pandas as pd
        safe_globals["pd"] = pd
    except ImportError:
        pass
    
    try:
        from src.core.strategy_base import UserStrategy
        safe_globals["UserStrategy"] = UserStrategy
    except ImportError as e:
        raise ImportError(f"無法導入 UserStrategy：{e}")
    
    # 執行策略源碼
    try:
        exec(compile(strategy_code, "<sandbox>", "exec"), safe_globals)
    except Exception as e:
        raise ImportError(f"策略編譯失敗：{e}")
    
    # 獲取策略類
    strategy_class = safe_globals.get(class_name)
    if not strategy_class:
        raise ImportError(f"找不到策略類：{class_name}")
    
    return strategy_class


def run_sandbox_backtest(
    code: str,
    strategy_code: str,
    cash: float = 100000.0,
    commission: float = 0.001,
    stop_loss_pct: Optional[float] = None,
    take_profit_pct: Optional[float] = None,
    benchmark: bool = False,
    timeframe: str = "1d",
    task_id: str = None,
    user_id: str = None,
):
    """
    執行沙箱模式回測
    
    Args:
        code: 股票代碼
        strategy_code: 用戶策略源碼
        cash: 初始資金
        commission: 手續費率
        stop_loss_pct: 止損百分比
        take_profit_pct: 止盈百分比
        benchmark: 是否對比基準
        timeframe: K 線週期
        task_id: 任務 ID
        user_id: 用戶 ID
    
    Returns:
        回測結果字典
    """
    from src.core.backtest import _prepare_data, _run_backtest_engine
    from src.core.strategy_base import UserStrategy
    
    logger.info(f"[沙箱回測] 開始執行：{code}, 任務 ID={task_id}")
    
    # 1. 載入用戶策略
    try:
        StrategyClass = load_strategy_from_code(strategy_code)
        strategy_instance = StrategyClass()
        
        if not isinstance(strategy_instance, UserStrategy):
            raise ValueError("策略必須繼承 UserStrategy")
            
    except Exception as e:
        logger.error(f"[沙箱回測] 策略載入失敗：{e}")
        return {
            "success": False,
            "error": f"策略載入失敗：{e}",
            "sandbox_mode": True,
        }
    
    # 2. 準備數據（與正式回測相同邏輯）
    try:
        df, stock_name = _prepare_data(code, timeframe)
        if df is None or df.empty:
            raise ValueError(f"無法獲取 {code} 的 K 線數據")
    except Exception as e:
        logger.error(f"[沙箱回測] 數據準備失敗：{e}")
        return {
            "success": False,
            "error": f"數據準備失敗：{e}",
            "sandbox_mode": True,
        }
    
    # 3. 執行回測引擎
    try:
        result = _run_backtest_engine(
            df=df,
            strategy=strategy_instance,  # 用戶自定義策略
            code=code,
            cash=cash,
            commission=commission,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            benchmark=benchmark,
            timeframe=timeframe,
            task_id=task_id,
            sandbox_mode=True,  # 標記為沙箱模式
        )
        
        # 添加沙箱標記
        result["sandbox_mode"] = True
        result["strategy_type"] = "custom_user_strategy"
        result["user_id"] = user_id
        
        logger.info(f"[沙箱回測] 完成：{code}, 最終資產={result.get('final_assets', 'N/A')}")
        
        return result
        
    except Exception as e:
        logger.error(f"[沙箱回測] 執行失敗：{e}", exc_info=True)
        return {
            "success": False,
            "error": f"回測執行失敗：{e}",
            "sandbox_mode": True,
        }
