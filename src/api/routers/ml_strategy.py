"""
ML 策略 API — 模型訓練、信號生成、模型管理
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from src.core.auth import require_auth
from src.models.user import User
from src.utils.logger import logger

router = APIRouter()


@router.post("/api/ml/train")
async def ml_train(body: dict, user: User = Depends(require_auth)):
    """
    訓練 ML 模型。

    body:
        code: str — 股票代碼
        model_type: str — random_forest | gradient_boosting | xgboost | logistic
        train_ratio: float — 訓練集比例（默認 0.7）
        features: list[str] — 特徵列表（可選）
        prob_threshold: float — 信號閾值（默認 0.6）
        n_estimators: int — 樹數量（默認 100）
        max_depth: int — 最大深度（默認 8）
    """
    from src.core.ml_strategy import train_and_backtest
    from src.core.db import load_daily_kline

    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "請提供股票代碼 (code)")

    model_type = body.get("model_type", "random_forest")
    train_ratio = body.get("train_ratio", 0.7)
    features = body.get("features")
    prob_threshold = body.get("prob_threshold", 0.6)
    model_kwargs = {k: body[k] for k in ("n_estimators", "max_depth", "learning_rate") if k in body}

    try:
        df = load_daily_kline(code)
        if df is None or df.empty:
            raise HTTPException(400, f"股票 {code} 無日線數據")

        # 確保有必要的列
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                raise HTTPException(400, f"數據缺少 {col} 列")

        result = train_and_backtest(
            df, model_type=model_type, train_ratio=train_ratio,
            features=features, prob_threshold=prob_threshold, **model_kwargs,
        )

        # 移除不可序列化的 model 對象
        signals = result["signals"]
        signals_list = signals.to_dict("records") if hasattr(signals, "to_dict") else []

        return {
            "success": True,
            "code": code,
            "model_name": result["model_name"],
            "train_metrics": result["train_metrics"],
            "test_metrics": result["test_metrics"],
            "feature_importance": result["feature_importance"][:10],
            "signals_count": len(signals_list),
            "signals_preview": signals_list[-5:] if signals_list else [],
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"ML 訓練失敗: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/ml/models")
async def ml_list_models(user: User = Depends(require_auth)):
    """列出已保存的 ML 模型。"""
    from src.core.ml_strategy import list_saved_models
    return {"success": True, "models": list_saved_models()}


@router.get("/api/ml/features")
async def ml_list_features():
    """列出默認特徵列表。"""
    from src.core.ml_strategy import DEFAULT_FEATURES
    return {"success": True, "features": DEFAULT_FEATURES}