"""
機器學習策略集成 — sklearn/XGBoost 接口

功能：
- 特徵工程管道：技術指標 → 特徵矩陣
- 模型訓練 + 預測 + 信號生成
- 與回測引擎整合
"""
from __future__ import annotations

import pickle
import time
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.config import DATA_DIR
from src.utils.logger import logger

_MODEL_DIR = DATA_DIR / "ml_models"
_MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 特徵工程
# ============================================================

DEFAULT_FEATURES = [
    "return_1d", "return_5d", "return_10d", "return_20d",
    "ma_ratio_5_20", "ma_ratio_5_60",
    "rsi_14", "macd_hist", "bb_pct_b",
    "vol_ratio_5", "vol_ratio_20",
    "atr_pct_14", "close_ma20_ratio",
]


def build_feature_matrix(df: pd.DataFrame, features: list[str] = None) -> pd.DataFrame:
    """
    從 OHLCV DataFrame 構建特徵矩陣。
    
    Args:
        df: DataFrame with columns [date, open, high, low, close, volume]
        features: 特徵名稱列表（默認 DEFAULT_FEATURES）
    
    Returns:
        DataFrame with feature columns + date
    """
    if features is None:
        features = list(DEFAULT_FEATURES)

    f = pd.DataFrame(index=df.index)
    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df.columns else close
    low = df["low"].astype(float) if "low" in df.columns else close
    volume = df["volume"].astype(float) if "volume" in df.columns else pd.Series(0, index=df.index)

    # 收益率
    if "return_1d" in features:
        f["return_1d"] = close.pct_change(1)
    if "return_5d" in features:
        f["return_5d"] = close.pct_change(5)
    if "return_10d" in features:
        f["return_10d"] = close.pct_change(10)
    if "return_20d" in features:
        f["return_20d"] = close.pct_change(20)

    # 均線比率
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    if "ma_ratio_5_20" in features:
        f["ma_ratio_5_20"] = ma5 / ma20 - 1
    if "ma_ratio_5_60" in features:
        f["ma_ratio_5_60"] = ma5 / ma60 - 1

    # RSI
    if "rsi_14" in features:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        f["rsi_14"] = 100 - 100 / (1 + rs)

    # MACD histogram
    if "macd_hist" in features:
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal = macd_line.ewm(span=9).mean()
        f["macd_hist"] = macd_line - signal

    # Bollinger %B
    if "bb_pct_b" in features:
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        f["bb_pct_b"] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    # 成交量比率
    if "vol_ratio_5" in features:
        vol_ma5 = volume.rolling(5).mean()
        f["vol_ratio_5"] = volume / vol_ma5.replace(0, np.nan)
    if "vol_ratio_20" in features:
        vol_ma20 = volume.rolling(20).mean()
        f["vol_ratio_20"] = volume / vol_ma20.replace(0, np.nan)

    # ATR%
    if "atr_pct_14" in features:
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        f["atr_pct_14"] = atr / close

    # 收盤價/MA20
    if "close_ma20_ratio" in features:
        f["close_ma20_ratio"] = close / ma20 - 1

    if "date" in df.columns:
        f["date"] = df["date"].values
    f["target"] = close.shift(-1) / close - 1  # 次日收益率

    return f


def prepare_train_data(df: pd.DataFrame, features: list[str] = None,
                        label_threshold: float = 0.0) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """
    準備訓練數據（去除 NaN，二分類標籤）。
    
    Args:
        df: 特徵矩陣（build_feature_matrix 輸出）
        features: 使用的特徵列
        label_threshold: 分類閾值（>threshold=1, <=threshold=0）
    
    Returns:
        (X, y, feature_names)
    """
    if features is None:
        features = list(DEFAULT_FEATURES)

    available = [f for f in features if f in df.columns]
    data = df[available + ["target"]].dropna()

    if data.empty:
        return np.array([]).reshape(0, len(available)), np.array([]), available

    X = data[available].values
    y = (data["target"] > label_threshold).astype(int).values

    return X, y, available


# ============================================================
# 模型訓練與預測
# ============================================================

def train_model(X: np.ndarray, y: np.ndarray, feature_names: list[str],
                 model_type: str = "random_forest", **kwargs) -> Any:
    """
    訓練分類模型。
    
    Args:
        X: 特徵矩陣
        y: 標籤
        feature_names: 特徵名稱
        model_type: random_forest | gradient_boosting | xgboost | logistic
    
    Returns:
        訓練好的模型
    """
    if len(X) == 0:
        raise ValueError("訓練數據為空")

    if model_type == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(
            n_estimators=kwargs.get("n_estimators", 100),
            max_depth=kwargs.get("max_depth", 8),
            min_samples_leaf=kwargs.get("min_samples_leaf", 20),
            random_state=42, n_jobs=-1,
        )
    elif model_type == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(
            n_estimators=kwargs.get("n_estimators", 100),
            max_depth=kwargs.get("max_depth", 5),
            learning_rate=kwargs.get("learning_rate", 0.1),
            random_state=42,
        )
    elif model_type == "xgboost":
        try:
            from xgboost import XGBClassifier
            model = XGBClassifier(
                n_estimators=kwargs.get("n_estimators", 100),
                max_depth=kwargs.get("max_depth", 6),
                learning_rate=kwargs.get("learning_rate", 0.1),
                random_state=42, n_jobs=-1,
                eval_metric="logloss",
            )
        except ImportError:
            logger.warning("XGBoost 未安裝，回退到 GradientBoosting")
            from sklearn.ensemble import GradientBoostingClassifier
            model = GradientBoostingClassifier(
                n_estimators=kwargs.get("n_estimators", 100),
                max_depth=kwargs.get("max_depth", 5),
                random_state=42,
            )
    elif model_type == "logistic":
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression(max_iter=1000, random_state=42)
    else:
        raise ValueError(f"不支持的模型類型: {model_type}")

    model.fit(X, y)
    return model


