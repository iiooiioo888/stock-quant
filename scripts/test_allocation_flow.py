"""手動驗證：配置欄市值權重、多股對比、組合回測權重。"""
import json
import time
import uuid

import requests

BASE = "http://127.0.0.1:8000"


def main():
    s = requests.Session()
    r = s.get(f"{BASE}/api/health", timeout=10)
    print("health", r.status_code)

    user = f"test_{uuid.uuid4().hex[:8]}"
    pw = "test_pw_2026"
    s.post(f"{BASE}/api/auth/register", json={"username": user, "password": pw}, timeout=15)
    lr = s.post(f"{BASE}/api/auth/login", json={"username": user, "password": pw}, timeout=15)
    tok = lr.json().get("token", "")
    s.headers["Authorization"] = f"Bearer {tok}"
    print("auth", user, bool(tok))

    positions = [
        {"code": "600519", "name": "茅台", "quantity": 100},
        {"code": "0700.HK", "name": "騰訊", "quantity": 200},
        {"code": "AAPL", "name": "Apple", "quantity": 50},
    ]
    put = s.put(f"{BASE}/api/my-allocation", json={"positions": positions}, timeout=30)
    print("put alloc", put.status_code, put.text[:200])

    get = s.get(f"{BASE}/api/my-allocation?weight_mode=market_value", timeout=120)
    d = get.json()
    print("\n=== 1) 市值權重 ===")
    print("success", d.get("success"), "count", d.get("count"))
    total_w = 0.0
    for p in d.get("positions", []):
        w = float(p.get("weight_pct") or 0)
        total_w += w
        print(
            f"  {p['code']}: qty={p['quantity']} price={p.get('last_price')} "
            f"mv={p.get('market_value')} weight={w}%"
        )
    print("  weight sum %", round(total_w, 2))

    print("\n=== 2) 多股對比 ===")
    cmp = s.post(
        f"{BASE}/api/stocks/compare",
        json={"codes": ["600519", "0700.HK", "AAPL"], "days": 120},
        timeout=180,
    )
    cj = cmp.json()
    print("loaded", cj.get("loaded"), "/", cj.get("total"))
    print("missing", cj.get("missing"))
    print("keys", list((cj.get("comparison") or {}).keys()))

    print("\n=== 3) 組合回測權重 ===")
    wmap = {
        p["code"].upper(): float(p["weight_pct"]) / 100.0
        for p in d.get("positions", [])
        if p.get("weight_pct")
    }
    codes = ["600519", "0700.HK", "AAPL"]
    strategy = "dual_ma"
    alloc = []
    weights = []
    for c in codes:
        w = wmap.get(c.upper(), 1.0 / len(codes))
        alloc.append({"strategy": strategy, "code": c, "weight": w})
        weights.append(w)
    print("submit weights", [round(x, 4) for x in weights])
    pr = s.post(
        f"{BASE}/api/portfolio",
        json={
            "allocations": alloc,
            "weights": weights,
            "rebalance": "none",
            "rebalance_freq_days": 21,
            "cash": 100000 + int(sum(weights) * 10000),
        },
        timeout=30,
    )
    pj = pr.json()
    print("portfolio", pj.get("success"), "task_id", pj.get("task_id"))
    tid = pj.get("task_id")
    if not tid:
        return
    for i in range(40):
        tr = s.get(f"{BASE}/api/tasks/{tid}", timeout=15)
        tj = tr.json()
        task = tj.get("task") or tj
        st = task.get("status")
        if st in ("completed", "failed", "cancelled"):
            params = task.get("params") or {}
            print("task status", st)
            print("params.weights", params.get("weights"))
            aw = [a.get("weight") for a in (params.get("allocations") or [])]
            print("allocations[].weight", aw)
            unequal = len(set(round(x, 4) for x in aw if x is not None)) > 1
            print("non-equal weights OK" if unequal else "WARN: weights look equal")
            break
        time.sleep(2)
    else:
        print("task timeout still running")


if __name__ == "__main__":
    main()
