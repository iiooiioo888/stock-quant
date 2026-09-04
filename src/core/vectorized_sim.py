"""全倉多頭模擬 — Numba 熱路徑；無 Numba 時走同等 Python 循環。"""

from __future__ import annotations

import numpy as np

try:
    from numba import jit
except ImportError:

    def jit(*_a, **_k):
        def deco(fn):
            return fn

        return deco


@jit(nopython=True, cache=True)
def _impact_frac(
    base: float, shares: float, bar_vol: float, cap: float, exp: float
) -> float:
    if base <= 0.0 or shares <= 0.0 or bar_vol <= 0.0:
        return base
    part = shares / bar_vol
    if part <= cap:
        return base
    return base * (part / cap) ** exp


@jit(nopython=True, cache=True)
def _cost(turnover: float, is_sell: bool, commission: float, min_comm: float, stamp: float, transfer: float) -> float:
    comm = turnover * commission
    if comm < min_comm:
        comm = min_comm
    if is_sell:
        comm += turnover * stamp
    comm += turnover * transfer
    return comm


@jit(nopython=True, cache=True)
def simulate_long(
    close: np.ndarray,
    vol: np.ndarray,
    want_buy: np.ndarray,
    want_sell: np.ndarray,
    cash0: float,
    commission: float,
    min_comm: float,
    stamp: float,
    transfer: float,
    slip_frac: float,
    use_vol_slip: np.int8,
    part_cap: float,
    impact_exp: float,
    order_size_cap: np.int64,
    enable_t1: np.int8,
    enable_limit: np.int8,
    lim: float,
    high: np.ndarray,
    low: np.ndarray,
    sl_frac: float,
    tp_frac: float,
    trail_frac: float,
) -> tuple:
    n = close.shape[0]
    equity = np.empty(n, dtype=np.float64)
    max_t = n
    buy_i = np.empty(max_t, dtype=np.int64)
    sell_i = np.empty(max_t, dtype=np.int64)
    buy_px = np.empty(max_t, dtype=np.float64)
    sell_px = np.empty(max_t, dtype=np.float64)
    sizes = np.empty(max_t, dtype=np.int64)
    pnls = np.empty(max_t, dtype=np.float64)
    n_paired = 0
    cash_bal = cash0
    shares = 0
    buy_bar = -1
    open_px = 0.0
    peak_px = 0.0
    blocked_buys = 0
    blocked_sells = 0
    t1_blocked = 0
    halt_bars = 0

    for i in range(n):
        px = close[i]
        halted = vol[i] <= 0.0 or px <= 0.0
        if halted:
            halt_bars += 1
            equity[i] = cash_bal + shares * (px if px > 0.0 else 0.0)
            continue

        prev = close[i - 1] if i > 0 else px
        chg = (px - prev) / prev if prev > 0.0 else 0.0
        limit_up = enable_limit == 1 and chg >= lim - 0.001
        limit_dn = enable_limit == 1 and chg <= -(lim - 0.001)

        hi = high[i] if high[i] > 0.0 else px
        lo = low[i] if low[i] > 0.0 else px
        force_sell = np.int8(0)
        force_fill = 0.0
        if shares > 0:
            if hi > peak_px:
                peak_px = hi
            stop_px = 0.0
            if sl_frac > 0.0:
                stop_px = open_px * (1.0 - sl_frac)
            if trail_frac > 0.0:
                tr = peak_px * (1.0 - trail_frac)
                if stop_px == 0.0 or tr > stop_px:
                    stop_px = tr
            if stop_px > 0.0 and lo <= stop_px:
                force_sell = np.int8(1)
                force_fill = stop_px
            elif tp_frac > 0.0:
                tp_px = open_px * (1.0 + tp_frac)
                if hi >= tp_px:
                    force_sell = np.int8(1)
                    force_fill = tp_px

        if shares > 0 and (want_sell[i] == 1 or force_sell == 1):
            if enable_t1 == 1 and buy_bar >= 0 and i <= buy_bar:
                t1_blocked += 1
            elif limit_dn:
                blocked_sells += 1
            else:
                sf = slip_frac
                if use_vol_slip == 1:
                    sf = _impact_frac(slip_frac, float(shares), vol[i], part_cap, impact_exp)
                fill = force_fill if force_sell == 1 else px * (1.0 - sf)
                turn = float(shares) * fill
                cost = _cost(turn, True, commission, min_comm, stamp, transfer)
                cash_bal += turn - cost
                if n_paired < max_t:
                    buy_i[n_paired] = buy_bar
                    sell_i[n_paired] = i
                    buy_px[n_paired] = open_px
                    sell_px[n_paired] = fill
                    sizes[n_paired] = shares
                    pnls[n_paired] = (fill - open_px) * shares - cost
                    n_paired += 1
                shares = 0
                buy_bar = -1
                peak_px = 0.0

        if shares == 0 and want_buy[i] == 1:
            if limit_up:
                blocked_buys += 1
            else:
                sf = slip_frac
                lot = 100
                est = int(cash_bal / px / lot) * lot
                if order_size_cap > 0 and est > order_size_cap:
                    est = int(order_size_cap / lot) * lot
                    if est <= 0:
                        est = int(order_size_cap)
                if use_vol_slip == 1 and est > 0:
                    sf = _impact_frac(slip_frac, float(est), vol[i], part_cap, impact_exp)
                fill = px * (1.0 + sf)
                qty = int(cash_bal / fill / lot) * lot
                if order_size_cap > 0 and qty > order_size_cap:
                    qty = int(order_size_cap / lot) * lot
                    if qty <= 0:
                        qty = int(order_size_cap)
                if qty > 0:
                    turn = float(qty) * fill
                    cost = _cost(turn, False, commission, min_comm, stamp, transfer)
                    if cash_bal >= turn + cost:
                        cash_bal -= turn + cost
                        shares = qty
                        buy_bar = i
                        open_px = fill
                        peak_px = fill

        equity[i] = cash_bal + shares * px

    return (
        equity,
        n_paired,
        buy_i,
        sell_i,
        buy_px,
        sell_px,
        sizes,
        pnls,
        blocked_buys,
        blocked_sells,
        t1_blocked,
        halt_bars,
        shares,
        cash_bal,
        buy_bar,
    )
