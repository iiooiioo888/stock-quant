"""
OpenAI 兼容 Chat Completions 客戶端（同步 + 流式）。
"""
from __future__ import annotations

import json
from typing import Any, Generator, Optional

import requests

from src.integrations.llm.config_resolver import LlmRuntimeConfig  # noqa: F401 — re-export for tests
from src.utils.logger import logger


class LlmNotConfiguredError(RuntimeError):
    pass


def chat_completions(
    cfg: LlmRuntimeConfig,
    messages: list[dict],
    *,
    tools: Optional[list[dict]] = None,
    tool_choice: str | dict = "auto",
    stream: bool = False,
) -> dict | Generator[str, None, None]:
    url = f"{cfg.api_base}/chat/completions"
    body: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "stream": stream,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice

    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }

    if not stream:
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=cfg.timeout_sec)
        except requests.RequestException as e:
            logger.warning(f"LLM 請求失敗: {e}")
            raise RuntimeError(f"LLM 連線失敗: {e}") from e
        if resp.status_code >= 400:
            raise RuntimeError(_parse_error(resp))
        return resp.json()

    return _stream_sse(url, headers, body, cfg.timeout_sec)


def _parse_error(resp: requests.Response) -> str:
    detail = resp.text[:500]
    try:
        j = resp.json()
        detail = j.get("error", {}).get("message") or j.get("detail") or detail
    except Exception:
        pass
    return f"LLM API 錯誤 ({resp.status_code}): {detail}"


def _stream_sse(url: str, headers: dict, body: dict, timeout: int) -> Generator[str, None, None]:
    """Yield content delta strings from OpenAI-compatible SSE."""
    try:
        resp = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=timeout,
            stream=True,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"LLM 連線失敗: {e}") from e

    if resp.status_code >= 400:
        raise RuntimeError(_parse_error(resp))

    for raw_line in resp.iter_lines(decode_unicode=True):
        if not raw_line or not raw_line.startswith("data:"):
            continue
        payload = raw_line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if content:
            yield content
