/* global Api */

/**
 * 全站右側「個人資產配置」— 市值/股數權重、多市場對比、組合回測權重聯動。
 */
(() => {
  const LOCAL_KEY = 'stockq:my_allocation_v1';
  const SU = () => window.StockQPro?.SymbolUtils;

  const state = {
    positions: [],
    enriched: [],
    weightMode: 'market_value',
    portfolioStrategy: 'dual_ma',
    updatedAt: null,
    loading: false,
    open: true,
  };

  function loadPrefs() {
    try {
      const p = window.StockQPro?.Prefs?.get?.('allocationRailOpen');
      if (p === false) state.open = false;
      const wm = window.StockQPro?.Prefs?.get?.('allocationWeightMode');
      if (wm === 'quantity' || wm === 'market_value') state.weightMode = wm;
      const ps = window.StockQPro?.Prefs?.get?.('allocationPortfolioStrategy');
      if (ps) state.portfolioStrategy = ps;
    } catch (_) {}
  }

  function savePrefs() {
    try {
      window.StockQPro?.Prefs?.save?.({
        allocationRailOpen: state.open,
        allocationWeightMode: state.weightMode,
        allocationPortfolioStrategy: state.portfolioStrategy,
      });
    } catch (_) {}
  }

  function readLocal() {
    try {
      const raw = localStorage.getItem(LOCAL_KEY);
      if (!raw) return [];
      const data = JSON.parse(raw);
      return Array.isArray(data.positions) ? data.positions : [];
    } catch (_) {
      return [];
    }
  }

  function writeLocal(positions) {
    localStorage.setItem(LOCAL_KEY, JSON.stringify({
      positions,
      updated_at: new Date().toISOString(),
    }));
  }

  function normalizeCode(code) {
    if (SU()?.normalizeCompareCode) return SU().normalizeCompareCode(code);
    let c = String(code || '').trim().toUpperCase();
    if (/^\d{1,6}$/.test(c)) c = c.padStart(6, '0');
    return c;
  }

  function dispatchChange() {
    window.dispatchEvent(new CustomEvent('stockq:allocation-changed', {
      detail: {
        positions: [...state.positions],
        enriched: [...state.enriched],
        weightMode: state.weightMode,
      },
    }));
  }

  async function fetchPriceForCode(code) {
    const raw = String(code || '').trim();
    const tries = [raw];
    if (/^\d{1,6}$/.test(raw)) {
      const c = raw.padStart(6, '0');
      const suf = /^6|^68|^51|^52|^56|^58/.test(c) ? '.SS' : '.SZ';
      tries.push(`${c}${suf}`);
    }
    for (const sym of tries) {
      try {
        const d = await Api.get(`/api/assets/price?symbol=${encodeURIComponent(sym)}`, { silent: true });
        if (d?.success && d.last_price > 0) return Number(d.last_price);
      } catch (_) {}
    }
    return 0;
  }

  async function enrichLocal() {
    const rows = state.positions.filter((p) => Number(p.quantity) > 0);
    const priced = await Promise.all(rows.map(async (p) => {
      const price = Number(p.last_price) > 0 ? Number(p.last_price) : await fetchPriceForCode(p.code);
      const qty = Number(p.quantity) || 0;
      const cost = Number(p.cost) || 0;
      const mv = price > 0 ? qty * price : (cost > 0 ? qty * cost : 0);
      return { ...p, last_price: price, market_value: mv };
    }));
    const totalMv = priced.reduce((s, r) => s + (r.market_value || 0), 0);
    const totalQty = priced.reduce((s, r) => s + (Number(r.quantity) || 0), 0);
    state.enriched = priced.map((r) => {
      let w = 0;
      if (state.weightMode === 'quantity') {
        w = totalQty > 0 ? (Number(r.quantity) / totalQty) * 100 : 0;
      } else {
        w = totalMv > 0 ? ((r.market_value || 0) / totalMv) * 100 : 0;
      }
      return { ...r, weight_pct: Math.round(w * 10) / 10 };
    });
  }

  async function load() {
    state.loading = true;
    render();
    if (typeof Api !== 'undefined' && Api.init && !Api._token) {
      try { Api.init(); } catch (_) {}
    }
    const token = typeof Api !== 'undefined' && Api._token;
    try {
      if (token) {
        const d = await Api.get(
          `/api/my-allocation?weight_mode=${encodeURIComponent(state.weightMode)}`,
          { silent: true },
        );
        if (d?.success && Array.isArray(d.positions)) {
          state.positions = d.positions.map((p) => ({
            code: p.code,
            name: p.name || '',
            quantity: p.quantity,
            cost: p.cost || 0,
            currency: p.currency || '',
            note: p.note || '',
            last_price: p.last_price,
            market_value: p.market_value,
            weight_pct: p.weight_pct,
          }));
          state.enriched = [...state.positions];
          state.updatedAt = d.updated_at || null;
          writeLocal(state.positions.map(({ last_price, market_value, weight_pct, ...rest }) => rest));
          dispatchChange();
          if (!state.positions.length) {
            const local = readLocal();
            if (local.length) {
              state.positions = local;
              await enrichLocal();
            }
          }
          return;
        }
      }
      state.positions = readLocal();
      await enrichLocal();
      dispatchChange();
    } catch (e) {
      state.positions = readLocal();
      await enrichLocal();
      console.warn('allocation load', e);
    } finally {
      state.loading = false;
      render();
      refreshPortfolioHint();
    }
  }

  async function persist() {
    const slim = state.positions.map(({ last_price, market_value, weight_pct, ...rest }) => rest);
    writeLocal(slim);
    dispatchChange();
    const token = typeof Api !== 'undefined' && Api._token;
    if (!token) {
      await enrichLocal();
      window.StockQPro?.App?.toast?.('已保存至本機（登入後可同步雲端）', 'inf');
      render();
      refreshPortfolioHint();
      return;
    }
    try {
      const d = await Api.put(
        `/api/my-allocation?weight_mode=${encodeURIComponent(state.weightMode)}`,
        { positions: slim },
      );
      if (d?.success) {
        writeLocal(slim);
        window.StockQPro?.App?.toast?.('配置已同步', 'ok');
        window.StockQPro?.CurrencyManager?.loadData?.();
        await load();
        return;
      }
      if (d === null) {
        window.StockQPro?.App?.toast?.('雲端同步需 Pro，持倉已保留在本機', 'warn');
        await enrichLocal();
        render();
        refreshPortfolioHint();
        return;
      }
    } catch (e) {
      window.StockQPro?.App?.toast?.(`保存失敗：${e?.message || e}`, 'er');
    }
    await enrichLocal();
    render();
    refreshPortfolioHint();
  }

  async function mergeLocalToServer() {
    const local = readLocal();
    if (!local.length || !(typeof Api !== 'undefined' && Api._token)) return;
    try {
      const remote = await Api.get('/api/my-allocation', { silent: true });
      if ((remote?.positions || []).length > 0) return;
      await Api.put('/api/my-allocation', { positions: local });
    } catch (_) {}
  }

  function getDisplayRows() {
    return state.enriched.length ? state.enriched : state.positions;
  }

  function weightLabel() {
    return state.weightMode === 'quantity' ? '股數占比' : '市值占比';
  }

  async function refreshPortfolioHint() {
    const el = document.getElementById('alloc-rail-summary');
    if (!el) return;
    const rows = getDisplayRows();
    if (!rows.length) {
      el.textContent = '尚未添加持倉';
      return;
    }
    const totalMv = rows.reduce((s, r) => s + (Number(r.market_value) || 0), 0);
    if (!(typeof Api !== 'undefined' && Api._token)) {
      el.innerHTML = `<span class="alloc-rail-sub">${rows.length} 檔 · ${weightLabel()} · 登入後結算</span>`;
      return;
    }
    try {
      const curr = window.StockQPro?.CurrencyManager?.current || 'MOP';
      const d = await Api.get(`/api/portfolio/summary?currency=${curr}`, { silent: true });
      const fmt = window.StockQPro?.CurrencyManager?.format?.bind(window.StockQPro.CurrencyManager)
        || ((v) => Number(v).toFixed(2));
      if (d?.success) {
        el.innerHTML = `<span class="alloc-rail-total">${fmt(d.total_value)}</span>`
          + `<span class="alloc-rail-sub">${rows.length} 檔 · ${weightLabel()} · ${curr}</span>`;
        return;
      }
    } catch (_) {}
    el.innerHTML = `<span class="alloc-rail-total">${totalMv > 0 ? totalMv.toLocaleString() : '—'}</span>`
      + `<span class="alloc-rail-sub">${rows.length} 檔 · 估算市值 (${weightLabel()})</span>`;
  }

  function setOpen(on) {
    state.open = !!on;
    savePrefs();
    document.querySelector('.app')?.classList.toggle('allocation-rail-open', state.open);
    const rail = document.getElementById('allocation-rail');
    if (rail) rail.setAttribute('aria-hidden', state.open ? 'false' : 'true');
    const btn = document.getElementById('alloc-rail-toggle');
    if (btn) {
      btn.classList.toggle('on', state.open);
      btn.setAttribute('aria-expanded', state.open ? 'true' : 'false');
    }
    render();
  }

  function toggle() {
    setOpen(!state.open);
  }

  function setWeightMode(mode) {
    const m = mode === 'quantity' ? 'quantity' : 'market_value';
    if (m === state.weightMode) return;
    state.weightMode = m;
    savePrefs();
    document.querySelectorAll('[data-alloc-weight-mode]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-alloc-weight-mode') === m);
    });
    load();
  }

  function addPosition(raw) {
    const code = normalizeCode(raw?.code || raw?.symbol);
    const qty = Number(raw?.quantity ?? raw?.qty ?? 0);
    if (!code) {
      window.StockQPro?.App?.toast?.('請輸入代碼', 'er');
      return false;
    }
    if (!Number.isFinite(qty) || qty <= 0) {
      window.StockQPro?.App?.toast?.('請輸入有效股數', 'er');
      return false;
    }
    const row = {
      code,
      name: String(raw?.name || '').trim(),
      quantity: qty,
      cost: Number(raw?.cost ?? raw?.price ?? 0) || 0,
      currency: raw?.currency || '',
      note: raw?.note || '',
      asset_type: 'equity',
    };
    const idx = state.positions.findIndex((p) => p.code === code);
    if (idx >= 0) state.positions[idx] = { ...state.positions[idx], ...row };
    else state.positions.push(row);
    persist();
    return true;
  }

  function removePosition(code) {
    state.positions = state.positions.filter((p) => p.code !== normalizeCode(code));
    persist();
  }

  function getCodes() {
    return getDisplayRows().map((p) => p.code).filter(Boolean);
  }

  function getWeightMap() {
    const map = {};
    getDisplayRows().forEach((p) => {
      const w = Number(p.weight_pct);
      if (p.code && Number.isFinite(w) && w > 0) {
        map[p.code.toUpperCase()] = w / 100;
      }
    });
    return map;
  }

  function applyToBacktest() {
    const codes = getCodes();
    if (!codes.length) {
      window.StockQPro?.App?.toast?.('請先添加持倉', 'inf');
      return;
    }
    const code = codes[0];
    const pos = getDisplayRows().find((p) => p.code === code);
    window.StockQPro?.App?.nav?.('backtest');
    setTimeout(() => {
      const hidden = document.getElementById('bt-code');
      const input = document.getElementById('bt-code-input');
      const picked = document.getElementById('bt-picked-code');
      const nameEl = document.getElementById('bt-picked-name');
      if (hidden) hidden.value = /^\d{6}$/.test(code) ? code : code;
      if (input) input.value = code;
      if (picked) picked.textContent = code;
      if (nameEl) nameEl.textContent = pos?.name || code;
      if (window.StockQPro?.backtestSymbol?.setSymbol && /^\d{6}$/.test(code)) {
        window.StockQPro.backtestSymbol.setSymbol(code);
      }
      window.StockQPro?.App?.toast?.(`回測標的：${code}`, 'ok');
    }, 120);
  }

  function applyToCompare() {
    const rows = getDisplayRows();
    const codes = rows.map((p) => p.code).filter((c) => SU()?.isValidCompareSymbol?.(c) ?? true);
    if (codes.length < 2) {
      window.StockQPro?.App?.toast?.('多股對比至少需 2 檔有效標的（A股/港股/美股等）', 'inf');
      return;
    }
    window.StockQPro?.App?.nav?.('compare');
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent('stockq:allocation-import-compare', {
        detail: {
          codes,
          names: Object.fromEntries(rows.map((p) => [p.code, p.name || ''])),
        },
      }));
    }, 200);
  }

  function applyToPortfolio() {
    const rows = getDisplayRows();
    if (!rows.length) {
      window.StockQPro?.App?.toast?.('請先添加持倉', 'inf');
      return;
    }
    const strategy = document.getElementById('alloc-pf-strategy')?.value
      || state.portfolioStrategy
      || 'dual_ma';
    state.portfolioStrategy = strategy;
    savePrefs();
    const codes = rows.map((p) => p.code);
    const weightMap = getWeightMap();
    window.StockQPro?.App?.nav?.('portfolio');
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent('stockq:allocation-import-portfolio', {
        detail: {
          codes,
          weightMap,
          strategy,
          weightMode: state.weightMode,
        },
      }));
    }, 220);
  }

  async function syncToWatchlist() {
    const codes = getCodes();
    if (!codes.length) return;
    let n = 0;
    for (const code of codes) {
      try {
        await Api.post(`/api/watchlist/add?code=${encodeURIComponent(code)}`);
        n += 1;
      } catch (_) {}
    }
    window.StockQPro?.App?.toast?.(`已同步 ${n} 檔至自選`, 'ok');
  }

  function bindForm() {
    const form = document.getElementById('alloc-rail-form');
    if (!form || form.dataset.bound === '1') return;
    form.dataset.bound = '1';
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      addPosition({
        code: document.getElementById('alloc-in-code')?.value,
        quantity: document.getElementById('alloc-in-qty')?.value,
        cost: document.getElementById('alloc-in-cost')?.value,
        name: document.getElementById('alloc-in-name')?.value,
      });
      form.reset();
    });
  }

  function bindActions() {
    document.getElementById('alloc-act-backtest')?.addEventListener('click', applyToBacktest);
    document.getElementById('alloc-act-compare')?.addEventListener('click', applyToCompare);
    document.getElementById('alloc-act-portfolio')?.addEventListener('click', applyToPortfolio);
    document.getElementById('alloc-act-watchlist')?.addEventListener('click', () => syncToWatchlist());
    document.getElementById('alloc-rail-close')?.addEventListener('click', () => setOpen(false));
    document.querySelectorAll('[data-alloc-weight-mode]').forEach((btn) => {
      btn.addEventListener('click', () => {
        setWeightMode(btn.getAttribute('data-alloc-weight-mode'));
      });
    });
    const strat = document.getElementById('alloc-pf-strategy');
    if (strat) {
      strat.value = state.portfolioStrategy;
      strat.addEventListener('change', () => {
        state.portfolioStrategy = strat.value;
        savePrefs();
      });
    }
  }

  function render() {
    const list = document.getElementById('alloc-rail-list');
    const empty = document.getElementById('alloc-rail-empty');
    if (!list) return;

    document.querySelectorAll('[data-alloc-weight-mode]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-alloc-weight-mode') === state.weightMode);
    });

    if (state.loading) {
      list.innerHTML = '<p class="alloc-rail-hint"><span class="ld"></span> 載入中…</p>';
      return;
    }

    const rows = getDisplayRows();
    if (!rows.length) {
      list.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    const wl = weightLabel();
    list.innerHTML = rows.map((p) => {
      const w = Number(p.weight_pct);
      const wText = Number.isFinite(w) && w > 0 ? w.toFixed(1) : '—';
      const barW = Number.isFinite(w) && w > 0 ? Math.min(100, w) : 0;
      const label = p.name || p.code;
      const price = Number(p.last_price) > 0 ? Number(p.last_price).toFixed(2) : '—';
      const mv = Number(p.market_value) > 0 ? Number(p.market_value).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—';
      return `<div class="alloc-row" data-code="${p.code}">
        <div class="alloc-row-top">
          <span class="alloc-row-name" title="${p.code}">${label}</span>
          <button type="button" class="alloc-row-rm" data-rm="${p.code}" aria-label="移除">×</button>
        </div>
        <div class="alloc-row-meta">
          <span>${p.code}</span>
          <span>${Number(p.quantity).toLocaleString()} 股</span>
        </div>
        <div class="alloc-row-bar" aria-hidden="true"><span style="width:${barW}%"></span></div>
        <div class="alloc-row-foot"><span>${wl} ${wText}${wText === '—' ? '' : '%'}</span><span>現 ${price} · ${mv}</span></div>
      </div>`;
    }).join('');

    list.querySelectorAll('[data-rm]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        removePosition(btn.getAttribute('data-rm'));
      });
    });
    list.querySelectorAll('.alloc-row').forEach((row) => {
      row.addEventListener('click', () => {
        const sym = row.getAttribute('data-code');
        if (sym && window.StockQPro?.openAsset) window.StockQPro.openAsset(sym);
        else if (sym) window.StockQPro?.App?.nav?.('assets');
      });
    });
  }

  let _inited = false;

  function init() {
    if (_inited) {
      load();
      return;
    }
    _inited = true;
    if (typeof Api !== 'undefined' && Api.init) {
      try { Api.init(); } catch (_) {}
    }
    loadPrefs();
    document.querySelector('.app')?.classList.toggle('allocation-rail-open', state.open);
    const rail = document.getElementById('allocation-rail');
    if (rail) rail.setAttribute('aria-hidden', state.open ? 'false' : 'true');
    const btn = document.getElementById('alloc-rail-toggle');
    if (btn && btn.dataset.bound !== '1') {
      btn.dataset.bound = '1';
      btn.addEventListener('click', toggle);
    }
    bindForm();
    bindActions();
    load();
    window.addEventListener('stockq:auth-changed', () => {
      mergeLocalToServer().then(load);
    });
    window.addEventListener('portfolio:currencyChange', refreshPortfolioHint);
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.Allocation = {
    init,
    load,
    toggle,
    setOpen,
    setWeightMode,
    add: addPosition,
    remove: removePosition,
    getPositions: () => [...getDisplayRows()],
    getCodes,
    getWeightMap,
    applyToBacktest,
    applyToCompare,
    applyToPortfolio,
  };

  // 由 app.js 在 Api.init() 之後呼叫；若 app 未載入則 DOMContentLoaded 兜底
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setTimeout(() => {
        if (!_inited) init();
      }, 0);
    });
  } else {
    setTimeout(() => {
      if (!_inited) init();
    }, 0);
  }
})();
