/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);

  const pickData = () => window.StockQPro?.stockPickData;

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
    if (mode === 'hot') renderHot();
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
      const loader = pickData()?.loadCatalogAshare;
      catalogAshare = loader ? await loader(namesMap) : [];
      const hint = catalogAshare.length
        ? `共 ${catalogAshare.length} 檔 A 股，可滾動瀏覽`
        : '資產庫暫無 A 股標的';
      if (catalogAshare.length) {
        const head = el?.previousElementSibling;
        if (head?.classList?.contains('bt-pick-hint')) {
          head.textContent = hint;
        }
      }
      renderPickList('bt-pick-catalog', catalogAshare, '資產庫暫無 A 股標的');
    } catch (_) {
      if (el) el.innerHTML = '<div class="bt-pick-empty">載入資產庫失敗</div>';
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

  async function renderHot() {
    const el = $id('bt-pick-hot');
    if (el) el.innerHTML = '<div class="bt-pick-empty">載入熱門…</div>';
    const rows = pickData()?.fetchHotAshare
      ? await pickData().fetchHotAshare(namesMap, 48)
      : (pickData()?.FALLBACK_HOT || []);
    renderPickList('bt-pick-hot', rows, '暫無熱門標的');
  }

  async function runSearch() {
    const q = String($id('bt-search-q')?.value || '').trim();
    const el = $id('bt-pick-search');
    if (!q) {
      if (el) el.innerHTML = '<div class="bt-pick-empty">輸入代碼或名稱關鍵字</div>';
      return;
    }
    if (el) el.innerHTML = '<div class="bt-pick-empty">搜索中…</div>';
    const rows = pickData()?.searchAshare
      ? await pickData().searchAshare(q, namesMap, 80)
      : [];
    renderPickList('bt-pick-search', rows, '未找到匹配標的');
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
    const hits = pickData()?.suggestFromNames
      ? pickData().suggestFromNames(raw, namesMap, 20)
      : [];
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
    await renderHot();
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
