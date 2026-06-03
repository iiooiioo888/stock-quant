#!/usr/bin/env bash
# 批量修復 src/core 的 ruff 可自動修項（本地執行）
set -euo pipefail
cd "$(dirname "$0")/.."
pip install -q ruff
ruff check src/core/ --fix
echo "--- remaining ---"
ruff check src/core/ --statistics || true
