"""
Grafana Dashboard 指標定義 - 預設儀表板配置
"""
from typing import Any


class DashboardMetrics:
    """
    Grafana Dashboard 指標定義
    
    提供預設的儀表板配置，可用於：
    1. 自動創建 Grafana Dashboard
    2. 前端直接讀取指標數據
    3. 導出為 JSON 供 Grafana 導入
    """
    
    @staticmethod
    def get_dashboard_config() -> dict[str, Any]:
        """獲取 Grafana Dashboard 配置"""
        return {
            "dashboard": {
                "title": "StockQ 監控儀表板",
                "tags": ["stockq", "quantitative"],
                "timezone": "browser",
                "panels": [
                    {
                        "id": 1,
                        "title": "任務隊列長度",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "task_queue_length",
                                "legendFormat": "{{queue}}",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                    },
                    {
                        "id": 2,
                        "title": "預計算緩存命中率",
                        "type": "gauge",
                        "targets": [
                            {
                                "expr": "precomputed_cache_hit_rate",
                                "legendFormat": "Hit Rate",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0},
                        "options": {
                            "min": 0,
                            "max": 1,
                            "thresholds": [
                                {"value": 0, "color": "red"},
                                {"value": 0.5, "color": "yellow"},
                                {"value": 0.8, "color": "green"},
                            ],
                        },
                    },
                    {
                        "id": 3,
                        "title": "回測任務總數",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "backtest_tasks_total{status=\"started\"}",
                                "legendFormat": "Started",
                            },
                            {
                                "expr": "backtest_tasks_total{status=\"completed\"}",
                                "legendFormat": "Completed",
                            },
                            {
                                "expr": "backtest_tasks_total{status=\"failed\"}",
                                "legendFormat": "Failed",
                            },
                        ],
                        "gridPos": {"h": 8, "w": 6, "x": 18, "y": 0},
                    },
                    {
                        "id": 4,
                        "title": "LLM 調用統計",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(llm_calls_total[5m])",
                                "legendFormat": "{{model}} - {{success}}",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
                    },
                    {
                        "id": 5,
                        "title": "數據源健康狀態",
                        "type": "table",
                        "targets": [
                            {
                                "expr": "data_source_health",
                                "legendFormat": "{{source}}",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
                        "options": {
                            "showHeader": True,
                            "columns": [
                                {"field": "Time", "header": "時間"},
                                {"field": "Value", "header": "狀態"},
                            ],
                        },
                    },
                    {
                        "id": 6,
                        "title": "API 請求延遲分佈",
                        "type": "heatmap",
                        "targets": [
                            {
                                "expr": "histogram_quantile(0.95, rate(api_request_latency_bucket[5m]))",
                                "legendFormat": "P95 Latency",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
                    },
                ],
                "refresh": "5s",
                "time": {
                    "from": "now-1h",
                    "to": "now",
                },
            }
        }
    
    @staticmethod
    def get_quick_stats(collector_metrics: dict) -> dict[str, Any]:
        """獲取快速統計數據（用於前端即時顯示）"""
        cache = collector_metrics.get("cache", {})
        queues = collector_metrics.get("queues", {})
        counters = collector_metrics.get("counters", {})
        
        total_tasks = sum(
            v for k, v in counters.items() 
            if k.startswith("backtest_tasks_total") and "started" in k
        )
        
        return {
            "cache_hit_rate": cache.get("hit_rate", 0.0),
            "cache_hits": cache.get("hits", 0),
            "cache_misses": cache.get("misses", 0),
            "total_queues": len(queues),
            "total_queue_length": sum(queues.values()),
            "queue_details": queues,
            "total_backtests": int(total_tasks),
            "timestamp": __import__("time").time(),
        }
