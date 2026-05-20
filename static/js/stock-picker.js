/**
 * stock-picker.js — 全站共用股票選擇器
 *
 * 保留原 input id 作為資料來源，將回測同款 UI 掛在輸入欄位旁。
 */

const StockPicker = {
  _UNIVERSE_MAX: 20000,
  _ROW_H: 36,
  _stocks: [],
  _loading: null,
  _MARKET_LABELS: {
    all: '全部',
    a_share: 'A 股',
    hk_stock: '港股',
    us_stock: '美股',
  },
  _MARKET_ORDER: ['all', 'a_share', 'hk_stock', 'us_stock'],
  _DEFAULT_STOCKS: [
    { code: '000001', name: '平安銀行', market: 'a_share', rank: 1 },
    { code: '600519', name: '貴州茅台', market: 'a_share', rank: 2 },
    { code: '000858', name: '五糧液', market: 'a_share', rank: 3 },
    { code: '00700', name: '騰訊控股', market: 'hk_stock', rank: 4 },
    { code: 'AAPL', name: 'Apple', market: 'us_stock', rank: 5 },
  ],

  initAll() {
    const singles = [
      ['optCode', '選擇優化標的'],
      ['wfCode', '選擇 Walk-Forward 標的'],
      ['hmCode', '選擇熱力圖標的'],
      ['histCode', '篩選回測股票'],
      ['cfCode', '選擇資金流向標的'],
      ['basicsCode', '選擇基本數據標的'],
    ];
    const multis = [
      ['pfCodes', '選擇組合標的'],
      ['cmpCodes', '選擇對比股票'],
      ['sigCodes', '選擇信號評分股票'],
      ['dbDownloadCodes', '選擇下載股票'],
    ];

    singles.forEach(([id, title]) => this.attach(id, { mode: 'single', title }));
    multis.forEach(([id, title]) => this.attach(id, { mode: 'multi', title }));
  },

  attach(inputId, options = {}) {
    const input = document.getElementById(inputId);
    if (!input || input.dataset.stockPickerBound) return;
    input.dataset.stockPickerBound = '1';

    const mode = options.mode || 'single';
    const state = {
      input,
      inputId,
      mode,
      title: options.title || '選擇股票',
      activeMarket: 'all',
      query: '',
    };

    input.classList.add('stock-picker-source');
    input.setAttribute('aria-hidden', 'true');

    const shell = document.createElement('div');
    shell.className = 'stock-picker-embed';
    shell.dataset.stockPickerFor = inputId;
    shell.innerHTML = this._template(state);
    input.insertAdjacentElement('afterend', shell);

    state.shell = shell;
    state.manual = shell.querySelector('[data-sp-manual]');
    state.search = shell.querySelector('[data-sp-search]');
    state.tabs = shell.querySelector('[data-sp-tabs]');
    state.grid = shell.querySelector('[data-sp-grid]');
    state.hint = shell.querySelector('[data-sp-hint]');
    state.selectedCode = shell.querySelector('[data-sp-selected-code]');
    state.selectedName = shell.querySelector('[data-sp-selected-name]');
    state.selectedLetter = shell.querySelector('[data-sp-selected-letter]');
    state.selectedIcon = shell.querySelector('[data-sp-selected-icon]');

    state.manual.value = input.value || '';
    this._bind(state);
    this._syncSelected(state);
    this._ensureStocks().then(() => {
      this._renderTabs(state);
      this._renderGrid(state);
      this._syncSelected(state);
    });
  },

  async _ensureStocks() {
    if (this._stocks.length) return this._stocks;
    if (this._loading) return this._loading;
    this._loading = (async () => {
      try {
        const data = await Api.getStocks(this._UNIVERSE_MAX);
        const stocks = (data?.stocks || [])
          .map((s, idx) => this._normalizeStock(s, idx))
          .filter(Boolean);
        this._stocks = stocks.length ? stocks : this._DEFAULT_STOCKS;
      } catch (err) {
        console.warn('stock picker universe load failed', err);
        this._stocks = this._DEFAULT_STOCKS;
      }
      return this._stocks;
    })();
    return this._loading;
  },

  _template(state) {
    const inputLabel = state.mode === 'multi' ? '代碼列表' : '股票代碼';
    return `
      <div class="bt-stock-section stock-picker-section">
        <div class="bt-section-head">
          <h3>${this._esc(state.title)}</h3>
          <span class="bt-load-hint" data-sp-hint>載入股票庫...</span>
        </div>
        <div class="stock-code-picker">
          <div class="bt-stock-toolbar">
            <div class="bt-selected-stock" title="當前選中">
              <div class="stock-code-icon bt-selected-icon">
                <img data-sp-selected-icon width="48" height="48" alt="">
                <span class="stock-code-letter" data-sp-selected-letter>?</span>
              </div>
              <div class="bt-selected-meta">
                <span class="bt-selected-code" data-sp-selected-code>—</span>
                <span class="bt-selected-name" data-sp-selected-name>未選擇</span>
              </div>
            </div>
            <input type="text" class="input-sm bt-code-manual stock-picker-manual" data-sp-manual placeholder="${inputLabel}" autocomplete="off">
            <input type="search" class="input-sm bt-code-search" data-sp-search placeholder="搜尋股票庫（代碼 / 名稱）…" autocomplete="off">
          </div>
          <div class="bt-market-tabs" data-sp-tabs role="tablist" aria-label="${this._esc(state.title)}市場分類"></div>
          <div class="stock-code-grid" data-sp-grid role="listbox" aria-label="${this._esc(state.title)}"></div>
        </div>
      </div>`;
  },

  _bind(state) {
    state.manual.addEventListener('input', () => {
      state.input.value = state.manual.value;
      state.input.dispatchEvent(new Event('input', { bubbles: true }));
      this._syncSelected(state);
      this._refreshActiveRows(state);
    });

    state.manual.addEventListener('change', () => {
      state.input.value = state.manual.value.trim();
      state.manual.value = state.input.value;
      state.input.dispatchEvent(new Event('change', { bubbles: true }));
      this._syncSelected(state);
      this._refreshActiveRows(state);
    });

    state.search.addEventListener('input', () => {
      state.query = state.search.value.trim().toLowerCase();
      this._renderGrid(state);
    });

    state.tabs.addEventListener('click', e => {
      const btn = e.target.closest('[data-market]');
      if (!btn) return;
      state.activeMarket = btn.dataset.market || 'all';
      this._renderTabs(state);
      this._renderGrid(state);
    });

    state.grid.addEventListener('click', e => {
      const row = e.target.closest('[data-code]');
      if (!row) return;
      const code = row.dataset.code || '';
      if (state.mode === 'multi') {
        const codes = this._parseCodes(state.input.value);
        if (!codes.includes(code)) codes.push(code);
        state.input.value = codes.join(',');
      } else {
        state.input.value = code;
      }
      state.manual.value = state.input.value;
      state.input.dispatchEvent(new Event('input', { bubbles: true }));
      state.input.dispatchEvent(new Event('change', { bubbles: true }));
      this._syncSelected(state);
      this._refreshActiveRows(state);
    });
  },

  _normalizeStock(item, idx = 0) {
    const code = String(item?.code || item?.symbol || '').trim();
    if (!code) return null;
    return {
      code,
      name: String(item?.name || item?.stock_name || item?.company_name || code).trim(),
      market: item?.market || item?.market_type || 'a_share',
      rank: Number(item?.rank_mv || item?.rank || idx + 1),
    };
  },

  _parseCodes(value) {
    return String(value || '')
      .split(/[\s,，;；]+/)
      .map(s => s.trim())
      .filter(Boolean);
  },

  _selectedCodes(state) {
    return state.mode === 'multi' ? this._parseCodes(state.input.value) : [String(state.input.value || '').trim()].filter(Boolean);
  },

  _findStock(code) {
    return this._stocks.find(s => String(s.code).toUpperCase() === String(code).toUpperCase());
  },

  _syncSelected(state) {
    const codes = this._selectedCodes(state);
    const first = codes[0] || '';
    const stock = this._findStock(first);
    const name = stock?.name || first || '未選擇';
    const label = state.mode === 'multi'
      ? (codes.length ? `${codes.length} 隻` : '—')
      : (first || '—');
    state.selectedCode.textContent = label;
    state.selectedName.textContent = state.mode === 'multi' && codes.length
      ? codes.slice(0, 4).join(', ') + (codes.length > 4 ? '...' : '')
      : name;
    state.selectedLetter.textContent = (name.replace(/\s/g, '') || first || '?').slice(0, 1);
    state.shell.querySelector('.bt-selected-stock')?.classList.toggle('bt-selected-stock--empty', !codes.length);
    if (state.selectedIcon && first && typeof Utils !== 'undefined') {
      Utils.bindStockIcon(state.selectedIcon, first, name, stock?.market || '');
    }
  },

  _counts() {
    const counts = { all: this._stocks.length, a_share: 0, hk_stock: 0, us_stock: 0 };
    this._stocks.forEach(s => {
      if (counts[s.market] != null) counts[s.market] += 1;
    });
    return counts;
  },

  _renderTabs(state) {
    const counts = this._counts();
    state.tabs.replaceChildren();
    this._MARKET_ORDER
      .filter(m => m === 'all' || counts[m] > 0)
      .forEach(market => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'bt-market-tab';
        btn.classList.toggle('a', state.activeMarket === market);
        btn.dataset.market = market;
        btn.setAttribute('role', 'tab');
        btn.setAttribute('aria-selected', String(state.activeMarket === market));
        btn.innerHTML = `<span>${this._esc(this._MARKET_LABELS[market] || market)}</span><strong>${counts[market] || 0}</strong>`;
        state.tabs.appendChild(btn);
      });
  },

  _displayList(state) {
    const q = state.query;
    return this._stocks.filter(s => {
      if (state.activeMarket !== 'all' && s.market !== state.activeMarket) return false;
      if (!q) return true;
      return s.code.toLowerCase().includes(q) || s.name.toLowerCase().includes(q);
    });
  },

  _renderGrid(state) {
    if (!this._stocks.length) {
      state.grid.innerHTML = '<div class="state-loading"><span class="ld"></span> 載入股票庫...</div>';
      return;
    }
    const list = this._displayList(state);
    const suffix = state.query ? `，篩選 ${list.length} 隻` : '';
    state.hint.textContent = `已載入 ${this._stocks.length} 隻${suffix}`;
    if (!list.length) {
      state.grid.innerHTML = '<div class="state-empty"><span class="state-icon">🔍</span><span class="state-text">找不到符合條件的股票</span></div>';
      return;
    }

    state.grid.innerHTML = `
      <div class="stock-universe-viewport stock-picker-viewport">
        <div class="stock-universe-spacer"></div>
        <div class="stock-universe-rows"></div>
      </div>`;
    const viewport = state.grid.querySelector('.stock-universe-viewport');
    viewport._stockPickerState = state;
    viewport._stockPickerList = list;
    viewport.addEventListener('scroll', () => this._paint(viewport), { passive: true });
    this._paint(viewport);
  },

  _paint(viewport) {
    const state = viewport._stockPickerState;
    const list = viewport._stockPickerList || [];
    const spacer = viewport.querySelector('.stock-universe-spacer');
    const rows = viewport.querySelector('.stock-universe-rows');
    if (!state || !spacer || !rows) return;

    spacer.style.height = `${list.length * this._ROW_H}px`;
    const start = Math.max(0, Math.floor(viewport.scrollTop / this._ROW_H) - 4);
    const count = Math.ceil((viewport.clientHeight || 260) / this._ROW_H) + 8;
    const end = Math.min(list.length, start + count);
    const selected = new Set(this._selectedCodes(state));

    rows.style.transform = `translateY(${start * this._ROW_H}px)`;
    rows.replaceChildren();
    for (let i = start; i < end; i++) {
      rows.appendChild(this._row(list[i], selected));
    }
  },

  _row(item, selected) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'stock-code-row';
    row.classList.toggle('a', selected.has(item.code));
    row.dataset.code = item.code;
    row.dataset.name = item.name || '';
    row.title = `${item.code} ${item.name}`;

    const iconWrap = document.createElement('span');
    iconWrap.className = 'stock-code-row-icon stock-code-icon';
    const img = document.createElement('img');
    img.width = 28;
    img.height = 28;
    Utils.bindStockIcon(img, item.code, item.name, item.market);
    iconWrap.appendChild(img);

    const rank = document.createElement('span');
    rank.className = 'stock-code-row-rank';
    rank.textContent = item.rank ? `#${item.rank}` : '';

    const code = document.createElement('span');
    code.className = 'stock-code-row-code';
    code.textContent = item.code;

    const name = document.createElement('span');
    name.className = 'stock-code-row-name';
    name.textContent = item.name || item.code;

    row.append(iconWrap, rank, code, name);
    return row;
  },

  _refreshActiveRows(state) {
    const viewport = state.grid.querySelector('.stock-universe-viewport');
    if (viewport) this._paint(viewport);
  },

  _esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[ch]));
  },
};

window.StockPicker = StockPicker;

document.addEventListener('DOMContentLoaded', () => {
  // 兼容已快取的 app.js：即使 App.init 尚未包含 StockPicker，也能自行掛載。
  setTimeout(() => {
    if (window.StockPicker) window.StockPicker.initAll();
  }, 0);
});
