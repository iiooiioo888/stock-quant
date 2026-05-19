#!/bin/bash
# Comprehensive API test for stock-quant
set -e
BASE="${STOCK_QUANT_URL:-http://localhost:8000}"
ADMIN_PW="${SQ_DEMO_ADMIN_PASSWORD:-stockquant2024}"
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")
AUTH="Authorization: Bearer $TOKEN"
PASS=0
FAIL=0
RESULTS=""

test_api() {
  local method="$1" path="$2" desc="$3" data="$4"
  if [ "$method" = "GET" ]; then
    resp=$(curl -s -w "\n%{http_code}" "$BASE$path" -H "$AUTH" 2>&1)
  else
    resp=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE$path" -H "$AUTH" -H "Content-Type: application/json" -d "$data" 2>&1)
  fi
  code=$(echo "$resp" | tail -1)
  body=$(echo "$resp" | sed '$d')
  if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
    echo "✅ [$code] $desc"
    PASS=$((PASS+1))
  else
    echo "❌ [$code] $desc"
    echo "   Response: $(echo "$body" | head -c 200)"
    FAIL=$((FAIL+1))
  fi
  RESULTS="$RESULTS\n${code}|${desc}"
}

echo "=========================================="
echo "  stock-quant 全功能 API 測試"
echo "=========================================="
echo ""

# 確保 admin 用戶存在
echo "── 0. 初始化 ──"
curl -s -X POST "$BASE/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" > /dev/null 2>&1
# 登錄獲取 token
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
if [ -z "$TOKEN" ]; then
  echo "❌ 登錄失敗，無法獲取 Token，請確保服務已啟動"
  exit 1
fi
echo "✅ 登錄成功"
AUTH="Authorization: Bearer $TOKEN"

# ====== 1. 認證 API ======
echo ""
echo "── 1. 認證 API ──"
test_api GET "/api/health" "健康檢查"
test_api GET "/api/status" "系統狀態"
test_api GET "/api/auth/me" "獲取當前用戶"
test_api PUT "/api/auth/settings" "更新用戶設置" '{"settings":{"theme":"dark"}}'

# ====== 2. 配置 API ======
echo ""
echo "── 2. 配置 API ──"
test_api GET "/api/config" "獲取配置"
test_api GET "/api/strategies/list" "策略列表"

# ====== 3. 股票數據 API ======
echo ""
echo "── 3. 股票數據 API ──"
test_api GET "/api/stocks" "股票列表"
test_api GET "/api/stocks/000001/kline?limit=10" "K線數據(000001)"
test_api POST "/api/stocks/compare" "多股對比" '{"codes":["000001","600519"],"days":60}'

# ====== 4. 回測 API ======
echo ""
echo "── 4. 回測 API ──"
test_api POST "/api/backtest?code=000001&strategy=dual_ma" "單策略回測"
test_api POST "/api/backtest/multi?code=000001" "全策略對比"
test_api POST "/api/backtest/advanced" "進階回測" '{"code":"000001","strategy":"macd","slippage_pct":0.1,"enable_t1":true,"enable_limit":true}'
test_api GET "/api/backtest/history?limit=10" "回測歷史"

# ====== 5. 優化 API ======
echo ""
echo "── 5. 優化 API ──"
test_api POST "/api/optimize?code=000001&strategy=dual_ma&method=grid&objective=sharpe&n_trials=5" "參數優化"
test_api POST "/api/auto-optimize" "全自動優化" '{"codes":["000001"],"strategies":["dual_ma"]}'

