"""演示模式數據填充"""
import time
import threading

from src.config import settings
from src.utils.logger import logger

DEMO_CODES = ["000001", "600519", "000858", "601318", "000333"]
DEMO_STRATEGIES = ["dual_ma", "macd", "bollinger", "rsi", "momentum"]


def seed_demo_data():
    """演示模式：後台填充示範數據（不阻塞啟動，自動重試）"""

    def _worker():
        try:
            from src.core.db import load_daily_kline, init_db
            from src.core.auth import ensure_default_admin

            init_db()
            ensure_default_admin()

            has_data = True
            for code in DEMO_CODES[:2]:
                df = load_daily_kline(code)
                if df.empty:
                    has_data = False
                    break

            if has_data:
                logger.info("📦 演示模式：數據已存在，跳過填充")
                return

            logger.info("📦 演示模式：正在下載 A 股示範數據...")
            from src.core.history import download_one

            total = 0
            for i, code in enumerate(DEMO_CODES, 1):
                for attempt in range(3):
                    try:
                        count = download_one(code)
                        if count > 0:
                            total += count
                            logger.info(f"📦 [{i}/{len(DEMO_CODES)}] {code}: {count} 條")
                            break
                    except Exception as e:
                        logger.debug(f"📦 {code} 第{attempt+1}次下載失敗: {e}")
                        if attempt < 2:
                            time.sleep(3)
                time.sleep(1)

            logger.info(f"📦 A 股下載完成: {total} 條記錄")

            if total > 0:
                logger.info("📦 演示模式：正在生成回測歷史...")
                from src.core.backtest import run_backtest

                bt_count = 0
                for code in DEMO_CODES:
                    for strat in DEMO_STRATEGIES:
                        try:
                            run_backtest(code, strategy_name=strat)
                            bt_count += 1
                        except Exception as e:
                            logger.debug(f"📦 回測 {code}/{strat} 跳過: {e}")
                logger.info(f"📦 演示模式：已生成 {bt_count} 條回測記錄")

            logger.info("📦 演示模式初始化完成 ✅")

        except Exception as e:
            logger.warning(f"📦 演示數據填充失敗（服務仍正常運行）: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    logger.info("📦 演示模式：後台數據填充已啟動")
