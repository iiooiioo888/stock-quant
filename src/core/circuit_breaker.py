"""
通用熔斷器裝飾器 — 防止持續請求已知故障的數據源。

用法：
    @circuit_breaker("eastmoney", failure_threshold=3, recovery_timeout=120)
    def fetch_xxx():
        ...

    # 查詢狀態
    from src.core.circuit_breaker import get_all_breakers, is_open
    get_all_breakers()  # dict[str, dict]
    is_open("eastmoney")  # bool
"""
from __future__ import annotations

import time
from functools import wraps
from threading import Lock
from typing import Any, Callable

from src.utils.logger import logger


class CircuitBreaker:
    """單個數據源的熔斷狀態。"""

    __slots__ = (
        "name", "failure_threshold", "recovery_timeout",
        "_consecutive_failures", "_opened_at", "_total_failures",
        "_total_successes", "_last_failure_at",
    )

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 120.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._total_failures = 0
        self._total_successes = 0
        self._last_failure_at = 0.0

    @property
    def is_open(self) -> bool:
        if self._opened_at <= 0:
            return False
        if time.time() - self._opened_at >= self.recovery_timeout:
            return False
        return True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._total_successes += 1

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        self._total_failures += 1
        self._last_failure_at = time.time()
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_at = time.time()
            logger.warning(
                f"[CircuitBreaker] {self.name} 連續失敗 {self._consecutive_failures} 次，"
                f"熔斷 {self.recovery_timeout:.0f}s"
            )

    def as_dict(self) -> dict[str, Any]:
        now = time.time()
        remaining = 0.0
        if self._opened_at > 0:
            remaining = max(0.0, self.recovery_timeout - (now - self._opened_at))
        return {
            "name": self.name,
            "is_open": self.is_open,
            "consecutive_failures": self._consecutive_failures,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "cooldown_remaining_sec": round(remaining, 1),
            "last_failure_at": self._last_failure_at,
        }


_breakers: dict[str, CircuitBreaker] = {}
_lock = Lock()


def _get_or_create(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: float = 120.0,
) -> CircuitBreaker:
    with _lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(name, failure_threshold, recovery_timeout)
        return _breakers[name]


def circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: float = 120.0,
) -> Callable:
    """
    裝飾器：為函數添加熔斷保護。

    熔斷期間直接拋出 CircuitBreakerOpenError，不執行函數體。
    """
    cb = _get_or_create(name, failure_threshold, recovery_timeout)

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if cb.is_open:
                raise CircuitBreakerOpenError(
                    f"數據源 {name} 熔斷中，剩餘 {cb.as_dict()['cooldown_remaining_sec']:.0f}s"
                )
            try:
                result = fn(*args, **kwargs)
                cb.record_success()
                return result
            except Exception:
                cb.record_failure()
                raise
        wrapper._circuit_breaker = cb  # type: ignore[attr-defined]
        return wrapper
    return decorator


class CircuitBreakerOpenError(Exception):
    """熔斷器開路時拋出。"""


def is_open(name: str) -> bool:
    """查詢指定數據源是否熔斷中。"""
    cb = _breakers.get(name)
    return cb.is_open if cb else False


def get_all_breakers() -> dict[str, dict]:
    """返回所有熔斷器的狀態快照。"""
    with _lock:
        return {name: cb.as_dict() for name, cb in _breakers.items()}


def reset_all() -> None:
    """測試用：重置所有熔斷器。"""
    with _lock:
        _breakers.clear()
