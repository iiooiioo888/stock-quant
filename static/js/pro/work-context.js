/**
 * 工作標的上下文：選一次代碼，總覽 / 回測 / 對比 / 分析 / 優化共用。
 */
(() => {
  const PAGE_TITLE = {
    dashboard: '總覽', tasks: '任務中心', watchlist: '自選股', scanner: '選股器',
    alerts: '預警', strategies: '策略庫', backtest: '策略回測', compare: '對比',
    portfolio: '持倉與淨值', backhistory: '回測歷史', optimize: '參數優化',
    walkforward: '滾動驗證', heatmap: '熱力圖', reports: '策略報告',
    assets: '資產庫', capitalflow: '資金流', data: '數據中心', analysis: '深度分析',
    signals: '信號', markets: '市場', crypto: '加密', scheduler: '定時',
    connectivity: '數據源', ai: 'AI', pricing: '定價', settings: '設定',
  };

  const LEGACY_IDS = ['optCode', 'wfCode', 'hmCode', 'anCode', 'anCodeManual', 'basicsCode', 'cfCode'];

  const GO_PAGES = ['backtest', 'compare', 'analysis', 'optimize', 'watchlist', 'signals', 'heatmap', 'walkforward'];

  /** 當前頁建議的下一步（減少來回找選單） */
  const NEXT = {
    dashboard: [
      { p: 'data', n: '下載數據' },
      { p: 'backtest', n: '開始回測' },
      { p: 'scanner', n: '選股' },
    ],
    data: [{ p: 'backtest', n: '去回測' }, { p: 'connectivity', n: '檢查數據源' }],
    strategies: [{ p: 'backtest', n: '用策略回測' }, { p: 'compare', n: '對比' }],
    backtest: [
      { p: 'tasks', n: '看任務進度' },
      { p: 'optimize', n: '優化參數' },
      { p: 'compare', n: '多股對比' },
    ],
    optimize: [{ p: 'walkforward', n: '滾動驗證' }, { p: 'heatmap', n: '熱力圖' }, { p: 'backtest', n: '回測' }],
    walkforward: [{ p: 'heatmap', n: '熱力圖' }, { p: 'backhistory', n: '歷史' }],
    heatmap: [{ p: 'backtest', n: '回測' }, { p: 'optimize', n: '優化' }],
    compare: [{ p: 'portfolio', n: '持倉結算' }, { p: 'backhistory', n: '歷史' }],
    portfolio: [{ p: 'backhistory', n: '回測歷史' }, { p: 'reports', n: '報告' }],
    backhistory: [{ p: 'compare', n: '對比' }, { p: 'reports', n: '報告' }],
    scanner: [{ p: 'watchlist', n: '加入自選' }, { p: 'backtest', n: '回測' }],
    watchlist: [{ p: 'alerts', n: '設預警' }, { p: 'backtest', n: '回測' }, { p: 'compare', n: '對比' }],
    alerts: [{ p: 'watchlist', n: '自選股' }, { p: 'tasks', n: '任務' }],
    assets: [{ p: 'backtest', n: '回測' }, { p: 'analysis', n: '分析' }, { p: 'compare', n: '對比' }],
    analysis: [{ p: 'signals', n: '信號' }, { p: 'backtest', n: '回測' }],
    signals: [{ p: 'alerts', n: '預警' }, { p: 'watchlist', n: '自選' }],
    tasks: [{ p: 'backhistory', n: '回測歷史' }, { p: 'backtest', n: '再跑一次' }],
    capitalflow: [{ p: 'scanner', n: '選股' }, { p: 'markets', n: '市場' }],
    markets: [{ p: 'assets', n: '資產庫' }, { p: 'crypto', n: '加密' }],
    reports: [{ p: 'backhistory', n: '歷史' }, { p: 'dashboard', n: '總覽' }],
  };

  function prefs() {
    return window.StockQPro?.Prefs;
  }

  function get() {
    const p = prefs()?.load?.() || {};
    const symbol = String(p.lastSymbol || '').trim();
    const name = String(p.lastSymbolName || '').trim();
    return { symbol, name };
  }

  function set(symbol, name = '') {
    const raw = String(symbol || '').trim();
    if (!raw) return get();
    const SU = window.StockQPro?.SymbolUtils;
    const code = SU?.normalizeAssetSymbol?.(raw) || raw.toUpperCase();
    const nm = String(name || '').trim();
    const cur = get();
    if (cur.symbol === code && (!nm || cur.name === nm)) {
      render();
      return get();
    }
    prefs()?.save?.({ lastSymbol: code, lastSymbolName: nm || cur.name || '' });
    render();
    return get();
  }

  function commitInput() {
    const top = document.getElementById('work-ctx-in');
    const dash = document.getElementById('dash-launch-in');
    const focused = document.activeElement;
    const el = (focused === dash || focused === top)
      ? focused
      : (String(dash?.value || '').trim() ? dash : top);
    const raw = String(el?.value || '').trim();
    if (raw) set(raw);
    return get();
  }

  function fillLegacy(code) {
    LEGACY_IDS.forEach((id) => {
      const el = document.getElementById(id);
      if (el && 'value' in el) el.value = code;
    });
    const sel = document.getElementById('anSelectedCode');
    if (sel) sel.textContent = code;
  }

  function applyToPage(pageId) {
    const { symbol, name } = get();
    if (!symbol) return;
    if (pageId === 'backtest') {
      const bt = window.StockQPro?.backtestSymbol;
      const c = String(symbol).replace(/\D/g, '');
      const ashare = c.length <= 6 ? c.padStart(6, '0') : '';
      if (bt?.setSymbol && /^\d{6}$/.test(ashare) && !/\.(HK|US)$/i.test(symbol)) {
        bt.setSymbol(ashare, name);
        return;
      }
      const el = document.getElementById('bt-code');
      if (el) el.value = symbol;
      return;
    }
    if (pageId === 'compare') {
      window.StockQPro?.pages?.compare?.applyWorkSymbol?.(symbol, name);
      return;
    }
    if (pageId === 'watchlist') {
      const el = document.getElementById('wl-code-input');
      if (el) el.value = symbol.replace(/\D/g, '').slice(-6) || symbol;
      return;
    }
    if (['optimize', 'walkforward', 'heatmap', 'analysis', 'signals', 'data'].includes(pageId)) {
      fillLegacy(symbol.replace(/\D/g, '').padStart(6, '0').slice(-6) || symbol);
    }
  }

  function go(action) {
    commitInput();
    const { symbol, name } = get();
    const App = window.StockQPro?.App;
    if (action === 'detail') {
      if (symbol) App?.openAsset?.(symbol);
      else App?.nav?.('assets', { syncHash: true });
      return;
    }
    if (!GO_PAGES.includes(action) && action !== 'assets') return;
    const page = action === 'assets' ? 'assets' : action;
    App?.nav?.(page, { syncHash: true });
    setTimeout(() => applyToPage(page), 80);
    if (symbol && page === 'compare') {
      setTimeout(() => window.StockQPro?.pages?.compare?.applyWorkSymbol?.(symbol, name), 120);
    }
  }

  function renderStrip() {
    const host = document.getElementById('work-ctx');
    if (!host) return;
    host.hidden = false;
    const { symbol, name } = get();
    const inEl = document.getElementById('work-ctx-in');
    const nameEl = document.getElementById('work-ctx-name');
    if (inEl && document.activeElement !== inEl) inEl.value = symbol || '';
    if (nameEl) nameEl.textContent = name || (symbol ? '' : 'Enter 設定');
    const dashIn = document.getElementById('dash-launch-in');
    if (dashIn && document.activeElement !== dashIn) dashIn.value = symbol || '';
    const dashName = document.getElementById('dash-launch-name');
    if (dashName) dashName.textContent = symbol ? `${symbol}${name ? ' · ' + name : ''}` : '尚未設定工作標的';
  }

  function renderRecents() {
    const host = document.getElementById('nav-recents');
    if (!host) return;
    const rec = (prefs()?.get?.('recentPages') || []).filter((p) => p && p !== 'dashboard').slice(0, 5);
    if (!rec.length) {
      host.hidden = true;
      host.innerHTML = '';
      return;
    }
    host.hidden = false;
    host.innerHTML = '<span class="nav-recents-lbl">最近</span>' + rec.map((p) => (
      `<button type="button" class="nav-recent-chip" data-nav-recent="${p}">${PAGE_TITLE[p] || p}</button>`
    )).join('');
  }

  function renderNext() {
    const host = document.getElementById('nav-next');
    if (!host) return;
    const pid = window.StockQPro?.App?.current || 'dashboard';
    const steps = NEXT[pid] || [{ p: 'dashboard', n: '回總覽' }, { p: 'backtest', n: '回測' }];
    host.innerHTML = '<span class="nav-recents-lbl">下一步</span>' + steps.map((s) => (
      `<button type="button" class="nav-recent-chip nav-next-chip" data-nav-next="${s.p}">${s.n}</button>`
    )).join('');
  }

  function render() {
    renderStrip();
    renderRecents();
    renderNext();
  }

  function bind() {
    document.addEventListener('click', (e) => {
      const goBtn = e.target.closest('[data-ctx-go]');
      if (goBtn) {
        const act = goBtn.getAttribute('data-ctx-go');
        if (act) go(act);
        return;
      }
      const next = e.target.closest('[data-nav-next]');
      if (next) {
        const p = next.getAttribute('data-nav-next');
        if (p) {
          window.StockQPro?.App?.nav?.(p, { syncHash: true });
          setTimeout(() => applyToPage(p), 80);
        }
      }
    });
    document.getElementById('work-ctx-open')?.addEventListener('click', () => go('detail'));
    const onEnter = (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const raw = String(e.target.value || '').trim();
      if (raw) set(raw);
      window.StockQPro?.App?.toast?.(raw ? `工作標的：${get().symbol}` : '請輸入代碼', raw ? 'ok' : 'inf');
    };
    document.getElementById('work-ctx-in')?.addEventListener('keydown', onEnter);
    document.getElementById('nav-recents')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-nav-recent]');
      if (!btn) return;
      const p = btn.getAttribute('data-nav-recent');
      if (p) {
        window.StockQPro?.App?.nav?.(p, { syncHash: true });
        setTimeout(() => applyToPage(p), 80);
      }
    });
    window.addEventListener('stockq:prefs-changed', () => render());
  }

  function focusInput() {
    const el = document.getElementById('work-ctx-in');
    if (!el) return;
    el.focus();
    el.select?.();
  }

  function init() {
    bind();
    render();
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.WorkContext = {
    get, set, go, applyToPage, render, init, focusInput, commitInput, PAGE_TITLE, NEXT,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
