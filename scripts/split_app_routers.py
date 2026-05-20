"""一次性腳本：從 app.py 提取區段到 routers"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "src/api/app.py"
lines = APP.read_text(encoding="utf-8").splitlines()

HEADER = '''"""{title}"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Request
from src.config import settings
from src.core.auth import require_auth, require_admin
from src.core.db import get_conn
from src.utils.logger import logger
from src.api.constants import STOCK_NAMES
from src.api.dispatch import dispatch_async_task

router = APIRouter()

'''


def write_router(name: str, title: str, ranges: list[tuple[int, int]]):
    parts = []
    for start, end in ranges:
        chunk = lines[start - 1 : end - 1]
        parts.append("\n".join(chunk))
    text = "\n\n".join(parts).replace("@app.", "@router.")
    text = text.replace("_dispatch_async_task", "dispatch_async_task")
    out = ROOT / f"src/api/routers/{name}.py"
    out.write_text(HEADER.format(title=title) + text, encoding="utf-8")
    print(f"wrote {out.name}: {text.count(chr(10))} lines")


write_router("auth", "認證與用戶", [(375, 674)])
write_router("stocks", "股票與市場", [(697, 1061)])
write_router("alerts", "預警", [(1335, 1455)])
write_router("backtest", "回測與優化", [(1103, 1334), (1457, 1551)])
write_router("data_center", "數據中心", [(2908, 3148)])
