# 批量修復 src/core 的 ruff 可自動修項（Windows）
Set-Location (Split-Path $PSScriptRoot -Parent)
pip install -q ruff
ruff check src/core/ --fix
Write-Host "--- remaining ---"
ruff check src/core/ --statistics
