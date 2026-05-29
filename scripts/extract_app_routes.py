"""Extract inline routes from app.py into router files."""
import re

SRC = "src/api/app.py"
content = open(SRC, "r", encoding="utf-8").read()
lines = content.split("\n")

route_pattern = re.compile(r'^@app\.(get|post|put|delete)\(')
routes = []
for i, line in enumerate(lines):
    m = route_pattern.match(line.strip())
    if m:
        routes.append((i, m.group(1), line.strip()))

print(f"Found {len(routes)} inline routes")

for idx, (line_no, method, decorator) in enumerate(routes):
    path = ""
    m = re.search(r'"([^"]+)"', decorator)
    if m:
        path = m.group(1)
    print(f"  L{line_no+1}: {method.upper()} {path}")