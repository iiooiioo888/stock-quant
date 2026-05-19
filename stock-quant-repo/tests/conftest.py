"""
測試配置 — 設置測試環境變量
"""
import os
import sys

# 確保項目根目錄在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 測試環境配置（避免影響生產數據）
os.environ.setdefault("SQ_DB_PATH", "/tmp/test_stock.db")
os.environ.setdefault("SQ_REDIS_ENABLED", "false")
os.environ.setdefault("SQ_LOG_LEVEL", "WARNING")
