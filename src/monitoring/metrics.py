"""
Prometheus 指標收集器 - 監控任務隊列、預計算命中率、API 效能
"""

import time
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict
import threading


@dataclass
class MetricSample:
    """單個指標樣本"""

    name: str
    value: float
    labels: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """
    指標收集器 - 支援自定義指標與 Prometheus 格式輸出

    監控項目：
    - 任務隊列長度 (task_queue_length)
    - 預計算命中率 (precomputed_cache_hit_rate)
    - API 請求延遲 (api_request_latency)
    - 回測任務總數 (backtest_tasks_total)
    - LLM 調用次數 (llm_calls_total)
    - 數據源健康狀態 (data_source_health)
    """

    _instance: Optional["MetricsCollector"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 指標存儲：{metric_name: [(value, labels, timestamp), ...]}
        self._metrics: dict[str, list[MetricSample]] = defaultdict(list)
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

        # 預計算緩存統計
        self._cache_hits = 0
        self._cache_misses = 0

        # 任務隊列統計
        self._queue_lengths: dict[str, int] = defaultdict(int)

        # 線程鎖
        self._metrics_lock = threading.Lock()

    def inc_counter(self, name: str, value: float = 1.0, labels: Optional[dict] = None):
        """增加計數器"""
        with self._metrics_lock:
            self._counters[name] += value
            self._record_sample(name, self._counters[name], labels or {})

    def set_gauge(self, name: str, value: float, labels: Optional[dict] = None):
        """設置儀表值"""
        with self._metrics_lock:
            key = self._make_key(name, labels or {})
            self._gauges[key] = value
            self._record_sample(name, value, labels or {})

    def observe_histogram(self, name: str, value: float, labels: Optional[dict] = None):
        """觀察直方圖值（用於延遲等）"""
        with self._metrics_lock:
            self._histograms[name].append(value)
            # 保留最近 1000 個樣本
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]
            self._record_sample(name, value, labels or {})

    def record_cache_hit(self):
        """記錄緩存命中"""
        with self._metrics_lock:
            self._cache_hits += 1
            self._update_cache_hit_rate()

    def record_cache_miss(self):
        """記錄緩存未命中"""
        with self._metrics_lock:
            self._cache_misses += 1
            self._update_cache_hit_rate()

    def _update_cache_hit_rate(self):
        """更新預計算命中率"""
        total = self._cache_hits + self._cache_misses
        if total > 0:
            hit_rate = self._cache_hits / total
            self.set_gauge("precomputed_cache_hit_rate", hit_rate)

    def set_queue_length(self, queue_name: str, length: int):
        """設置任務隊列長度"""
        self._queue_lengths[queue_name] = length
        self.set_gauge("task_queue_length", length, {"queue": queue_name})

    def record_backtest_task(self, status: str = "started"):
        """記錄回測任務"""
        self.inc_counter("backtest_tasks_total", labels={"status": status})

    def record_llm_call(self, model: str, success: bool = True):
        """記錄 LLM 調用"""
        self.inc_counter(
            "llm_calls_total", labels={"model": model, "success": str(success).lower()}
        )

    def record_data_source_health(self, source: str, healthy: bool):
        """記錄數據源健康狀態"""
        self.set_gauge(
            "data_source_health", 1.0 if healthy else 0.0, {"source": source}
        )

    def _record_sample(self, name: str, value: float, labels: dict):
        """記錄指標樣本"""
        sample = MetricSample(name=name, value=value, labels=labels)
        self._metrics[name].append(sample)
        # 保留最近 10000 個樣本
        if len(self._metrics[name]) > 10000:
            self._metrics[name] = self._metrics[name][-10000:]

    def _make_key(self, name: str, labels: dict) -> str:
        """生成儀表唯一鍵"""
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}" if label_str else name

    def get_counter(self, name: str) -> float:
        """獲取計數器值"""
        return self._counters.get(name, 0.0)

    def get_gauge(self, name: str, labels: Optional[dict] = None) -> Optional[float]:
        """獲取儀表值"""
        key = self._make_key(name, labels or {})
        return self._gauges.get(key)

    def get_histogram_stats(self, name: str) -> dict:
        """獲取直方圖統計數據"""
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_values = sorted(values)
        count = len(sorted_values)
        return {
            "count": count,
            "sum": sum(sorted_values),
            "avg": sum(sorted_values) / count,
            "p50": sorted_values[int(count * 0.5)],
            "p95": (
                sorted_values[int(count * 0.95)] if count > 20 else sorted_values[-1]
            ),
            "p99": (
                sorted_values[int(count * 0.99)] if count > 100 else sorted_values[-1]
            ),
        }

    def get_all_metrics(self) -> dict:
        """獲取所有指標（用於 Prometheus 導出）"""
        with self._metrics_lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    name: self.get_histogram_stats(name) for name in self._histograms
                },
                "cache": {
                    "hits": self._cache_hits,
                    "misses": self._cache_misses,
                    "hit_rate": self.get_gauge("precomputed_cache_hit_rate") or 0.0,
                },
                "queues": dict(self._queue_lengths),
            }

    def reset(self):
        """重置所有指標（測試用）"""
        with self._metrics_lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._cache_hits = 0
            self._cache_misses = 0
            self._queue_lengths.clear()
