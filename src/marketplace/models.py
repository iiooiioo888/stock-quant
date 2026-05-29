"""
策略市場數據模型
"""
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime
from enum import Enum
import uuid


class StrategyVisibility(Enum):
    """策略可見性"""
    PRIVATE = "private"  # 僅自己可見
    PUBLIC = "public"  # 公開分享
    UNLISTED = "unlisted"  # 有連結即可訪問，但不出現在列表中


class StrategyCategory(Enum):
    """策略分類"""
    TREND_FOLLOWING = "trend_following"  # 趨勢跟隨
    MEAN_REVERSION = "mean_reversion"  # 均值回歸
    MOMENTUM = "momentum"  # 動能策略
    ARBITRAGE = "arbitrage"  # 套利策略
    MARKET_MAKING = "market_making"  # 做市策略
    MULTI_FACTOR = "multi_factor"  # 多因子策略
    CUSTOM = "custom"  # 自定義


@dataclass
class StrategyModel:
    """策略模型"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    category: StrategyCategory = StrategyCategory.CUSTOM
    author: str = "anonymous"
    version: str = "1.0.0"
    
    # 策略代碼（沙箱格式）
    code: str = ""
    
    # 參數定義
    parameters: dict[str, Any] = field(default_factory=dict)
    
    # 回測統計
    backtest_stats: dict[str, Any] = field(default_factory=dict)
    
    # 可見性
    visibility: StrategyVisibility = StrategyVisibility.PRIVATE
    
    # 時間戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 標籤
    tags: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "author": self.author,
            "version": self.version,
            "code": self.code,
            "parameters": self.parameters,
            "backtest_stats": self.backtest_stats,
            "visibility": self.visibility.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyModel":
        """從字典創建"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=StrategyCategory(data.get("category", "custom")),
            author=data.get("author", "anonymous"),
            version=data.get("version", "1.0.0"),
            code=data.get("code", ""),
            parameters=data.get("parameters", {}),
            backtest_stats=data.get("backtest_stats", {}),
            visibility=StrategyVisibility(data.get("visibility", "private")),
            tags=data.get("tags", []),
        )


@dataclass
class StrategyRating:
    """策略評分"""
    strategy_id: str = ""
    user_id: str = ""
    rating: int = 5  # 1-5 星
    comment: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            "strategy_id": self.strategy_id,
            "user_id": self.user_id,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyRating":
        """從字典創建"""
        return cls(
            strategy_id=data.get("strategy_id", ""),
            user_id=data.get("user_id", ""),
            rating=min(5, max(1, data.get("rating", 5))),
            comment=data.get("comment", ""),
        )


@dataclass
class StrategyShare:
    """策略分享記錄"""
    strategy_id: str = ""
    shared_by: str = ""
    shared_with: list[str] = field(default_factory=list)  # 用戶 ID 列表
    share_token: str = field(default_factory=lambda: str(uuid.uuid4()))
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def is_valid(self) -> bool:
        """檢查分享是否有效"""
        if self.expires_at is None:
            return True
        return datetime.now() < self.expires_at
    
    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            "strategy_id": self.strategy_id,
            "shared_by": self.shared_by,
            "shared_with": self.shared_with,
            "share_token": self.share_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "is_valid": self.is_valid(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyShare":
        """從字典創建"""
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])
        
        return cls(
            strategy_id=data.get("strategy_id", ""),
            shared_by=data.get("shared_by", ""),
            shared_with=data.get("shared_with", []),
            share_token=data.get("share_token", str(uuid.uuid4())),
            expires_at=expires_at,
        )
