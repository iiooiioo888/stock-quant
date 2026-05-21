/**
 * stock-detail.js — 每支股票獨立詳情頁（#/stock/代碼）
 * TradingView K 線牆 + Polymarket 相關市場
 */
const StockDetail = {
  _code: '',
  _name: '',
  _loading: false,
  _indexList: [],
  _routerReady: false,

  initRouter() {
    if (this._routerReady) return;
    this._routerReady = true;
    window.addEventListener('hashchange', () => this.routeFromHash(false));
    window.addEventListener('popstate', () => this.routeFromHash(false));
  },

  /** 解析 hash，返回是否已處理 */
  routeFromHash(pushTab = true) {
    const raw = (location.hash || '').replace(/^#/, '').trim();
    const parts = raw.split('/').filter(Boolean);

    if (parts[0] === 'stock' && parts[1]) {
      const code = decodeURIComponent(parts[1]);
      this._showDetailView(code, false);
      if (pushTab && typeof App !== 'undefined') App.loadTab('stock-detail');
      return true;
    }

    if (parts[0] === 'stocks' || raw === 'stock-detail' || raw === 'stock') {
      this.showIndex(false);
      if (pushTab && typeof App !== 'undefined') App.loadTab('stock-detail');
      return true;
    }

    return false;
  },

  _stockPath(code) {
    return `/stock/${encodeURIComponent(String(code || '').trim())}`;
  },

  _setHash(path, push = true) {
    const p = String(path || '/stocks').replace(/^#/, '');
    const hash = '#' + p;
    if (location.hash === hash) return;
    if (push && history.pushState) {
      history.pushState({ stockDetail: p }, '', hash);
    } else {
      location.hash = hash;
    }
  },

  onTabActivated() {
    const raw = (location.hash || '').replace(/^#/, '').trim();
    if (raw.startsWith('stock/') && raw.split('/')[1]) {
      this.routeFromHash(false);
    } else if (!raw || raw === 'stocks' || raw === 'stock-detail' || raw === 'stock') {
      this.showIndex(false);
    } else if (this._code) {
      this._showDetailView(this._code, false);
    } else {
      this.showIndex(false);
    }
  },

  showIndex(pushHash = true) {
    if (pushHash) this._setHash('/stocks');
    document.getElementById('sdIndexView')?.classList.remove('h');
    document.getElementById('sdDetailView')?.classList.add('h');
    document.title = '股票詳情 · Stock Quant';
    this._code = '';
    this.loadIndex();
  },

  _showDetailView(code, pushHash = true) {
    const c = String(code || '').trim();
    if (!c) {
      this.showIndex(pushHash);
      return;
    }
    if (pushHash) this._setHash(this._stockPath(c));
    document.getElementById('sdIndexView')?.classList.add('h');
    document.getElementById('sdDetailView')?.classList.remove('h');
    const hint = document.getElementById('sdUrlHint');
    if (hint) hint.textContent = location.hash || this._stockPath(c);
    this.load(c);
  },

  open(code) {
    const c = String(code || '').trim();
    if (!c) return;
    this.initRouter();
    this._showDetailView(c, true);
    if (typeof App !== 'undefined') App.loadTab('stock-detail');
  },

  async loadIndex() {
    const grid = document.getElementById('sdStockGrid');
    if (!grid) return;
    grid.innerHTML = '<div class="state-loading"><span class="ld"></span> 載入股票列表…</div>';
    try {
      let list = [];
      if (typeof StockPicker !== 'undefined' && StockPicker._stocks?.length) {
        list = StockPicker._stocks;
      } else if (typeof Api !== 'undefined') {
        const d = await Api.getStocks(800);
        list = (d?.stocks || d || []).map((s, i) => ({
          code: s.code || s.symbol,
          name: s.name || s.stock_name || '',
          market: s.market || 'a_share',
          rank: s.rank || i + 1,
        })).filter(s => s.code);
      }
      this._indexList = list;
      this._paintIndexGrid();
    } catch (e) {
      grid.innerHTML = `<p class="err">載入失敗：${e.message || e}</p>`;
    }
  },

  _paintIndexGrid() {
    const grid = document.getElementById('sdStockGrid');
    const q = (document.getElementById('sdIndexSearch')?.value || '').trim().toLowerCase();
    if (!grid) return;

    let list = this._indexList || [];
    if (q) {
      list = list.filter(s =>
        String(s.code).toLowerCase().includes(q) ||
        String(s.name || '').toLowerCase().includes(q)
      );
    }

    if (!list.length) {
      grid.innerHTML = '<p class="muted" style="padding:16px">沒有匹配的股票</p>';
      return;
    }

    const show = list.slice(0, 400);
    grid.innerHTML = show.map(s => {
      const path = this._stockPath(s.code);
      const name = this._esc(s.name || s.code);
      const code = this._esc(s.code);
      return `<a href="${path}" class="sd-stock-card" data-code="${code}">
        <span class="sd-stock-card-code">${code}</span>
        <span class="sd-stock-card-name">${name}</span>
      </a>`;
    }).join('');

    if (list.length > show.length) {
      grid.innerHTML += `<p class="sec-desc" style="grid-column:1/-1">僅顯示前 ${show.length} 筆，請用搜尋縮小範圍（共 ${list.length} 筆）</p>`;
    }

    grid.querySelectorAll('.sd-stock-card').forEach(el => {
      el.addEventListener('click', e => {
        e.preventDefault();
        const code = el.dataset.code || '';
        if (code) this.open(code);
      });
    });
  },

  async load(code) {
    const c = String(code || this._code || '').trim();
    if (!c) {
      this.showIndex(false);
      return;
    }
    if (this._loading && c === this._code) return;
    this._code = c;
    this._loading = true;

    const meta = document.getElementById('sdMeta');
    const klineBox = document.getElementById('sdMainKline');
    if (meta) meta.textContent = '載入中…';
    if (klineBox) klineBox.innerHTML = '<div class="chart-placeholder"><span class="ld"></span> 載入行情…</div>';

    try {
      const d = await Api.get(`/api/stocks/${encodeURIComponent(c)}/analysis-page`);
      if (!d?.success) throw new Error('載入失敗');
      this._name = d.name || c;
      document.title = `${this._name} (${d.code}) · 個股詳情`;
      this._renderHeader(d);
      await this._renderTvWall(d);
      this._renderPolymarket(d);
    } catch (e) {
      if (meta) meta.textContent = `載入失敗：${e.message || e}`;
      if (klineBox) {
        klineBox.innerHTML = '<div class="chart-placeholder">無法載入 K 線，請先在數據中心下載該股歷史數據</div>';
      }
      document.title = `${c} · 個股詳情`;
    } finally {
      this._loading = false;
      if (typeof Charts !== 'undefined') {
        requestAnimationFrame(() => Charts.resizeTab('tab-stock-detail'));
      }
    }
  },

  _renderHeader(d) {
    const codeEl = document.getElementById('sdCode');
    const nameEl = document.getElementById('sdName');
    const meta = document.getElementById('sdMeta');
    const manual = document.getElementById('sdCodeInput');
    if (codeEl) codeEl.textContent = d.code;
    if (nameEl) nameEl.textContent = d.name || d.code;
    if (manual) manual.value = d.code;
    const sp = d.sparkline || {};
    const src = d.kline_source || sp.source || '';
    if (meta) {
      meta.textContent = src
        ? `獨立頁 · ${d.code} · 數據源 ${src}`
        : `獨立頁 · ${d.code}`;
    }
    if (typeof Utils !== 'undefined' && Utils.bindStockIcon) {
      const img = document.getElementById('sdIcon');
      const letter = document.getElementById('sdIconLetter');
      if (img && letter) Utils.bindStockIcon(img, d.code, d.name, '');
    }
  },

  async _renderTvWall(d) {
    const klineBox = document.getElementById('sdMainKline');
    const metricsEl = document.getElementById('sdMetrics');
    if (!klineBox || typeof Charts === 'undefined') return;

    const ready = await this._waitLw();
    if (!ready) {
      klineBox.innerHTML = '<div class="chart-placeholder">圖表庫載入中，請稍後…</div>';
      return;
    }

    const kline = d.kline || [];
    const title = `${d.code} ${d.name || ''}`.trim();
    if (kline.length >= 10) {
      klineBox.innerHTML = '';
      Charts.drawLWKlineChart('sdMainKline', kline, [], title);
    } else {
      const sp = d.sparkline || {};
      if (sp.prices?.length) {
        klineBox.innerHTML = '';
        Charts.drawTVSparklineChart('sdMainKline', sp.dates, sp.prices, {
          changePct: sp.change_pct,
        });
      } else {
        klineBox.innerHTML = '<div class="chart-placeholder">暫無 K 線數據，請先下載歷史行情</div>';
      }
    }

    const m = (typeof Dashboard !== 'undefined' && Dashboard._calcSeriesMetrics)
      ? Dashboard._calcSeriesMetrics(d.code, d.sparkline || {})
      : null;
    if (!metricsEl) return;
    if (!m) {
      metricsEl.innerHTML = '';
      return;
    }
    const chgCls = m.totalReturn > 0 ? 'up' : (m.totalReturn < 0 ? 'down' : 'flat');
    const sign = m.totalReturn > 0 ? '+' : '';
    metricsEl.innerHTML = `
      <div class="sd-metric-card">
        <span class="sd-metric-label">最新價</span>
        <span class="sd-metric-val">${this._fmtPrice(m.latest, d.code)}</span>
      </div>
      <div class="sd-metric-card">
        <span class="sd-metric-label">區間漲跌</span>
        <span class="sd-metric-val ${chgCls}">${sign}${m.totalReturn.toFixed(2)}%</span>
      </div>
      <div class="sd-metric-card">
        <span class="sd-metric-label">20日動量</span>
        <span class="sd-metric-val ${m.momentum20 >= 0 ? 'up' : 'down'}">${m.momentum20.toFixed(2)}%</span>
      </div>
      <div class="sd-metric-card">
        <span class="sd-metric-label">年化波動</span>
        <span class="sd-metric-val">${m.volatility.toFixed(1)}%</span>
      </div>
      <div class="sd-metric-card">
        <span class="sd-metric-label">最大回撤</span>
        <span class="sd-metric-val down">${m.maxDrawdown.toFixed(2)}%</span>
      </div>
      <div class="sd-metric-card">
        <span class="sd-metric-label">風險比</span>
        <span class="sd-metric-val">${m.riskScore.toFixed(2)}</span>
      </div>`;
  },

  _renderPolymarket(d) {
    const hint = document.getElementById('sdPmHint');
    const pm = d.polymarket || {};
    if (typeof PolymarketUI === 'undefined') {
      if (hint) hint.textContent = 'Polymarket 模組未載入';
      return;
    }
    PolymarketUI.useScope('stock');
    if (pm.disabled) {
      if (hint) hint.textContent = pm.error || 'Polymarket 功能已關閉';
      PolymarketUI.setMarkets([]);
      return;
    }
    const queries = (pm.queries || []).join(' · ');
    const markets = pm.markets || [];
    if (hint) {
      hint.textContent = markets.length
        ? `依「${queries}」搜尋到 ${markets.length} 個相關預測市場`
        : `未找到與「${queries}」相關的預測市場（可至預測市場 Tab 手動搜尋）`;
    }
    PolymarketUI.setMarkets(markets);
    if (markets.length) PolymarketUI.showDetail(markets[0]);
  },

  _fmtPrice(value, code) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    if (/^\d{6}$/.test(String(code))) {
      return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  },

  _esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  },

  async _waitLw(maxMs = 12000) {
    const start = Date.now();
    while (Date.now() - start < maxMs) {
      if (typeof Charts !== 'undefined' && Charts._lwReady?.()) return true;
      await new Promise(r => setTimeout(r, 120));
    }
    return typeof Charts !== 'undefined' && Charts._lwReady?.();
  },

  _copyPageLink() {
    const url = `${location.origin}${location.pathname}${location.search}${this._stockPath(this._code)}`;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(() => {
        if (typeof Utils !== 'undefined') Utils.toast('已複製個股頁連結', 2000, 'success');
      }).catch(() => this._fallbackCopy(url));
    } else {
      this._fallbackCopy(url);
    }
  },

  _fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      if (typeof Utils !== 'undefined') Utils.toast('已複製連結', 2000, 'success');
    } catch (e) {
      if (typeof Utils !== 'undefined') Utils.toast('複製失敗', 2000, 'error');
    }
    document.body.removeChild(ta);
  },

  bindUi() {
    if (this._bound) return;
    this._bound = true;
    this.initRouter();

    document.getElementById('sdBackToList')?.addEventListener('click', () => this.showIndex());
    document.getElementById('sdCopyLinkBtn')?.addEventListener('click', () => this._copyPageLink());
    document.getElementById('sdIndexReload')?.addEventListener('click', () => this.loadIndex());
    document.getElementById('sdIndexSearch')?.addEventListener('input', () => this._paintIndexGrid());

    document.getElementById('sdGoBtn')?.addEventListener('click', () => {
      const c = document.getElementById('sdCodeInput')?.value?.trim();
      if (c) this.open(c);
    });
    document.getElementById('sdCodeInput')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const c = e.target.value?.trim();
        if (c) this.open(c);
      }
    });
    document.getElementById('sdBacktestBtn')?.addEventListener('click', () => {
      if (typeof App === 'undefined' || !this._code) return;
      App.loadTab('backtest');
      if (typeof Backtest !== 'undefined' && Backtest.setCode) Backtest.setCode(this._code);
    });
    document.getElementById('sdAnalysisBtn')?.addEventListener('click', () => {
      if (typeof App === 'undefined' || !this._code) return;
      App.loadTab('analysis');
      const el = document.getElementById('anCode');
      if (el) {
        el.value = this._code;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    document.getElementById('sdPmTabBtn')?.addEventListener('click', () => {
      if (typeof App !== 'undefined') App.loadTab('polymarket');
    });
  },
};

StockDetail.bindUi();
