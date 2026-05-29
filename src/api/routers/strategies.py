"""strategies 路由（P5 從 app.py 拆分）。"""
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.core.auth import require_auth, require_admin, get_current_user
from src.models.user import User
from src.utils.logger import logger

router = APIRouter()


@router.post("/api/strategies/create")
async def create_strategy(body: dict):
    """從模板創建用戶策略"""
    from src.core.strategy_base import create_strategy_template

    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "請提供策略名稱")

    filepath = body.get("filepath")
    try:
        result_path = create_strategy_template(name, filepath)
        return {"success": True, "filepath": result_path, "name": name}
    except Exception as e:
        logger.error(f"創建策略模板失敗: {e}")
        raise HTTPException(500, str(e))




@router.get("/api/strategies/list")
async def list_strategies_api(user=Depends(get_current_user)):
    """列出所有策略（內置 + 用戶）"""
    from src.core.api_cache import cached_response
    from src.core.backtest import STRATEGIES, STRATEGY_NAMES
    from src.core.strategy_base import list_user_strategies
    from src.core.admin_controls import is_allowed

    if not is_allowed("strategies", "list", user=user):
        raise HTTPException(403, "策略庫已被管理員關閉（僅管理員可用）")

    def _build():
        # 內置策略
        builtin = []
        controls = None
        try:
            from src.core.admin_controls import get_controls
            controls = (get_controls().get("scopes") or {}).get("strategies") or {}
        except Exception:
            controls = {}
        for name, cls in STRATEGIES.items():
            if controls and controls.get("builtin_enabled") is False:
                continue
            if controls and not is_allowed("strategies", None, user=user, name=name):
                continue
            display = STRATEGY_NAMES.get(name, name)
            desc = (cls.__doc__ or "").strip().split("\n")[0]
            builtin.append({
                "name": name,
                "display_name": display,
                "source": "builtin",
                "description": f"{display} — {desc}" if desc else display,
                "params": {},
            })

        user_strategies = list_user_strategies()
        user_list = []
        for s in user_strategies:
            if controls and controls.get("user_enabled") is False:
                continue
            if controls and not is_allowed("strategies", None, user=user, name=s.get("name")):
                continue
            user_list.append({
                "name": s["name"],
                "source": "user",
                "description": s["description"],
                "params": s["params"],
                "filepath": s.get("filepath", ""),
            })

        return {
            "builtin": builtin,
            "user": user_list,
            "total": len(builtin) + len(user_list),
        }

    return cached_response("api:strategies:list", ttl=120, builder=_build)




@router.get("/api/strategies/likes")
async def strategy_likes_state_api(user=Depends(get_current_user)):
    """策略點讚：全站計數；登入用戶另返回已點讚列表。"""
    from src.core.admin_controls import is_allowed
    from src.core.strategy_likes import get_like_counts, get_user_liked_keys

    if not is_allowed("strategies", "list", user=user):
        raise HTTPException(403, "策略庫已被管理員關閉")

    counts = get_like_counts()
    mine: list[str] = []
    if user:
        mine = get_user_liked_keys(user.id)
    return {"success": True, "counts": counts, "mine": mine}




@router.post("/api/strategies/likes/toggle")
async def strategy_likes_toggle_api(body: dict, user=Depends(require_auth)):
    """切換當前用戶對某策略的點讚。"""
    from src.core.admin_controls import is_allowed
    from src.core.strategy_likes import normalize_strategy_key, toggle_like

    if not is_allowed("strategies", "list", user=user):
        raise HTTPException(403, "策略庫已被管理員關閉")

    raw_key = body.get("key") or body.get("strategy_key") or ""
    try:
        key = normalize_strategy_key(str(raw_key))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    try:
        result = toggle_like(user.id, key)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"點讚失敗: {e}") from e

    return {"success": True, **result}




