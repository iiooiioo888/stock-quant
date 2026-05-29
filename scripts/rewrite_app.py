"""
Rewrite app.py: remove inline routes, add router includes.
Keeps: lifespan, middleware, CORS, router registrations.
"""
SRC = "src/api/app.py"
content = open(SRC, "r", encoding="utf-8").read()
lines = content.split("\n")

# Find the first @app.xxx route (line 510 per our analysis)
first_route_line = None
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("@app.") and ("get(" in stripped or "post(" in stripped or "put(" in stripped or "delete(" in stripped):
        first_route_line = i
        break

if first_route_line is None:
    print("ERROR: No @app.xxx routes found")
    exit(1)

print(f"First inline route at line {first_route_line + 1}")

# Keep everything up to the first route
before_routes = lines[:first_route_line - 3]  # -3 to remove section comment

# Find where static pages end (last @app.xxx for /, /app, /admin etc)
last_static_line = None
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("@app.") and ("get(" in stripped or "post(" in stripped):
        last_static_line = i

# Find the _builtin_dashboard function (keep it)
builtin_start = None
for i, line in enumerate(lines):
    if "def _builtin_dashboard" in line:
        builtin_start = i
        break

# Build new app.py
new_lines = []
new_lines.extend(before_routes)

# Add new router imports and includes
new_lines.append("")
new_lines.append("# ============================================================")
new_lines.append("# P5: 路由拆分 — 從 app.py 提取的領域路由")
new_lines.append("# ============================================================")
new_lines.append("from src.api.routers.portfolio import router as portfolio_router")
new_lines.append("from src.api.routers.management import router as management_router")
new_lines.append("from src.api.routers.signals_heatmap import router as signals_heatmap_router")
new_lines.append("from src.api.routers.risk import router as risk_router")
new_lines.append("from src.api.routers.report_backtest import router as report_backtest_router")
new_lines.append("from src.api.routers.paper import router as paper_router")
new_lines.append("from src.api.routers.data_ops import router as data_ops_router")
new_lines.append("from src.api.routers.strategies import router as strategies_router")
new_lines.append("from src.api.routers.static_pages import router as static_pages_router")
new_lines.append("")
new_lines.append("app.include_router(portfolio_router)")
new_lines.append("app.include_router(management_router)")
new_lines.append("app.include_router(signals_heatmap_router)")
new_lines.append("app.include_router(risk_router)")
new_lines.append("app.include_router(report_backtest_router)")
new_lines.append("app.include_router(paper_router)")
new_lines.append("app.include_router(data_ops_router)")
new_lines.append("app.include_router(strategies_router)")
new_lines.append("app.include_router(static_pages_router)")
new_lines.append("")

# Keep the _builtin_dashboard function if it exists
if builtin_start is not None:
    new_lines.append("")
    # Read from builtin_start to end
    for i in range(builtin_start, len(lines)):
        new_lines.append(lines[i])

new_content = "\n".join(new_lines)
print(f"New app.py: {len(new_lines)} lines (was {len(lines)})")

# Write
with open(SRC, "w", encoding="utf-8") as f:
    f.write(new_content)
print("✅ app.py rewritten")