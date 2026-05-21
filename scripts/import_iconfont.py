#!/usr/bin/env python3
"""將 iconfont.cn「下載至本地」的 ZIP 或資料夾匯入 static/iconfont/。"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_IF = ROOT / "static" / "iconfont"
DATA_CFG = ROOT / "data" / "iconfont_project.json"


def _copy_tree(src: Path, dest: Path, names: tuple[str, ...]) -> int:
    n = 0
    for name in names:
        for p in src.rglob(name):
            if not p.is_file():
                continue
            rel = p.relative_to(src)
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
            n += 1
    return n


def import_from_dir(src: Path) -> dict:
    STATIC_IF.mkdir(parents=True, exist_ok=True)
    stocks = STATIC_IF / "stocks"
    stocks.mkdir(exist_ok=True)
    copied = _copy_tree(
        src,
        STATIC_IF,
        ("iconfont.js", "iconfont.css", "iconfont.woff", "iconfont.woff2", "iconfont.ttf"),
    )
    svg_n = 0
    for svg in src.rglob("*.svg"):
        if "demo" in svg.parts:
            continue
        name = svg.name.upper() if svg.stem.isdigit() or len(svg.stem) <= 6 else svg.name
        if _is_stock_code_filename(svg.stem):
            dest = stocks / f"{svg.stem.upper()}.svg"
            shutil.copy2(svg, dest)
            svg_n += 1
    symbol_url = ""
    js = STATIC_IF / "iconfont.js"
    if js.is_file():
        text = js.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"//at\.alicdn\.com/t/[^\s'\"]+", text)
        if m:
            symbol_url = "https:" + m.group(0) if m.group(0).startswith("//") else m.group(0)
    return {"copied_assets": copied, "stock_svgs": svg_n, "symbol_js_url": symbol_url}


def _is_stock_code_filename(stem: str) -> bool:
    s = stem.strip().upper()
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", s) or re.fullmatch(r"\d{5,6}", s))


def main() -> None:
    ap = argparse.ArgumentParser(description="匯入 iconfont.cn 本地下載包")
    ap.add_argument("path", help="ZIP 或解壓後的資料夾路徑")
    ap.add_argument("--write-config", action="store_true", help="寫入 data/iconfont_project.json 的 symbol_js_url")
    args = ap.parse_args()
    src = Path(args.path).resolve()
    if not src.exists():
        raise SystemExit(f"路徑不存在: {src}")

    if src.suffix.lower() == ".zip":
        tmp = ROOT / "data" / "_iconfont_import"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(tmp)
        subdirs = [p for p in tmp.iterdir() if p.is_dir()]
        src = subdirs[0] if len(subdirs) == 1 else tmp

    stats = import_from_dir(src)
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    if args.write_config and stats.get("symbol_js_url"):
        cfg = {}
        if DATA_CFG.is_file():
            cfg = json.loads(DATA_CFG.read_text(encoding="utf-8"))
        cfg["enabled"] = True
        cfg["symbol_js_url"] = stats["symbol_js_url"]
        cfg.setdefault("css_url", "/static/iconfont/iconfont.css")
        DATA_CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已更新 {DATA_CFG}")


if __name__ == "__main__":
    main()
