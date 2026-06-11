"""
LLM 服務層 — 模型路由 + Prompt Cache + 專用 Prompt 管理。

職責：
- 根據任務類型選擇輕量/重量模型
- Redis Prompt Cache（相同問題 + 相同數據 → 返回上次結果）
- 提供各業務場景的專用 System Prompt
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Generator, Optional

from src.integrations.llm.client import chat_completions
from src.integrations.llm.config_resolver import LlmRuntimeConfig, resolve_llm_config
from src.utils.logger import logger

# ---------------------------------------------------------------------------
# 模型路由
# ---------------------------------------------------------------------------

# 任務類型 → 推薦模型層級
_TASK_MODEL_TIERS: dict[str, str] = {
    # 輕量任務（gpt-4o-mini）
    "stock_summary": "light",
    "signal_translate": "light",
    "data_anomaly": "light",
    "simple_qa": "light",
    "morning_report": "light",
    # 重量任務（gpt-4o / claude）
    "strategy_analysis": "heavy",
    "backtest_report": "heavy",
    "code_generate": "heavy",
    "param_optimize": "heavy",
    "multi_strategy_design": "heavy",
    "portfolio_report": "heavy",
}

# 層級 → 模型名稱映射（可由配置覆蓋）
_TIER_MODEL_OVERRIDES: dict[str, str] = {}


def set_tier_model(tier: str, model: str) -> None:
    """運行時覆蓋某層級的模型名。"""
    _TIER_MODEL_OVERRIDES[tier] = model


def _resolve_model_for_task(cfg: LlmRuntimeConfig, task_type: str) -> str:
    """根據任務類型決定實際使用的模型名。"""
    tier = _TASK_MODEL_TIERS.get(task_type, "light")
    override = _TIER_MODEL_OVERRIDES.get(tier)
    if override:
        return override
    # 如果用戶配置的模型本身是重量級（含 gpt-4o, claude 等），直接使用
    model_lower = cfg.model.lower()
    if tier == "heavy" and "mini" in model_lower:
        # 用戶配的是 mini，但任務需要重量級 → 用 gpt-4o
        return "gpt-4o"
    if tier == "light" and "mini" not in model_lower:
        # 用戶配的是重量級，但任務是輕量 → 用 mini 省成本
        return "gpt-4o-mini"
    return cfg.model


# ---------------------------------------------------------------------------
# Prompt Cache（Redis）
# ---------------------------------------------------------------------------

_CACHE_PREFIX = "llm:cache:"
_CACHE_TTL = 3600  # 1 小時
_redis_client = None
_cache_available = False
_cache_initialized = False


def _get_cache_redis():
    global _redis_client, _cache_available, _cache_initialized
    if _cache_initialized:
        return _redis_client
    _cache_initialized = True
    try:
        from src.config import settings

        if not getattr(settings, "redis_enabled", False):
            return None
        import redis as redis_lib

        url = getattr(settings, "redis_url", "redis://localhost:6379/0")
        pwd = getattr(settings, "redis_password", "")
        _redis_client = redis_lib.from_url(
            url,
            password=pwd or None,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        _cache_available = True
        logger.info("✅ LLM Prompt Cache: Redis 已連接")
        return _redis_client
    except Exception:
        _redis_client = None
        _cache_available = False
        return None


def _cache_key(task_type: str, prompt: str, context: str = "") -> str:
    raw = f"{task_type}|{prompt}|{context}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{_CACHE_PREFIX}{h}"


def cache_get(task_type: str, prompt: str, context: str = "") -> Optional[dict]:
    """查詢 Prompt Cache；命中返回完整結果 dict，否則 None。"""
    r = _get_cache_redis()
    if not r:
        return None
    try:
        key = _cache_key(task_type, prompt, context)
        raw = r.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def cache_set(task_type: str, prompt: str, result: dict, context: str = "") -> None:
    """寫入 Prompt Cache。"""
    r = _get_cache_redis()
    if not r:
        return
    try:
        key = _cache_key(task_type, prompt, context)
        r.setex(key, _CACHE_TTL, json.dumps(result, ensure_ascii=False, default=str))
    except Exception:
        pass


def cache_stats() -> dict:
    r = _get_cache_redis()
    if not r:
        return {"available": False, "backend": "none"}
    try:
        count = 0
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=f"{_CACHE_PREFIX}*", count=100)
            count += len(keys)
            if cursor == 0:
                break
        return {"available": True, "backend": "redis", "cached_prompts": count}
    except Exception as e:
        return {"available": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 專用 System Prompt
# ---------------------------------------------------------------------------

_PROMPTS: dict[str, str] = {
    "analyze": """你是 StockQ 量化平台的回測分析師。用戶將提供回測結果數據，你的任務是：
