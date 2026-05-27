# -*- coding: utf-8 -*-
import re
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "static" / "app.html"
text = p.read_text(encoding="utf-8")
m = re.search(r"(  <!-- ═══ SIDEBAR ═══ -->.*?  </nav>\n)", text, re.S)
if not m:
    raise SystemExit("sidebar not found")
block = m.group(1)
block = block.replace('class="tp"', 'class="sb-lbl"')
block = block.replace('<nav class="sidebar"', '<nav class="sidebar sidebar--labeled"')
block = block.replace('<span class="sb-lbl">調度</span>', '<span class="sb-lbl">定時</span>')
block = block.replace('title="接口檢查"', 'title="數據源連線檢查"')
block = block.replace('<span class="sb-lbl">接口</span>', '<span class="sb-lbl">連線</span>')
block = block.replace('<span class="sb-lbl">WF</span>', '<span class="sb-lbl">滾動</span>')
block = re.sub(r'\s*<div class="sd" aria-hidden="true"></div>\s*', "\n", block)
block = block.replace(
    '<nav class="sidebar sidebar--labeled" aria-label="主導航">\n',
    '<nav class="sidebar sidebar--labeled" aria-label="主導航">\n    <p class="sb-grp-hd">工作台</p>\n',
)
inserts = [
    ('data-p="compare"', '    <p class="sb-grp-hd">行情 · 組合</p>\n    '),
    ('data-p="risk"', '    <p class="sb-grp-hd">風控 · 紀錄</p>\n    '),
    ('data-p="optimize"', '    <p class="sb-grp-hd">回測進階</p>\n    '),
    ('data-p="ai"', '    <p class="sb-grp-hd">實驗 · AI</p>\n    '),
    ('data-p="settings"', '    <p class="sb-grp-hd">系統</p>\n    '),
]
for needle, hdr in inserts:
    block = block.replace(
        f'    <button type="button" class="sb" {needle}',
        hdr + f'<button type="button" class="sb" {needle}',
        1,
    )
cap_m = re.search(r'(    <button[^>]*data-p="capitalflow"[^>]*>.*?</button>\n)', block, re.S)
if cap_m:
    cap_btn = cap_m.group(1)
    block = block.replace(cap_btn, "", 1)
    tasks_m = re.search(r'(    <button[^>]*data-p="tasks"[^>]*>.*?</button>\n)', block, re.S)
    if tasks_m:
        block = block.replace(tasks_m.group(1), tasks_m.group(1) + cap_btn, 1)
text = text[: m.start()] + block + text[m.end() :]
p.write_text(text, encoding="utf-8")
print("sidebar patched")
