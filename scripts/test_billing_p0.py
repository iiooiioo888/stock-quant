"""Quick smoke test for P0 billing changes."""
import sys
sys.path.insert(0, ".")

from src.core.billing_plans import PLANS, PLAN_ORDER, plans_public_payload, FEATURE_LABELS, plan_definition
from src.core.entitlements import _VALID_PLAN_IDS, usage_snapshot

# 1. Verify plan structure
print("=== Plans ===")
for pid in PLAN_ORDER:
    p = PLANS[pid]
    print(f"  {pid}: {p.name} - ${p.price_monthly}/mo, {len(p.features)} features")

# 2. Verify pro_ai exists
assert "pro_ai" in PLANS, "pro_ai plan missing!"
assert "pro_ai" in PLAN_ORDER, "pro_ai not in PLAN_ORDER!"
assert "pro_ai" in _VALID_PLAN_IDS, "pro_ai not in _VALID_PLAN_IDS!"
print("\n[OK] pro_ai plan registered correctly")

# 3. Verify new features exist
new_features = [
    "ai_strategy_recommend", "ai_report_interpret", "ai_code_generate",
    "ai_param_suggest", "ai_market_report",
    "walkforward", "monte_carlo", "efficient_frontier",
    "degradation_detect", "signal_backtest", "signal_heatmap",
    "signal_ranking", "full_report",
    "risk_position_calc", "risk_budget_check", "risk_drawdown_protect",
    "risk_pipeline", "correlation_monitor", "signal_arbitration",
    "minute_kline", "data_quality_repair", "custom_strategies",
    "sandbox_backtest", "strategy_leaderboard", "paper_trading",
    "realtime_ws_symbols", "rest_api_access",
    "signal_history", "strategy_browse", "position_calc_basic",
]
for f in new_features:
    assert f in FEATURE_LABELS, f"Feature {f} missing from FEATURE_LABELS!"
print(f"[OK] All {len(new_features)} new features present in FEATURE_LABELS")

# 4. Verify pro has walkforward but not ai_strategy_recommend
pro = plan_definition("pro")
assert "walkforward" in pro.features, "Pro should have walkforward"
assert "ai_strategy_recommend" not in pro.features, "Pro should NOT have ai_strategy_recommend"
print("[OK] Pro plan features correct")

# 5. Verify pro_ai has ai features
pro_ai = plan_definition("pro_ai")
assert "ai_strategy_recommend" in pro_ai.features, "Pro+AI should have ai_strategy_recommend"
assert "ai_code_generate" in pro_ai.features, "Pro+AI should have ai_code_generate"
assert "ai_market_report" in pro_ai.features, "Pro+AI should have ai_market_report"
print("[OK] Pro+AI plan features correct")

# 6. Verify new limits
assert pro.limits.daily_ai_queries == 20
assert pro.limits.daily_walkforward == 5
assert pro.limits.daily_monte_carlo == 10
assert pro.limits.daily_signal_ranking == 10
assert pro.limits.daily_full_report == 3
assert pro.limits.max_custom_strategies == 5
assert pro.limits.export_row_limit == 1000
print("[OK] Pro limits correct")

assert pro_ai.limits.daily_ai_queries == 100
assert pro_ai.limits.daily_walkforward == 10
assert pro_ai.limits.realtime_ws_symbols == 20
assert pro_ai.limits.export_row_limit == 10000
print("[OK] Pro+AI limits correct")

# 7. Verify usage_snapshot has new fields
snap = usage_snapshot(0)
assert "ai_queries_today" in snap
assert "walkforward_today" in snap
assert "monte_carlo_today" in snap
assert "signal_ranking_today" in snap
assert "full_report_today" in snap
print("[OK] usage_snapshot has new fields")

# 8. Verify plans_public_payload includes new limits
payload = plans_public_payload()
for p in payload:
    assert "daily_ai_queries" in p["limits"], f"{p['id']} missing daily_ai_queries"
    assert "daily_walkforward" in p["limits"], f"{p['id']} missing daily_walkforward"
    assert "export_row_limit" in p["limits"], f"{p['id']} missing export_row_limit"
print("[OK] plans_public_payload includes new limits")

# 9. Verify pricing
assert PLANS["free"].price_monthly == 0
assert PLANS["pro"].price_monthly == 29
assert PLANS["pro_ai"].price_monthly == 44
assert PLANS["institutional"].price_monthly == 199
print("[OK] Pricing correct")

print("\n=== ALL P0 TESTS PASSED ===")