@router.post("/api/strategies/upload")
async def upload_strategy(file: UploadFile = File(...)):
    """上傳用戶策略 .py 文件（AST 白名單沙箱，寫入前校驗）"""
    from src.config import settings
    from src.core.strategy_base import load_user_strategy
    from src.core.strategy_sandbox import (
        sanitize_strategy_filename,
        validate_strategy_source,
    )

    if not settings.allow_strategy_upload:
        raise HTTPException(403, "管理員已禁用自定義策略上傳（SQ_ALLOW_STRATEGY_UPLOAD=false）")

    safe_name = sanitize_strategy_filename(file.filename or "")
    if not safe_name:
        raise HTTPException(400, "檔名僅允許字母數字與底線，且須為 .py（例: my_ma_strategy.py）")

    raw = await file.read(settings.strategy_upload_max_bytes + 1)
    if len(raw) > settings.strategy_upload_max_bytes:
        raise HTTPException(400, f"策略檔案超過 {settings.strategy_upload_max_bytes} bytes 上限")

    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "策略檔案必須為 UTF-8 編碼")

    check = validate_strategy_source(source, max_bytes=settings.strategy_upload_max_bytes)
    if not check.ok:
        raise HTTPException(400, f"策略安全校驗失敗: {check.error}")

    strategies_dir = Path(__file__).parent.parent.parent / "strategies"
    strategies_dir.mkdir(exist_ok=True)
    dest = (strategies_dir / safe_name).resolve()
    if strategies_dir.resolve() not in dest.parents:
        raise HTTPException(400, "非法路徑")

    try:
        dest.write_text(source, encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"文件保存失敗: {e}")

    strategy_classes = load_user_strategy(str(dest), source=source)
    if not strategy_classes:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            400,
            "文件中未找到有效的 UserStrategy 子類，或未通過安全校驗",
        )

    names = [getattr(s, "name", s.__name__) for s in strategy_classes]
    return {
        "success": True,
        "filename": safe_name,
        "filepath": str(dest),
        "strategies": names,
        "count": len(strategy_classes),
    }




@router.get("/api/strategies/leaderboard")
async def get_leaderboard_api(sort_by: str = "sharpe", limit: int = 50):
    """獲取策略排行榜"""
    from src.core.leaderboard import get_leaderboard, get_leaderboard_summary

    try:
        results = get_leaderboard(sort_by=sort_by, limit=limit)
        summary = get_leaderboard_summary()
        return {
            "success": True,
            "results": results,
            "summary": summary,
            "total": len(results),
            "empty": len(results) == 0,
            "hint": (
                "排行榜暫無數據，請先 POST /api/strategies/leaderboard/update 生成排名"
                if len(results) == 0 else None
            ),
        }
    except Exception as e:
        logger.error(f"獲取排行榜失敗: {e}", exc_info=True)
        raise HTTPException(500, str(e))




@router.post("/api/strategies/leaderboard/update")
async def update_leaderboard_api(codes: list[str] = None):
    """更新策略排行榜"""
    from src.core.leaderboard import update_leaderboard

    try:
        results = update_leaderboard(codes=codes)
        return {
            "success": True,
            "total": len(results),
            "message": f"排行榜已更新，共 {len(results)} 條記錄",
        }
    except Exception as e:
        logger.error(f"更新排行榜失敗: {e}")
        raise HTTPException(500, str(e))




@router.post("/api/strategies/test")
async def test_user_strategy(body: dict):
    """快速回測用戶策略"""
    from src.core.strategy_base import list_user_strategies, quick_backtest_user_strategy

    strategy_name = body.get("strategy_name", "").strip()
    code = body.get("code", "").strip()
    params = body.get("params", {})

    if not strategy_name or not code:
        raise HTTPException(400, "請提供 strategy_name 和 code")

    # 查找策略
    user_strategies = list_user_strategies()
    target = None
    for s in user_strategies:
        if s["name"] == strategy_name:
            target = s
            break

    if not target:
        raise HTTPException(404, f"未找到用戶策略: {strategy_name}，可用: {[s['name'] for s in user_strategies]}")

    try:
        cls = target["class"]
        instance = cls(**params)
        result = quick_backtest_user_strategy(instance, code)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"用戶策略回測失敗: {e}")
        raise HTTPException(500, str(e))


# ====== 實時行情 ======



