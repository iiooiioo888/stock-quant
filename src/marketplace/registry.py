"""
策略市場註冊表 - 管理策略的上傳、檢索、評分
"""
import json
import sqlite3
from typing import Optional, List, Any, Dict
from datetime import datetime
from pathlib import Path

from src.marketplace.models import (
    StrategyModel,
    StrategyRating,
    StrategyShare,
    StrategyVisibility,
    StrategyCategory,
)
from src.utils.logger import logger


class StrategyMarketplace:
    """
    策略市場註冊表
    
    功能：
    - 策略上傳與存儲
    - 策略檢索（按分類/標籤/作者）
    - 評分與評論系統
    - 分享機制（公開/私有/未列出）
    - 下載統計
    """
    
    _instance: Optional["StrategyMarketplace"] = None
    
    def __new__(cls, db_path: str = "data/strategy_market.db"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = "data/strategy_market.db"):
        if self._initialized:
            return
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        self._initialized = True
        
        logger.info(f"策略市場初始化完成，數據庫：{self.db_path}")
    
    def _init_database(self):
        """初始化數據庫表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 策略表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'custom',
                author TEXT DEFAULT 'anonymous',
                version TEXT DEFAULT '1.0.0',
                code TEXT,
                parameters TEXT,
                backtest_stats TEXT,
                visibility TEXT DEFAULT 'private',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                download_count INTEGER DEFAULT 0,
                tags TEXT
            )
        """)
        
        # 評分表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(strategy_id, user_id)
            )
        """)
        
        # 分享表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                shared_by TEXT NOT NULL,
                share_token TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategies_category ON strategies(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategies_visibility ON strategies(visibility)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategies_author ON strategies(author)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_strategy ON ratings(strategy_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shares_token ON shares(share_token)")
        
        conn.commit()
        conn.close()
    
    def _ensure_status_column(self):
        """確保 strategies 表有 status 和 review_comment 欄位"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE strategies ADD COLUMN status TEXT DEFAULT 'pending_review'")
        except sqlite3.OperationalError:
            pass  # 欄位已存在
        try:
            cursor.execute("ALTER TABLE strategies ADD COLUMN review_comment TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

    def upload_strategy(self, strategy: StrategyModel) -> dict:
        """上傳策略（直接發佈，管理員可後台刪除）"""
        self._ensure_status_column()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO strategies 
                (id, name, description, category, author, version, code, 
                 parameters, backtest_stats, visibility, tags, updated_at, status, review_comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', NULL)
            """, (
                strategy.id,
                strategy.name,
                strategy.description,
                strategy.category.value,
                strategy.author,
                strategy.version,
                strategy.code,
                json.dumps(strategy.parameters),
                json.dumps(strategy.backtest_stats),
                strategy.visibility.value,
                json.dumps(strategy.tags),
                datetime.now().isoformat(),
            ))
            
            conn.commit()
            logger.info(f"策略已發佈：{strategy.name} ({strategy.id})")
            
            return {
                "success": True,
                "strategy_id": strategy.id,
                "message": f"策略 '{strategy.name}' 已發佈",
                "status": "published",
            }
        
        except Exception as e:
            logger.error(f"策略上傳失敗：{e}")
            return {
                "success": False,
                "error": str(e),
            }
        
        finally:
            conn.close()

    def approve_strategy(self, strategy_id: str) -> dict:
        """審批通過策略"""
        self._ensure_status_column()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE strategies SET status = 'published', review_comment = NULL WHERE id = ?",
                (strategy_id,),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return {"success": False, "error": "策略不存在"}
            logger.info(f"策略已通過審批: {strategy_id}")
            return {"success": True, "message": "策略已通過審批"}
        finally:
            conn.close()

    def reject_strategy(self, strategy_id: str, comment: str = "") -> dict:
        """退回策略（帶評語）"""
        self._ensure_status_column()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE strategies SET status = 'rejected', review_comment = ? WHERE id = ?",
                (comment, strategy_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return {"success": False, "error": "策略不存在"}
            logger.info(f"策略已退回: {strategy_id}，原因: {comment}")
            return {"success": True, "message": "策略已退回", "comment": comment}
        finally:
            conn.close()

    def list_pending_strategies(self) -> list[dict]:
        """列出所有待審批策略"""
        self._ensure_status_column()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM strategies WHERE status = 'pending_review' ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append({
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "category": row["category"],
                    "author": row["author"],
                    "version": row["version"],
                    "visibility": row["visibility"],
                    "tags": json.loads(row["tags"] or "[]"),
                    "created_at": row["created_at"],
                    "status": row["status"],
                    "review_comment": row["review_comment"],
                })
            return results
        finally:
            conn.close()
    
    def get_strategy(self, strategy_id: str) -> Optional[StrategyModel]:
        """獲取策略"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return self._row_to_strategy(row)
    
    def list_strategies(
        self,
        category: Optional[StrategyCategory] = None,
        visibility: StrategyVisibility = StrategyVisibility.PUBLIC,
        author: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StrategyModel]:
        """列出策略"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM strategies WHERE visibility = ?"
        params = [visibility.value]
        
        if category:
            query += " AND category = ?"
            params.append(category.value)
        
        if author:
            query += " AND author = ?"
            params.append(author)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_strategy(row) for row in rows]
    
    def rate_strategy(self, rating: StrategyRating) -> dict:
        """評分策略"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO ratings 
                (strategy_id, user_id, rating, comment, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                rating.strategy_id,
                rating.user_id,
                rating.rating,
                rating.comment,
                datetime.now().isoformat(),
            ))
            
            conn.commit()
            
            # 計算平均評分
            avg_rating = self._get_average_rating(rating.strategy_id)
            
            return {
                "success": True,
                "average_rating": avg_rating,
                "message": "評分成功",
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
        
        finally:
            conn.close()
    
    def get_ratings(self, strategy_id: str) -> list[StrategyRating]:
        """獲取策略的所有評分"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM ratings WHERE strategy_id = ? ORDER BY created_at DESC",
            (strategy_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [
            StrategyRating(
                strategy_id=row[1],
                user_id=row[2],
                rating=row[3],
                comment=row[4],
            )
            for row in rows
        ]
    
    def _get_average_rating(self, strategy_id: str) -> float:
        """計算平均評分"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT AVG(rating) FROM ratings WHERE strategy_id = ?",
            (strategy_id,)
        )
        result = cursor.fetchone()[0]
        conn.close()
        
        return round(result, 2) if result else 0.0
    
    def share_strategy(
        self,
        strategy_id: str,
        shared_by: str,
        expires_at: Optional[datetime] = None,
    ) -> Optional[StrategyShare]:
        """創建分享連結"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        share = StrategyShare(
            strategy_id=strategy_id,
            shared_by=shared_by,
            expires_at=expires_at,
        )
        
        try:
            cursor.execute("""
                INSERT INTO shares (strategy_id, shared_by, share_token, expires_at)
                VALUES (?, ?, ?, ?)
            """, (
                share.strategy_id,
                share.shared_by,
                share.share_token,
                share.expires_at.isoformat() if share.expires_at else None,
            ))
            
            conn.commit()
            return share
        
        except Exception as e:
            logger.error(f"創建分享連結失敗：{e}")
            return None
        
        finally:
            conn.close()
    
    def get_strategy_by_token(self, token: str) -> Optional[StrategyModel]:
        """通過分享 token 獲取策略"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT strategy_id, expires_at FROM shares WHERE share_token = ?",
            (token,)
        )
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        strategy_id, expires_at = row
        
        # 檢查是否過期
        if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
            conn.close()
            return None
        
        # 獲取策略
        strategy = self.get_strategy(strategy_id)
        conn.close()
        
        return strategy
    
    def increment_download_count(self, strategy_id: str):
        """增加下載計數"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE strategies 
            SET download_count = download_count + 1 
            WHERE id = ?
        """, (strategy_id,))
        
        conn.commit()
        conn.close()
    
    def get_strategy_stats(self, strategy_id: str) -> dict:
        """獲取策略統計數據"""
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            return {"error": "策略不存在"}
        
        ratings = self.get_ratings(strategy_id)
        avg_rating = self._get_average_rating(strategy_id)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT download_count FROM strategies WHERE id = ?",
            (strategy_id,)
        )
        download_count = cursor.fetchone()[0]
        conn.close()
        
        return {
            "strategy_id": strategy_id,
            "name": strategy.name,
            "author": strategy.author,
            "average_rating": avg_rating,
            "total_ratings": len(ratings),
            "download_count": download_count,
            "created_at": strategy.created_at.isoformat(),
        }
    
    def _row_to_strategy(self, row: tuple) -> StrategyModel:
        """將數據庫行轉換為 StrategyModel"""
        return StrategyModel(
            id=row[0],
            name=row[1],
            description=row[2],
            category=StrategyCategory(row[3]),
            author=row[4],
            version=row[5],
            code=row[6],
            parameters=json.loads(row[7] or "{}"),
            backtest_stats=json.loads(row[8] or "{}"),
            visibility=StrategyVisibility(row[9]),
            created_at=datetime.fromisoformat(row[10]),
            updated_at=datetime.fromisoformat(row[11]),
            tags=json.loads(row[13] or "[]"),
        )
    
    def list_all_strategies(self) -> list[dict]:
        """列出所有策略（管理員用）"""
        self._ensure_status_column()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM strategies ORDER BY created_at DESC")
            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append({
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "category": row["category"],
                    "author": row["author"],
                    "version": row["version"],
                    "visibility": row["visibility"],
                    "tags": json.loads(row["tags"] or "[]"),
                    "created_at": row["created_at"],
                    "status": row["status"] if "status" in row.keys() else "published",
                    "download_count": row["download_count"],
                })
            return results
        finally:
            conn.close()

    def admin_delete_strategy(self, strategy_id: str) -> dict:
        """管理員刪除策略（無需驗證作者）"""
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            return {"success": False, "error": "策略不存在"}

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM ratings WHERE strategy_id = ?", (strategy_id,))
            cursor.execute("DELETE FROM shares WHERE strategy_id = ?", (strategy_id,))
            cursor.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
            conn.commit()
            logger.info(f"管理員已刪除策略: {strategy_id}")
            return {"success": True, "message": f"策略 '{strategy.name}' 已刪除"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def delete_strategy(self, strategy_id: str, user_id: str) -> dict:
        """刪除策略（僅作者可刪除）"""
        strategy = self.get_strategy(strategy_id)
        
        if not strategy:
            return {"success": False, "error": "策略不存在"}
        
        if strategy.author != user_id:
            return {"success": False, "error": "無權限刪除他人策略"}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 刪除相關評分和分享
            cursor.execute("DELETE FROM ratings WHERE strategy_id = ?", (strategy_id,))
            cursor.execute("DELETE FROM shares WHERE strategy_id = ?", (strategy_id,))
            cursor.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
            
            conn.commit()
            
            return {
                "success": True,
                "message": f"策略 '{strategy.name}' 已刪除",
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
        
        finally:
            conn.close()