1. 用簡潔條列解讀核心指標（年化收益、最大回撤、夏普比率、勝率、盈虧比）
2. 指出策略的優勢與風險
3. 給出可操作的優化建議（如調參、加風控）
4. 使用繁體中文，數字保留合理精度
不要編造數據；僅基於用戶提供的數據進行分析。""",
    "suggest": """你是 StockQ 量化平台的策略推薦專家。根據用戶描述的投資目標和偏好：
1. 推薦 2-3 個適合的量化策略（從平台策略庫中選取）
2. 說明每個策略的適用場景、風險特徵、歷史表現
3. 給出參數配置建議
4. 提醒風險注意事項
使用繁體中文回答，語氣專業但易懂。""",
    "generate": """你是 StockQ 量化平台的策略代碼工程師。用戶會描述想要的策略邏輯，你需要：
1. 生成符合 StockQ 策略框架的 Python 代碼
2. 代碼必須包含 `generate_signals(df, params)` 函數
3. 添加清晰的中文註釋
4. 列出關鍵參數及其推薦範圍
5. 提醒潛在風險（過擬合、參數敏感性等）
代碼必須可直接在 StockQ 平台運行。""",
    "optimize": """你是 StockQ 量化平台的參數調優顧問。根據用戶的回測結果和策略描述：
1. 分析當前參數的表現
2. 建議調整的參數及其方向（增大/減小/替換）
3. 解釋調整理由（基於量化原理）
4. 提供 2-3 組推薦參數組合
5. 提醒不要過度優化
使用繁體中文，結合具體數據說明。""",
    "report": """你是 StockQ 量化平台的投資報告撰寫者。根據提供的數據和分析結果：
1. 撰寫結構化投資報告（摘要、市場概況、策略分析、風險提示、結論）
2. 數據引用要準確
3. 語言專業、邏輯清晰
4. 包含免責聲明
使用繁體中文，格式清晰。""",
    "morning": """你是 StockQ 量化平台的市場分析師，負責撰寫每日晨報：
