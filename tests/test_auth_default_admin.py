"""默認管理員賬號初始化測試"""

from src.core.auth import (
    ensure_default_admin,
    get_user_by_username,
    hash_password,
    verify_password,
)
from src.core.db import get_conn


def test_default_admin_is_admin_admin():
    """首次建立時預設密碼為 admin；與共用測試 DB 隔離。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE username = ?", ("admin",))

    ensure_default_admin()

    user = get_user_by_username("admin")
    assert user is not None
    assert user.role == "admin"
    assert verify_password("admin", user.password_hash)


def test_existing_admin_role_promoted_password_preserved():
    """已存在的 admin 不應在每次啟動時被重置密碼。"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, role = 'user' WHERE username = ?",
            (hash_password("old-password"), "admin"),
        )

    ensure_default_admin()

    user = get_user_by_username("admin")
    assert user is not None
    assert user.role == "admin"
    assert verify_password("old-password", user.password_hash)
