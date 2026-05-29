"""Quick smoke test for P3: Multi-level cache + API stateless."""
import sys
sys.path.insert(0, ".")

# 1. Test rate_limiter.py imports
from src.core.rate_limiter import check_rate_limit, get_usage, reset, stats, is_available, _MemoryRateLimiter
print("[OK] rate_limiter.py imports")

# 2. Test memory fallback (Redis not available)
allowed, retry = check_rate_limit("192.168.1.1", 5, namespace="test")
assert allowed is True, f"First request should be allowed, got {allowed}"
print("[OK] Memory rate limiter: first request allowed")

# 3. Test rate limit exhaustion
for _ in range(4):
    check_rate_limit("192.168.1.2", 5, namespace="test2")
allowed, retry = check_rate_limit("192.168.1.2", 5, namespace="test2")
assert allowed is True, f"5th request should be allowed"
allowed, retry = check_rate_limit("192.168.1.2", 5, namespace="test2")
assert allowed is False, f"6th request should be blocked"
assert retry > 0, f"retry_after should be > 0"
print("[OK] Memory rate limiter: limit exhaustion works")

# 4. Test different IPs are isolated
allowed, _ = check_rate_limit("192.168.1.3", 5, namespace="test3")
assert allowed is True
print("[OK] Memory rate limiter: IP isolation works")

# 5. Test stats without Redis
s = stats()
assert s["backend"] == "memory"
assert s["available"] is False
print("[OK] rate_limiter stats without Redis")

# 6. Test api_cache.py imports
from src.core.api_cache import get_cached, set_cached, cached_response, invalidate_prefix, clear_all, cache_stats
print("[OK] api_cache.py imports")

# 7. Test api_cache memory fallback
clear_all()
assert get_cached("test:key") is None
set_cached("test:key", {"hello": "world"}, ttl=10)
result = get_cached("test:key")
assert result == {"hello": "world"}, f"Expected dict, got {result}"
print("[OK] api_cache memory: set/get works")

# 8. Test cached_response
clear_all()
call_count = 0
def builder():
    global call_count
    call_count += 1
    return {"count": call_count}

result1 = cached_response("test:builder", ttl=10, builder=builder)
assert result1 == {"count": 1}
result2 = cached_response("test:builder", ttl=10, builder=builder)
assert result2 == {"count": 1}, f"Should return cached value, got {result2}"
assert call_count == 1, f"Builder should only be called once, called {call_count} times"
print("[OK] api_cache: cached_response dedup works")

# 9. Test invalidate_prefix
set_cached("prefix:a", 1, ttl=10)
set_cached("prefix:b", 2, ttl=10)
set_cached("other:c", 3, ttl=10)
invalidate_prefix("prefix:")
assert get_cached("prefix:a") is None
assert get_cached("prefix:b") is None
assert get_cached("other:c") == 3
print("[OK] api_cache: invalidate_prefix works")

# 10. Test cache_stats
stats_result = cache_stats()
assert "redis_available" in stats_result
assert "memory_entries" in stats_result
print("[OK] api_cache: cache_stats works")

# 11. Test api_cache JSON serialization (for Redis compatibility)
clear_all()
set_cached("test:complex", {"list": [1, 2, 3], "nested": {"a": "b"}}, ttl=10)
result = get_cached("test:complex")
assert result["list"] == [1, 2, 3]
assert result["nested"]["a"] == "b"
print("[OK] api_cache: complex object serialization works")

print("\n=== ALL P3 TESTS PASSED ===")