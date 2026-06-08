#!/bin/bash
# 使用 uv/pip-tools 編譯依賴腳本
set -e

echo "=== 編譯 Python 依賴 ==="

# 檢查是否安裝 uv
if ! command -v uv &> /dev/null; then
    echo "安裝 uv..."
    pip install uv
fi

# 編譯生產依賴
echo "編譯生產依賴..."
uv pip compile pyproject.toml --extra dev -o requirements-compiled.txt --generate-hashes

echo "✓ 依賴編譯完成：requirements-compiled.txt"
echo ""
echo "使用方法:"
echo "  uv pip install --system -r requirements-compiled.txt"
