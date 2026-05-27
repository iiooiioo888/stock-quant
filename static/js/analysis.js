/**
 * analysis.js — 深度分析 Tab（調用後端同步分析 API）
 */

const Analysis = {
  _UNIVERSE_MAX: 20000,
  _UNIVERSE_ROW_H: 52,
  _universeList: [],
  _activeMarket: 'all',
  _searchQuery: '',
  _snapshotTimer: null,
  _snapshotCode: '',
  _MARKET_LABELS: {
    all: '全部',
    a_share: 'A股',
    hk_stock: '港股',
    us_stock: '美股',
  },
  _MARKET_ORDER: ['all', 'a_share', 'hk_stock', 'us_stock'],

  init() {
    this._bindCodeControls();
    const saved = (typeof LocalStore !== 'undefined' && LocalStore.get('lastAnalysis')?.code) || '600519';
    this.setCode(this.getCode() || saved);
    const strat = typeof LocalStore !== 'undefined' ? LocalStore.get('lastAnalysis')?.strategy : null;
    const sel = document.getElementById('anStrategy');
    if (strat && sel && [...sel.options].some(o => o.value === strat)) sel.value = strat;
    this.loadStockOptions();
  },

  /** 進入深度分析 Tab：補全股票列表並自動跑一次交易分析 */
  onTabShow() {
    this._bindCodeControls();
    if (!this._universeList?.length) this.loadStockOptions();
    const code = this.getCode() || '600519';
    if (!this.getCode()) this.setCode(code);
    else this._scheduleSnapshot(code);
    const stats = document.getElementById('anStats');
    if (stats && !stats.innerHTML.trim()) {
      stats.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 分析中…</p>';
    }
    this.tradeAnalysis();
  },

  getCode() {
    return document.getElementById('anCode')?.value?.trim() || '';
  },

  setCode(code, name = '') {
    const clean = String(code || '').trim();
    if (!clean) return;
    const found = this._universeList.find(s => String(s.code) === clean);
    const stockName = name || found?.name || this._stockName(clean) || clean;

    const hidden = document.getElementById('anCode');
    const manual = document.getElementById('anCodeManual');
    if (hidden) hidden.value = clean;
    if (manual) manual.value = clean;
    this._updateSelectedStock(clean, stockName);
    this._refreshActiveRows(clean);
    this._scheduleSnapshot(clean);
    if (typeof LocalStore !== 'undefined') {
      LocalStore.pushRecentStock({ code: clean, name: stockName, market: found?.market || '' });
      const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
      LocalStore.save({ lastAnalysis: { code: clean, strategy } });
    }
  },

  _scheduleSnapshot(code) {
    if (this._snapshotTimer) clearTimeout(this._snapshotTimer);
    const c = String(code || '').trim();
    if (!c) return;
    this._snapshotTimer = setTimeout(() => this._loadSnapshot(c), 280);
  },

  async _loadSnapshot(code) {
    const root = document.getElementById('anStockSnapshot');
    if (!root || typeof StockContent === 'undefined' || typeof Api === 'undefined') return;
    if (this._snapshotCode === code && root.dataset.loaded === code) return;
    this._snapshotCode = code;
    root.dataset.loaded = '';
    root.innerHTML = '<p class="muted"><span class="ld"></span> 載入個股快照…</p>';
    try {
      const d = await Api.get(
        `/api/stocks/${encodeURIComponent(code)}/analysis-page?kline_days=120&sparkline_days=60`,
      );
      if (this.getCode() !== code) return;
      if (!d?.success) throw new Error('載入失敗');
      StockContent.renderAnalysisSnapshot(root, d);
      root.dataset.loaded = code;
    } catch (e) {
      if (this.getCode() !== code) return;
      root.innerHTML = `<p class="err">快照載入失敗：${this._esc(e.message || e)}</p>`;
    }
  },

  _refreshActiveRows(code) {
    document.querySelectorAll('#anCodeGrid .stock-code-row').forEach(row => {
      row.classList.toggle('a', row.dataset.code === code);
    });
  },

  _bindCodeControls() {
    if (this._boundCodeControls) return;
    this._boundCodeControls = true;

    const manual = document.getElementById('anCodeManual');
    manual?.addEventListener('input', e => {
      this.setCode(e.target.value || '');
    });
    manual?.addEventListener('change', e => {
      this.setCode(e.target.value || '');
    });

    const search = document.getElementById('anCodeSearch');
    search?.addEventListener('input', e => {
      this._searchQuery = (e.target.value || '').trim().toLowerCase();
      this._renderStockPicker();
    });

    document.getElementById('anMarketTabs')?.addEventListener('click', e => {
      const btn = e.target.closest('[data-market]');
      if (!btn) return;
      this._activeMarket = btn.dataset.market || 'all';
      this._renderMarketTabs();
      this._renderStockPicker();
    });

    const anGrid = document.getElementById('anCodeGrid');
    anGrid?.addEventListener('click', e => {
      const row = e.target.closest('[data-code]');
      if (!row) return;
      this.setCode(row.dataset.code, row.dataset.name || '');
    });
    anGrid?.addEventListener('dblclick', e => {
      const row = e.target.closest('[data-code]');
      if (!row?.dataset.code || typeof App === 'undefined') return;
      App.openStockDetail(row.dataset.code);
    });
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

  _normalizeStock(item, idx = 0) {
    const code = String(item?.code || item?.symbol || '').trim();
    if (!code) return null;
    return {
      code,
      name: String(item?.name || item?.stock_name || item?.company_name || code).trim(),
      market: item?.market || item?.market_type || 'a_share',
      rank: Number(item?.rank_mv || item?.rank || idx + 1),
      intro: String(item?.intro || '').trim(),
    };
  },

  _stockName(code) {
    const map = {
      '600519': '貴州茅台',
      '000001': '平安銀行',
      '00700': '騰訊控股',
      AAPL: 'Apple',
      MSFT: 'Microsoft',
    };
    return map[String(code || '').toUpperCase()] || '';
  },

  _updateSelectedStock(code, name) {
    const card = document.getElementById('anSelectedStock');
    const codeEl = document.getElementById('anSelectedCode');
    const nameEl = document.getElementById('anSelectedName');
    const letterEl = document.getElementById('anSelectedLetter');
    const icon = document.getElementById('anSelectedIcon');

    card?.classList.toggle('bt-selected-stock--empty', !code);
    if (codeEl) codeEl.textContent = code || '-';
    if (nameEl) nameEl.textContent = name || '未選擇';
    if (letterEl) letterEl.textContent = (name || code || '?').slice(0, 1).toUpperCase();
    if (icon && code) Utils.bindStockIcon(icon, code, name);
  },

  _marketCounts() {
    const counts = { all: this._universeList.length, a_share: 0, hk_stock: 0, us_stock: 0 };
    this._universeList.forEach(s => {
      if (counts[s.market] != null) counts[s.market] += 1;
    });
    return counts;
  },

  _renderMarketTabs() {
    const host = document.getElementById('anMarketTabs');
    if (!host) return;
    const counts = this._marketCounts();
    host.innerHTML = this._MARKET_ORDER.map(market => `
      <button type="button" class="bt-market-tab ${this._activeMarket === market ? 'a' : ''}" data-market="${market}">
        ${this._MARKET_LABELS[market] || market}
        <strong>${counts[market] || 0}</strong>
      </button>
    `).join('');
  },

  _displayList() {
    const q = this._searchQuery;
    return this._universeList.filter(s => {
      if (this._activeMarket !== 'all' && s.market !== this._activeMarket) return false;
      if (!q) return true;
      return s.code.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)
        || (s.intro || '').toLowerCase().includes(q);
    });
  },

  _createStockRow(item) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = `stock-code-row ${this.getCode() === item.code ? 'a' : ''}`;
    row.dataset.code = item.code;
    row.dataset.name = item.name || '';
    row.title = `${item.code} ${item.name}${item.intro ? '\n' + item.intro : ''}`;
    row.innerHTML = `
      <span class="stock-code-row-rank">#${this._esc(item.rank)}</span>
      <span class="stock-code-icon stock-code-row-icon"><img width="28" height="28" alt=""><span class="stock-code-letter">${this._esc((item.name || item.code).slice(0, 1))}</span></span>
      <span class="stock-code-row-code">${this._esc(item.code)}</span>
      <span class="stock-code-row-text">
        <span class="stock-code-row-name">${this._esc(item.name || item.code)}</span>
        ${item.intro ? `<span class="stock-code-row-intro">${this._esc(item.intro)}</span>` : ''}
      </span>
    `;
    const img = row.querySelector('img');
    if (img) Utils.bindStockIcon(img, item.code, item.name, item.market || '');
    return row;
  },

  _mountVirtualList(host, list) {
    host.innerHTML = `
      <div class="stock-universe-viewport" style="height:${Math.min(480, Math.max(160, list.length * this._UNIVERSE_ROW_H))}px">
        <div class="stock-universe-spacer" style="height:${list.length * this._UNIVERSE_ROW_H}px"></div>
        <div class="stock-universe-rows"></div>
      </div>
    `;
    const viewport = host.querySelector('.stock-universe-viewport');
    viewport._stockList = list;
    viewport.addEventListener('scroll', () => this._paintVirtualList(viewport));
    this._paintVirtualList(viewport);
  },

  _paintVirtualList(viewport) {
    const list = viewport?._stockList || [];
    const rows = viewport?.querySelector('.stock-universe-rows');
    if (!rows) return;
    const start = Math.max(0, Math.floor(viewport.scrollTop / this._UNIVERSE_ROW_H) - 4);
    const visible = Math.ceil(viewport.clientHeight / this._UNIVERSE_ROW_H) + 8;
    const end = Math.min(list.length, start + visible);
    rows.style.transform = `translateY(${start * this._UNIVERSE_ROW_H}px)`;
    rows.innerHTML = '';
    list.slice(start, end).forEach(item => rows.appendChild(this._createStockRow(item)));
  },

  _renderStockPicker() {
    const host = document.getElementById('anCodeGrid');
    const hint = document.getElementById('anStockLoadHint');
    if (!host) return;
    const list = this._displayList();
    if (hint) {
      const suffix = this._searchQuery ? `，篩選 ${list.length} 隻` : '';
      hint.textContent = `已載入 ${this._universeList.length} 隻${suffix}`;
    }
    if (!list.length) {
      host.innerHTML = `<div class="state-empty"><span class="state-icon">🔍</span><span class="state-text">找不到符合條件的股票</span></div>`;
      return;
    }
    this._mountVirtualList(host, list);
  },

  async loadStockOptions() {
    const host = document.getElementById('anCodeGrid');
    const hint = document.getElementById('anStockLoadHint');
    if (host) host.innerHTML = `<div class="state-loading"><span class="ld"></span> 載入股票庫...</div>`;
    if (hint) hint.textContent = `載入 TOP ${this._UNIVERSE_MAX} 中...`;

    try {
      const data = await Api.getStocks(this._UNIVERSE_MAX);
      const stocks = (data?.stocks || [])
        .map((s, idx) => this._normalizeStock(s, idx))
        .filter(Boolean);
      if (!stocks.length) throw new Error('empty stock universe');
      this._universeList = stocks;
    } catch (err) {
      console.warn('analysis stock universe load failed', err);
      this._universeList = [
        { code: '600519', name: '貴州茅台', market: 'a_share', rank: 1 },
        { code: '000001', name: '平安銀行', market: 'a_share', rank: 2 },
        { code: '00700', name: '騰訊控股', market: 'hk_stock', rank: 3 },
        { code: 'AAPL', name: 'Apple', market: 'us_stock', rank: 4 },
      ];
      if (hint) hint.textContent = '股票庫載入失敗，已使用內建標的';
    }

    this._renderMarketTabs();
    this.setCode(this.getCode() || this._universeList[0]?.code || '600519');
    this._renderStockPicker();
  },

  _showSection(which) {
    document.getElementById('anResult')?.classList.remove('h');
    document.querySelectorAll('#anResult .sec').forEach(el => el.classList.add('h'));
    if (which === 'dist') {
      document.getElementById('anDistChart')?.closest('.sec')?.classList.remove('h');
    } else if (which === 'mc') {
      document.getElementById('anMcChart')?.closest('.sec')?.classList.remove('h');
    } else if (which === 'rolling') {
      document.getElementById('anRollingChart')?.closest('.sec')?.classList.remove('h');
    }
  },

  async tradeAnalysis() {
    if (this._analysisRunning) return Utils.toast('分析進行中，請稍候', 2500, 'warning');
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'warning');

    this._analysisRunning = true;
    const btn = document.getElementById('anTradeBtn');
    document.getElementById('anResult')?.classList.add('h');
    Utils.btnLoading(btn, true, '分析中...');
    try {
    const d = await Api.runTradeAnalysis({ code, strategy });
    if (!d?.success) return;

    const a = d.trade_analysis;
    if (!a?.total_trades) {
      return Utils.toast('無交易記錄，請換股票或策略後重試', 3000, 'warning');
    }

    const streak = a.streak || {};
    document.getElementById('anStats').innerHTML = `
      <div class="c"><h3>總交易</h3><div class="v">${a.total_trades}</div></div>
      <div class="c"><h3>盈虧比</h3><div class="v">${a.profit_factor === Infinity ? '∞' : Utils.formatNum(a.profit_factor, 2)}</div></div>
      <div class="c"><h3>期望值</h3><div class="v ${a.expectancy >= 0 ? 'gn' : 'rd'}">${Utils.formatNum(a.expectancy, 4)}</div></div>
      <div class="c"><h3>平均盈利</h3><div class="v gn">${Utils.formatNum(a.avg_win || 0, 2)}</div></div>
      <div class="c"><h3>平均虧損</h3><div class="v rd">${Utils.formatNum(a.avg_loss || 0, 2)}</div></div>
      <div class="c"><h3>最長連勝</h3><div class="v gn">${streak.max_win_streak || 0}</div></div>
      <div class="c"><h3>最長連虧</h3><div class="v rd">${streak.max_loss_streak || 0}</div></div>
      <div class="c"><h3>恢復因子</h3><div class="v">${Utils.formatNum(a.recovery_factor || 0, 2)}</div></div>`


    const dist = a.distribution || {};
    if (dist.bins?.length && dist.counts?.length) {
      const labels = [];
      for (let i = 0; i < dist.counts.length; i++) {
        labels.push(`${dist.bins[i]}~${dist.bins[i + 1]}%`);
      }
      Charts.drawBarChart('anDistChart', dist.counts, labels, '交易次數');
    }

    this._showSection('dist');
    Utils.toast('交易分析完成', 2000, 'success');
    } catch (e) {
      Utils.toast('交易分析失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      this._analysisRunning = false;
      Utils.btnLoading(btn, false, '📊 交易分析');
    }
  },

  async monteCarlo() {
    if (this._analysisRunning) return Utils.toast('分析進行中，請稍候', 2500, 'warning');
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'warning');

    this._analysisRunning = true;
    const btn = document.getElementById('anMcBtn');
    document.getElementById('anResult')?.classList.add('h');
    Utils.btnLoading(btn, true, '模擬中...');
    try {
    const d = await Api.runMonteCarlo({ code, strategy, n_simulations: 1000, days: 252 });
    if (!d?.success) return;

    const mc = d.monte_carlo || {};
    const p = mc.percentiles || {};
    const probProfit = (mc.prob_profit || 0) * 100;

    document.getElementById('anStats').innerHTML = `
      <div class="c"><h3>模擬次數</h3><div class="v">${mc.n_simulations || 1000}</div></div>
      <div class="c"><h3>5% 分位</h3><div class="v rd">${Utils.formatPct(((p.p5 || 1) - 1) * 100)}</div></div>
      <div class="c"><h3>中位數</h3><div class="v">${Utils.formatPct(((p.p50 || 1) - 1) * 100)}</div></div>
      <div class="c"><h3>95% 分位</h3><div class="v gn">${Utils.formatPct(((p.p95 || 1) - 1) * 100)}</div></div>
      <div class="c"><h3>均值</h3><div class="v">${Utils.formatPct(((p.mean || 1) - 1) * 100)}</div></div>
      <div class="c"><h3>盈利概率</h3><div class="v ${probProfit >= 50 ? 'gn' : 'rd'}">${probProfit.toFixed(1)}%</div></div>
      <div class="c"><h3>大回撤概率</h3><div class="v rd">${((mc.prob_large_drawdown || 0) * 100).toFixed(1)}%</div></div>`


    const curves = mc.simulated_curves || {};
    const pathSeries = Object.entries(curves).map(([label, data]) => ({
      label,
      data,
      dates: data.map((_, i) => String(i)),
    }));
    if (pathSeries.length) {
      if (typeof ProCharts !== 'undefined') ProCharts.renderMonteCarloFan(curves);
      else Charts.drawLineChart('anMcChart', pathSeries);
    }

    this._showSection('mc');
    Utils.toast('蒙特卡羅模擬完成', 2000, 'success');
    } catch (e) {
      Utils.toast('蒙特卡羅模擬失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      this._analysisRunning = false;
      Utils.btnLoading(btn, false, '🎲 蒙特卡羅');
    }
  },

  async rollingMetrics() {
    if (this._analysisRunning) return Utils.toast('分析進行中，請稍候', 2500, 'warning');
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'warning');

    this._analysisRunning = true;
    const btn = document.getElementById('anRollingBtn');
    document.getElementById('anResult')?.classList.add('h');
    Utils.btnLoading(btn, true, '計算中...');
    try {
    const d = await Api.runRollingMetrics({ code, strategy, window: 60 });
    if (!d?.success) return;

    const rm = d.rolling_metrics || {};
    if (!rm.rolling_sharpe?.length) {
      return Utils.toast('數據不足（需要至少 60 個交易日）', 3000, 'warning');
    }

    const summary = rm.summary || {};
    const lastSharpe = rm.rolling_sharpe[rm.rolling_sharpe.length - 1];
    const lastVol = (rm.rolling_volatility || [])[rm.rolling_volatility.length - 1];
    const lastDd = (rm.rolling_max_dd || [])[rm.rolling_max_dd.length - 1];

    document.getElementById('anStats').innerHTML = `
      <div class="c"><h3>最新滾動夏普</h3><div class="v">${Utils.formatNum(lastSharpe, 2)}</div></div>
      <div class="c"><h3>最新波動率</h3><div class="v">${Utils.formatNum(lastVol, 2)}%</div></div>
      <div class="c"><h3>最新回撤</h3><div class="v rd">${Utils.formatNum(lastDd, 2)}%</div></div>
      <div class="c"><h3>窗口</h3><div class="v">${rm.window || 60}天</div></div>`;

    Charts.drawLineChart('anRollingChart', [
      { label: '滾動夏普', data: rm.rolling_sharpe, dates: rm.dates },
      { label: '波動率 (%)', data: (rm.rolling_volatility || []).map(v => v * 100), dates: rm.dates },
      { label: '回撤 (%)', data: (rm.rolling_max_dd || []).map(v => -Math.abs(v) * 100), dates: rm.dates },
    ]);

    this._showSection('rolling');
    Utils.toast('滾動指標計算完成', 2000, 'success');
    } catch (e) {
      Utils.toast('滾動指標計算失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      this._analysisRunning = false;
      Utils.btnLoading(btn, false, '📉 滾動指標');
    }
  },
};

window.Analysis = Analysis;
