"""外部 HTTP 防護與 Mock 輔助（P1）。"""
from __future__ import annotations

from typing import Any, Callable

import pytest


class ExternalNetworkBlocked(RuntimeError):
    """測試未標記 network 時禁止真實外連。"""


def block_requests_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """攔截 requests 常見方法，避免 flaky 外網。"""

    def _deny(name: str) -> Callable[..., Any]:
        def _inner(*_a: Any, **_k: Any) -> Any:
            raise ExternalNetworkBlocked(
                f"requests.{name} blocked — mock with responses or @pytest.mark.network"
            )

        return _inner

    import requests

    for method in ("get", "post", "put", "delete", "head", "patch", "request"):
        if hasattr(requests, method):
            monkeypatch.setattr(requests, method, _deny(method))
    if hasattr(requests, "Session"):
        monkeypatch.setattr(requests.Session, "request", _deny("Session.request"))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "network: 需要真實外網連線")


@pytest.fixture
def block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """手動啟用：阻擋 requests 外連。"""
    block_requests_session(monkeypatch)
