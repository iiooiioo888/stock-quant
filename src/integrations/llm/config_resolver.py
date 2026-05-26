"""
LLM 運行時配置：請求覆寫 > 用戶設置 > 環境變量。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.config import settings


@dataclass
class LlmRuntimeConfig:
    api_key: str
    api_base: str
    model: str
    temperature: float
    max_tokens: int
    timeout_sec: int
    max_tool_rounds: int
    source: str = "env"


def _mask_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 8:
        return "****" if k else ""
    return f"{k[:4]}…{k[-4:]}"


def extract_user_llm(user_settings: dict | None) -> dict:
    if not isinstance(user_settings, dict):
        return {}
    llm = user_settings.get("llm")
    return llm if isinstance(llm, dict) else {}


def resolve_llm_config(
    request_overrides: dict | None = None,
    user_settings: dict | None = None,
) -> Optional[LlmRuntimeConfig]:
    """合併配置；無有效 api_key 時返回 None。"""
    if not settings.llm_enabled:
        return None

    user_llm = extract_user_llm(user_settings)
    req = request_overrides if isinstance(request_overrides, dict) else {}

    api_key = (
        str(req.get("api_key") or req.get("apiKey") or "").strip()
        or str(user_llm.get("api_key") or "").strip()
        or (settings.llm_api_key or "").strip()
    )
    if not api_key:
        return None

    api_base = (
        str(req.get("api_base") or req.get("apiBase") or "").strip()
        or str(user_llm.get("api_base") or "").strip()
        or (settings.llm_api_base or "https://api.openai.com/v1")
    ).rstrip("/")
    model = (
        str(req.get("model") or "").strip()
        or str(user_llm.get("model") or "").strip()
        or settings.llm_model
    )

    if str(req.get("api_key") or req.get("apiKey") or "").strip():
        source = "request"
    elif str(user_llm.get("api_key") or "").strip():
        source = "user"
    else:
        source = "env"

    return LlmRuntimeConfig(
        api_key=api_key,
        api_base=api_base,
        model=model,
        temperature=float(req.get("temperature") if req.get("temperature") is not None else settings.llm_temperature),
        max_tokens=int(req.get("max_tokens") or settings.llm_max_tokens),
        timeout_sec=int(req.get("timeout_sec") or settings.llm_timeout_sec),
        max_tool_rounds=int(req.get("max_tool_rounds") or settings.llm_max_tool_rounds),
        source=source,
    )


def llm_status_payload(cfg: LlmRuntimeConfig | None, tool_count: int) -> dict:
    env_has = bool((settings.llm_api_key or "").strip())
    if not cfg:
        return {
            "enabled": settings.llm_enabled,
            "configured": False,
            "env_configured": env_has,
            "model": None,
            "api_base": None,
            "api_key_masked": "",
            "source": None,
            "tool_count": tool_count,
        }
    return {
        "enabled": settings.llm_enabled,
        "configured": True,
        "env_configured": env_has,
        "model": cfg.model,
        "api_base": cfg.api_base,
        "api_key_masked": _mask_key(cfg.api_key),
        "source": cfg.source,
        "tool_count": tool_count,
    }


def is_llm_configured(
    request_overrides: dict | None = None,
    user_settings: dict | None = None,
) -> bool:
    """是否已具備可用 LLM 配置（含環境變量）。"""
    return resolve_llm_config(request_overrides, user_settings) is not None


def public_llm_settings(user_settings: dict | None) -> dict:
    """返回可給前端的用戶 LLM 設置（不含明文 key）。"""
    llm = extract_user_llm(user_settings)
    key = str(llm.get("api_key") or "").strip()
    return {
        "api_base": str(llm.get("api_base") or "").strip(),
        "model": str(llm.get("model") or "").strip(),
        "has_api_key": bool(key),
        "api_key_masked": _mask_key(key),
    }
