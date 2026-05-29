"""
P5: Split inline routes from app.py into router files.

Extracts 98 inline @app.xxx routes grouped by domain,
creates router files, and rewrites app.py to use them.
"""
import re, os

SRC = "src/api/app.py"
DST_DIR = "src/api/routers"

content = open(SRC, "r", encoding="utf-8").read()
lines = content.split("\n")

# ── Step 1: Parse all route blocks ──
route_re = re.compile(r'^@app\.(get|post|put|delete)\((.+?)\)(\s*#.*)?$')

def get_path_from_decorator(line):
    m = re.search(r'"([^"]+)"', line)
    return m.group(1) if m else ""

def extract_block(start_idx):
    """Extract a route block: decorator(s) + async def + function body."""
    # Back up to include decorators and comments before @app
    idx = start_idx
    # Get the decorator line
    dec_line = lines[idx].rstrip()
    # Find the async def line
    def_idx = idx + 1
    while def_idx < len(lines) and not lines[def_idx].strip().startswith("async def"):
        def_idx += 1
    
    if def_idx >= len(lines):
        return None, start_idx + 1
    
    # Find end of function body (next @app, next top-level def/class, or section separator)
    body_start = def_idx + 1
    # Indent level of function body
    body_indent = len(lines[body_start]) - len(lines[body_start].lstrip()) if body_start < len(lines) else 0
    
    end_idx = def_idx + 1
    while end_idx < len(lines):
        line = lines[end_idx].rstrip()
        stripped = line.strip()
        if not stripped:
            end_idx += 1
            continue
        # Check if we hit a new top-level construct
        current_indent = len(line) - len(line.lstrip())
        if current_indent == 0 and (stripped.startswith("@") or stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("# =====")):
            break
        # Check for next section comment
        if stripped.startswith("# ======") and current_indent == 0:
            break
        end_idx += 1
    
    # Include blank lines after
    while end_idx < len(lines) and not lines[end_idx].strip():
        end_idx += 1
    
    block = "\n".join(lines[start_idx:end_idx])
    return block, end_idx

# ── Step 2: Group routes ──
groups = {
    "portfolio": {"paths": [], "blocks": [], "help_fn": {}},
    "management": {"paths": [], "blocks": []},
    "signals_heatmap": {"paths": [], "blocks": [], "help_fn": {}},
    "risk": {"paths": [], "blocks": []},
    "report_backtest": {"paths": [], "blocks": []},
    "paper": {"paths": [], "blocks": []},
    "data_ops": {"paths": [], "blocks": []},
    "strategies": {"paths": [], "blocks": [], "help_fn": {}},
    "static_pages": {"paths": [], "blocks": []},
}

# Find all @app.xxx lines and their positions
route_starts = []
for i, line in enumerate(lines):
    stripped = line.strip()
    if route_re.match(stripped):
        path = get_path_from_decorator(stripped)
        route_starts.append((i, path))

# Classify each route
for idx, (line_no, path) in enumerate(route_starts):
    # Determine group
    if path.startswith("/api/portfolio/"):
        group = "portfolio"
    elif path.startswith("/api/scheduler") or path.startswith("/api/cache") or path.startswith("/api/config") or path.startswith("/api/notify") or path.startswith("/api/data-sources") or path.startswith("/api/status"):
        group = "management"
    elif path.startswith("/api/signals/") or path.startswith("/api/heatmap"):
        group = "signals_heatmap"
    elif path.startswith("/api/risk/") or path.startswith("/api/risk-pipeline"):
        group = "risk"
    elif path.startswith("/api/report/") or path in ("/api/backtest/trade-analysis", "/api/backtest/monte-carlo", "/api/backtest/rolling-metrics"):
        group = "report_backtest"
    elif path.startswith("/api/paper/"):
        group = "paper"
    elif path.startswith("/api/data-quality/") or path.startswith("/api/export/") or path.startswith("/api/screener/") or path.startswith("/api/benchmark") or path.startswith("/api/realtime"):
        group = "data_ops"
    elif path.startswith("/api/strategies/"):
        group = "strategies"
    elif path.startswith("/static/") or path.startswith("/favicon") or path.startswith("/manual") or path in ("/", "/app", "/admin", "/panel", "/legacy/", "/legacy"):
        group = "static_pages"
    else:
        continue
    
    groups[group]["paths"].append(path)
    # Store line range
    next_start = route_starts[idx + 1][0] if idx + 1 < len(route_starts) else len(lines)
    groups[group]["blocks"].append((line_no, next_start))

# Print summary
for gname, gdata in groups.items():
    print(f"{gname}: {len(gdata['paths'])} routes")
    for p in gdata["paths"]:
        print(f"  {p}")

# ── Step 3: Build router files ──
def build_router_file(group_name, route_blocks, lines_src, extra_imports="", help_fns_before=""):
    """Build a router file from extracted route blocks."""
    header = f'"""{group_name} 路由（P5 從 app.py 拆分）。"""\n'
    header += "import json\nimport time\nfrom pathlib import Path\n\n"
    header += "from fastapi import APIRouter, Depends, HTTPException, Query, Request\n"
    header += "from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse\n"
    header += "from fastapi.staticfiles import StaticFiles\n\n"
    header += "from src.config import settings\n"
    header += "from src.core.auth import require_auth, require_admin, get_current_user\n"
    header += "from src.models.user import User\n"
    header += "from src.utils.logger import logger\n\n"
    if extra_imports:
        header += extra_imports + "\n\n"
    header += 'router = APIRouter()\n\n\n'
    
    body = ""
    for start, end in route_blocks:
        block = "\n".join(lines_src[start:end])
        # Convert @app.xxx to @router.xxx
        block = block.replace("@app.get(", "@router.get(")
        block = block.replace("@app.post(", "@router.post(")
        block = block.replace("@app.put(", "@router.put(")
        block = block.replace("@app.delete(", "@router.delete(")
        body += block + "\n\n\n"
    
    return header + body

# Write router files
for gname, gdata in groups.items():
    if not gdata["blocks"]:
        continue
    
    router_content = build_router_file(gname, gdata["blocks"], lines)
    filepath = os.path.join(DST_DIR, f"{gname}.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(router_content)
    print(f"\n✅ Created {filepath} ({len(gdata['blocks'])} routes)")

# ── Step 4: Build new app.py ──
# Find the range of inline routes (from first @app.xxx to last)
if route_starts:
    first_route = route_starts[0][0]
    last_route_end = len(lines)
    # The last route we're extracting (everything except static pages)
    extracted_ranges = set()
    for gname, gdata in groups.items():
        if gname == "static_pages":
            continue
        for start, end in gdata["blocks"]:
            for i in range(start, end):
                extracted_ranges.add(i)
    
    # Find section comments above routes to remove
    # (lines like "# ====== xxx ======")
    
    print(f"\nFirst inline route at line {first_route+1}")
    print(f"Extracted {len(extracted_ranges)} lines to router files")

print("\n=== Router files created ===")
for gname, gdata in groups.items():
    if gdata["blocks"]:
        print(f"  {gname}.py: {len(gdata['blocks'])} routes")