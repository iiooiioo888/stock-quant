# -*- coding: utf-8 -*-
"""從 app.py 移除已提取模塊並接入 routers"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "src" / "api" / "app.py"
lines = path.read_text(encoding="utf-8").splitlines()

# 移除 STOCK_NAMES 塊 (28-87, 1-based -> index 27-86)
del lines[27:87]

# 在 logger import 後插入 imports
insert_at = 22
imports = [
    "from src.api.constants import STOCK_NAMES",
    "from src.api.demo import seed_demo_data",
    "from src.api import state",
    "from src.api.routers.health import router as health_router",
    "from src.api.routers.tasks import router as tasks_router",
]
for i, imp in enumerate(imports):
    lines.insert(insert_at + i, imp)

# 移除 _start_time 行
lines = [l for l in lines if l.strip() != "_start_time = time.time()"]

# 移除 _seed_demo_data 整個函數 (find def _seed_demo_data)
start = next(i for i, l in enumerate(lines) if l.startswith("def _seed_demo_data"))
end = next(i for i, l in enumerate(lines[start:], start) if l.startswith("@asynccontextmanager"))
del lines[start:end]

# lifespan: replace _seed_demo_data with seed_demo_data
text = "\n".join(lines)
text = text.replace("_seed_demo_data()", "seed_demo_data()")

lines = text.splitlines()

# 移除 health 路由 (search @app.get("/api/health"))
h_start = next(i for i, l in enumerate(lines) if '@app.get("/api/health")' in l)
h_end = next(i for i, l in enumerate(lines[h_start:], h_start) if lines[i].startswith("@app.get(\"/api/data-sources\")"))
del lines[h_start:h_end]

# 移除 tasks 路由
t_start = next(i for i, l in enumerate(lines) if l.strip() == "# ====== 任務管理 ======")
t_end = next(i for i, l in enumerate(lines[t_start:], t_start) if lines[i].strip() == "# ====== 配置 ======")
del lines[t_start:t_end]

# 移除 WebSocket 區塊
ws_start = next(i for i, l in enumerate(lines) if l.strip() == "# ====== WebSocket 實時推送 ======")
ws_end = next(i for i, l in enumerate(lines[ws_start:], ws_start) if lines[i].strip() == "# ====== 風險管理 API ======")
del lines[ws_start:ws_end]

# 在 app = FastAPI 後添加 include_router
app_idx = next(i for i, l in enumerate(lines) if l.startswith("app = FastAPI"))
insert_router = [
    "",
    "app.include_router(health_router)",
    "app.include_router(tasks_router)",
    "",
    "from src.api.ws import router as ws_router, manager, ws_realtime_push",
    "app.include_router(ws_router)",
]
for i, row in enumerate(insert_router):
    lines.insert(app_idx + 1 + i, row)

# lifespan: _ws_realtime_push -> ws_realtime_push
text = "\n".join(lines)
text = text.replace("_ws_realtime_push()", "ws_realtime_push()")
text = text.replace("time.time() - _start_time", "time.time() - state.start_time")

path.write_text(text + "\n", encoding="utf-8")
print("patched app.py")
