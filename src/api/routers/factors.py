"""
多因子選股 API — 因子定義、計算、IC 分析、正交化、選股打分

端點：
- GET  /api/factors/definitions   列出所有因子定義
- POST /api/factors/screen        多因子選股打分
- POST /api/factors/ic            因子 IC 分析
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.auth import require_auth
from src.models.user import User
from src.utils.logger import logger

router = APIRouter()


# ── Pydantic Models ──────────────────────────────────────────


class FactorDefinition(BaseModel):
    """因子定義"""

    key: str = Field(..., description="因子唯一標識", examples=["pe_ttm"])
    label: str = Field(..., description="因子中文名稱", examples=["市盈率(TTM)"])
    category: str = Field(..., description="因子類別", examples=["value"])
    direction: int = Field(
        ..., description="方向：1=越高越好, -1=越低越好, 0=中性", examples=[-1]
    )
    description: str = Field(..., description="因子說明", examples=["越低越好"])


class FactorDefinitionsResponse(BaseModel):
    """因子定義響應"""

    success: bool = True
    factors: list[FactorDefinition] = Field(..., description="因子列表")
    categories: dict[str, list[str]] = Field(
        ...,
        description="按類別分組",
        examples=[{"value": ["pe_ttm", "pb"], "quality": ["roe", "gross_margin"]}],
    )


class FactorScreenRequest(BaseModel):
    """多因子選股請求"""

    codes: list[str] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="股票代碼列表",
        examples=[["600519", "000001", "601318"]],
    )
    weights: Optional[dict[str, float]] = Field(
        None,
        description="因子權重（可選，默認等權）",
        examples=[{"pe_ttm": 0.3, "roe": 0.3, "momentum_20d": 0.4}],
    )
    top_n: int = Field(20, ge=1, le=100, description="返回前 N 名")


class StockScore(BaseModel):
    """個股打分結果"""

    code: str = Field(..., examples=["600519"])
    score: float = Field(..., description="綜合得分", examples=[1.2345])
    rank: int = Field(..., description="排名", examples=[1])
    factors: dict = Field(default_factory=dict, description="各因子原始值")


class FactorScreenResponse(BaseModel):
    """多因子選股響應"""

    success: bool = True
    results: list[StockScore] = Field(..., description="打分排名結果")
    total: int = Field(..., description="輸入股票總數", examples=[3])
    returned: int = Field(..., description="返回結果數", examples=[3])


class ICAnalysisRequest(BaseModel):
    """因子 IC 分析請求"""

    factor_values: list[float] = Field(
        ...,
        min_length=5,
        description="因子值序列",
        examples=[[0.5, 0.8, 1.2, 0.3, 0.9, 1.1, 0.6, 0.7, 1.0, 0.4]],
    )
    forward_returns: list[float] = Field(
        ...,
        min_length=5,
        description="對應的未來收益率序列",
        examples=[[0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.03, 0.02, 0.01, -0.01]],
    )


class ICResult(BaseModel):
    """IC 分析結果"""

    ic: float = Field(..., description="Pearson IC", examples=[0.15])
    rank_ic: float = Field(..., description="Spearman Rank IC", examples=[0.18])
    ic_ir: float = Field(..., description="IC 信息比率", examples=[0.15])
    n: int = Field(..., description="有效樣本數", examples=[10])


class ICAnalysisResponse(BaseModel):
    """IC 分析響應"""

    success: bool = True
    result: ICResult


# ── 端點 ─────────────────────────────────────────────────────


@router.get(
    "/api/factors/definitions",
    response_model=FactorDefinitionsResponse,
    summary="列出所有因子定義",
    description="""
返回系統支持的所有因子，包括名稱、類別、方向和說明。

**因子類別：**
- `value` — 價值因子（PE、PB、股息率）
- `quality` — 質量因子（ROE、毛利率、淨利率、負債率）
- `growth` — 成長因子（營收同比、利潤同比）
- `momentum` — 動量因子（20/60日收益率）
- `volatility` — 波動因子（年化波動率、ATR 比率）
- `liquidity` — 流動性因子（換手率、量比）

**direction 說明：**
- `1` = 越高越好（如 ROE、股息率）
- `-1` = 越低越好（如 PE、PB、負債率）
- `0` = 中性（如換手率、量比）
""",
    responses={
        200: {
            "description": "成功返回因子定義列表",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "factors": [
                            {
                                "key": "pe_ttm",
                                "label": "市盈率(TTM)",
                                "category": "value",
                                "direction": -1,
                                "description": "越低越好",
                            },
                            {
                                "key": "roe",
                                "label": "ROE",
                                "category": "quality",
                                "direction": 1,
                                "description": "越高越好",
                            },
                            {
                                "key": "momentum_20d",
                                "label": "20日動量",
                                "category": "momentum",
                                "direction": 1,
                                "description": "20日收益率",
                            },
                        ],
                        "categories": {
                            "value": ["pe_ttm", "pb", "dividend_yield"],
                            "quality": [
                                "roe",
                                "gross_margin",
                                "net_margin",
                                "debt_ratio",
                            ],
                            "momentum": ["momentum_20d", "momentum_60d"],
                        },
                    }
                }
            },
        }
    },
)
async def factor_definitions():
    """列出所有因子定義（名稱、類別、方向、說明）"""
    from src.core.factor_engine import list_factor_definitions, list_factor_categories

    return {
        "success": True,
        "factors": list_factor_definitions(),
        "categories": list_factor_categories(),
    }


@router.post(
    "/api/factors/screen",
    response_model=FactorScreenResponse,
    summary="多因子選股打分",
    description="""
