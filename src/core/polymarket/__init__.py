"""
Polymarket 預測市場數據包 — 只讀整合（Gamma 元數據 + CLOB 訂單簿/價格）

REST API 與 MCP tools 均通過 PolymarketService 訪問，避免邏輯分叉。
"""
from src.core.polymarket.service import PolymarketService, get_polymarket_service

__all__ = ["PolymarketService", "get_polymarket_service"]
