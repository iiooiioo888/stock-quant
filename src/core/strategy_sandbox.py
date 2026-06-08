"""
用戶策略上傳沙箱 — AST 白名單 + 危險語法攔截

上傳的 .py 在寫入磁碟或 exec_module 之前必須通過本模組校驗。
無法做到完整沙箱（import 時仍會執行模組頂層代碼），因此採：
  - 導入白名單（僅允許量化常用庫 + strategy_base）
  - 禁止危險內建與雙下劃線屬性鏈
  - 檔案大小 / 語法節點數上限
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

# 允許 import 的頂層模組（其餘一律拒絕）
ALLOWED_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "math",
        "statistics",
        "fractions",
        "decimal",
        "typing",
        "collections",
        "numpy",
        "pandas",
        "backtrader",
        "src",
    }
)

# 仍保留黑名單，防止白名單子模組被濫用（如 src.os 不存在但防禦性）
BLOCKED_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "socket",
        "http",
        "https",
        "ftplib",
        "smtplib",
        "ctypes",
        "importlib",
        "code",
        "codeop",
        "pickle",
        "shelve",
        "dbm",
        "sqlite3",
        "multiprocessing",
        "threading",
        "signal",
        "mmap",
        "pathlib",
        "builtins",
        "pty",
        "tty",
        "fcntl",
        "resource",
        "tempfile",
        "webbrowser",
        "urllib",
        "requests",
        "paramiko",
        "fabric",
        "asyncio",
    }
)

# src 下僅允許此子路徑
ALLOWED_SRC_SUBMODULES: frozenset[str] = frozenset(
    {
        "src.core.strategy_base",
    }
)

FORBIDDEN_CALL_NAMES: frozenset[str] = frozenset(
    {
        "open",
        "eval",
        "exec",
        "compile",
        "compile_command",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "dir",
        "input",
        "breakpoint",
        "help",
        "memoryview",
        "super",  # super 在策略中不必要，且常被濫用於逃逸
    }
)

ALLOWED_DUNDER_ATTRS: frozenset[str] = frozenset(
    {
        "__init__",
        "__name__",
        "__doc__",
        "__str__",
        "__repr__",
    }
)

MAX_SOURCE_BYTES = 65_536
MAX_AST_NODES = 8_000
SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}\.py$")


@dataclass(frozen=True)
class StrategyValidationResult:
    ok: bool
    error: str = ""


def sanitize_strategy_filename(filename: str) -> str | None:
    """僅允許安全檔名，禁止路徑穿越。"""
    if not filename or "/" in filename or "\\" in filename:
        return None
    base = filename
    if base in (".", "..") or ".." in base:
        return None
    if not SAFE_FILENAME_RE.match(base):
        return None
    if base.startswith("_"):
        return None
    return base


def _import_root(module: str | None) -> str:
    if not module:
        return ""
    return module.split(".")[0]


def _is_allowed_import(module: str | None) -> bool:
    if not module:
        return False
    root = _import_root(module)
    if root in BLOCKED_IMPORT_ROOTS:
        return False
    if root == "src":
        return module in ALLOWED_SRC_SUBMODULES or module.startswith(
            "src.core.strategy_base"
        )
    return root in ALLOWED_IMPORT_ROOTS


def validate_strategy_source(
    source: str, *, max_bytes: int = MAX_SOURCE_BYTES
) -> StrategyValidationResult:
    """校驗策略源碼；通過後方可寫入磁碟或動態載入。"""
    if not isinstance(source, str):
        return StrategyValidationResult(False, "源碼必須為字串")

    encoded = source.encode("utf-8")
    if len(encoded) > max_bytes:
        return StrategyValidationResult(
            False, f"策略檔案超過大小上限 ({max_bytes} bytes)"
        )

    if "\x00" in source:
        return StrategyValidationResult(False, "源碼包含非法字元")

    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as e:
        return StrategyValidationResult(False, f"語法錯誤: {e}")

    node_count = 0
    for node in ast.walk(tree):
        node_count += 1
        if node_count > MAX_AST_NODES:
            return StrategyValidationResult(False, "策略過於複雜（AST 節點過多）")

        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if not _is_allowed_import(mod):
                    return StrategyValidationResult(False, f"禁止導入模組: {mod}")

        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                return StrategyValidationResult(False, "禁止相對導入")
            if any(getattr(a, "name", None) == "*" for a in node.names):
                return StrategyValidationResult(False, "禁止 from ... import *")
            mod = node.module
            if not _is_allowed_import(mod):
                return StrategyValidationResult(False, f"禁止導入模組: {mod}")

        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALL_NAMES:
                return StrategyValidationResult(False, f"禁止調用: {func.id}()")
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALL_NAMES:
                return StrategyValidationResult(False, f"禁止調用: {func.attr}()")

        elif isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__") and attr not in ALLOWED_DUNDER_ATTRS:
                return StrategyValidationResult(False, f"禁止訪問屬性: {attr}")
            if attr in (
                "__import__",
                "__builtins__",
                "__globals__",
                "__code__",
                "__subclasses__",
                "__bases__",
                "__mro__",
                "__dict__",
                "gi_frame",
                "f_globals",
                "f_locals",
            ):
                return StrategyValidationResult(False, f"禁止訪問屬性: {attr}")

        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id in (
                "__builtins__",
                "__globals__",
            ):
                return StrategyValidationResult(
                    False, "禁止訪問 __builtins__ / __globals__"
                )

        elif isinstance(node, ast.Global):
            if any(name.startswith("__") for name in node.names):
                return StrategyValidationResult(False, "禁止 global 雙下劃線名稱")

    # 必須定義至少一個 UserStrategy 子類（靜態檢查類名繼承較難，檢查是否引用 UserStrategy）
    if "UserStrategy" not in source:
        return StrategyValidationResult(
            False,
            "策略須繼承 UserStrategy（from src.core.strategy_base import UserStrategy）",
        )

    return StrategyValidationResult(True)


def validate_strategy_file(
    filepath: str, *, max_bytes: int = MAX_SOURCE_BYTES
) -> StrategyValidationResult:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read(max_bytes + 1)
    except OSError as e:
        return StrategyValidationResult(False, f"無法讀取檔案: {e}")
    if len(source.encode("utf-8")) > max_bytes:
        return StrategyValidationResult(
            False, f"策略檔案超過大小上限 ({max_bytes} bytes)"
        )
    return validate_strategy_source(source, max_bytes=max_bytes)
