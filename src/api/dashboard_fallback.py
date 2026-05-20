"""
dashboard_fallback.py — 內建儀表盤 HTML（fallback）

當 static/index.html 不存在時使用此精簡頁面。
完整 SPA 請確保 static/ 目錄存在。
"""


def _builtin_dashboard() -> str:
    """精簡 fallback：健康檢查與 API 文檔入口"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>stock-quant</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{max-width:480px;padding:32px;text-align:center;background:#1e293b;border-radius:12px;border:1px solid #334155}
h1{font-size:22px;color:#38bdf8;margin-bottom:12px}
p{color:#94a3b8;font-size:14px;line-height:1.6;margin-bottom:20px}
a{color:#38bdf8;text-decoration:none;margin:0 8px}
a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="card">
<h1>📈 stock-quant</h1>
<p>未找到 <code>static/index.html</code>。請確認 static 目錄已部署，或重新構建 Docker 鏡像。</p>
<p>
<a href="/api/health">健康檢查</a>
<a href="/docs">API 文檔</a>
<a href="/redoc">ReDoc</a>
</p>
</div>
</body>
</html>"""
