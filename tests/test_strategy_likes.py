"""策略庫點讚 API 與儲存"""

import os
import tempfile

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    path = os.path.join(tempfile.gettempdir(), f"test_strat_likes_{os.getpid()}.db")
    if os.path.exists(path):
        os.remove(path)
    monkeypatch.setenv("SQ_DB_PATH", path)
    from src.config import settings
    from src.core.database.connection import reset_thread_connection

    settings.db_path = path
    reset_thread_connection()
    yield path
    reset_thread_connection()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def test_strategy_likes_toggle(isolated_db):
    from src.core.database import init_database
    from src.core.auth import create_user
    from src.core.strategy_likes import (
        toggle_like,
        get_like_counts,
        get_user_liked_keys,
    )

    init_database()
    user = create_user("like_tester", "password123")

    r1 = toggle_like(user.id, "dual_ma")
    assert r1["liked"] is True
    assert r1["count"] == 1

    r2 = toggle_like(user.id, "dual_ma")
    assert r2["liked"] is False
    assert r2["count"] == 0

    toggle_like(user.id, "macd")
    assert get_user_liked_keys(user.id) == ["macd"]
    assert get_like_counts().get("macd") == 1


def test_normalize_strategy_key_rejects_invalid():
    from src.core.strategy_likes import normalize_strategy_key

    with pytest.raises(ValueError):
        normalize_strategy_key("")
    with pytest.raises(ValueError):
        normalize_strategy_key("bad key!")
