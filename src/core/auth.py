"""
認證模塊 — JWT Token + bcrypt 密碼處理
"""
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.db import get_conn
from src.models.user import User
from src.utils.logger import logger

# JWT 密鑰：優先從環境變量讀取，否則從文件持久化讀取/生成
JWT_SECRET: str = os.environ.get("SQ_JWT_SECRET", "")
if not JWT_SECRET:
    from pathlib import Path
    _secret_file = Path(__file__).resolve().parent.parent.parent / "data" / ".jwt_secret"
    if _secret_file.exists():
        JWT_SECRET = _secret_file.read_text().strip()
    else:
        JWT_SECRET = secrets.token_hex(32)
        _secret_file.parent.mkdir(parents=True, exist_ok=True)
        _secret_file.write_text(JWT_SECRET)
        os.chmod(_secret_file, 0o600)
    logger.info("JWT 密鑰已從本地文件加載（持久化，重啟不失效）")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24  # Token 有效期 24 小時
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"


def _validate_jwt_secret_for_production():
    """生產環境啟動時檢查 JWT 密鑰配置。"""
    from src.config import settings
    if settings.demo_mode or settings.debug:
        return
    if not os.environ.get("SQ_JWT_SECRET"):
        logger.error(
            "🚨 安全風險: SQ_JWT_SECRET 未設置！"
            " 生產環境必須顯式配置 JWT 密鑰，否則重啟後所有 token 失效。"
            " 請在 .env 中設置 SQ_JWT_SECRET=<隨機字串>（至少 32 字元）"
        )

# HTTP Bearer 提取器（可選模式：無 token 時不報錯）
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """使用 bcrypt 對密碼進行哈希"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """驗證密碼是否匹配 bcrypt 哈希"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: int, role: str) -> str:
    """創建 JWT Token（有效期 24 小時）"""
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def classify_token(token: str) -> str:
    """
    校驗 Token 狀態（不拋異常）。
    返回: ok | expired | invalid
    """
    if not token or not str(token).strip():
        return "invalid"
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return "ok"
    except jwt.ExpiredSignatureError:
        return "expired"
    except jwt.InvalidTokenError:
        return "invalid"


def verify_token(token: str) -> Optional[dict]:
    """
    解碼並驗證 JWT Token
    
    返回 payload 字典或 None（無效/過期時）
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Token 已過期")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Token 無效: {e}")
        return None


def get_user_by_id(user_id: int) -> Optional[User]:
    """根據用戶 ID 查詢用戶"""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return None
    return User.from_row(dict(row))


def get_user_by_username(username: str) -> Optional[User]:
    """根據用戶名查詢用戶"""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    return User.from_row(dict(row))


# ============================================================
# FastAPI 依賴注入
# ============================================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """
    FastAPI 依賴：從 Authorization header 提取當前用戶
    
    - 有有效 token → 返回 User 對象
    - 無 token 或 token 無效 → 返回 None（向後兼容）
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        return None

    user = get_user_by_id(payload.get("user_id"))
    return user


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """
    FastAPI 依賴：要求必須登錄
    
    - 有有效 token → 返回 User 對象
    - 無 token 或 token 無效 → 拋出 401
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="未登錄，請先獲取 Token")

    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 無效或已過期，請重新登錄")

    user = get_user_by_id(payload.get("user_id"))
    if not user:
        raise HTTPException(status_code=401, detail="用戶不存在")

    return user


async def require_admin(
    user: User = Depends(require_auth),
) -> User:
    """
    FastAPI 依賴：要求管理員權限
    
    - role='admin' → 通過
    - 其他角色 → 拋出 403
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user


# ============================================================
# 默認管理員賬號初始化
# ============================================================

def ensure_default_admin():
    """確保默認管理員賬號存在，並維持預設 admin/admin 可登入。"""
    default_pw = (
        os.environ.get("SQ_DEMO_ADMIN_PASSWORD")
        or os.environ.get("SQ_DEFAULT_ADMIN_PASSWORD")
        or DEFAULT_ADMIN_PASSWORD
    )
    pw_hash = hash_password(default_pw)
    existing = get_user_by_username(DEFAULT_ADMIN_USERNAME)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        if existing:
            # 僅確保 role 為 admin，不重置密碼（避免每次啟動覆蓋用戶修改的密碼）
            if existing.get("role") != "admin":
                conn.execute(
                    "UPDATE users SET role = 'admin' WHERE username = ?",
                    (DEFAULT_ADMIN_USERNAME,),
                )
            logger.info(f"管理員賬號 {DEFAULT_ADMIN_USERNAME} 已存在，跳過初始化。")
            return
        conn.execute(
            """INSERT INTO users (username, password_hash, role, settings, created_at)
               VALUES (?, ?, 'admin', '{}', ?)""",
            (DEFAULT_ADMIN_USERNAME, pw_hash, now),
        )

    # 僅首次創建時寫入密碼文件
    from pathlib import Path
    pw_file = Path(__file__).resolve().parent.parent.parent / "data" / ".admin_password"
    pw_file.parent.mkdir(parents=True, exist_ok=True)
    pw_file.write_text(f"{DEFAULT_ADMIN_USERNAME}:{default_pw}\n")
    try:
        os.chmod(pw_file, 0o600)
    except Exception:
        pass
    logger.warning(f"已創建默認管理員賬號 {DEFAULT_ADMIN_USERNAME}，密碼已寫入: {pw_file}")
    logger.warning("默認賬號為 admin/admin；公開部署請設置 SQ_DEMO_ADMIN_PASSWORD 或登入後修改密碼。")


def create_user(username: str, password: str, role: str = "user") -> User:
    """
    創建新用戶
    
    Args:
        username: 用戶名
        password: 明文密碼
        role: 角色 ('admin' | 'user')
    
    Returns:
        創建的 User 對象
    
    Raises:
        ValueError: 用戶名已存在
    """
    existing = get_user_by_username(username)
    if existing:
        raise ValueError(f"用戶名 '{username}' 已存在")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pw_hash = hash_password(password)

    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO users (username, password_hash, role, settings, created_at)
               VALUES (?, ?, ?, '{}', ?)""",
            (username, pw_hash, role, now),
        )
        user_id = cursor.lastrowid

    return User(id=user_id, username=username, password_hash=pw_hash, role=role, created_at=now, settings={})


def list_users() -> list[dict]:
    """列出所有用戶（不含密碼哈希）"""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, username, role, settings, created_at FROM users ORDER BY id").fetchall()
    users = []
    for row in rows:
        d = dict(row)
        try:
            d["settings"] = json.loads(d.get("settings") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["settings"] = {}
        users.append(d)
    return users


def update_user_role(user_id: int, new_role: str) -> bool:
    """修改用戶角色"""
    if new_role not in ("admin", "user"):
        raise ValueError(f"無效角色: {new_role}，可選: admin, user")
    with get_conn() as conn:
        cursor = conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    return cursor.rowcount > 0


def delete_user(user_id: int) -> bool:
    """刪除用戶及其關聯數據"""
    with get_conn() as conn:
        # 先刪關聯數據
        conn.execute("DELETE FROM user_watchlists WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_alert_rules WHERE user_id = ?", (user_id,))
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cursor.rowcount > 0


def reset_password(user_id: int, new_password: str) -> bool:
    """重置用戶密碼"""
    pw_hash = hash_password(new_password)
    with get_conn() as conn:
        cursor = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    return cursor.rowcount > 0
