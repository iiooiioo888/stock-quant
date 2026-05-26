/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);

  const HOT_A_SHARE = [
    { code: '600519', name: '貴州茅台' },
    { code: '600036', name: '招商銀行' },
    { code: '000001', name: '平安銀行' },
    { code: '000858', name: '五糧液' },
    { code: '601318', name: '中國平安' },
    { code: '300750', name: '寧德時代' },
    { code: '002594', name: '比亞迪' },
    { code: '600900', name: '長江電力' },
  ];

  let namesMap = {};
  let catalogAshare = [];
  let searchTimer = null;
  let pickMode = 'code';

  function normalizeCode(raw) {
    const s = String(raw || '').trim();
    if (/^\d{1,6}$/.test(s)) return s.padStart(6, '0');
    const m = s.match(/(\d{6})/);
    if (m) return m[1];
    if (s.includes('.')) return s.split('.')[0].replace(/\D/g, '').padStart(6, '0').slice(-6);
    return s;
  }

  function isValidAshare(code) {
    return /^\d{6}$/.test(code);
  }

  function resolveName(code) {
    return namesMap[code] || catalogAshare.find((x) => x.code === code)?.name || '';
  }

  function setSymbol(code, name = '') {
    const c = normalizeCode(code);
    if (!isValidAshare(c)) {
      window.StockQPro?.App?.toast?.('請選擇 6 位 A 股代碼', 'er');
      return false;
    }
    const n = name || resolveName(c) || c;
    const hidden = $id('bt-code');
    if (hidden) hidden.value = c;
    const codeEl = $id('bt-picked-code');
    const nameEl = $id('bt-picked-name');
    const input = $id('bt-code-input');
    if (codeEl) codeEl.textContent = c;
    if (nameEl) nameEl.textContent = n;
    if (input && input !== document.activeElement) input.value = c;
    return true;
  }

  function getSymbol() {
    return normalizeCode($id('bt-code')?.value || $id('bt-code-input')?.value);
  }

  function switchPickMode(mode) {
    pickMode = mode;
    document.querySelectorAll('[data-bt-pick]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-bt-pick') === mode);
    });
    document.querySelectorAll('.bt-pick-panel').forEach((pane) => {
      pane.classList.toggle('on', pane.getAttribute('data-bt-pick-panel') === mode);
    });
    if (mode === 'watch') loadWatchlist();
    if (mode === 'catalog' && !catalogAshare.length) loadCatalog();
  }

  function renderPickList(containerId, items, emptyText) {
    const el = $id(containerId);
    if (!el) return;
    if (!items.length) {
      el.innerHTML = `<div class="bt-pick-empty">${emptyText}</div>`;
      return;
    }
    el.innerHTML = items.map((it) => `
      <button type="button" class="bt-pick-item" data-code="${it.code}" data-name="${(it.name || '').replace(/"/g, '&quot;')}">
        <span class="bt-pick-item-code">${it.code}</span>
        <span class="bt-pick-item-name">${it.name || it.code}</span>
        ${it.extra ? `<span class="bt-pick-item-extra">${it.extra}</span>` : ''}
      </button>`).join('');
    el.querySelectorAll('.bt-pick-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        setSymbol(btn.getAttribute('data-code'), btn.getAttribute('data-name'));
        window.StockQPro?.App?.toast?.(`已選 ${btn.getAttribute('data-code')}`, 'ok');
      });
    });
  }

  async function loadNames() {
    try {
      const d = await Api.get('/api/stocks/names');
      namesMap = d?.names || {};
    } catch (_) {
      namesMap = {};
    }
  }

  async function loadCatalog() {
    const el = $id('bt-pick-catalog');
    if (el) el.innerHTML = '<div class="bt-pick-empty">載入中…</div>';
    try {
      const d = await Api.getAssetsCatalog();
      const list = (d?.instruments || [])
        .filter((i) => i.group === 'a_share' && i.asset_class === 'stock')
        .map((i) => {
          const code = normalizeCode(i.symbol);
          return { code, name: i.name || code, symbol: i.symbol };
        })
        .filter((i) => isValidAshare(i.code));
      const seen = new Set();
      catalogAshare = list.filter((i) => {
        if (seen.has(i.code)) return false;
        seen.add(i.code);
        return true;
      });
      if (!catalogAshare.length && Object.keys(namesMap).length) {
        catalogAshare = Object.entries(namesMap)
          .map(([code, name]) => ({ code: normalizeCode(code), name: name || code }))
          .filter((i) => isValidAshare(i.code));
      }
      renderPickList('bt-pick-catalog', catalogAshare, '資產庫暫無 A 股標的');
    } catch (_) {
      if (Object.keys(namesMap).length) {
        catalogAshare = Object.entries(namesMap)
          .map(([code, name]) => ({ code: normalizeCode(code), name: name || code }))
          .filter((i) => isValidAshare(i.code));
        renderPickList('bt-pick-catalog', catalogAshare, '資產庫暫無 A 股標的');
      } else if (el) {
        el.innerHTML = '<div class="bt-pick-empty">載入資產庫失敗</div>';
      }
    }
  }

  async function loadWatchlist() {
    const el = $id('bt-pick-watch');
    if (el) el.innerHTML = '<div class="bt-pick-empty">載入中…</div>';
    let items = [];
    try {
      const d = await Api.getWatchlist();
      items = (d?.items || []).map((x) => ({ code: x.code, name: x.name }));
    } catch (_) {
      try {
        const leg = await Api.getAlertRules();
        items = Object.entries(leg?.rules || {}).map(([code, rule]) => ({
          code,
          name: rule?.name || code,
        }));
      } catch (__) { /* ignore */ }
    }
    items = items.filter((x) => isValidAshare(normalizeCode(x.code)));
    renderPickList('bt-pick-watch', items, '自選列表為空，請先在「自選股」添加');
  }

  function renderHot() {
    renderPickList('bt-pick-hot', HOT_A_SHARE, '');
  }

  async function runSearch() {
    const q = String($id('bt-search-q')?.value || '').trim();
    const el = $id('bt-pick-search');
    if (!q) {
      if (el) el.innerHTML = '<div class="bt-pick-empty">輸入代碼或名稱關鍵字</div>';
      return;
    }
    if (el) el.innerHTML = '<div class="bt-pick-empty">搜索中…</div>';
    try {
      const d = await Api.getStockUniverse('a_share', 30, 0, q);
      const rows = (d?.stocks || []).map((s) => ({
        code: normalizeCode(s.code),
        name: s.name || namesMap[s.code] || s.code,
        extra: s.industry || '',
      })).filter((x) => isValidAshare(x.code));
      renderPickList('bt-pick-search', rows, '未找到匹配標的');
    } catch (_) {
      const local = Object.entries(namesMap)
        .filter(([code, name]) => code.includes(q) || String(name).includes(q))
        .slice(0, 30)
        .map(([code, name]) => ({ code: normalizeCode(code), name }));
      renderPickList('bt-pick-search', local.filter((x) => isValidAshare(x.code)), '搜索失敗，請改試代碼輸入');
    }
  }

  function onCodeInput() {
    const raw = String($id('bt-code-input')?.value || '').trim();
    const c = normalizeCode(raw);
    if (isValidAshare(c)) {
      setSymbol(c, resolveName(c));
      const sug = $id('bt-code-suggest');
      if (sug) sug.hidden = true;
      return;
    }
    if (raw.length < 1) return;
    const hits = Object.entries(namesMap)
      .filter(([code, name]) => code.startsWith(raw) || String(name).includes(raw))
      .slice(0, 8)
      .map(([code, name]) => ({ code: normalizeCode(code), name }));
    const sug = $id('bt-code-suggest');
    if (!sug) return;
    if (!hits.length) {
      sug.hidden = true;
      return;
    }
    sug.hidden = false;
    sug.innerHTML = hits.map((h) => `
      <button type="button" class="bt-suggest-item" data-code="${h.code}" data-name="${h.name}">
        <span>${h.code}</span> ${h.name}
      </button>`).join('');
    sug.querySelectorAll('.bt-suggest-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        setSymbol(btn.getAttribute('data-code'), btn.getAttribute('data-name'));
        sug.hidden = true;
      });
    });
  }

  function bindOnce() {
    const root = $id('bt-symbol-card');
    if (!root || root.dataset.bound) return;
    root.dataset.bound = '1';

    document.querySelectorAll('[data-bt-pick]').forEach((btn) => {
      btn.addEventListener('click', () => switchPickMode(btn.getAttribute('data-bt-pick') || 'code'));
    });

    $id('bt-code-input')?.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(onCodeInput, 200);
    });
    $id('bt-code-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const c = normalizeCode($id('bt-code-input')?.value);
        if (isValidAshare(c)) setSymbol(c, resolveName(c));
      }
    });

    $id('bt-search-btn')?.addEventListener('click', runSearch);
    $id('bt-search-q')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runSearch();
    });

    $id('bt-pick-assets-nav')?.addEventListener('click', () => {
      window.StockQPro?.App?.nav?.('assets', { syncHash: true });
    });

    $id('bt-open-asset')?.addEventListener('click', () => {
      const c = getSymbol();
      if (c && window.StockQPro?.openAsset) window.StockQPro.openAsset(c);
    });
  }

  async function init() {
    bindOnce();
    await loadNames();
    renderHot();
    const initial = normalizeCode($id('bt-code')?.value || '600519');
    setSymbol(initial, resolveName(initial) || '貴州茅台');
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.backtestSymbol = {
    init,
    setSymbol,
    getSymbol,
    normalizeCode,
    isValidAshare,
  };
})();
