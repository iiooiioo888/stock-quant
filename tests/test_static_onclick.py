"""靜態檢查：inline onclick 引用的全域函數與 App 方法是否存在。"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def _collect_app_methods() -> set[str]:
    app_js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    methods = set(re.findall(r"\bApp\.(\w+)\s*=", app_js))
    methods |= set(re.findall(r"\bApp\.(\w+)\s*\(", app_js))
    methods |= set(re.findall(r"^\s+(\w+)\([^)]*\)\s*\{", app_js, re.MULTILINE))
    methods |= set(re.findall(r"^\s+async\s+(\w+)\([^)]*\)", app_js, re.MULTILINE))
    return methods


def _collect_global_wrappers() -> set[str]:
    app_js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    return set(re.findall(r"^function\s+(\w+)\s*\(", app_js, re.MULTILINE))


def _collect_module_globals() -> set[str]:
    names = set()
    for path in STATIC.glob("js/*.js"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"^(const|var)\s+(\w+)\s*=", text, re.MULTILINE):
            for m in re.finditer(r"^(const|var)\s+(\w+)\s*=", text, re.MULTILINE):
                names.add(m.group(2))
        if re.search(r"window\.(\w+)\s*=", text):
            for m in re.finditer(r"window\.(\w+)\s*=", text):
                names.add(m.group(1))
    return names


def _scan_onclick_handlers() -> list[tuple[str, str]]:
    refs = []
    pattern = re.compile(r'onclick\s*=\s*["\']([^"\']+)["\']')
    for path in [STATIC / "index.html", *STATIC.glob("js/*.js")]:
        text = path.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            refs.append((str(path.relative_to(ROOT)), m.group(1).strip()))
    return refs


def _resolve_call(expr: str) -> tuple[str, str] | None:
    expr = expr.split(";")[0].strip()
    if (
        expr.startswith("event.")
        or expr.startswith("if(")
        or expr.startswith("document.")
    ):
        return None
    m = re.match(r"App\.(\w+)\s*\(", expr)
    if m:
        return ("App", m.group(1))
    m = re.match(r"(\w+)\.(\w+)\s*\(", expr)
    if m:
        return (m.group(1), m.group(2))
    m = re.match(r"(\w+)\s*\(", expr)
    if m:
        return ("global", m.group(1))
    return None


class TestStaticOnclick:
    def test_no_switch_tab_reference(self):
        dashboard = (STATIC / "js" / "dashboard.js").read_text(encoding="utf-8")
        assert "switchTab" not in dashboard

    def test_scheduler_tab_exists_in_html(self):
        html = (STATIC / "app.html").read_text(encoding="utf-8")
        # 任務中心 Tab（原 scheduler 已合併到 tasks）
        assert 'data-p="tasks"' in html
        assert 'id="pg-tasks"' in html

    def test_onclick_handlers_resolve(self):
        app_methods = _collect_app_methods()
        globals_fn = _collect_global_wrappers()
        modules = _collect_module_globals()
        allowed_builtins = {"confirm", "alert", "prompt"}

        missing = []
        skip_prefixes = ("return ", "if(", "document.", "event.")
        for location, handler in _scan_onclick_handlers():
            if (
                any(handler.startswith(p) for p in skip_prefixes)
                or "preventDefault" in handler
            ):
                continue
            resolved = _resolve_call(handler)
            if not resolved:
                continue
            kind, name = resolved
            if kind == "App":
                if name not in app_methods:
                    missing.append(f"{location}: App.{name}")
            elif kind == "global":
                if name in allowed_builtins:
                    continue
                if name not in globals_fn and name not in modules:
                    missing.append(f"{location}: {name}()")
            else:
                mod = kind
                if mod not in modules:
                    missing.append(f"{location}: {mod}.{name}")

        assert not missing, "未定義的 onclick 處理函數:\n" + "\n".join(missing)
