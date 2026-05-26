"""
LLM Agent — 工具調用 + 可選流式輸出（SSE 事件）。
"""
from __future__ import annotations

import json
from typing import Any, Generator, Optional

from src.integrations.llm.client import chat_completions
from src.integrations.llm.config_resolver import LlmRuntimeConfig, resolve_llm_config
from src.integrations.llm.tools_bridge import execute_tool, tools_for_llm

SYSTEM_PROMPT = """你是 StockQ 量化平台的數據助手，服務於 A 股投資研究。

規則：
1. 回答必須基於工具返回的數據；沒有數據時說明並建議用戶補充代碼或先下載 K 線。
2. 使用繁體中文，數字保留合理小數；百分比說清楚是收益還是回撤。
3. 北向資金指滬深港通淨流入，與地產機構資本報告不是同一概念。
4. 不要編造股價、財報或回測結果；需要時調用工具。
5. 整合多個工具結果時，用簡潔條列或短表格說明。
6. 回測：用 sq_run_backtest 提交任務，若返回 async=true，告知 task_id 並用 sq_get_task 查進度；完成後解讀 result_preview。"""


def _normalize_history(history: list | None) -> list[dict]:
    if not history:
        return []
    out = []
    for item in history[-20:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and content is not None:
            out.append({"role": role, "content": str(content)[:4000]})
    return out


def _run_tool_round(
    messages: list[dict],
    tools: list[dict],
    cfg: LlmRuntimeConfig,
    tool_log: list[dict],
    round_i: int,
) -> tuple[Optional[str], bool]:
    """
    執行一輪 LLM（可能含工具）。
    返回 (final_answer, had_tool_calls)。
    """
    data = chat_completions(cfg, messages, tools=tools, tool_choice="auto", stream=False)
    if not isinstance(data, dict):
        return None, False

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = message.get("tool_calls") or []

    if tool_calls:
        messages.append({
            "role": "assistant",
            "content": message.get("content"),
            "tool_calls": tool_calls,
        })
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except Exception:
                args = {}
            if not isinstance(args, dict):
                args = {}

            result = execute_tool(name, args)
            tool_log.append({
                "round": round_i + 1,
                "name": name,
                "arguments": args,
                "ok": result.get("ok"),
                "error": result.get("error"),
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or name,
                "content": result.get("result_text") or json.dumps(result, ensure_ascii=False),
            })
        return None, True

    answer = (message.get("content") or "").strip()
    return answer or None, False


def run_chat(
    user_message: str,
    history: list | None = None,
    *,
    request_overrides: dict | None = None,
    user_settings: dict | None = None,
) -> dict:
    cfg = resolve_llm_config(request_overrides, user_settings)
    if not cfg:
        return {
            "success": False,
            "configured": False,
            "error": "未配置 LLM：請在「設定」填寫 API Key，或設置環境變量 SQ_LLM_API_KEY",
        }

    msg = (user_message or "").strip()
    if not msg:
        return {"success": False, "configured": True, "error": "消息不能為空"}

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_normalize_history(history))
    messages.append({"role": "user", "content": msg})

    tools = tools_for_llm()
    tool_log: list[dict] = []

    for round_i in range(cfg.max_tool_rounds):
        answer, had_tools = _run_tool_round(messages, tools, cfg, tool_log, round_i)
        if had_tools:
            continue
        if answer:
            return {
                "success": True,
                "configured": True,
                "answer": answer,
                "tool_calls": tool_log,
                "rounds": round_i + 1,
                "model": cfg.model,
                "source": cfg.source,
            }

    return {
        "success": False,
        "configured": True,
        "error": "工具調用輪次已達上限，請縮小問題範圍後重試",
        "tool_calls": tool_log,
        "rounds": cfg.max_tool_rounds,
        "model": cfg.model,
        "source": cfg.source,
    }


def stream_chat_events(
    user_message: str,
    history: list | None = None,
    *,
    request_overrides: dict | None = None,
    user_settings: dict | None = None,
) -> Generator[dict, None, None]:
    """生成 SSE 事件 dict：status / tool_start / tool_end / token / done / error。"""
    cfg = resolve_llm_config(request_overrides, user_settings)
    if not cfg:
        yield {"type": "error", "message": "未配置 LLM：請在「設定」填寫 API Key"}
        return

    msg = (user_message or "").strip()
    if not msg:
        yield {"type": "error", "message": "消息不能為空"}
        return

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_normalize_history(history))
    messages.append({"role": "user", "content": msg})

    tools = tools_for_llm()
    tool_log: list[dict] = []

    yield {"type": "status", "message": "正在分析問題…", "model": cfg.model}

    for round_i in range(cfg.max_tool_rounds):
        yield {"type": "status", "message": f"第 {round_i + 1} 輪推理…"}

        data = chat_completions(cfg, messages, tools=tools, tool_choice="auto", stream=False)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls = message.get("tool_calls") or []

        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}
                if not isinstance(args, dict):
                    args = {}

                yield {"type": "tool_start", "name": name, "arguments": args}
                result = execute_tool(name, args)
                tool_log.append({
                    "round": round_i + 1,
                    "name": name,
                    "arguments": args,
                    "ok": result.get("ok"),
                    "error": result.get("error"),
                })
                yield {
                    "type": "tool_end",
                    "name": name,
                    "ok": result.get("ok"),
                    "error": result.get("error"),
                }
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "content": result.get("result_text") or json.dumps(result, ensure_ascii=False),
                })
            continue

        yield {"type": "status", "message": "正在生成回答…"}

        direct = (message.get("content") or "").strip()
        if direct:
            yield {"type": "token", "content": direct}
            yield {
                "type": "done",
                "success": True,
                "answer": direct,
                "tool_calls": tool_log,
                "rounds": round_i + 1,
                "model": cfg.model,
                "source": cfg.source,
            }
            return

        answer_parts: list[str] = []
        try:
            stream = chat_completions(cfg, messages, tools=None, stream=True)
            for token in stream:
                answer_parts.append(token)
                yield {"type": "token", "content": token}
        except Exception:
            try:
                data2 = chat_completions(cfg, messages, tools=None, stream=False)
                answer = ((data2.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                answer_parts = [answer]
                if answer:
                    yield {"type": "token", "content": answer}
            except Exception as e2:
                yield {"type": "error", "message": str(e2)}
                return

        answer = "".join(answer_parts).strip()
        if answer:
            yield {
                "type": "done",
                "success": True,
                "answer": answer,
                "tool_calls": tool_log,
                "rounds": round_i + 1,
                "model": cfg.model,
                "source": cfg.source,
            }
            return

    yield {
        "type": "error",
        "message": "工具調用輪次已達上限",
        "tool_calls": tool_log,
    }