對輸入的股票列表進行多因子綜合打分。

**流程：**
1. 載入每只股票的基本面數據（PE/ROE 等）和 K 線數據（動量/波動等）
2. 對每個因子進行 Z-Score 標準化
3. 根據因子方向調整（direction=-1 取反）
4. 按權重加權求和得到綜合得分
5. 按得分降序排名

**使用場景：**
- 選股池篩選：從候選股票中選出最優標的
- 因子歸因：了解哪些因子對收益貢獻最大
- 策略研發：測試不同因子權重組合的效果

**請求範例：**
```json
{
  "codes": ["600519", "000001", "601318", "000858", "000333"],
  "weights": {"pe_ttm": 0.2, "roe": 0.3, "momentum_20d": 0.3, "volatility_20d": 0.2},
  "top_n": 3
}
```

**響應範例：**
```json
{
  "success": true,
  "results": [
    {"code": "600519", "score": 1.2345, "rank": 1, "factors": {"pe_ttm": 25.3, "roe": 31.2}},
    {"code": "601318", "score": 0.8912, "rank": 2, "factors": {"pe_ttm": 8.5, "roe": 18.7}},
    {"code": "000858", "score": 0.5678, "rank": 3, "factors": {"pe_ttm": 22.1, "roe": 25.4}}
  ],
  "total": 5,
  "returned": 3
}
```
""",
    responses={
        200: {"description": "成功返回打分結果"},
        400: {"description": "參數錯誤（codes 為空或超過 500）"},
        401: {"description": "未登錄"},
    },
)
async def factor_screen(body: FactorScreenRequest, user: User = Depends(require_auth)):
    """多因子選股打分。"""
    from src.core.factor_engine import screen_by_factors
    from src.core.fundamental import get_fundamentals
    from src.core.db import load_daily_kline

    codes = body.codes
    weights = body.weights
    top_n = body.top_n

    # 載入基本面數據
    fundamentals_map = {}
    for code in codes:
        try:
            fund = get_fundamentals(code, max_age_days=30)
            if fund:
                fundamentals_map[code] = fund
        except Exception:
            pass

    # 載入 K 線數據
    import pandas as pd

    kline_map = {}
    for code in codes:
        try:
            df = load_daily_kline(code)
            if df is not None and not df.empty:
                kline_map[code] = df
        except Exception:
            pass

    results = screen_by_factors(
        codes=codes,
        fundamentals_map=fundamentals_map,
        kline_map=kline_map,
        weights=weights,
        top_n=top_n,
    )

    return {
        "success": True,
        "results": results,
        "total": len(codes),
        "returned": len(results),
    }


@router.post(
    "/api/factors/ic",
    response_model=ICAnalysisResponse,
    summary="因子 IC 分析",
    description="""
計算因子的 Information Coefficient（IC），衡量因子與未來收益的相關性。

**指標說明：**
- `ic` — Pearson 相關係數（線性相關）
- `rank_ic` — Spearman 秩相關（排序相關，更穩健）
- `ic_ir` — IC 信息比率（IC 均值 / IC 標準差）
- `n` — 有效樣本數

**判斷標準：**
- |IC| > 0.03：因子有效
- |IC| > 0.05：因子較強
- |IC| > 0.10：因子很強

**請求範例：**
```json
{
  "factor_values": [0.5, 0.8, 1.2, 0.3, 0.9, 1.1, 0.6, 0.7, 1.0, 0.4],
  "forward_returns": [0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.03, 0.02, 0.01, -0.01]
}
```

**響應範例：**
```json
{
  "success": true,
  "result": {
    "ic": 0.15,
    "rank_ic": 0.18,
    "ic_ir": 0.15,
    "n": 10
  }
}
```
""",
    responses={
        200: {"description": "成功返回 IC 分析結果"},
        400: {"description": "參數錯誤（數據不足）"},
        401: {"description": "未登錄"},
    },
)
async def factor_ic_analysis(
    body: ICAnalysisRequest, user: User = Depends(require_auth)
):
    """因子 IC 分析。"""
    from src.core.factor_engine import compute_ic

    result = compute_ic(body.factor_values, body.forward_returns)
    return {"success": True, "result": result}



@router.post("/api/factors/eval-expression")
async def eval_factor_expression_api(body: dict, user: User = Depends(require_auth)):
    """自訂因子表達式（白名單四則運算）。body: expression, factors"""
    from src.core.factor_expression import FactorExpressionError, eval_factor_expression

    expr = str((body or {}).get("expression") or "")
    factors = (body or {}).get("factors") or {}
    if not isinstance(factors, dict):
        raise HTTPException(400, "factors 須為物件")
    try:
        value = eval_factor_expression(expr, factors)
    except FactorExpressionError as e:
        raise HTTPException(400, str(e))
    return {"success": True, "value": value, "expression": expr}


@router.post("/api/factors/combo-ga")
async def combo_ga_api(body: dict, user: User = Depends(require_auth)):
    """遺傳演算法尋找策略權重。body.returns: [[r1,r2,...], ...] 日×策略"""
    from src.core.combo_ga import optimize_weights
    import numpy as np

    raw = (body or {}).get("returns")
    if not raw:
        raise HTTPException(400, "缺少 returns")
    try:
        arr = np.asarray(raw, dtype=float)
        out = optimize_weights(
            arr,
            generations=int((body or {}).get("generations") or 40),
            pop_size=int((body or {}).get("pop_size") or 32),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"success": True, **out}
