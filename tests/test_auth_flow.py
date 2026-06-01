"""認證全流程"""
import pytest


def test_register_login_and_protected_write(client):
    username = "testuser_flow_01"
    password = "testpass123"

    reg = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    if reg.status_code == 400 and ("已存在" in reg.json().get("detail", "") or "已存在" in reg.json().get("msg", "")):
        login = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
    else:
        assert reg.status_code == 200
        login = reg
        if reg.status_code != 200:
            login = client.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )

    assert login.status_code == 200
    token = login.json().get("token")
    assert token

    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200

    # 在 debug/demo 非公開部署模式下，回測 POST 端點豁免認證（允許匿名提交）。
    # 僅在非 demo/debug 模式下才期望 401。
    from src.config import settings
    if not settings.demo_mode and not settings.debug:
        denied = client.post("/api/backtest?code=000001&strategy=dual_ma")
        assert denied.status_code == 401

    # 無論何種模式，帶 token 的請求都應成功（或返回業務層錯誤，非 401）
    allowed = client.post(
        "/api/backtest?code=000001&strategy=dual_ma",
        headers=headers,
    )
    assert allowed.status_code == 200
