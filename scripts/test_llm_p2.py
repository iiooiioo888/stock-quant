"""Quick smoke test for P2 LLM new API."""
import sys
sys.path.insert(0, ".")

# 1. Test service.py imports
from src.integrations.llm.service import (
    invoke_llm, invoke_llm_stream, get_system_prompt, cache_stats,
    set_tier_model, _resolve_model_for_task, _PROMPTS,
    _TASK_MODEL_TIERS, cache_get, cache_set,
)
print("[OK] service.py imports")

# 2. Test __init__.py re-exports
from src.integrations.llm import invoke_llm, invoke_llm_stream
print("[OK] __init__.py re-exports")

# 3. Verify system prompts exist
for key in ("analyze", "suggest", "generate", "optimize", "report", "morning"):
    assert key in _PROMPTS, f"Missing prompt: {key}"
    assert len(_PROMPTS[key]) > 50, f"Prompt too short: {key}"
print(f"[OK] {len(_PROMPTS)} system prompts defined")

# 4. Verify task model tiers
assert "backtest_report" in _TASK_MODEL_TIERS
assert "code_generate" in _TASK_MODEL_TIERS
assert "morning_report" in _TASK_MODEL_TIERS
assert _TASK_MODEL_TIERS["morning_report"] == "light"
assert _TASK_MODEL_TIERS["code_generate"] == "heavy"
print("[OK] Task model tiers correct")

# 5. Test model routing logic
from src.integrations.llm.config_resolver import LlmRuntimeConfig

class FakeCfg:
    def __init__(self, model):
        self.model = model

# mini → heavy task → should upgrade to gpt-4o
cfg = FakeCfg("gpt-4o-mini")
result = _resolve_model_for_task(cfg, "code_generate")
assert result == "gpt-4o", f"Expected gpt-4o, got {result}"
print("[OK] Model routing: mini → heavy task → gpt-4o")

# heavy → light task → should downgrade to mini
cfg = FakeCfg("gpt-4o")
result = _resolve_model_for_task(cfg, "morning_report")
assert result == "gpt-4o-mini", f"Expected gpt-4o-mini, got {result}"
print("[OK] Model routing: heavy → light task → gpt-4o-mini")

# mini → light task → keep mini
cfg = FakeCfg("gpt-4o-mini")
result = _resolve_model_for_task(cfg, "stock_summary")
assert result == "gpt-4o-mini", f"Expected gpt-4o-mini, got {result}"
print("[OK] Model routing: mini → light → gpt-4o-mini")

# heavy → heavy task → keep heavy
cfg = FakeCfg("gpt-4o")
result = _resolve_model_for_task(cfg, "strategy_analysis")
assert result == "gpt-4o", f"Expected gpt-4o, got {result}"
print("[OK] Model routing: heavy → heavy → gpt-4o")

# 6. Test set_tier_model
set_tier_model("light", "custom-model")
cfg = FakeCfg("gpt-4o")
result = _resolve_model_for_task(cfg, "morning_report")
assert result == "custom-model", f"Expected custom-model, got {result}"
print("[OK] set_tier_model override works")
# Reset
set_tier_model("light", "")

# 7. Test cache (without Redis, should return None)
result = cache_get("test", "hello")
assert result is None
print("[OK] cache_get returns None without Redis")

stats = cache_stats()
assert stats["backend"] == "none"
print("[OK] cache_stats returns backend=none without Redis")

# 8. Test get_system_prompt
for task in ("analyze", "suggest", "generate", "optimize", "report", "morning"):
    prompt = get_system_prompt(task)
    assert len(prompt) > 50
print("[OK] get_system_prompt returns valid prompts")

# 9. Test prompt content quality
assert "StockQ" in _PROMPTS["analyze"]
assert "generate_signals" in _PROMPTS["generate"]
assert "晨報" in _PROMPTS["morning"]
assert "參數" in _PROMPTS["optimize"]
print("[OK] Prompt content quality checks passed")

# 10. Test llm router endpoints exist
from src.api.routers.llm import router
routes = [r.path for r in router.routes]
expected = [
    "/api/llm/chat", "/api/llm/chat/stream",
    "/api/llm/analyze", "/api/llm/analyze/stream",
    "/api/llm/suggest", "/api/llm/generate",
    "/api/llm/optimize", "/api/llm/report", "/api/llm/morning",
    "/api/llm/status", "/api/llm/settings",
]
for ep in expected:
    assert ep in routes, f"Missing endpoint: {ep}"
print(f"[OK] All {len(expected)} endpoints registered in router")

print("\n=== ALL P2 TESTS PASSED ===")