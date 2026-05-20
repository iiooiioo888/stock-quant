/**
 * backtest.js — 回測 Tab（支持進階回測 + 分析）
 */

const Backtest = {
  _lastResult: null,
  _running: false,
  _codesLoaded: false,
  _loadingStocks: false,
  _stockMap: new Map(),
  _searchQuery: '',

  _UNIVERSE_MAX: 20000,
  _UNIVERSE_ROW_H: 52,
  _universeList: [],
  _universeFiltered: null,
  _activeMarket: 'all',

  _GROUP_LABELS: {
    demo: '快捷示範',
    watchlist: '監控列表',
    universe: '市值 TOP',
    db: '本地 K 線',
  },

  _MARKET_LABELS: {
    all: '全部',
    a_share: 'A 股',
    hk_stock: '港股',
    us_stock: '美股',
  },

  _MARKET_ORDER: ['all', 'a_share', 'hk_stock', 'us_stock'],

  /** 預設示範股（與演示配置一致） */
  _DEFAULT_STOCKS: [
    { code: '000001', name: '平安銀行' },
    { code: '600519', name: '貴州茅台' },
    { code: '000858', name: '五糧液' },
    { code: '601318', name: '中國平安' },
    { code: '000333', name: '美的集團' },
  ],

  init() {
    this._bindCodeControls();
    this.populateStockSelectSync();
    this.setCode(this.getCode() || '600519');
    this.loadStockOptions();
  },

  /** Tab 切換時若無可選股票則重載 */
  ensureStockOptions() {
    const grid = document.getElementById('btCodeGrid');
    if (!grid) return;
    const hasStock = grid.querySelector('.stock-code-btn, .stock-universe-viewport');
    if (!hasStock || !this._codesLoaded) {
      this.populateStockSelectSync();
      this.loadStockOptions(true);
    }
  },

  /** 同步寫入示範股（不依賴 API） */
  populateStockSelectSync() {
    const map = new Map();
    const add = (code, name, group) => this._stockMapAdd(map, code, name, group);
    this._DEFAULT_STOCKS.forEach(s => add(s.code, s.name, 'demo'));
    this._applyStockPicker(map);
  },

  _stockMapAdd(map, code, name, group) {
    const c = String(code || '').trim();
    if (!c || map.has(c)) return;
    map.set(c, { code: c, name: (name || c).trim(), group });
  },

  _withTimeout(promise, ms = 8000) {
    return Promise.race([
      promise,
      new Promise(resolve => setTimeout(() => resolve(null), ms)),
    ]);
  },

  getCode() {
    const hidden = document.getElementById('btCode')?.value?.trim();
    const manual = document.getElementById('btCodeManual')?.value?.trim();
    return hidden || manual || '';
  },

  setCode(code) {
    const c = String(code || '').trim();
    const hidden = document.getElementById('btCode');
    const manual = document.getElementById('btCodeManual');
    if (hidden) hidden.value = c;
    if (manual) manual.value = c;
    this._highlightStockButton(c);
    this._updatePickHint(c);
  },

  _updatePickHint(code) {
    const item = code ? this._stockMap.get(code) : null;
    const name = item?.name || code || '請選擇股票';
    const codeEl = document.getElementById('btSelectedCode');
    const nameEl = document.getElementById('btSelectedName');
    const letterEl = document.getElementById('btSelectedLetter');
    const img = document.getElementById('btSelectedIcon');
    const wrap = document.getElementById('btSelectedStock');

    if (codeEl) codeEl.textContent = code || '—';
    if (nameEl) nameEl.textContent = name;
    if (letterEl) {
      letterEl.textContent = (name.replace(/\s/g, '') || code || '?').charAt(0);
      letterEl.style.display = '';
    }
    if (wrap) wrap.classList.toggle('bt-selected-stock--empty', !code);

    if (img && typeof Utils !== 'undefined' && Utils.bindStockIcon) {
      img.style.display = '';
      img.removeAttribute('data-fallback');
      Utils.bindStockIcon(img, code, name);
    }
  },

  _highlightStockButton(code) {
    const grid = document.getElementById('btCodeGrid');
    if (!grid) return;
    grid.querySelectorAll('.stock-code-btn, .stock-code-row').forEach(btn => {
      btn.classList.toggle('a', btn.dataset.code === code);
    });
    const vp = grid.querySelector('.stock-universe-viewport');
    if (vp) this._paintUniverseViewport(vp);
  },

  _bindCodeControls() {
    const grid = document.getElementById('btCodeGrid');
    const manual = document.getElementById('btCodeManual');
    const search = document.getElementById('btCodeSearch');
    const marketTabs = document.getElementById('btMarketTabs');
    if (!grid || grid.dataset.bound) return;
    grid.dataset.bound = '1';

    grid.addEventListener('click', e => {
      const btn = e.target.closest('.stock-code-btn, .stock-code-row');
      if (!btn?.dataset.code) return;
      this.setCode(btn.dataset.code);
    });

    if (manual && !manual.dataset.bound) {
      manual.dataset.bound = '1';
      manual.addEventListener('input', () => {
        const v = manual.value.replace(/\D/g, '').slice(0, 6);
        manual.value = v;
        const hidden = document.getElementById('btCode');
        if (hidden) hidden.value = v;
        this._highlightStockButton(v);
        this._updatePickHint(v);
      });
      manual.addEventListener('change', () => this.setCode(manual.value.trim()));
    }

    if (search && !search.dataset.bound) {
      search.dataset.bound = '1';
      search.addEventListener('input', () => {
        this._searchQuery = search.value.trim().toLowerCase();
        this._filterStockButtons();
      });
    }

    if (marketTabs && !marketTabs.dataset.bound) {
      marketTabs.dataset.bound = '1';
      marketTabs.addEventListener('click', e => {
        const btn = e.target.closest('.bt-market-tab');
        if (!btn?.dataset.market) return;
        this._activeMarket = btn.dataset.market;
        this._universeFiltered = null;
        this._renderMarketTabs();
        this._applyStockPicker(this._stockMap);
      });
    }
  },

  _marketCounts() {
    const counts = { all: this._universeList.length };
    this._universeList.forEach(item => {
      const m = item.market || 'unknown';
      counts[m] = (counts[m] || 0) + 1;
    });
    return counts;
  },

  _renderMarketTabs() {
    const el = document.getElementById('btMarketTabs');
    if (!el) return;
    const counts = this._marketCounts();
    const markets = this._MARKET_ORDER.filter(m => m === 'all' || counts[m] > 0);
    el.replaceChildren();
    markets.forEach(market => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'bt-market-tab';
      btn.dataset.market = market;
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', String(this._activeMarket === market));
      btn.classList.toggle('a', this._activeMarket === market);
      btn.innerHTML = `<span>${this._MARKET_LABELS[market] || market}</span><strong>${counts[market] || 0}</strong>`;
      el.appendChild(btn);
    });
  },

  _filterStockButtons() {
    const q = this._searchQuery;
    const grid = document.getElementById('btCodeGrid');
    if (!grid) return;

    if (this._universeList.length) {
      if (!q) {
        this._universeFiltered = null;
      } else {
        this._universeFiltered = this._universeList.filter(item => {
          const code = (item.code || '').toLowerCase();
          const name = (item.name || '').toLowerCase();
          return code.includes(q) || name.includes(q);
        });
      }
      const vp = grid.querySelector('.stock-universe-viewport');
      if (vp) this._paintUniverseViewport(vp);
    }

    grid.querySelectorAll('.stock-code-btn').forEach(btn => {
      if (!q) {
        btn.classList.remove('h');
        return;
      }
      const code = (btn.dataset.code || '').toLowerCase();
      const name = (btn.dataset.name || '').toLowerCase();
      const hit = code.includes(q) || name.includes(q);
      btn.classList.toggle('h', !hit);
    });
    grid.querySelectorAll('.stock-code-group:not([data-group="universe"])').forEach(sec => {
      const visible = sec.querySelector('.stock-code-btn:not(.h)');
      sec.classList.toggle('h', !visible);
    });
  },

  _universeDisplayList() {
    const base = this._activeMarket === 'all'
      ? this._universeList
      : this._universeList.filter(item => item.market === this._activeMarket);
    if (!this._searchQuery) return base;
    return base.filter(item => {
      const code = (item.code || '').toLowerCase();
      const name = (item.name || '').toLowerCase();
      const market = (item.market || '').toLowerCase();
      return code.includes(this._searchQuery)
        || name.includes(this._searchQuery)
        || market.includes(this._searchQuery)
        || (item.intro || '').toLowerCase().includes(this._searchQuery);
    });
  },

  _createCompactStockRow(item) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'stock-code-row';
    row.dataset.code = item.code;
    row.dataset.name = item.name || '';
    row.title = `${item.code} ${item.name}${item.intro ? '\n' + item.intro : ''}`;

    const iconWrap = document.createElement('span');
    iconWrap.className = 'stock-code-row-icon stock-code-icon';
    const img = document.createElement('img');
    img.width = 28;
    img.height = 28;
    if (typeof Utils !== 'undefined' && Utils.bindStockIcon) {
      Utils.bindStockIcon(img, item.code, item.name);
    }
    iconWrap.appendChild(img);

    const rank = document.createElement('span');
    rank.className = 'stock-code-row-rank';
    rank.textContent = item.rank_mv != null ? `#${item.rank_mv}` : '';

    const codeEl = document.createElement('span');
    codeEl.className = 'stock-code-row-code';
    codeEl.textContent = item.code;

    const textWrap = document.createElement('span');
    textWrap.className = 'stock-code-row-text';

    const nameEl = document.createElement('span');
    nameEl.className = 'stock-code-row-name';
    nameEl.textContent = item.name || item.code;

    textWrap.appendChild(nameEl);
    if (item.intro) {
      const introEl = document.createElement('span');
      introEl.className = 'stock-code-row-intro';
      introEl.textContent = item.intro;
      textWrap.appendChild(introEl);
    }

    row.append(iconWrap, rank, codeEl, textWrap);
    if (this.getCode() === item.code) row.classList.add('a');
    return row;
  },

  _paintUniverseViewport(viewport) {
    const list = this._universeDisplayList();
    const spacer = viewport.querySelector('.stock-universe-spacer');
    const rows = viewport.querySelector('.stock-universe-rows');
    if (!spacer || !rows) return;

    spacer.style.height = `${list.length * this._UNIVERSE_ROW_H}px`;
    const scrollTop = viewport.scrollTop;
    const viewH = viewport.clientHeight || 320;
    const start = Math.max(0, Math.floor(scrollTop / this._UNIVERSE_ROW_H) - 5);
    const count = Math.ceil(viewH / this._UNIVERSE_ROW_H) + 12;
    const end = Math.min(list.length, start + count);

    rows.style.transform = `translateY(${start * this._UNIVERSE_ROW_H}px)`;
    rows.replaceChildren();
    for (let i = start; i < end; i++) {
      rows.appendChild(this._createCompactStockRow(list[i]));
    }
  },

  _mountUniverseVirtual(host, list) {
    host.replaceChildren();
    const viewport = document.createElement('div');
    viewport.className = 'stock-universe-viewport';
    const spacer = document.createElement('div');
    spacer.className = 'stock-universe-spacer';
    const rows = document.createElement('div');
    rows.className = 'stock-universe-rows';
    viewport.append(spacer, rows);

    const onScroll = () => this._paintUniverseViewport(viewport);
    viewport.addEventListener('scroll', onScroll, { passive: true });
    viewport._universeScroll = onScroll;

    host.appendChild(viewport);
    requestAnimationFrame(() => this._paintUniverseViewport(viewport));
  },

  _createStockButton(item) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'stock-code-btn';
    btn.dataset.code = item.code;
    btn.dataset.name = item.name;
    btn.setAttribute('role', 'option');
    btn.title = `${item.code} ${item.name}`;

    const iconWrap = document.createElement('div');
    iconWrap.className = 'stock-code-icon';
    const img = document.createElement('img');
    img.width = 44;
    img.height = 44;
    if (typeof Utils !== 'undefined' && Utils.bindStockIcon) {
      Utils.bindStockIcon(img, item.code, item.name);
    } else {
      img.src = '';
      img.alt = item.name;
    }
    iconWrap.appendChild(img);

    const codeEl = document.createElement('span');
    codeEl.className = 'stock-code-btn-code';
    codeEl.textContent = item.code;

    const nameEl = document.createElement('span');
    nameEl.className = 'stock-code-btn-name';
    nameEl.textContent = item.name;

    btn.append(iconWrap, codeEl, nameEl);
    return btn;
  },

  _applyStockPicker(map) {
    const grid = document.getElementById('btCodeGrid');
    if (!grid) return;

    this._stockMap = map;
    const groups = { demo: [], watchlist: [], universe: [], db: [] };
    [...map.values()].forEach(item => {
      if (item.group === 'universe') return;
      const g = groups[item.group] ? item.group : 'db';
      groups[g].push(item);
    });
    groups.demo.sort((a, b) => a.code.localeCompare(b.code));
    groups.watchlist.sort((a, b) => a.code.localeCompare(b.code));
    groups.db.sort((a, b) => a.code.localeCompare(b.code));

    const keep = this.getCode();
    grid.replaceChildren();

    let total = 0;
    ['demo', 'watchlist', 'db'].forEach(key => {
      const list = groups[key];
      if (!list.length) return;
      total += list.length;

      const sec = document.createElement('div');
      sec.className = 'stock-code-group';
      sec.dataset.group = key;

      const title = document.createElement('div');
      title.className = 'stock-code-group-title';
      title.textContent = `${this._GROUP_LABELS[key]}（${list.length}）`;

      const row = document.createElement('div');
      row.className = 'stock-code-group-btns';
      list.forEach(item => row.appendChild(this._createStockButton(item)));

      sec.append(title, row);
      grid.appendChild(sec);
    });

    if (this._universeList.length) {
      total += this._universeList.length;
      const sec = document.createElement('div');
      sec.className = 'stock-code-group stock-code-group-universe';
      sec.dataset.group = 'universe';

      const title = document.createElement('div');
      title.className = 'stock-code-group-title';
      const shown = this._universeDisplayList().length;
      const marketLabel = this._MARKET_LABELS[this._activeMarket] || this._activeMarket;
      const suffix = this._searchQuery
        ? ` · 篩選 ${shown} / ${this._universeList.length}`
        : '';
      title.textContent = `${marketLabel} ${this._GROUP_LABELS.universe}（${shown}）${suffix}`;

      const host = document.createElement('div');
      host.className = 'stock-universe-host';
      this._mountUniverseVirtual(host, this._universeList);

      sec.append(title, host);
      grid.appendChild(sec);
    }

    if (!total) {
      grid.innerHTML = '<p class="stock-code-grid-empty">暫無可選股票，請在「數據中心」→ 股票庫 同步市值 TOP 20000</p>';
    }

    this._codesLoaded = total > 0;
    this._filterStockButtons();
    if (keep) this.setCode(keep);
    else this._updatePickHint('');
  },

  async loadStockOptions(force = false) {
    const grid = document.getElementById('btCodeGrid');
    if (!grid) return;
    if (this._loadingStocks && !force) return;
    this._loadingStocks = true;
    const loadHint = document.getElementById('btStockLoadHint');
    if (loadHint) loadHint.textContent = '載入股票列表…';

    const map = new Map();
    const add = (code, name, group) => this._stockMapAdd(map, code, name, group);

    this._DEFAULT_STOCKS.forEach(s => add(s.code, s.name, 'demo'));
    this._applyStockPicker(map);

    try {
      const silent = { silent: true };
      const [cfg, rules, stocks, names] = await Promise.all([
        this._withTimeout(Api.get('/api/config', silent)),
        this._withTimeout(Api.get('/api/alerts/rules', silent)),
        this._withTimeout(Api.getStocks(this._UNIVERSE_MAX), 60000),
        this._withTimeout(Api.get('/api/stocks/names', silent)),
      ]);

      const nameMap = names?.names || {};
      const wl = cfg?.watchlist;
      if (Array.isArray(wl)) {
        wl.forEach(code => {
          const r = rules?.rules?.[code];
          add(code, r?.name || nameMap[code], 'watchlist');
        });
      }
      if (rules?.rules && typeof rules.rules === 'object') {
        Object.entries(rules.rules).forEach(([code, r]) => {
          add(code, r?.name || nameMap[code], 'watchlist');
        });
      }

      const uniRows = stocks?.stocks || [];
      this._universeList = uniRows
        .map(s => ({
          code: String(s.code || '').trim(),
          name: (s.name || nameMap[s.code] || s.code || '').trim(),
          rank_mv: s.rank_mv,
          market: s.market,
          intro: (s.intro || '').trim(),
        }))
        .filter(s => s.code)
        .sort((a, b) => (a.rank_mv ?? 999999) - (b.rank_mv ?? 999999));

      this._universeList.forEach(s => this._stockMapAdd(map, s.code, s.name, 'universe'));
      this._renderMarketTabs();

      if (!this._universeList.length) {
        Object.entries(nameMap).slice(0, 80).forEach(([code, name]) => add(code, name, 'db'));
      }
    } catch (e) {
      console.warn('載入股票列表失敗:', e);
    } finally {
      this._loadingStocks = false;
    }

    this._applyStockPicker(map);
    const n = this._universeList.length;
    this._renderMarketTabs();
    if (loadHint) {
      loadHint.textContent = n > 0
        ? `已載入 ${n} 隻 · 滾動或搜尋`
        : '請在數據中心同步股票庫';
    }
    this._updatePickHint(this.getCode());
  },

  async run() {
    const code = this.getCode();
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'error');
    if (this._running) return Utils.toast('回測進行中，請稍候', 2000, 'error');
    this._running = true;

    const strategy = document.getElementById('btStrategy').value;
    const sl = document.getElementById('btSL').value;
    const tp = document.getElementById('btTP').value;
    const trailing = document.getElementById('btTrailing')?.value || '';
    const slippage = document.getElementById('btSlippage')?.value;
    const t1 = document.getElementById('btT1')?.checked;
    const limit = document.getElementById('btLimit')?.checked;
    const bench = document.getElementById('btBench').checked;

    document.getElementById('btResult').classList.add('h');
    document.getElementById('btAllResult').classList.add('h');

    // Use advanced backtest if any advanced params set
    const hasAdvanced = trailing || slippage || (t1 === false) || (limit === false);
    let d;

    if (hasAdvanced) {
      const body = {
        code, strategy,
        stop_loss_pct: sl || undefined,
        take_profit_pct: tp || undefined,
        trailing_stop_pct: trailing || undefined,
        slippage_pct: slippage ? parseFloat(slippage) : 0,
        enable_t1: t1 !== false,
        enable_limit: limit !== false,
        benchmark: bench,
      };
      d = await Api.runAdvancedBacktest(body);
    } else {
      d = await Api.runBacktest({ code, strategy, stop_loss_pct: sl, take_profit_pct: tp, benchmark: bench });
    }

    if (!d || !d.success) { this._running = false; return; }

    try {
      if (d.is_duplicate) {
        Utils.toast('⏳ ' + (d.message || '相同回測正在執行中，等待完成...'), 3000, 'warning');
      } else if (d.async && d.task_id) {
        Utils.toast('📋 任務已提交，執行中...', 2000, 'info');
      }
      const resolved = await Api.resolveTaskResponse(d);
      const r = resolved?.result || resolved?.task?.result;
      if (!r) {
        Utils.toast('未取得回測結果', 3000, 'error');
        return;
      }
      this._lastResult = r;
      this._displayResult(r);
    } catch (e) {
      Utils.toast('回測失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      this._running = false;
    }
  },

  /**
   * 顯示回測結果（可從 run() 或任務結果中調用）
   */
  _displayResult(r) {
    const code = r.code || '';
    const strategy = r.strategy || '';

    document.getElementById('btStats').innerHTML = `
      <div class="c"><h3>收益率</h3><div class="v ${Utils.badgeClass(r.total_return_pct)}">${Utils.formatPct(r.total_return_pct)}</div></div>
      <div class="c"><h3>年化收益</h3><div class="v ${Utils.badgeClass(r.annual_return_pct)}">${Utils.formatPct(r.annual_return_pct)}</div></div>
      <div class="c"><h3>夏普比率</h3><div class="v">${Utils.formatNum(r.sharpe_ratio, 4)}</div></div>
      <div class="c"><h3>最大回撤</h3><div class="v rd">${Utils.formatPct(-r.max_drawdown_pct)}</div></div>
      <div class="c"><h3>勝率</h3><div class="v">${Utils.formatNum(r.win_rate_pct, 1)}%</div></div>
      <div class="c"><h3>交易次數</h3><div class="v">${r.total_trades}</div></div>
      <div class="c"><h3>最終市值</h3><div class="v">¥${(r.final_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</div></div>`;

    // 風險指標
    document.getElementById('btRiskStats').innerHTML = `
      <div class="c"><h3>VaR 95%</h3><div class="v rd">${Utils.formatNum(r.var_95, 4)}</div></div>
      <div class="c"><h3>CVaR 95%</h3><div class="v rd">${Utils.formatNum(r.cvar_95, 4)}</div></div>
      <div class="c"><h3>Sortino</h3><div class="v">${Utils.formatNum(r.sortino_ratio, 4)}</div></div>
      <div class="c"><h3>Calmar</h3><div class="v">${Utils.formatNum(r.calmar_ratio, 4)}</div></div>
      <div class="c"><h3>年化波動率</h3><div class="v">${Utils.formatNum(r.annual_volatility, 4)}</div></div>
      <div class="c"><h3>月勝率</h3><div class="v">${Utils.formatNum(r.monthly_win_rate, 1)}%</div></div>
      <div class="c"><h3>盈虧比</h3><div class="v">${Utils.formatNum(r.profit_loss_ratio, 2)}</div></div>
      <div class="c"><h3>回撤恢復天數</h3><div class="v">${r.max_drawdown_recovery_days || 0}</div></div>`;

    // 基準對比
    const benchDiv = document.getElementById('btBenchStats');
    if (r.benchmark_comparison) {
      const b = r.benchmark_comparison;
      benchDiv.innerHTML = `
        <div class="c"><h3>Alpha</h3><div class="v ${Utils.badgeClass(b.alpha)}">${Utils.formatNum(b.alpha, 4)}</div></div>
        <div class="c"><h3>Beta</h3><div class="v">${Utils.formatNum(b.beta, 4)}</div></div>
        <div class="c"><h3>信息比率</h3><div class="v">${Utils.formatNum(b.information_ratio, 4)}</div></div>
        <div class="c"><h3>跟蹤誤差</h3><div class="v">${Utils.formatNum(b.tracking_error, 4)}</div></div>`;
      benchDiv.parentElement.classList.remove('h');
    } else {
      benchDiv.parentElement.classList.add('h');
    }

    // K 線圖
    const klineContainer = document.getElementById('btKlineContainer');
    const klineCanvas = document.getElementById('btKlineChart');
    if (klineContainer && typeof LightweightCharts !== 'undefined') {
      klineCanvas.style.display = 'none';
      klineContainer.style.display = 'block';
      Charts.drawLWKlineChart('btKlineContainer', r.kline, r.signals, `${code} ${strategy}`);
    } else {
      if (klineContainer) klineContainer.style.display = 'none';
      if (klineCanvas) {
        klineCanvas.style.display = 'block';
        Charts.drawKlineChart('btKlineChart', r.kline, r.signals, `${code} ${strategy}`);
      }
    }

    // 淨值曲線
    Charts.drawLineChart('btChart', [{ label: `${code} ${strategy}`, data: r.nav, dates: r.dates }]);

    // 月度收益熱力圖
    this._drawMonthlyHeatmap(r);

    // 回撤水下圖
    this._drawDrawdownChart(r);

    // 交易明細
    const trades = r.trade_details || [];
    document.getElementById('btTradeCount').textContent = trades.length + ' 筆';
    document.getElementById('btTrades').innerHTML = trades.map(t =>
      `<tr>
        <td>${t.buy_date}</td>
        <td class="r">${t.buy_price}</td>
        <td>${t.sell_date}</td>
        <td class="r">${t.sell_price}</td>
        <td class="r">${t.size}</td>
        <td class="r"><span class="b ${Utils.badgeClass(t.pnl)}">${t.pnl >= 0 ? '+' : ''}${t.pnl}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(t.return_pct)}">${Utils.formatPct(t.return_pct)}</span></td>
        <td class="r">${t.hold_days}</td>
      </tr>`
    ).join('');

    // Hide analysis panels on new backtest (if they exist)
    ['btTradeAnalysis', 'btMonteCarlo', 'btRollingMetrics'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.add('h');
    });

    document.getElementById('btResult').classList.remove('h');
  },

  async runMulti() {
    const code = this.getCode();
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'error');
    if (this._running) return Utils.toast('回測進行中，請稍候', 2000, 'error');
    this._running = true;

    document.getElementById('btResult').classList.add('h');
    document.getElementById('btAllResult').classList.add('h');

    const d = await Api.runMultiBacktest(code);
    if (!d || !d.success) { this._running = false; return; }

    try {
      if (d.is_duplicate) {
        Utils.toast('⏳ ' + (d.message || '相同任務執行中，等待完成...'), 3000, 'warning');
      } else if (d.async && d.task_id) {
        Utils.toast('📋 多策略對比已提交', 2000, 'info');
      }
      const resolved = await Api.resolveTaskResponse(d);
      const results = resolved?.results || resolved?.result || resolved?.task?.result;
      if (!results) {
        Utils.toast('未取得對比結果', 3000, 'error');
        return;
      }
      this.displayMultiResults(Array.isArray(results) ? results : (results.results || []));
    } catch (e) {
      Utils.toast('多策略對比失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      this._running = false;
    }
  },

  displayMultiResults(results) {
    if (!results || !results.length) return;
    document.getElementById('btResult').classList.add('h');
    document.getElementById('btAllCount').textContent = results.length + ' 個策略';
    document.getElementById('btAllTable').innerHTML = results.map(r =>
      `<tr>
        <td><strong>${r.strategy}</strong></td>
        <td class="r"><span class="b ${Utils.badgeClass(r.total_return_pct)}">${Utils.formatPct(r.total_return_pct)}</span></td>
        <td class="r">${Utils.formatNum(r.sharpe_ratio, 2)}</td>
        <td class="r">${Utils.formatNum(r.sortino_ratio, 2)}</td>
        <td class="r">${Utils.formatNum(r.calmar_ratio, 2)}</td>
        <td class="r">${Utils.formatPct(-r.max_drawdown_pct)}</td>
        <td class="r">${Utils.formatNum(r.var_95, 4)}</td>
        <td class="r">${Utils.formatNum(r.win_rate_pct, 1)}%</td>
        <td class="r">${r.total_trades}</td>
      </tr>`
    ).join('');
    const series = results.filter(r => r.nav && r.nav.length > 1).map(r => ({
      label: r.strategy,
      data: r.nav,
      dates: r.dates,
    }));
    if (typeof Charts !== 'undefined') Charts.drawLineChart('btAllChart', series);
    document.getElementById('btAllResult').classList.remove('h');
  },

  // ============================================================
  // Monthly Heatmap & Drawdown Chart
  // ============================================================

  /**
   * 月度收益熱力圖 — 從淨值數據中提取月度收益
   */
  _drawMonthlyHeatmap(r) {
    if (!r || !r.dates || !r.nav || r.dates.length < 2) return;

    const monthlyReturns = [];
    let monthStart = {};
    let prevNav = r.nav[0];

    for (let i = 0; i < r.dates.length; i++) {
      const date = r.dates[i];
      if (!date || date.length < 7) continue;
      const year = date.substring(0, 4);
      const month = parseInt(date.substring(5, 7));
      const key = year + '-' + month;

      if (!monthStart[key]) {
        monthStart[key] = { nav: r.nav[i], year: parseInt(year), month: month };
      }
      prevNav = r.nav[i];
    }

    // 計算每月收益
    const keys = Object.keys(monthStart).sort();
    for (let i = 0; i < keys.length; i++) {
      const cur = monthStart[keys[i]];
      let prevMonthNav = null;
      // 找上個月的最後一個 NAV
      if (i > 0) {
        const prevKey = keys[i - 1];
        // 找到 dates 中屬於上個月的最後一個 NAV
        for (let j = r.dates.length - 1; j >= 0; j--) {
          const d = r.dates[j];
          if (d && d.substring(0, 4) === prevKey.split('-')[0] &&
              parseInt(d.substring(5, 7)) === parseInt(prevKey.split('-')[1])) {
            prevMonthNav = r.nav[j];
            break;
          }
        }
      }
      if (prevMonthNav && prevMonthNav > 0) {
        monthlyReturns.push({
          year: cur.year,
          month: cur.month,
          return_pct: ((cur.nav / prevMonthNav) - 1) * 100,
        });
      }
    }

    if (monthlyReturns.length) {
      Charts.drawMonthlyHeatmap('btMonthlyHeatmap', monthlyReturns);
    }
  },

  /**
   * 回撤水下圖 — 從淨值計算回撤序列
   */
  _drawDrawdownChart(r) {
    if (!r || !r.nav || r.nav.length < 2) return;

    const nav = r.nav;
    const dates = r.dates || nav.map((_, i) => String(i));
    const drawdown = [];
    let peak = nav[0];

    for (let i = 0; i < nav.length; i++) {
      if (nav[i] > peak) peak = nav[i];
      const dd = peak > 0 ? ((nav[i] - peak) / peak) * 100 : 0;
      drawdown.push(dd);
    }

    Charts.drawAreaChart('btDrawdownChart', [{
      label: '回撤 (%)',
      data: drawdown,
      dates: dates,
      color: '#ef4444',
      fill: true,
    }]);
  },

  // ============================================================
  // Trade Analysis (client-side from last result)
  // ============================================================

  runTradeAnalysis() {
    const r = this._lastResult;
    if (!r || !r.trade_details || !r.trade_details.length) {
      return Utils.toast('請先運行回測');
    }

    const trades = r.trade_details;
    const wins = trades.filter(t => t.return_pct > 0);
    const losses = trades.filter(t => t.return_pct <= 0);
    const returns = trades.map(t => t.return_pct);
    const holdDays = trades.map(t => t.hold_days);

    // Win/Loss streaks
    let maxWinStreak = 0, maxLoseStreak = 0, curWin = 0, curLose = 0;
    trades.forEach(t => {
      if (t.return_pct > 0) { curWin++; curLose = 0; maxWinStreak = Math.max(maxWinStreak, curWin); }
      else { curLose++; curWin = 0; maxLoseStreak = Math.max(maxLoseStreak, curLose); }
    });

    // Return distribution
    const buckets = {};
    const bucketSize = 5;
    returns.forEach(r => {
      const b = Math.floor(r / bucketSize) * bucketSize;
      buckets[b] = (buckets[b] || 0) + 1;
    });

    const avgWin = wins.length ? wins.reduce((s, t) => s + t.return_pct, 0) / wins.length : 0;
    const avgLoss = losses.length ? losses.reduce((s, t) => s + t.return_pct, 0) / losses.length : 0;
    const avgHold = holdDays.reduce((s, d) => s + d, 0) / holdDays.length;

    document.getElementById('btTAStats').innerHTML = `
      <div class="c"><h3>總交易</h3><div class="v">${trades.length}</div></div>
      <div class="c"><h3>盈利/虧損</h3><div class="v gn">${wins.length} / <span class="rd">${losses.length}</span></div></div>
      <div class="c"><h3>平均盈利</h3><div class="v gn">${Utils.formatPct(avgWin)}</div></div>
      <div class="c"><h3>平均虧損</h3><div class="v rd">${Utils.formatPct(avgLoss)}</div></div>
      <div class="c"><h3>平均持有天數</h3><div class="v">${avgHold.toFixed(1)}</div></div>
      <div class="c"><h3>最長連勝</h3><div class="v gn">${maxWinStreak}</div></div>
      <div class="c"><h3>最長連虧</h3><div class="v rd">${maxLoseStreak}</div></div>
      <div class="c"><h3>最大單筆盈利</h3><div class="v gn">${Utils.formatPct(Math.max(...returns))}</div></div>
      <div class="c"><h3>最大單筆虧損</h3><div class="v rd">${Utils.formatPct(Math.min(...returns))}</div></div>`;

    // Return distribution chart
    const labels = Object.keys(buckets).sort((a, b) => a - b).map(k => k + '%');
    const data = Object.keys(buckets).sort((a, b) => a - b).map(k => buckets[k]);
    Charts.drawBarChart('mcChart', data, labels, '交易次數');

    document.getElementById('btTradeAnalysis').classList.remove('h');
    document.getElementById('btMonteCarlo').classList.add('h');
    document.getElementById('btRollingMetrics').classList.add('h');
  },

  // ============================================================
  // Monte Carlo (client-side simulation)
  // ============================================================

  runMonteCarlo() {
    const r = this._lastResult;
    if (!r || !r.trade_details || !r.trade_details.length) {
      return Utils.toast('請先運行回測');
    }

    const trades = r.trade_details;
    const returns = trades.map(t => t.return_pct / 100);
    const nSims = 500;
    const nTrades = trades.length;

    // Simulate
    const finalValues = [];
    const allPaths = [];

    for (let sim = 0; sim < nSims; sim++) {
      let nav = 1.0;
      const path = [nav];
      for (let t = 0; t < nTrades; t++) {
        const idx = Math.floor(Math.random() * returns.length);
        nav *= (1 + returns[idx]);
        path.push(nav);
      }
      finalValues.push(nav);
      if (sim < 10) allPaths.push(path); // Keep first 10 for chart
    }

    finalValues.sort((a, b) => a - b);
    const p5 = finalValues[Math.floor(nSims * 0.05)];
    const p50 = finalValues[Math.floor(nSims * 0.5)];
    const p95 = finalValues[Math.floor(nSims * 0.95)];
    const mean = finalValues.reduce((s, v) => s + v, 0) / nSims;

    document.getElementById('mcStats').innerHTML = `
      <div class="c"><h3>模擬次數</h3><div class="v">${nSims}</div></div>
      <div class="c"><h3>5% 分位</h3><div class="v rd">${Utils.formatPct((p5 - 1) * 100)}</div></div>
      <div class="c"><h3>中位數</h3><div class="v">${Utils.formatPct((p50 - 1) * 100)}</div></div>
      <div class="c"><h3>95% 分位</h3><div class="v gn">${Utils.formatPct((p95 - 1) * 100)}</div></div>
      <div class="c"><h3>均值</h3><div class="v">${Utils.formatPct((mean - 1) * 100)}</div></div>
      <div class="c"><h3>虧損概率</h3><div class="v rd">${((finalValues.filter(v => v < 1).length / nSims) * 100).toFixed(1)}%</div></div>`;

    // Draw paths
    const labels = Array.from({ length: nTrades + 1 }, (_, i) => i);
    const series = allPaths.map((path, i) => ({
      label: `模擬 ${i + 1}`,
      data: path,
      dates: labels.map(String),
    }));
    Charts.drawLineChart('mcChart2', series);

    document.getElementById('btMonteCarlo').classList.remove('h');
    document.getElementById('btTradeAnalysis').classList.add('h');
    document.getElementById('btRollingMetrics').classList.add('h');
  },

  // ============================================================
  // Rolling Metrics (client-side from NAV)
  // ============================================================

  runRollingMetrics() {
    const r = this._lastResult;
    if (!r || !r.nav || r.nav.length < 60) {
      return Utils.toast('需要至少 60 個數據點');
    }

    const nav = r.nav;
    const dates = r.dates || nav.map((_, i) => String(i));
    const windowSize = 60;

    // Calculate rolling returns and volatility
    const rollingSharpe = [];
    const rollingVol = [];
    const rollingDD = [];
    const rollingLabels = [];

    for (let i = windowSize; i < nav.length; i++) {
      const windowNav = nav.slice(i - windowSize, i);
      const windowReturns = [];
      for (let j = 1; j < windowNav.length; j++) {
        windowReturns.push((windowNav[j] - windowNav[j - 1]) / windowNav[j - 1]);
      }

      const mean = windowReturns.reduce((s, v) => s + v, 0) / windowReturns.length;
      const std = Math.sqrt(windowReturns.reduce((s, v) => s + (v - mean) ** 2, 0) / windowReturns.length);
      const annReturn = mean * 252;
      const annVol = std * Math.sqrt(252);
      const sharpe = annVol > 0 ? annReturn / annVol : 0;

      // Rolling max drawdown
      let peak = windowNav[0];
      let maxDD = 0;
      windowNav.forEach(v => {
        if (v > peak) peak = v;
        const dd = (peak - v) / peak;
        if (dd > maxDD) maxDD = dd;
      });

      rollingSharpe.push(sharpe);
      rollingVol.push(annVol * 100);
      rollingDD.push(-maxDD * 100);
      rollingLabels.push(dates[i] || '');
    }

    const series = [
      { label: '滾動夏普', data: rollingSharpe, dates: rollingLabels },
      { label: '滾動波動率 (%)', data: rollingVol, dates: rollingLabels },
      { label: '滾動回撤 (%)', data: rollingDD, dates: rollingLabels },
    ];
    Charts.drawLineChart('rollingChart', series);

    document.getElementById('btRollingMetrics').classList.remove('h');
    document.getElementById('btTradeAnalysis').classList.add('h');
    document.getElementById('btMonteCarlo').classList.add('h');
  },
};

window.Backtest = Backtest;
