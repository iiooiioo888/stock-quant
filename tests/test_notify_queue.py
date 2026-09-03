"""通知隊列、重試與渠道。"""

from unittest.mock import MagicMock, patch

from src.core.alerts import get_notification_channels, send_bark, send_serverchan
from src.core.notify_queue import send_with_retry


def test_channels_include_serverchan_and_bark():
    keys = {c["key"] for c in get_notification_channels()}
    assert "serverchan" in keys
    assert "bark" in keys
    assert "telegram" in keys


def test_send_with_retry_succeeds_second_try(monkeypatch):
    monkeypatch.setattr("src.core.notify_queue.settings.notify_max_retries", 2)
    monkeypatch.setattr("src.core.notify_queue.time.sleep", lambda *_: None)
    logged = []
    monkeypatch.setattr(
        "src.core.notify_queue.log_notification",
        lambda *a, **k: logged.append(k.get("status") or a),
    )
    n = {"i": 0}

    def flaky():
        n["i"] += 1
        if n["i"] < 2:
            raise RuntimeError("tmp")
        return True

    assert send_with_retry("webhook", flaky, "hello") is True
    assert n["i"] == 2


def test_serverchan_posts_sendkey():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"code": 0}
    mock_resp.content = b"{}"
    with patch("src.core.alerts.requests.post", return_value=mock_resp) as post:
        ok = send_serverchan("SCTKEY", "msg")
    assert ok is True
    assert "SCTKEY" in post.call_args[0][0]


def test_bark_get_url():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"code": 200}
    mock_resp.content = b"{}"
    with patch("src.core.alerts.requests.get", return_value=mock_resp) as get:
        ok = send_bark("https://api.day.app/devkey", "hello")
    assert ok is True
    assert "api.day.app" in get.call_args[0][0]
