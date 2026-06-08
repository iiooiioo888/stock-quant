"""
HTTP 探活 GET /api/health/sop — 與 CLI ops probe / scripts/probe_health_sop_url 共用。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from src.core.ops_health import VERDICT_CRITICAL, exit_code_for_verdict

DEFAULT_SOP_URL = "http://127.0.0.1:8000/api/health/sop"


def fetch_sop(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("response is not a JSON object")
    return data


def probe_sop_url(
    url: str = DEFAULT_SOP_URL,
    *,
    timeout: float = 10.0,
    ci_mode: bool = False,
) -> tuple[dict, int]:
    """
    請求 SOP 端點並回傳 (摘要 dict, exit_code)。
    失敗時摘要含 error，exit_code 為 2。
    """
    try:
        data = fetch_sop(url, timeout)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        ValueError,
    ) as e:
        return {
            "ok": False,
            "error": str(e),
            "url": url,
            "verdict": VERDICT_CRITICAL,
        }, 2

    sop = data.get("sop") if isinstance(data.get("sop"), dict) else {}
    verdict = str(sop.get("verdict") or VERDICT_CRITICAL)
    code = exit_code_for_verdict(verdict, ci_mode=ci_mode)
    summary = {
        "ok": True,
        "url": url,
        "status": data.get("status"),
        "checked_at": data.get("checked_at"),
        "verdict": verdict,
        "verdict_zh": sop.get("verdict_zh"),
        "exit_code": code,
        "index_audit": data.get("index_audit"),
        "data_sources": data.get("data_sources"),
    }
    return summary, code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe /api/health/sop over HTTP")
    parser.add_argument("--url", default=DEFAULT_SOP_URL, help="SOP health endpoint")
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="HTTP timeout seconds"
    )
    parser.add_argument(
        "--ci", action="store_true", help="Only critical fails (exit 2)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Print JSON summary to stdout"
    )
    args = parser.parse_args(argv)

    summary, code = probe_sop_url(args.url, timeout=args.timeout, ci_mode=args.ci)
    if not summary.get("ok"):
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"probe failed: {summary.get('error')}", file=sys.stderr)
        return code

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        zh = summary.get("verdict_zh") or summary.get("verdict")
        print(f"{zh} ({summary.get('verdict')}) exit={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
