/**
 * stock-detail.js — 每支股票獨立詳情頁（#/stock/代碼）
 * TradingView K 線牆 + 技術/信號概覽
 */
const StockDetail = {
  _code: '',
  _name: '',
  _loading: false,
  _indexList: [],
  _routerReady: false,
  _panelsMounted: false,
  _currentSubTab: 'overview',
  _pendingSubTab: null,
  _lastDetailData: null,
  _overviewRendered: false,
  _SUB_TABS: ['overview', 'backtest', 'optimize', 'walkforward', 'heatmap', 'history'],

  initRouter() {
    if (this._routerReady) return;
    this._routerReady = true;
    // hash / popstate 由 App.initRouter 統一分發
  },

  /** 解析 hash，返回是否已處理 */
  routeFromHash(pushTab = true) {
    const raw = (location.hash || '').replace(/^#/, '').trim();
    const parts = raw.split('/').filter(Boolean);

    if (parts[0] === 'stock' && parts[1]) {
      const code = decodeURIComponent(parts[1]);
      const sub = parts[2] && this._SUB_TABS.includes(parts[2]) ? parts[2] : null;
      if (sub && sub !== 'overview') this._pendingSubTab = sub;
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
    } else if (history.replaceState) {
      history.replaceState({ stockDetail: p }, '', hash);
    } else {
      location.hash = hash;
    }
  },

  onTabActivated() {
    const raw = (location.hash || '').replace(/^#/, '').trim();
    const parts = raw.split('/').filter(Boolean);
    if (parts[0] === 'stock' && parts[1]) {
      const sub = parts[2] && this._SUB_TABS.includes(parts[2]) ? parts[2] : null;
      if (sub) this._pendingSubTab = sub;
      this.routeFromHash(false);
      return;
    }
    if (typeof App !== 'undefined' && App.isStockHash(raw)) {
      this.routeFromHash(false);
      return;
    }
    this.showIndex(true);
  },

  showIndex(pushHash = true) {
    if (pushHash) this._setHash('/stocks');
    const search = document.getElementById('sdIndexSearch');
    if (search && typeof LocalStore !== 'undefined') {
      const q = LocalStore.get('sdIndexSearch') || '';
      if (q && !search.value) search.value = q;
    }
    this._renderRecentChips();
    document.getElementById('sdIndexView')?.classList.remove('h');
    document.getElementById('sdDetailView')?.classList.add('h');
    document.title = '股票詳情 · Stock Quant';
    this._code = '';
    this._name = '';
    this._currentSubTab = 'overview';
    this._pendingSubTab = null;
    this._lastDetailData = null;
    this._overviewRendered = false;
    this.loadIndex();
  },

  /** 將回測相關 Tab 面板掛載到個股頁 */
  _mountBacktestPanels() {
    if (this._panelsMounted) return;
    const mount = document.getElementById('sdPanelsMount');
    if (!mount) return;
    ['backtest', 'optimize', 'walkforward', 'heatmap', 'history'].forEach(name => {
      const el = document.getElementById('tab-' + name);
      if (!el || el.dataset.sdMounted === '1') return;
      el.classList.add('sd-embedded-tab');
      el.classList.remove('h');
      const wrap = document.createElement('div');
      wrap.id = 'sd-panel-' + name;
      wrap.className = 'sd-panel h';
      wrap.appendChild(el);
      mount.appendChild(wrap);
      el.dataset.sdMounted = '1';
    });
    this._panelsMounted = true;
  },

  _syncModules(code, name = '') {
    const c = String(code || '').trim();
    if (!c) return;
    if (typeof Backtest !== 'undefined' && Backtest.setCode) Backtest.setCode(c);
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.value = val;
    };
    setVal('optCode', c);
    setVal('wfCode', c);
    setVal('hmCode', c);
    setVal('histCode', c);
  },

  _syncContextBar() {
    const codeEl = document.getElementById('sdContextCode');
    const nameEl = document.getElementById('sdContextName');
    const iconHost = document.getElementById('sdContextIcon');
    if (codeEl) codeEl.textContent = this._code || '—';
    if (nameEl) nameEl.textContent = this._name ? ` ${this._name}` : '';
    if (!iconHost) return;
    if (this._code && typeof Utils !== 'undefined' && Utils.stockIconHtml) {
      iconHost.innerHTML =
        `<span class="sd-icon-square">${Utils.stockIconHtml(this._code, this._name, 40)}</span>`;
      Utils.hydrateStockIcons(iconHost);
    } else {
      iconHost.innerHTML = '';
    }
  },

  _onSubTabActivated(tab) {
    if (typeof App === 'undefined') return;
    switch (tab) {
      case 'backtest':
        if (typeof Backtest !== 'undefined') {
          Backtest.populateStockSelectSync?.();
          Backtest.ensureStockOptions?.();
          if (Backtest._lastResult && Backtest._displayResult) {
            Backtest._displayResult(Backtest._lastResult);
            Backtest._finishDisplay?.();
          }
        }
        break;
      case 'optimize':
        App._onOptimizeTab?.();
        break;
      case 'walkforward':
        App._onWalkforwardTab?.();
        break;
      case 'heatmap':
        if (typeof Heatmap !== 'undefined') Heatmap.initTab();
        break;
      case 'history':
        App._onHistoryTab?.();
        break;
      case 'overview':
        this._ensureOverview();
        break;
      default:
        break;
    }
  },

  async _ensureOverview() {
    if (!this._code || this._overviewRendered) return;
    const d = this._lastDetailData;
    if (!d) return;
    this._renderTechnical(d);
    this._renderSignals(d);
    await this._renderTvWall(d);
    this._overviewRendered = true;
    if (typeof Charts !== 'undefined') {
      requestAnimationFrame(() => Charts.resizeTab('tab-stock-detail'));
    }
  },

  activateSubTab(tab) {
    if (!this._code && tab !== 'overview') {
      if (typeof Utils !== 'undefined') Utils.toast('請先選擇或載入股票', 2500, 'warn');
      return;
    }
    this._mountBacktestPanels();
    const t = this._SUB_TABS.includes(tab) ? tab : 'overview';
    this._currentSubTab = t;

    document.querySelectorAll('.sd-subnav-btn').forEach(btn => {
      btn.classList.toggle('a', btn.dataset.sdTab === t);
    });

    const ctx = document.getElementById('sdStockContext');
    if (ctx) ctx.classList.toggle('h', t === 'overview');

    const overview = document.getElementById('sd-panel-overview');
    if (overview) overview.classList.toggle('h', t !== 'overview');

    ['backtest', 'optimize', 'walkforward', 'heatmap', 'history'].forEach(name => {
      const panel = document.getElementById('sd-panel-' + name);
      const tabEl = document.getElementById('tab-' + name);
      const show = t === name;
      if (panel) panel.classList.toggle('h', !show);
      if (tabEl?.classList.contains('sd-embedded-tab')) tabEl.classList.toggle('h', !show);
    });

    if (this._code) {
      this._syncModules(this._code, this._name);
      const path = t === 'overview'
        ? this._stockPath(this._code)
        : `${this._stockPath(this._code)}/${t}`;
      this._setHash(path, false);
    }
    this._syncContextBar();
    this._onSubTabActivated(t);

    if (typeof Charts !== 'undefined') {
      requestAnimationFrame(() => Charts.resizeTab('tab-stock-detail'));
    }
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
          price: s.price,
          change_pct: s.change_pct,
          total_mv: s.total_mv,
          industry: s.industry || '',
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
    const iconHtml = (s) =>
      (typeof Utils !== 'undefined' && Utils.stockIconHtml)
        ? Utils.stockIconHtml(s.code, s.name || s.code, 48, s.market || '')
        : '';

    grid.innerHTML = show.map(s => {
      const path = this._stockPath(s.code);
      const name = this._esc(s.name || s.code);
      const code = this._esc(s.code);
      const mkt = this._esc(s.market || '');
      const mktLabel = { a_share: 'A股', hk_stock: '港股', us_stock: '美股' }[s.market] || '';
      const price = s.price != null ? Number(s.price).toFixed(2) : '';
      const chg = s.change_pct;
      const chgCls = chg > 0 ? 'up' : (chg < 0 ? 'down' : '');
      const chgTxt = chg != null ? `${chg > 0 ? '+' : ''}${Number(chg).toFixed(2)}%` : '';
      const mv = s.total_mv != null ? `${Number(s.total_mv).toFixed(0)}億` : '';
      const meta = [mktLabel, price && `¥${price}`, chgTxt && `<span class="${chgCls}">${chgTxt}</span>`, mv]
        .filter(Boolean).join(' · ');
      return `<a href="${path}" class="sd-stock-card" data-code="${code}" data-market="${mkt}">
        <div class="sd-stock-card-top">
          ${iconHtml(s)}
          <div class="sd-stock-card-text">
            <span class="sd-stock-card-code">${code}</span>
            <span class="sd-stock-card-name">${name}</span>
            ${meta ? `<div class="sd-stock-card-meta">${meta}</div>` : ''}
          </div>
        </div>
      </a>`;
    }).join('');

    if (list.length > show.length) {
      grid.innerHTML += `<p class="sec-desc" style="grid-column:1/-1">僅顯示前 ${show.length} 筆，請用搜尋縮小範圍（共 ${list.length} 筆）</p>`;
    }

    if (typeof Utils !== 'undefined' && Utils.observeStockIcons) {
      Utils.observeStockIcons(grid);
    } else if (typeof Utils !== 'undefined' && Utils.hydrateStockIcons) {
      Utils.hydrateStockIcons(grid);
    }

    grid.querySelectorAll('.sd-stock-card').forEach(el => {
      el.addEventListener('click', e => {
        e.preventDefault();
        const code = el.dataset.code || '';
        if (code) this.open(code);
      });
      // 雙擊快速刷新該股詳情
      el.addEventListener('dblclick', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const code = el.dataset.code || '';
        if (code) {
          this.load(code);
          if (typeof Utils !== 'undefined') {
            Utils.toast(`重新載入 ${code}`, 1500);
          }
        }
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
    this._overviewRendered = false;
    this._lastDetailData = null;
    this._loading = true;

    const meta = document.getElementById('sdMeta');
    const klineBox = document.getElementById('sdMainKline');
    if (meta) meta.textContent = '載入中…';
    if (klineBox) klineBox.innerHTML = '<div class="chart-placeholder"><span class="ld"></span> 載入行情…</div>';

    try {
      const d = await Api.get(`/api/stocks/${encodeURIComponent(c)}/analysis-page`);
      if (!d?.success) throw new Error('載入失敗');
      this._name = d.name || c;
      this._lastDetailData = d;
      if (typeof LocalStore !== 'undefined') {
        LocalStore.pushRecentStock({
          code: d.code,
          name: this._name,
          market: d.profile?.market || d.market || '',
        });
      }
      document.title = `${this._name} (${d.code}) · 個股詳情`;
      this._renderHeader(d);
      this._renderTechnical(d);
      this._renderSignals(d);
      this._syncFavoriteBtn();
      this._syncModules(c, this._name);
      this._syncContextBar();
      const sub = this._pendingSubTab || 'overview';
      this._pendingSubTab = null;
      this.activateSubTab(sub);
      if (sub === 'overview') {
        await this._renderTvWall(d);
        this._overviewRendered = true;
      }
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

  _sc() {
    return typeof StockContent !== 'undefined' ? StockContent : null;
  },

  _renderRecentChips() {
    const section = document.getElementById('sdRecentSection');
    const host = document.getElementById('sdRecentChips');
    if (!section || !host || typeof LocalStore === 'undefined') return;
    const list = LocalStore.getRecentStocks(16);
    if (!list.length) {
      section.classList.add('h');
      host.innerHTML = '';
      return;
    }
    section.classList.remove('h');
    host.innerHTML = list.map(s => {
      const code = this._esc(s.code);
      const name = this._esc(s.name || s.code);
      const fav = LocalStore.isFavorite(s.code);
      return `<button type="button" class="sd-recent-chip" data-code="${code}" title="${name} (雙擊查看詳情)">
        <span class="sd-recent-code">${code}</span>
        <span class="sd-recent-name">${name}</span>
        ${fav ? '<span class="sd-recent-fav" title="已收藏">★</span>' : ''}
      </button>`;
    }).join('');
    host.querySelectorAll('.sd-recent-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const code = btn.dataset.code || '';
        if (code) this.open(code);
      });
      // 雙擊跳轉詳情頁（已在詳情頁，刷新該股）
      btn.addEventListener('dblclick', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const code = btn.dataset.code || '';
        if (code) {
          this.load(code);
          if (typeof Utils !== 'undefined') {
            Utils.toast(`重新載入 ${code}`, 1500);
          }
        }
      });
    });
  },

  _renderHeader(d) {
    const codeEl = document.getElementById('sdCode');
    const nameEl = document.getElementById('sdName');
    const meta = document.getElementById('sdMeta');
    const manual = document.getElementById('sdCodeInput');
    const profile = d.profile || {};
    const mkt = profile.market || d.market || '';
    if (codeEl) codeEl.textContent = d.code;
    if (nameEl) nameEl.textContent = d.name || profile.name || d.code;
    if (manual) manual.value = d.code;
    const sp = d.sparkline || {};
    const o = d.overview || {};
    const src = d.kline_source || sp.source || o.kline_source || '';
    const parts = [`獨立頁 · ${d.code}`];
    if (profile.market_label) parts.push(profile.market_label);
    if (profile.exchange) parts.push(profile.exchange);
    if (src) parts.push(`行情 ${src}`);
    if (o.date_from && o.date_to) parts.push(`K線 ${o.date_from}~${o.date_to}`);
    if (meta) meta.textContent = parts.join(' · ');

    const tagsEl = document.getElementById('sdHeroTags');
    const sc = this._sc();
    if (sc) {
      sc.renderTags(tagsEl, sc.buildHeroTags(profile, d.financials));
      sc.renderIntro(document.getElementById('sdIntro'), profile);
      sc.renderMetricGrid(
        document.getElementById('sdFinanceGrid'),
        sc.buildFinanceItems(d.financials, profile, d.code),
        '暫無財務數據，請在數據中心更新基本面或同步股票庫。',
      );
      const fin = d.financials || {};
      const asof = document.getElementById('sdFinanceAsof');
      if (asof) {
        const date = fin.update_date || profile.universe_updated_at || '';
        asof.textContent = date ? `更新 ${date}` : '';
      }
    } else {
      if (tagsEl) tagsEl.innerHTML = '';
    }

    if (typeof Utils !== 'undefined' && Utils.bindStockIcon) {
      const img = document.getElementById('sdIcon');
      const letter = document.getElementById('sdIconLetter');
      const inferMkt = Utils.inferStockMarket(d.code, mkt);
      if (img && letter) Utils.bindStockIcon(img, d.code, d.name || profile.name, inferMkt);
    }
  },

  _renderTechnical(d) {
    const sc = this._sc();
    const grid = document.getElementById('sdTechnicalGrid');
    const meta = document.getElementById('sdTechnicalMeta');
    if (!sc || !grid) return;
    const o = d.overview || {};
    const items = sc.buildTechnicalItems(o, o.technical);
    sc.renderMetricGrid(grid, items, o.message || '暫無 K 線技術數據，請先下載歷史行情');
    if (meta) {
      meta.textContent = o.has_kline && o.lookback_days
        ? `回看 ${o.lookback_days} 日`
        : '';
    }
  },

  _renderSignals(d) {
    const sc = this._sc();
    const list = document.getElementById('sdSignalsList');
    const meta = document.getElementById('sdSignalsMeta');
    if (!sc || !list) return;
    const sig = d.signals || {};
    sc.renderSignals(list, meta, sig.signals, sig.strength, sig.updated_at);
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

  _syncFavoriteBtn() {
    const btn = document.getElementById('sdFavoriteBtn');
    if (!btn || typeof LocalStore === 'undefined' || !this._code) return;
    const on = LocalStore.isFavorite(this._code);
    btn.textContent = on ? '★ 已收藏' : '☆ 收藏';
    btn.classList.toggle('a', on);
  },

  _toggleFavorite() {
    if (!this._code || typeof LocalStore === 'undefined') return;
    const on = LocalStore.toggleFavorite(this._code);
    this._syncFavoriteBtn();
    this._renderRecentChips();
    if (typeof Utils !== 'undefined') {
      Utils.toast(on ? '已加入本機收藏' : '已取消收藏', 2000, 'success');
    }
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
    document.getElementById('sdFavoriteBtn')?.addEventListener('click', () => this._toggleFavorite());
    document.getElementById('sdIndexReload')?.addEventListener('click', () => this.loadIndex());
    document.getElementById('sdIndexSearch')?.addEventListener('input', e => {
      const q = (e.target?.value || '').trim();
      if (typeof LocalStore !== 'undefined') LocalStore.set('sdIndexSearch', q);
      this._paintIndexGrid();
    });
    document.getElementById('sdClearRecent')?.addEventListener('click', () => {
      if (typeof LocalStore === 'undefined') return;
      LocalStore.clearRecentStocks();
      this._renderRecentChips();
      if (typeof Utils !== 'undefined') Utils.toast('已清除本機最近瀏覽', 2000, 'success');
    });

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
    this._mountBacktestPanels();
    document.getElementById('sdSubnav')?.addEventListener('click', e => {
      const btn = e.target.closest('.sd-subnav-btn[data-sd-tab]');
      if (!btn) return;
      this.activateSubTab(btn.dataset.sdTab);
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
      if (typeof App !== 'undefined') App.loadTab('markets');
    });
  },
};

StockDetail.bindUi();
