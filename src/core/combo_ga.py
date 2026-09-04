"""多策略權重遺傳演算法 — 在收益序列上尋找權重組合。"""

from __future__ import annotations

import numpy as np


def optimize_weights(
    returns: np.ndarray,
    *,
    generations: int = 40,
    pop_size: int = 32,
    seed: int = 42,
) -> dict:
    """
    returns: shape (T, K) 各策略日收益。
    最大化夏普（無風險 0）。
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 2 or r.shape[0] < 5 or r.shape[1] < 2:
        raise ValueError("需要至少 5 日、2 個策略的收益矩陣")
    rng = np.random.default_rng(seed)
    k = r.shape[1]

    def fitness(w: np.ndarray) -> float:
        w = np.clip(w, 0, None)
        s = w.sum()
        if s <= 0:
            return -1e9
        w = w / s
        port = r @ w
        std = float(np.std(port))
        if std <= 0:
            return -1e9
        return float(np.mean(port) / std * np.sqrt(252))

    pop = rng.random((pop_size, k))
    pop = pop / pop.sum(axis=1, keepdims=True)
    best_w = pop[0]
    best_f = fitness(best_w)

    for _ in range(generations):
        scores = np.array([fitness(ind) for ind in pop])
        elite_i = int(np.argmax(scores))
        if scores[elite_i] > best_f:
            best_f = float(scores[elite_i])
            best_w = pop[elite_i].copy()
        # 錦標賽
        nxt = [pop[elite_i].copy()]
        while len(nxt) < pop_size:
            a, b = rng.integers(0, pop_size, size=2)
            p1 = pop[a] if scores[a] >= scores[b] else pop[b]
            c, d = rng.integers(0, pop_size, size=2)
            p2 = pop[c] if scores[c] >= scores[d] else pop[d]
            alpha = rng.random()
            child = alpha * p1 + (1 - alpha) * p2
            child = child + rng.normal(0, 0.05, size=k)
            child = np.clip(child, 0, None)
            s = child.sum()
            child = child / s if s > 0 else np.ones(k) / k
            nxt.append(child)
        pop = np.array(nxt)

    w = np.clip(best_w, 0, None)
    w = w / w.sum()
    return {
        "weights": [round(float(x), 6) for x in w],
        "sharpe": round(float(best_f), 4),
        "generations": generations,
        "pop_size": pop_size,
    }
