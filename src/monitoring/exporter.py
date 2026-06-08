"""
Prometheus 格式導出器 - 將指標轉換為 Prometheus exposition format
"""

from typing import Optional
from src.monitoring.metrics import MetricsCollector


class PrometheusExporter:
    """
    Prometheus Exporter - 將內部指標轉換為 Prometheus 格式

    使用方式：
    1. 在 FastAPI 中添加端點：/metrics
    2. Grafana 配置 Prometheus data source 指向 http://<host>:<port>/metrics
    """

    def __init__(self, collector: Optional[MetricsCollector] = None):
        self.collector = collector or MetricsCollector()

    def generate_metrics(self) -> str:
        """生成 Prometheus exposition format 字串"""
        lines = []
        metrics = self.collector.get_all_metrics()

        # Counters
        for name, value in metrics["counters"].items():
            lines.append(f"# HELP {name} Counter metric")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")

        # Gauges
        for key, value in metrics["gauges"].items():
            # 解析 key: name{label1=val1,label2=val2}
            if "{" in key:
                name_part = key.split("{")[0]
                labels_part = key.split("{")[1].rstrip("}")
                lines.append(f"# HELP {name_part} Gauge metric")
                lines.append(f"# TYPE {name_part} gauge")
                lines.append(f"{name_part}{{{labels_part}}} {value}")
            else:
                lines.append(f"# HELP {key} Gauge metric")
                lines.append(f"# TYPE {key} gauge")
                lines.append(f"{key} {value}")

        # Histograms
        for name, stats in metrics["histograms"].items():
            lines.append(f"# HELP {name} Histogram metric")
            lines.append(f"# TYPE {name} histogram")
            if stats["count"] > 0:
                lines.append(f"{name}_count {stats['count']}")
                lines.append(f"{name}_sum {stats['sum']}")
                # Buckets
                lines.append(f'{name}_bucket{{le="0.5"}} {0}')
                lines.append(f'{name}_bucket{{le="1.0"}} {0}')
                lines.append(f'{name}_bucket{{le="5.0"}} {0}')
                lines.append(f"{name}_bucket{{le=\"10.0\"}} {stats['count']}")
                lines.append(f"{name}_bucket{{le=\"+Inf\"}} {stats['count']}")

        # Cache hit rate
        cache = metrics["cache"]
        lines.append("# HELP precomputed_cache_hits_total Total cache hits")
        lines.append("# TYPE precomputed_cache_hits_total counter")
        lines.append(f"precomputed_cache_hits_total {cache['hits']}")

        lines.append("# HELP precomputed_cache_misses_total Total cache misses")
        lines.append("# TYPE precomputed_cache_misses_total counter")
        lines.append(f"precomputed_cache_misses_total {cache['misses']}")

        lines.append("# HELP precomputed_cache_hit_rate Cache hit rate (0-1)")
        lines.append("# TYPE precomputed_cache_hit_rate gauge")
        lines.append(f"precomputed_cache_hit_rate {cache['hit_rate']}")

        # Queue lengths
        for queue_name, length in metrics["queues"].items():
            lines.append(f"# HELP task_queue_length Current queue length")
            lines.append("# TYPE task_queue_length gauge")
            lines.append(f'task_queue_length{{queue="{queue_name}"}} {length}')

        return "\n".join(lines) + "\n"

    def get_content_type(self) -> str:
        """返回 Prometheus 內容類型"""
        return "text/plain; version=0.0.4; charset=utf-8"
