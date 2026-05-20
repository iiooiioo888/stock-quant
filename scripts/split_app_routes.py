# -*- coding: utf-8 -*-
"""一次性腳本：從 app.py 提取路由到 routers/"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app_path = ROOT / "src" / "api" / "app.py"
lines = app_path.read_text(encoding="utf-8").splitlines()

# STOCK_NAMES -> constants.py
start = next(i for i, l in enumerate(lines) if l.startswith("STOCK_NAMES = {"))
end = next(i for i, l in enumerate(lines[start:], start) if l.strip() == "}")
const_block = "\n".join(lines[start : end + 1])
(ROOT / "src" / "api" / "constants.py").write_text(
    '"""常用 A 股中文名映射"""\n\n' + const_block + "\n",
    encoding="utf-8",
)

# tasks router
tasks_lines = lines[1724:1799]
tasks_body = "\n".join(tasks_lines).replace("@app.", "@router.")
routers = ROOT / "src" / "api" / "routers"
routers.mkdir(exist_ok=True)
(routers / "__init__.py").write_text('"""API 路由模塊"""\n', encoding="utf-8")
(routers / "tasks.py").write_text(
    '"""任務管理 API 路由"""\nfrom fastapi import APIRouter, HTTPException\n\n'
    "router = APIRouter(tags=[\"tasks\"])\n\n"
    + tasks_body
    + "\n",
    encoding="utf-8",
)

# health router (725-833)
health_lines = lines[724:833]
health_body = "\n".join(health_lines).replace("@app.", "@router.")
health_body = health_body.replace("_start_time", "state.start_time")
(routers / "health.py").write_text(
    '"""健康檢查 API 路由"""\nimport time\nimport shutil\n\n'
    "from fastapi import APIRouter\n\n"
    "from src.config import settings\n"
    "from src.core.db import get_db_stats\n"
    "from src.api import state\n\n"
    "router = APIRouter(tags=[\"health\"])\n\n"
    + health_body
    + "\n",
    encoding="utf-8",
)

print("Extracted constants.py, routers/tasks.py, routers/health.py")
