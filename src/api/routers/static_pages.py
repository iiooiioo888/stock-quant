"""static_pages 路由（P5 從 app.py 拆分）。"""
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.core.auth import require_auth, require_admin, get_current_user
from src.models.user import User
from src.utils.logger import logger

router = APIRouter()

static_dir = Path(__file__).resolve().parents[3] / "static"


@router.get("/static/iconfont/stocks/{filename}", include_in_schema=False)
async def compat_iconfont_stock_svg_mount(
    filename: str,
    market: str = Query(""),
    name: str = Query(""),
):
    """優先於 StaticFiles：舊版 /static/iconfont/stocks/{code}.svg 改走 Logo 快取。"""
    from src.api.routers.stocks import _stock_logo_response

    if not str(filename or "").lower().endswith(".svg"):
        raise HTTPException(404, "not found")
    return _stock_logo_response(filename[:-4], market, name)




@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """避免瀏覽器預設請求 favicon.ico 404。"""
    path = static_dir / "img" / "brand.svg"
    if path.is_file():
        return FileResponse(path, media_type="image/svg+xml")
    raise HTTPException(404, "favicon not found")


def _serve_static_html(filename: str, *, fallback=None) -> HTMLResponse:
    """返回 static/ 下獨立 HTML 頁（企業首頁 / 工作台 / 管理後台）。"""
    path = static_dir / filename
    if path.exists():
        return HTMLResponse(content=path.read_text(encoding="utf-8"))
    if fallback:
        return HTMLResponse(content=fallback())
    raise HTTPException(404, f"{filename} not found")




@router.get("/manual", response_class=HTMLResponse)
async def user_manual():
    """使用手冊（docs/manual/README.md）。"""
    import html as html_module

    root = Path(__file__).resolve().parents[3]
    readme = root / "docs" / "manual" / "README.md"
    if not readme.is_file():
        raise HTTPException(404, "手冊尚未就緒")
    body = html_module.escape(readme.read_text(encoding="utf-8"))
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8"/>
<title>StockQ Pro 使用手冊</title>
<style>body{{font-family:system-ui,sans-serif;background:#0a0b10;color:#eeeef2;
margin:0;padding:24px 32px;line-height:1.6}} a{{color:#e8b830}}
pre{{white-space:pre-wrap;font-size:.9rem}}</style></head>
<body><p><a href="/app">← 工作台</a> · <a href="/">產品介紹</a></p>
<pre>{body}</pre></body></html>"""
    )




@router.get("/", response_class=HTMLResponse)
async def site_home():
    """產品介紹首頁（功能介紹、三入口導航）。"""
    return _serve_static_html("home.html", fallback=_builtin_dashboard)




@router.get("/app", response_class=HTMLResponse)
async def app_workbench():
    """量化交易工作台（原 SPA 主界面）。"""
    return _serve_static_html("app.html", fallback=_builtin_dashboard)




@router.get("/admin", response_class=HTMLResponse)
async def admin_console():
    """管理員後台。"""
    return _serve_static_html("admin.html")




@router.get("/panel", response_class=HTMLResponse)
async def panel_alias():
    """工作台別名（與 /app 相同）。"""
    return await app_workbench()




@router.get("/legacy/", response_class=HTMLResponse)


@router.get("/legacy", response_class=HTMLResponse)
async def legacy_spa():
    """舊版完整 SPA（Legacy 工作台）。"""
    return _serve_static_html("legacy/index.html", fallback=_builtin_dashboard)


def _builtin_dashboard() -> str:
    """內建儀表盤 HTML — fallback 版（從 dashboard_fallback.py 載入）"""
    try:
        from src.api.dashboard_fallback import _builtin_dashboard as _fb_dashboard
        return _fb_dashboard()
    except ImportError:
        # 極簡 fallback：只顯示基本鏈接
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>stock-quant</title></head>
<body style="background:#0f172a;color:#e2e8f0;font-family:sans-serif;text-align:center;padding:80px">
<h1>📈 stock-quant</h1>
<p>static/index.html 未找到，使用內建 fallback。</p>
<p>請檢查 static/ 目錄是否存在。</p>
<p style="margin-top:30px"><a href="/api/health" style="color:#38bdf8">健康檢查</a> ·
<a href="/docs" style="color:#38bdf8">API 文檔</a></p>
</body></html>"""



