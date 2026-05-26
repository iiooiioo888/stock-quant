"""One-off: build static/home.html body from app.html pg-home block."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "static" / "app.html").read_text(encoding="utf-8")
start = app.index('<div class="pg on" id="pg-home">')
end = app.index('<div class="pg" id="pg-dashboard">')
block = app[start:end]
block = block.replace('<div class="pg on" id="pg-home">', '<div class="site-home" id="site-home">')
block = re.sub(r'data-go="([^"]+)"', r'href="/app#/\1"', block)
block = re.sub(
    r'<button type="button" class="btn btn-ac"([^>]*)>([^<]+)</button>',
    r'<a class="site-btn site-btn-primary"\1>\2</a>',
    block,
)
block = re.sub(
    r'<button type="button" class="btn btn-sm"([^>]*)>([^<]+)</button>',
    r'<a class="site-btn" style="font-size:.68rem;padding:6px 10px"\1>\2</a>',
    block,
)
block = re.sub(
    r'<button type="button" class="btn"([^>]*)>([^<]+)</button>',
    r'<a class="site-btn"\1>\2</a>',
    block,
)
block = re.sub(
    r'<article class="home-feat" ',
    r'<a class="home-feat" ',
    block,
)
block = block.replace("</article>", "</a>")

header = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>StockQ Pro — A 股量化回測與實時盯盤</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/static/css/pro.css?v=stockq-site-v1" />
  <link rel="stylesheet" href="/static/css/site.css?v=stockq-site-v1" />
  <style>body{overflow:auto;height:auto}.home-feat{text-decoration:none;color:inherit}</style>
</head>
<body>
<div class="site-wrap">
  <header class="site-header">
    <div class="site-header-inner">
      <a href="/" class="site-brand"><span class="site-brand-icon">Q</span> StockQ <span>Pro</span></a>
      <nav class="site-nav" aria-label="官網導航">
        <a href="#features">產品能力</a>
        <a href="#portals">入口</a>
        <a href="/docs" target="_blank" rel="noopener">API 文檔</a>
      </nav>
      <div class="site-actions">
        <a href="/admin" class="site-btn">管理後台</a>
        <a href="/app" class="site-btn site-btn-primary">進入工作台</a>
      </div>
    </div>
  </header>
  <main class="site-main">
"""

portals = """
    <h2 class="site-section-title" id="portals">系統入口</h2>
    <div class="site-portals">
      <div class="portal-card">
        <h3>官網首頁</h3>
        <p>產品介紹、能力概覽與快速開始指引（當前頁面）。</p>
        <span class="site-btn" style="opacity:.6;cursor:default">您已在這裡</span>
      </div>
      <div class="portal-card">
        <h3>量化工作台</h3>
        <p>儀表盤、策略庫、回測、自選、預警與風控 — 日常交易分析主界面。</p>
        <a href="/app" class="site-btn site-btn-primary">打開 /app</a>
      </div>
      <div class="portal-card admin">
        <h3>管理員後台</h3>
        <p>用戶與角色管理、系統健康檢查（需 admin 賬號登錄）。</p>
        <a href="/admin" class="site-btn">打開 /admin</a>
      </div>
    </div>
"""

footer = """
  </main>
  <footer class="site-footer">
    <div class="site-footer-inner">
      <span>© StockQ Pro · 本地量化工作站</span>
      <div class="site-footer-links">
        <a href="/app">工作台</a>
        <a href="/admin">管理後台</a>
        <a href="/static/legacy/index.html">舊版 UI</a>
        <a href="/docs" target="_blank" rel="noopener">API</a>
      </div>
    </div>
  </footer>
</div>
<script src="/static/js/site/home-landing.js?v=stockq-site-v1"></script>
</body>
</html>
"""

# strip outer pg-home wrapper closing
block = block.replace("</div>\n\n      ", "</div>\n", 1)
inner = block.replace('<div class="site-home" id="site-home">', "").rstrip()
if inner.endswith("</div>"):
    inner = inner[:-6].rstrip()

html = header + inner + portals + footer
(ROOT / "static" / "home.html").write_text(html, encoding="utf-8")
print("wrote", ROOT / "static" / "home.html", len(html), "chars")