# ====== 6. 組合 API ======
PF_ALLOC='[{"strategy":"dual_ma","code":"000001"},{"strategy":"macd","code":"600519"}]'
PF_SIGNALS='[{"strategy":"dual_ma","code":"000001","signal":"buy"},{"strategy":"macd","code":"600519","signal":"sell"}]'
echo ""
echo "── 6. 組合 API ──"
test_api GET "/api/portfolio/presets" "預設組合列表"
test_api POST "/api/portfolio/preset/conservative" "穩健型組合回測"
test_api POST "/api/portfolio" "自定義組合回測" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/risk-parity" "風險平價" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/mvo" "均值方差" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/vol-target" "波動率目標" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/max-diversification" "最大分散化" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/anti-correlation" "低相關組合" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/regime-switch" "狀態切換" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/dynamic" "動態組合" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/kelly" "Kelly公式" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/degradation" "衰減分析" "{\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/arbitrate" "套利組合" "{\"strategy_signals\":${PF_SIGNALS},\"allocations\":${PF_ALLOC}}"
test_api POST "/api/portfolio/frontier" "有效前沿" "{\"allocations\":${PF_ALLOC}}"

# ====== 7. 篩選器 API ======
echo ""
echo "── 7. 篩選器 API ──"
test_api POST "/api/screener/screen" "股票篩選" '{"filters":{"ma_aligned":true}}'
test_api GET "/api/screener/stocks?market=all" "篩選器股票列表"

# ====== 8. 信號 API ======
echo ""
echo "── 8. 信號 API ──"
test_api GET "/api/signals/current" "當前信號"
test_api GET "/api/signals/history?days=30" "歷史信號"
test_api GET "/api/signals/strength?code=000001" "信號強度"

# ====== 9. 數據中心 API ======
echo ""
echo "── 9. 數據中心 API ──"
test_api GET "/api/data/sectors?sector_type=industry&top_n=10" "行業板塊"
test_api GET "/api/data/capital-flow?code=000001&days=10" "資金流向"
test_api GET "/api/data/north-flow?days=10" "北向資金"
test_api GET "/api/data/dragon-tiger" "龍虎榜"
test_api POST "/api/data/fundamentals/screen" "基本面篩選" '{"filters":{"pe_max":20,"pb_max":3}}'

# ====== 10. Walk-Forward API ======
echo ""
echo "── 10. Walk-Forward API ──"
test_api POST "/api/walkforward?code=000001&strategy=dual_ma&train_days=250&test_days=125&n_trials=5" "Walk-Forward分析"

# ====== 11. 熱力圖 API ======
echo ""
echo "── 11. 熱力圖 API ──"
test_api GET "/api/heatmap/params/dual_ma" "熱力圖參數"
test_api POST "/api/heatmap?code=000001&strategy=dual_ma&param_x=fast&param_y=slow&grid_size=5" "熱力圖生成"

# ====== 12. 預警 API ======
echo ""
echo "── 12. 預警 API ──"
test_api GET "/api/alerts?limit=10" "預警歷史"
test_api GET "/api/alerts/rules" "預警規則"
test_api PUT "/api/alerts/rules" "更新預警規則" '{"000001":{"name":"平安銀行","price_above":14.0,"price_below":10.0}}'

# ====== 13. 監控列表 API ======
echo ""
echo "── 13. 監控列表 API ──"
test_api POST "/api/watchlist/add?code=600036&name=招商銀行" "添加監控"

# ====== 14. 通知 API ======
echo ""
echo "── 14. 通知 API ──"
test_api GET "/api/notify/channels" "通知渠道"
test_api POST "/api/notify/test" "測試通知"

# ====== 15. 調度器 API ======
echo ""
echo "── 15. 調度器 API ──"
test_api GET "/api/scheduler/jobs" "調度任務列表"
test_api POST "/api/scheduler/enable" "啟用調度"
test_api POST "/api/scheduler/disable" "禁用調度"

# ====== 16. 報告 API ======
echo ""
echo "── 16. 報告 API ──"
test_api POST "/api/report/full" "生成報告" '{"code":"000001","strategy":"dual_ma"}'

# ====== 17. 排行榜 API ======
echo ""
echo "── 17. 排行榜 API ──"
test_api GET "/api/strategies/leaderboard?sort_by=sharpe&limit=10" "策略排行榜"

# ====== 18. WebSocket ======
echo ""
echo "── 18. WebSocket ──"
# 用 curl 測試 WebSocket 升級（不依賴 websockets 庫）
ws_code=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Upgrade: websocket" -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGVzdA==" \
  "$BASE/ws" 2>/dev/null || echo "000")
if [ "$ws_code" = "101" ]; then
  echo "✅ [WS] WebSocket 升級響應"
  PASS=$((PASS+1))
else
  # 101 或 200 都算成功（有些代理返回 200）
  if [ "$ws_code" = "200" ]; then
    echo "✅ [WS] WebSocket 端點可達"
    PASS=$((PASS+1))
  else
    echo "❌ [WS] WebSocket 升級失敗: HTTP $ws_code"
    FAIL=$((FAIL+1))
  fi
fi

# ====== 19. 前端靜態文件 ======
echo ""
echo "── 19. 前端靜態文件 ──"
for f in "/" "/static/css/style.css" "/static/js/app.js" "/static/js/api.js" "/static/js/utils.js" "/static/js/charts.js" "/static/js/dashboard.js" "/static/js/backtest.js" "/static/js/optimize.js" "/static/js/portfolio.js" "/static/js/signals.js" "/static/js/screener.js" "/static/js/heatmap.js" "/static/js/data.js" "/static/js/analysis.js"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$f")
  if [ "$code" = "200" ]; then
    echo "✅ [$code] 靜態文件: $f"
    PASS=$((PASS+1))
  else
    echo "❌ [$code] 靜態文件: $f"
    FAIL=$((FAIL+1))
  fi
done

# ====== Summary ======
echo ""
echo "=========================================="
echo "  測試完成: ✅ $PASS 通過 / ❌ $FAIL 失敗"
echo "=========================================="
