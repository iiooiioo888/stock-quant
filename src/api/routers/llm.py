"""LLM 智能問答 API（含 SSE 流式、用戶 Key 設置）"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.config import settings
from src.core.auth import require_auth
from src.core.db import get_conn
from src.integrations.llm.agent import run_chat, stream_chat_events
from src.integrations.llm.config_resolver import (
    extract_user_llm,
    llm_status_payload,
    public_llm_settings,
    resolve_llm_config,
)
from src.integrations.llm.tools_bridge import tool_names_for_llm

router = APIRouter()


def _user_settings_dict(user) -> dict:
    s = getattr(user, "settings", None)
    return s if isinstance(s, dict) else {}


def _save_user_llm_settings(user_id: int, llm_partial: dict) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT settings FROM users WHERE id = ?", (user_id,)).fetchone()
        all_settings = {}
        if row and row[0]:
            try:
                all_settings = json.loads(row[0])
            except Exception:
                all_settings = {}
        if not isinstance(all_settings, dict):
            all_settings = {}
        llm = extract_user_llm(all_settings)
        for key in ("api_key", "api_base", "model"):
            if key in llm_partial:
                val = str(llm_partial[key] or "").strip()
                if key == "api_key" and val == "":
                    llm.pop("api_key", None)
                elif val:
                    llm[key] = val
                elif key != "api_key":
                    llm.pop(key, None)
        if llm:
            all_settings["llm"] = llm
        elif "llm" in all_settings:
            del all_settings["llm"]
        conn.execute(
            "UPDATE users SET settings = ? WHERE id = ?",
            (json.dumps(all_settings, ensure_ascii=False), user_id),
        )
    return all_settings


@router.get("/api/llm/status")
async def llm_status():
    """LLM 服務狀態（環境變量層級；登錄後請用 /api/llm/settings）。"""
    cfg = resolve_llm_config()
    payload = llm_status_payload(cfg, len(tool_names_for_llm()))
    payload["tools"] = tool_names_for_llm()
    return payload


@router.get("/api/llm/settings")
async def llm_get_settings(user=Depends(require_auth)):
    """讀取當前用戶 LLM 設置（不含明文 Key）。"""
    user_settings = _user_settings_dict(user)
    cfg = resolve_llm_config(user_settings=user_settings)
    return {
        "success": True,
        "settings": public_llm_settings(user_settings),
        "configured": cfg is not None,
        "env_configured": bool((settings.llm_api_key or "").strip()),
        "defaults": {
            "api_base": (settings.llm_api_base or "").rstrip("/"),
            "model": settings.llm_model,
        },
    }


@router.put("/api/llm/settings")
async def llm_put_settings(body: dict, user=Depends(require_auth)):
    """保存用戶 LLM API Key / Base / Model 到帳號設置。"""
    llm_body = body.get("llm") if isinstance(body.get("llm"), dict) else body
    if llm_body.get("clear"):
        allowed = {"api_key": "", "api_base": "", "model": ""}
    else:
        allowed = {}
        if "api_key" in llm_body:
            allowed["api_key"] = llm_body.get("api_key")
        if "api_base" in llm_body:
            allowed["api_base"] = llm_body.get("api_base")
        if "model" in llm_body:
            allowed["model"] = llm_body.get("model")

    all_settings = _save_user_llm_settings(user.id, allowed)
    user.settings = all_settings
    cfg = resolve_llm_config(user_settings=all_settings)
    return {
        "success": True,
        "message": "LLM 設置已保存",
        "settings": public_llm_settings(all_settings),
        "configured": cfg is not None,
    }


@router.post("/api/llm/chat")
async def llm_chat(body: dict, user=Depends(require_auth)):
    """智能問答（非流式）。"""
    from src.core.entitlements import gate_ai_assistant

    gate_ai_assistant(user)
    message = body.get("message") or body.get("query") or ""
    history = body.get("history") or body.get("messages")
    overrides = body.get("llm_config") if isinstance(body.get("llm_config"), dict) else None
    user_settings = _user_settings_dict(user)

    result = run_chat(
        message,
        history=history,
        request_overrides=overrides,
        user_settings=user_settings,
    )
    if not result.get("success"):
        if not result.get("configured"):
            raise HTTPException(503, result.get("error") or "LLM 未配置")
        raise HTTPException(400, result.get("error") or "問答失敗")
    return {"success": True, **result}


def _sse_encode(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/api/llm/chat/stream")
async def llm_chat_stream(body: dict, user=Depends(require_auth)):
    """智能問答（SSE 流式：status / tool_* / token / done）。"""
    from src.core.entitlements import gate_ai_assistant

    gate_ai_assistant(user)
    message = body.get("message") or body.get("query") or ""
    history = body.get("history") or body.get("messages")
    overrides = body.get("llm_config") if isinstance(body.get("llm_config"), dict) else None
    user_settings = _user_settings_dict(user)

    def event_gen():
        try:
            for ev in stream_chat_events(
                message,
                history=history,
                request_overrides=overrides,
                user_settings=user_settings,
            ):
                yield _sse_encode(ev)
        except Exception as e:
            yield _sse_encode({"type": "error", "message": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