1. 基於提供的市場數據，概述昨日市場表現
2. 分析主要板塊/行業動向
3. 關注重要信號（北向資金、成交量異常等）
4. 給出今日關注要點
5. 風險提醒
使用繁體中文，簡潔有力，重點突出。如果沒有足夠數據，說明並建議用戶先下載行情。""",
}


def get_system_prompt(task: str) -> str:
    """獲取專用 System Prompt。"""
    return _PROMPTS.get(task, _PROMPTS.get("analyze", "你是量化投資助手。"))


# ---------------------------------------------------------------------------
# 統一調用接口
# ---------------------------------------------------------------------------


def invoke_llm(
    task_type: str,
    user_message: str,
    *,
    history: list | None = None,
    system_prompt: str | None = None,
    request_overrides: dict | None = None,
    user_settings: dict | None = None,
    enable_cache: bool = True,
    cache_context: str = "",
) -> dict:
    """
    統一 LLM 調用入口。

    - task_type: 用於模型路由和 prompt cache key
    - enable_cache: 是否啟用 prompt cache（流式調用應關閉）
    - 返回 {"success": True/False, "answer": ..., "model": ..., "cached": bool, ...}
    """
    # 1. 查詢 cache
    if enable_cache:
        cached = cache_get(task_type, user_message, cache_context)
        if cached:
            cached["cached"] = True
            return cached

    # 2. 解析配置
    cfg = resolve_llm_config(request_overrides, user_settings)
    if not cfg:
        return {
            "success": False,
            "configured": False,
            "error": "未配置 LLM：請在「設定」填寫 API Key，或設置環境變量 SQ_LLM_API_KEY",
        }

    # 3. 模型路由
    model = _resolve_model_for_task(cfg, task_type)
    original_model = cfg.model
    cfg.model = model

    # 4. 構建消息
    sys_prompt = system_prompt or get_system_prompt(task_type)
    messages: list[dict] = [{"role": "system", "content": sys_prompt}]
    if history:
        for item in history[-10:]:
            if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
                messages.append(
                    {
                        "role": item["role"],
                        "content": str(item.get("content", ""))[:4000],
                    }
                )
    messages.append({"role": "user", "content": user_message})

    # 5. 調用 LLM
    t0 = time.time()
    try:
        data = chat_completions(cfg, messages, stream=False)
    except Exception as e:
        cfg.model = original_model
        return {"success": False, "configured": True, "error": str(e)}
    finally:
        cfg.model = original_model

    if not isinstance(data, dict):
        return {"success": False, "configured": True, "error": "LLM 返回格式異常"}

    choice = (data.get("choices") or [{}])[0]
    answer = ((choice.get("message") or {}).get("content") or "").strip()
    elapsed = round(time.time() - t0, 2)

    result = {
        "success": bool(answer),
        "configured": True,
        "answer": answer,
        "model": model,
        "task_type": task_type,
        "elapsed_sec": elapsed,
        "cached": False,
    }
    if not answer:
        result["error"] = "LLM 未返回有效回答"

    # 6. 寫入 cache
    if enable_cache and answer:
        cache_set(task_type, user_message, result, cache_context)

    return result


def invoke_llm_stream(
    task_type: str,
    user_message: str,
    *,
    history: list | None = None,
    system_prompt: str | None = None,
    request_overrides: dict | None = None,
    user_settings: dict | None = None,
) -> Generator[dict, None, None]:
    """
    統一 LLM 流式調用入口（SSE 事件）。

    Yields: {"type": "status"|"token"|"done"|"error", ...}
    """
    cfg = resolve_llm_config(request_overrides, user_settings)
    if not cfg:
        yield {"type": "error", "message": "未配置 LLM：請在「設定」填寫 API Key"}
        return

    model = _resolve_model_for_task(cfg, task_type)
    original_model = cfg.model
    cfg.model = model

    sys_prompt = system_prompt or get_system_prompt(task_type)
    messages: list[dict] = [{"role": "system", "content": sys_prompt}]
    if history:
        for item in history[-10:]:
            if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
                messages.append(
                    {
                        "role": item["role"],
                        "content": str(item.get("content", ""))[:4000],
                    }
                )
    messages.append({"role": "user", "content": user_message})

    yield {"type": "status", "message": f"正在使用 {model} 分析…", "model": model}

    try:
        parts: list[str] = []
        stream = chat_completions(cfg, messages, tools=None, stream=True)
        for token in stream:
            parts.append(token)
            yield {"type": "token", "content": token}
        answer = "".join(parts).strip()
        if answer:
            yield {
                "type": "done",
                "success": True,
                "answer": answer,
                "model": model,
                "task_type": task_type,
            }
        else:
            yield {"type": "error", "message": "LLM 未返回有效回答"}
    except Exception as e:
        yield {"type": "error", "message": str(e)}
    finally:
        cfg.model = original_model
