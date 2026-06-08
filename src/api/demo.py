"""演示模式數據填充"""

import threading

from src.utils.logger import logger


def seed_demo_data():
    """演示模式：後台預載常見數據（不阻塞啟動）"""

    def _worker():
        try:
            from src.core.database.seed import seed_common_data

            seed_common_data(
                "quick",
                force=False,
                catalog=True,
                sector=False,
                fundamentals=False,
                backtest_samples=True,
            )
            logger.info("📦 演示模式初始化完成 ✅")
        except Exception as e:
            logger.warning(f"📦 演示數據填充失敗（服務仍正常運行）: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    logger.info("📦 演示模式：後台數據填充已啟動")
