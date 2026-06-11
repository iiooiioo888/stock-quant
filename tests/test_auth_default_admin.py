"""默認管理員賬號初始化測試"""

from src.core.auth import (
    ensure_default_admin,
    get_user_by_username,
    hash_password,
    verify_password,
)
from src.core.db import get_conn


def test_default_admin_is_admin_admin():
    ensure_default_admin()

    user = get_user_by_username("admin")
    assert user is not None
    assert user.role == "admin"
    assert verify_password("admin", user.password_hash)


def test_existing_admin_password_is_reset_to_default():
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, role = 'user' WHERE username = ?",
            (hash_password("old-password"), "admin"),
        )

    ensure_default_admin()

    user = get_user_by_username("admin")
    assert user is not None
    assert user.role == "admin"
    assert verify_password("admin", user.password_hash)
