"""
指標預計算 API 路由
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from src.utils.logger import logger

router = APIRouter(prefix="/api/indicators", tags=["indicators"])


@router.get("/precomputed/list")
async def list_precomputed_indicators(
    code: str = Query(..., description="股票代碼"),
) -> Dict[str, Any]:
    """列出某支股票已預計算的指標"""
    from src.config import settings
    import sqlite3
    
    db_path = settings.db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 查詢所有屬於該股票的指標表
        query = """
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name LIKE ?
        ORDER BY name
        """
        prefix = f"indicator_{code}_"
        cursor.execute(query, (f"{prefix}%",))
        
        tables = [row[0] for row in cursor.fetchall()]
        
        indicators = []
        for table in tables:
            parts = table.split("_")
            if len(parts) >= 4:
                indicator_name = parts[2]
                params_hash = parts[3]
                
                # 獲取行數
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                row_count = cursor.fetchone()[0]
                
                # 獲取最新日期
                cursor.execute(f'SELECT MAX(date) FROM "{table}"')
                latest_date = cursor.fetchone()[0]
                
                indicators.append({
                    "table": table,
                    "indicator": indicator_name,
                    "params_hash": params_hash,
                    "row_count": row_count,
                    "latest_date": latest_date,
                })
        
        return {
            "code": code,
            "total": len(indicators),
            "indicators": indicators,
        }
    
    finally:
        conn.close()


@router.get("/precomputed/get")
async def get_precomputed_indicator(
    code: str = Query(..., description="股票代碼"),
    indicator: str = Query(..., description="指標名稱，如 sma/macd/rsi"),
    params: Optional[str] = Query(None, description="參數 JSON 字串"),
) -> Dict[str, Any]:
    """獲取已預計算的指標數據"""
    import json
    
    from src.core.indicators.precomputed_indicators import get_cached_indicator
    
    params_dict = None
    if params:
        try:
            params_dict = json.loads(params)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"參數 JSON 格式錯誤：{e}")
    
    df = get_cached_indicator(code, indicator, params_dict)
    
    if df is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到預計算指標：{code} {indicator} {params_dict}",
        )
    
    return {
        "code": code,
        "indicator": indicator,
        "params": params_dict,
        "columns": df.columns.tolist(),
        "row_count": len(df),
        "data": df.to_dict(orient="records"),
    }


@router.post("/precomputed/warmup")
async def warmup_indicators_endpoint(
    background_tasks: BackgroundTasks,
    codes: Optional[List[str]] = Query(None, description="股票代碼清單"),
    indicators: Optional[List[str]] = Query(None, description="指標名稱清單"),
    max_workers: int = Query(4, ge=1, le=16, description="最大 worker 數"),
    all_stocks: bool = Query(False, description="是否處理所有股票"),
) -> Dict[str, Any]:
    """
    預熱指標緩存（非同步任務）
    
    可選：
    - 指定股票清單
    - 指定指標子集
    - 處理所有股票
    """
    from src.core.indicators.precomputed_indicators import warmup_indicators
    
    # 如果選擇所有股票，需要先獲取清單
    actual_codes = codes
    if all_stocks and not codes:
        from src.core.stock_universe import get_all_codes
        actual_codes = get_all_codes()
    
    if not actual_codes:
        return {
            "status": "error",
            "message": "沒有指定股票代碼",
        }
    
    logger.info(f"開始預熱指標：{len(actual_codes)} 支股票，指標={indicators}")
    
    # 執行預熱（同步，但可以在 background task 中執行）
    result = warmup_indicators(
        codes=actual_codes,
        subset_indicators=indicators,
        max_workers=max_workers,
    )
    
    return result


@router.delete("/precomputed/clear")
async def clear_precomputed_indicators(
    code: str = Query(..., description="股票代碼"),
    indicator: Optional[str] = Query(None, description="指標名稱，不指定則清除所有"),
) -> Dict[str, Any]:
    """清除預計算指標緩存"""
    from src.config import settings
    import sqlite3
    
    db_path = settings.db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 查詢要刪除的表
        if indicator:
            from src.core.indicators.precomputed_indicators import _params_hash
            from src.core.indicators.precomputed_indicators import DEFAULT_INDICATORS
            
            # 找出所有匹配的配置
            configs = [cfg for cfg in DEFAULT_INDICATORS if cfg.name == indicator]
            
            tables_to_delete = []
            for cfg in configs:
                params_hash = _params_hash(cfg.params)
                table_name = f"indicator_{code}_{indicator}_{params_hash}"
                tables_to_delete.append(table_name)
        else:
            # 刪除該股票的所有指標表
            prefix = f"indicator_{code}_"
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name LIKE ?
            """, (f"{prefix}%",))
            tables_to_delete = [row[0] for row in cursor.fetchall()]
        
        # 刪除表
        deleted_count = 0
        for table in tables_to_delete:
            cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
            deleted_count += 1
        
        conn.commit()
        
        return {
            "status": "success",
            "code": code,
            "indicator": indicator,
            "deleted_tables": deleted_count,
            "tables": tables_to_delete[:10],  # 只返回前 10 個
        }
    
    finally:
        conn.close()


@router.get("/config/list")
async def list_indicator_configs() -> Dict[str, Any]:
    """列出所有可用的指標配置"""
    from src.core.indicators.precomputed_indicators import DEFAULT_INDICATORS
    
    configs = []
    for cfg in DEFAULT_INDICATORS:
        configs.append({
            "name": cfg.name,
            "params": cfg.params,
            "output_columns": cfg.output_columns,
            "ttl_days": cfg.ttl_days,
        })
    
    return {
        "total": len(configs),
        "configs": configs,
    }
