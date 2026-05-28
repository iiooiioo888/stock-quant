param()

$ErrorActionPreference = "Stop"

function Write-Allow([string]$userMessage) {
  $out = @{
    permission   = "allow"
    user_message = $userMessage
  } | ConvertTo-Json -Depth 10 -Compress
  Write-Output $out
}

try {
  $raw = [Console]::In.ReadToEnd()
  $event = $null
  if (-not [string]::IsNullOrWhiteSpace($raw)) {
    try { $event = $raw | ConvertFrom-Json } catch { $event = $null }
  }

  $msg = @"
FastAPI 子代理守門提示（自動）：
- 只改動本次需求相關檔案，優先聚焦 `src/api/**`、`src/core/**`
- 嚴禁把 `data/`、`logs/`、`.env`、`*.db*`、`__pycache__/`、密碼檔等納入提交/變更
- 改完要自檢：至少確認 `python -m compileall src` 可過；有測試就跑 `pytest -q`
- 若新增 SSE / Router / Error handler：同步確認 `src/api/app.py` 註冊、錯誤格式一致
"@.Trim()

  Write-Allow $msg
  exit 0
} catch {
  # fail open
  Write-Allow "FastAPI 子代理守門提示：請遵守專案規範並在修改後做基本自檢（compileall / pytest）。"
  exit 0
}

