"""
用戶模型 — 數據類定義
"""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class User:
    """用戶數據模型"""

    id: Optional[int] = None
    username: str = ""
    password_hash: str = ""  # bcrypt 加密後的密碼
    role: str = "user"  # 'admin' | 'user'
    created_at: str = ""
    preferred_currency: str = "MOP"  # HKD | MOP | USD | CNY
    settings: dict = field(
        default_factory=dict
    )  # 用戶個性化設置（監控列表、預警、偏好等）

    def to_dict(self, include_hash: bool = False) -> dict:
        """轉為字典（可選是否包含密碼哈希）"""
        d = {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
            "settings": self.settings,
            "preferred_currency": self.preferred_currency,
        }
        if include_hash:
            d["password_hash"] = self.password_hash
        return d

    @classmethod
    def from_row(cls, row: dict) -> "User":
        """從數據庫行創建 User 實例"""
        settings = {}
        if row.get("settings"):
            try:
                settings = json.loads(row["settings"])
            except (json.JSONDecodeError, TypeError):
                settings = {}
        pref = (
            row.get("preferred_currency") or settings.get("preferred_currency") or "MOP"
        ).upper()
        if pref not in ("HKD", "MOP", "USD", "CNY"):
            pref = "MOP"
        return cls(
            id=row.get("id"),
            username=row.get("username", ""),
            password_hash=row.get("password_hash", ""),
            role=row.get("role", "user"),
            created_at=row.get("created_at", ""),
            preferred_currency=pref,
            settings=settings,
        )
