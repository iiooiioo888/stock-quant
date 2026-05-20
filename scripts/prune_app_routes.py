"""從 app.py 移除已遷移到 routers 的區段"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "src/api/app.py"
lines = APP.read_text(encoding="utf-8").splitlines()

# 1-indexed inclusive start, exclusive end
REMOVE = [
    (375, 674),
    (697, 1061),
    (1064, 1100),  # _dispatch_async_task
    (1103, 1334),
    (1335, 1455),
    (1457, 1551),
    (2908, 3148),
]

# convert to 0-indexed ranges, merge overlapping, sort reverse
ranges = sorted([(s - 1, e - 1) for s, e in REMOVE], reverse=True)
for start, end in ranges:
    del lines[start:end]

# insert router imports after existing router includes
insert_at = None
for i, line in enumerate(lines):
    if "from src.api.routers.dashboard_market" in line:
        insert_at = i + 1
        break

new_imports = [
    "from src.api.routers.auth import router as auth_router",
    "from src.api.routers.stocks import router as stocks_router",
    "from src.api.routers.backtest import router as backtest_router",
    "from src.api.routers.alerts import router as alerts_router",
    "from src.api.routers.data_center import router as data_center_router",
]
if insert_at:
    for j, imp in enumerate(new_imports):
        lines.insert(insert_at + j, imp)

# insert include_router after ws_router
for i, line in enumerate(lines):
    if "app.include_router(ws_router)" in line:
        includes = [
            "app.include_router(auth_router)",
            "app.include_router(stocks_router)",
            "app.include_router(backtest_router)",
            "app.include_router(alerts_router)",
            "app.include_router(data_center_router)",
        ]
        for j, inc in enumerate(includes):
            lines.insert(i + 1 + j, inc)
        break

APP.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("app.py lines:", len(lines))