def evaluate_model(model, X_test: np.ndarray, y_test: np.ndarray) -> dict:
    """評估模型性能。"""
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    y_pred = model.predict(X_test)
    return {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "samples": len(y_test),
    }


def get_feature_importance(model, feature_names: list[str]) -> list[dict]:
    """提取特徵重要性。"""
    try:
        importances = model.feature_importances_
    except AttributeError:
        try:
            importances = np.abs(model.coef_[0])
        except AttributeError:
            return []

    pairs = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
    return [{"feature": name, "importance": round(float(imp), 4)} for name, imp in pairs]


# ============================================================
# 模型保存/加載
# ============================================================

def save_model(model, name: str, metadata: dict = None) -> str:
    """保存模型到磁盤。"""
    path = _MODEL_DIR / f"{name}.pkl"
    payload = {"model": model, "metadata": metadata or {}, "saved_at": time.time()}
    with open(path, "wb") as f:
        pickle.dump(payload, f)
    logger.info(f"模型已保存: {path}")
    return str(path)


def load_model(name: str) -> Optional[tuple]:
    """加載模型，返回 (model, metadata)。"""
    path = _MODEL_DIR / f"{name}.pkl"
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            payload = pickle.load(f)
        return payload.get("model"), payload.get("metadata", {})
    except Exception as e:
        logger.warning(f"模型加載失敗: {e}")
        return None


def list_saved_models() -> list[dict]:
    """列出已保存的模型。"""
    out = []
    for p in sorted(_MODEL_DIR.glob("*.pkl")):
        stat = p.stat()
        out.append({
            "name": p.stem,
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
        })
    return out


# ============================================================
# 信號生成（與回測整合）
# ============================================================

def generate_signals(df: pd.DataFrame, model, features: list[str] = None,
                      prob_threshold: float = 0.6) -> pd.DataFrame:
    """
    使用模型生成交易信號。
    
    Args:
        df: OHLCV DataFrame
        model: 訓練好的模型
        features: 特徵名稱
        prob_threshold: 概率閾值（>threshold 買入）
    
    Returns:
        DataFrame with columns [date, signal, probability]
        signal: 1=買入, -1=賣出, 0=持有
    """
    feat_df = build_feature_matrix(df, features)
    available = [f for f in (features or DEFAULT_FEATURES) if f in feat_df.columns]
    data = feat_df[available].dropna()

    if data.empty:
        return pd.DataFrame(columns=["date", "signal", "probability"])

    X = data.values
    probs = model.predict_proba(X)[:, 1]  # 類別 1 的概率

    signals = np.zeros(len(probs))
    signals[probs > prob_threshold] = 1   # 買入
    signals[probs < (1 - prob_threshold)] = -1  # 賣出

    result = pd.DataFrame({
        "signal": signals.astype(int),
        "probability": np.round(probs, 4),
    }, index=data.index)

    if "date" in feat_df.columns:
        result["date"] = feat_df.loc[data.index, "date"].values

    return result


# ============================================================
# 便捷端到端流程
# ============================================================

def train_and_backtest(df: pd.DataFrame, model_type: str = "random_forest",
                        train_ratio: float = 0.7, features: list[str] = None,
                        prob_threshold: float = 0.6, **model_kwargs) -> dict:
    """
    端到端：特徵工程 → 訓練 → 回測。
    
    Args:
        df: OHLCV DataFrame
        model_type: 模型類型
        train_ratio: 訓練集比例
        features: 特徵列表
        prob_threshold: 信號閾值
        **model_kwargs: 模型參數
    
    Returns:
        {"model": model, "train_metrics": dict, "test_metrics": dict,
         "feature_importance": list, "signals": DataFrame, "model_path": str}
    """
    feat_df = build_feature_matrix(df, features)
    X, y, feat_names = prepare_train_data(feat_df, features)

    if len(X) < 100:
        raise ValueError(f"數據不足（{len(X)} 條），至少需要 100 條")

    # 時間序列切分（不打亂）
    split = int(len(X) * train_ratio)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    # 訓練
    model = train_model(X_train, y_train, feat_names, model_type=model_type, **model_kwargs)

    # 評估
    train_metrics = evaluate_model(model, X_train, y_train)
    test_metrics = evaluate_model(model, X_test, y_test)

    # 特徵重要性
    importance = get_feature_importance(model, feat_names)

    # 生成信號
    signals = generate_signals(df, model, features, prob_threshold)

    # 保存模型
    model_name = f"ml_{model_type}_{int(time.time())}"
    model_path = save_model(model, model_name, {
        "model_type": model_type,
        "features": feat_names,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "prob_threshold": prob_threshold,
    })

    return {
        "model": model,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "feature_importance": importance,
        "signals": signals,
        "model_name": model_name,
        "model_path": model_path,
    }
