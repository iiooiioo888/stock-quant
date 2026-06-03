/**
 * dashboard.js — 儀表盤 Tab（含迷你走勢圖 + 多種圖表）
 */

const Dashboard = {
  _dataReady: false,
  _pollTimer: null,
  _pollCount: 0,
  _maxPolls: 30,
  _healthCache: null,
  _healthCacheAt: 0,
  _chartsLoaded: false,
  _backtestAggCache: null,
  _sparklineCache: {},
  _sparklineCacheTtlMs: 60000,
  _lwRetryCount: 0,
  _lwRetryMax: 20,

  async _getHealth(force = false) {
    const now = Date.now();
    if (!force && this._healthCache && now - this._healthCacheAt < 15000) {
      return this._healthCache;
    }
    const d = await Api.getHealth();
    if (d) {
      this._healthCache = d;
      this._healthCacheAt = now;
    }
    return d;
  },

  async _getSparklines(codes, days) {
    const key = codes.join(',') + ':' + days;
    const hit = this._sparklineCache[key];
    if (hit && Date.now() - hit.at < this._sparklineCacheTtlMs) {
      return hit.data;
    }
    const d = await Api.get(`/api/sparkline?codes=${codes.join(',')}&days=${days}`);
    if (d?.sparklines) {
      this._sparklineCache[key] = { at: Date.now(), data: d };
    }
    return d;
  },

  async _getBacktestAgg(limit = 50) {
    if (this._backtestAggCache && this._backtestAggCache.limit >= limit) {
      return this._backtestAggCache.results;
    }
    const d = await Api.getBacktestHistory('', '', limit);
    const results = d?.results || [];
    this._backtestAggCache = { limit, results };
    return results;
  },

  async load() {
    this._pollCount = 0;
    this._dataReady = false;
    this._chartsLoaded = false;
    const health = await this._getHealth(true);
    await Promise.allSettled([
      this.loadStats(health),
      this.loadRules(),
      this.loadDashboardCharts(),
    ]);
    this._chartsLoaded = true;
    this._checkDataReady(health);
  },

  /** Tab 顯示時補繪/重算圖表尺寸 */
  ensureCharts() {
    const ids = [
      'dashSparklineChart', 'dashBacktestChart', 'dashSignalRadar', 'dashSectorChart', 'dashLeaderboardChart',
      'dashMomentumRankChart', 'dashVolatilityRankChart', 'dashDrawdownRankChart', 'dashRiskScatterChart',
    ];
    const indexGrid = document.getElementById('indexChartsGrid');
    if (indexGrid && !indexGrid.querySelector('.index-chart-card')) {
      this._loadMajorIndicesCharts();
    }
    const tvGrid = document.getElementById('tvWatchlistGrid');
    if (tvGrid && tvGrid.querySelector('.index-charts-loading')) {
      this._lwRetryCount = 0;
      this._loadTradingViewWall();
    }
    const missing = ids.some(id => {
      const el = document.getElementById(id);
      return el && !Chart.getChart(el);
    });
    if (missing) {
      this.loadDashboardCharts(true);
    } else if (typeof Charts !== 'undefined') {
      Charts.resizeTab('tab-dashboard');
    }
  },

  stopPolling(hideBanner = true) {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    if (hideBanner) {
      const el = document.getElementById('dataLoadingBanner');
      if (el) el.style.display = 'none';
    }
  },

  async _checkDataReady(cachedHealth) {
    if (this._dataReady) return;
    this._pollCount++;
    if (this._pollCount > this._maxPolls) {
      this.stopPolling();
      this._showDataLoading('數據下載較慢，請手動刷新頁面查看');
      return;
    }
    const d = cachedHealth || await this._getHealth();
    if (!d) return;
    if (d.data_ready) {
      this._dataReady = true;
      this._hideDataLoading(d);
      this.stopPolling();
      return;
    }
    this._showDataLoading();
    if (!this._pollTimer) {
      this._pollTimer = setInterval(() => this._checkDataReady(), 10000);
    }
  },

  _showDataLoading(msg) {
    let el = document.getElementById('dataLoadingBanner');
    if (!el) {
      el = document.createElement('div');
      el.id = 'dataLoadingBanner';
      el.className = 'state-loading-banner';
      el.innerHTML = '<span class="ld"></span><div><strong>📊 首次啟動中</strong><br><span class="state-loading-sub">正在下載歷史數據和生成回測，約需 1-2 分鐘，數據就緒後自動刷新...</span></div>';
      const grid = document.getElementById('statsGrid');
      if (grid) grid.parentNode.insertBefore(el, grid);
    }
    if (msg) el.querySelector('.state-loading-sub').textContent = msg;
    el.style.display = 'flex';
  },

  _hideDataLoading(cachedHealth) {
    const el = document.getElementById('dataLoadingBanner');
    if (el) el.style.display = 'none';
    if (cachedHealth) {
      this._healthCache = cachedHealth;
      this._healthCacheAt = Date.now();
    }
    this.loadStats(cachedHealth);
    if (!this._chartsLoaded) {
      this.loadDashboardCharts().then(() => { this._chartsLoaded = true; });
    }
  },

  async loadStats(cachedHealth) {
    const d = cachedHealth || await this._getHealth();
    if (!d) return;

    document.getElementById('statsGrid').innerHTML = `
      <div class="dash-kpi dash-kpi--blue stat-card">
        <span class="dash-kpi-icon" aria-hidden="true">📊</span>
        <div class="dash-kpi-body">
          <span class="dash-kpi-label">監控股票</span>
          <span class="dash-kpi-value bl"><span class="dash-kpi-num" data-target="${d.total_stocks || 0}">0</span></span>
          <span class="dash-kpi-hint stat-hint">正在追蹤</span>
        </div>
      </div>
      <div class="dash-kpi dash-kpi--green stat-card">
        <span class="dash-kpi-icon" aria-hidden="true">📁</span>
        <div class="dash-kpi-body">
          <span class="dash-kpi-label">數據條數</span>
          <span class="dash-kpi-value"><span class="dash-kpi-num" data-target="${d.total_klines || 0}" data-format="locale">0</span></span>
          <span class="dash-kpi-hint stat-hint">歷史 K 線</span>
        </div>
      </div>
      <div class="dash-kpi dash-kpi--red stat-card">
        <span class="dash-kpi-icon" aria-hidden="true">🔔</span>
        <div class="dash-kpi-body">
          <span class="dash-kpi-label">累計預警</span>
          <span class="dash-kpi-value rd"><span class="dash-kpi-num" data-target="${d.total_alerts || 0}">0</span></span>
          <span class="dash-kpi-hint stat-hint">已觸發</span>
        </div>
      </div>
      <div class="dash-kpi dash-kpi--purple stat-card">
        <span class="dash-kpi-icon" aria-hidden="true">💾</span>
        <div class="dash-kpi-body">
          <span class="dash-kpi-label">數據庫</span>
          <span class="dash-kpi-value"><span class="dash-kpi-num" data-target="${d.db_size_mb || 0}" data-decimals="1">0</span><span class="dash-kpi-unit">MB</span></span>
          <span class="dash-kpi-hint stat-hint">存儲佔用</span>
        </div>
      </div>`;

    // KPI 動態計數動畫
    document.querySelectorAll('#statsGrid .dash-kpi-num[data-target]').forEach((el, i) => {
      const target = parseFloat(el.dataset.target) || 0;
      const decimals = parseInt(el.dataset.decimals) || 0;
      setTimeout(() => {
        if (typeof App !== 'undefined' && App.animateCounter) {
          App.animateCounter(el, target, {
            duration: 700,
            decimals: decimals,
          });
        } else {
          el.textContent = el.dataset.format === 'locale' ? target.toLocaleString() : target;
        }
      }, i * 100);
    });

    document.getElementById('sysStatus').textContent = '運行 ' + (d.uptime || '');
  },

  async _waitChartLibs(chartJsMs = 8000, lwMs = 12000) {
    const start = Date.now();
    while (Date.now() - start < chartJsMs) {
      if (typeof Chart !== 'undefined') break;
      await new Promise(r => setTimeout(r, 80));
    }
    if (typeof Chart === 'undefined') return false;
    const lwStart = Date.now();
    while (Date.now() - lwStart < lwMs) {
      if (typeof Charts !== 'undefined' && Charts._lwReady?.()) return true;
      await new Promise(r => setTimeout(r, 80));
    }
    return typeof Charts !== 'undefined' && Charts._lwReady?.();
  },

  _lwLoadFailedHtml() {
    return '<div class="index-charts-loading">圖表庫載入失敗，請檢查網路或 CDN（lightweight-charts）</div>';
  },

  _bumpLwRetry() {
    this._lwRetryCount += 1;
    return this._lwRetryCount >= this._lwRetryMax;
  },

  /**
   * 載入儀表盤所有新增圖表
   */
  async loadDashboardCharts(force = false) {
    if (this._chartsLoading) return;
    if (this._chartsLoaded && !force) return;
    this._chartsLoading = true;
    try {
    const ready = await this._waitChartLibs();
    if (!ready) {
      setTimeout(() => { this._chartsLoading = false; this.loadDashboardCharts(force); }, 400);
      return;
    }
    await Promise.allSettled([
      this._loadMajorIndicesCharts(),
      this._loadTradingViewWall(),
      this._loadSparklineChart(),
      this._loadBacktestHistory(),
      this._loadSignalRadar(),
      this._loadSectorBars(),
      this._loadStrategyLeaderboard(),
      this.loadCryptoPrices(),
    ]);
    if (typeof Charts !== 'undefined') {
      Charts.resizeTab('tab-dashboard');
    }
    this._chartsLoaded = true;
    } finally {
      this._chartsLoading = false;
    }
  },

  _indexChartId(symbol) {
    return 'idx-chart-' + String(symbol).replace(/[^a-zA-Z0-9]/g, '_');
  },

  _formatIndexPrice(value, symbol) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '-';
    if (symbol.includes('^') || symbol.endsWith('.SS') || symbol.endsWith('.SZ')) {
      return n >= 1000 ? n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
        : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  },

  _tvChartId(code) {
    return 'tv-chart-' + String(code).replace(/[^a-zA-Z0-9]/g, '_');
  },

  _escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  },

  _calcSeriesMetrics(code, sp) {
    const prices = (sp.prices || []).map(Number).filter(Number.isFinite);
    const dates = sp.dates || prices.map((_, i) => String(i));
    if (prices.length < 3) return null;
    const returns = [];
    for (let i = 1; i < prices.length; i++) {
      if (prices[i - 1] > 0) returns.push(prices[i] / prices[i - 1] - 1);
    }
    const avg = returns.length ? returns.reduce((a, b) => a + b, 0) / returns.length : 0;
    const variance = returns.length
      ? returns.reduce((sum, r) => sum + Math.pow(r - avg, 2), 0) / returns.length
      : 0;
    let peak = prices[0];
    let maxDd = 0;
    prices.forEach(p => {
      peak = Math.max(peak, p);
      if (peak > 0) maxDd = Math.min(maxDd, p / peak - 1);
    });
    const base20 = prices[Math.max(0, prices.length - 21)];
    const momentum20 = base20 > 0 ? (prices[prices.length - 1] / base20 - 1) * 100 : 0;
    const totalReturn = prices[0] > 0 ? (prices[prices.length - 1] / prices[0] - 1) * 100 : 0;
    const vol = Math.sqrt(variance) * Math.sqrt(252) * 100;
    return {
      code,
      dates,
      prices,
      latest: prices[prices.length - 1],
      totalReturn,
      momentum20,
      volatility: vol,
      maxDrawdown: maxDd * 100,
      riskScore: vol ? momentum20 / vol : 0,
      changePct: sp.change_pct ?? totalReturn,
    };
  },

  async _loadTradingViewWall() {
    const grid = document.getElementById('tvWatchlistGrid');
    const meta = document.getElementById('tvChartsMeta');
    if (!grid || typeof Charts === 'undefined') return;
    if (!Charts._lwReady?.()) {
      if (this._bumpLwRetry()) {
        grid.innerHTML = this._lwLoadFailedHtml();
        this._renderProfessionalMetrics([]);
        if (meta) meta.textContent = '圖表庫未載入';
        return;
      }
      setTimeout(() => this._loadTradingViewWall(), 400);
      return;
    }
    this._lwRetryCount = 0;

    try {
      const codes = await this._resolveSparklineCodes(8);
      const d = await this._getSparklines(codes, 90);
      const sparklines = d?.sparklines || {};
      const metrics = codes
        .map(code => this._calcSeriesMetrics(code, sparklines[code] || {}))
        .filter(Boolean);

      if (!metrics.length) {
        grid.innerHTML = '<div class="index-charts-loading">暫無本地行情數據，請先在「下載數據」同步 K 線</div>';
        this._renderProfessionalMetrics([]);
        if (meta) meta.textContent = '本地行情不足';
        return;
      }

      if (meta) {
        meta.textContent = `TradingView Lightweight Charts · ${metrics.length} 檔監控股 · 近 90 日`;
      }

      if (typeof Charts.destroyIndexCharts === 'function') {
        Charts.destroyIndexCharts('tv-chart-');
      }

      grid.innerHTML = metrics.map(m => {
        const chgCls = m.totalReturn > 0 ? 'up' : (m.totalReturn < 0 ? 'down' : 'flat');
        const sign = m.totalReturn > 0 ? '+' : '';
        const riskCls = m.riskScore >= 0 ? 'up' : 'down';
        return `
          <article class="tv-chart-card tv-chart-card--link" role="button" tabindex="0"
            title="查看 ${this._escapeHtml(m.code)} 個股分析"
            onclick="App.openStockDetail('${String(m.code).replace(/'/g, "\\'")}')">
            <header class="tv-chart-header">
              <div>
                <div class="tv-chart-code">${this._escapeHtml(m.code)}</div>
                <div class="tv-chart-sub">90日走勢 · 本地資料庫</div>
              </div>
              <div class="tv-chart-quote">
                <div class="tv-chart-price">${this._formatIndexPrice(m.latest, m.code)}</div>
                <div class="index-chart-change ${chgCls}">${sign}${m.totalReturn.toFixed(2)}%</div>
              </div>
            </header>
            <div id="${this._tvChartId(m.code)}" class="tv-chart-cw"></div>
            <footer class="tv-metrics-row">
              <span>動量 <b class="${m.momentum20 >= 0 ? 'up' : 'down'}">${m.momentum20.toFixed(2)}%</b></span>
              <span>波動 <b>${m.volatility.toFixed(1)}%</b></span>
              <span>回撤 <b class="down">${m.maxDrawdown.toFixed(2)}%</b></span>
              <span>風險比 <b class="${riskCls}">${m.riskScore.toFixed(2)}</b></span>
            </footer>
          </article>`;
      }).join('');

      requestAnimationFrame(() => {
        metrics.forEach(m => {
          Charts.drawTVSparklineChart(this._tvChartId(m.code), m.dates, m.prices, { changePct: m.totalReturn });
        });
        this._renderProfessionalMetrics(metrics);
        Charts.resizeTab('tab-dashboard');
      });
    } catch (e) {
      grid.innerHTML = '<div class="index-charts-loading">專業行情牆載入失敗，請稍後刷新</div>';
    }
  },

  _renderProfessionalMetrics(metrics) {
    if (typeof Charts === 'undefined') return;
    if (!metrics?.length) {
      ['dashMomentumRankChart', 'dashVolatilityRankChart', 'dashDrawdownRankChart', 'dashRiskScatterChart']
        .forEach(id => Charts.setPlaceholder(id, '暫無足夠行情數據'));
      return;
    }

    const byMomentum = [...metrics].sort((a, b) => b.momentum20 - a.momentum20).slice(0, 8);
    Charts.clearPlaceholder('dashMomentumRankChart');
    Charts.drawHorizontalBarChart(
      'dashMomentumRankChart',
      byMomentum.map(m => m.code),
      byMomentum.map(m => m.momentum20),
      '20日動量 (%)',
    );

    const byVol = [...metrics].sort((a, b) => b.volatility - a.volatility).slice(0, 8);
    Charts.clearPlaceholder('dashVolatilityRankChart');
    Charts.drawHorizontalBarChart(
      'dashVolatilityRankChart',
      byVol.map(m => m.code),
      byVol.map(m => m.volatility),
      '年化波動率 (%)',
    );

    const byDd = [...metrics].sort((a, b) => a.maxDrawdown - b.maxDrawdown).slice(0, 8);
    Charts.clearPlaceholder('dashDrawdownRankChart');
    Charts.drawHorizontalBarChart(
      'dashDrawdownRankChart',
      byDd.map(m => m.code),
      byDd.map(m => m.maxDrawdown),
      '最大回撤 (%)',
    );

    this._renderRiskScatter(metrics);
  },

  _renderRiskScatter(metrics) {
    const canvas = document.getElementById('dashRiskScatterChart');
    if (!canvas || typeof Chart === 'undefined') return;
    Charts.clearPlaceholder('dashRiskScatterChart');
    const old = Chart.getChart(canvas);
    if (old) old.destroy();
    const colors = Charts.getThemeColors();
    new Chart(canvas.getContext('2d'), {
      type: 'scatter',
      data: {
        datasets: [{
          label: '監控股',
          data: metrics.map(m => ({ x: m.volatility, y: m.momentum20, code: m.code })),
          borderColor: '#38bdf8',
          backgroundColor: metrics.map(m => m.momentum20 >= 0 ? 'rgba(34,197,94,0.72)' : 'rgba(239,68,68,0.72)'),
          pointRadius: 5,
          pointHoverRadius: 7,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
            callbacks: {
              label: ctx => {
                const p = ctx.raw || {};
                return `${p.code}: 動量 ${Number(p.y || 0).toFixed(2)}%, 波動 ${Number(p.x || 0).toFixed(1)}%`;
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: '年化波動率 (%)', color: colors.text },
            ticks: { color: colors.text, font: { size: 9 } },
            grid: { color: colors.grid },
          },
          y: {
            title: { display: true, text: '20日動量 (%)', color: colors.text },
            ticks: { color: colors.text, font: { size: 9 } },
            grid: { color: colors.grid },
          },
        },
      },
    });
    Charts._scheduleResize(canvas);
  },

  /**
   * 全球主要指數 — 專業 K 線圖
   */
  async _loadMajorIndicesCharts() {
    const grid = document.getElementById('indexChartsGrid');
    const meta = document.getElementById('indexChartsMeta');
    if (!grid) return;

    const lwReady = typeof Charts !== 'undefined' && Charts._lwReady && Charts._lwReady();
    if (!lwReady) {
      if (this._bumpLwRetry()) {
        grid.innerHTML = this._lwLoadFailedHtml();
        return;
      }
      setTimeout(() => this._loadMajorIndicesCharts(), 400);
      return;
    }
    this._lwRetryCount = 0;

    try {
      const d = await Api.getIndicesCharts(90, 'dashboard');
      const list = d?.indices || [];
      if (!list.length) {
        grid.innerHTML = '<div class="index-charts-loading">暫無法取得指數行情，請稍後刷新</div>';
        return;
      }

      if (meta) {
        const srcHint = (d.sources && d.sources.length)
          ? ` · ${d.sources.join(' / ')}`
          : '';
        meta.textContent = `專業 K 線 · ${list.length} 個指數 · 近 ${d.days || 90} 日${srcHint}`;
      }

      if (typeof Charts !== 'undefined' && Charts.destroyIndexCharts) {
        Charts.destroyIndexCharts();
      }

      grid.innerHTML = list.map(item => {
        const id = this._indexChartId(item.symbol);
        const chg = Number(item.change_pct) || 0;
        const chgCls = chg > 0 ? 'up' : (chg < 0 ? 'down' : 'flat');
        const sign = chg > 0 ? '+' : '';
        return `
        <article class="index-chart-card" data-symbol="${item.symbol}">
          <header class="index-chart-header">
            <div>
              <div class="index-chart-title">${item.name}</div>
              <div class="index-chart-symbol">${item.symbol}</div>
            </div>
            <div class="index-chart-quote">
              <div class="index-chart-price">${this._formatIndexPrice(item.latest, item.symbol)}</div>
              <div class="index-chart-change ${chgCls}">${sign}${chg.toFixed(2)}%</div>
            </div>
          </header>
          <div id="${id}" class="index-chart-cw"></div>
        </article>`;
      }).join('');

      requestAnimationFrame(() => {
        list.forEach(item => {
          const cid = this._indexChartId(item.symbol);
          if (typeof Charts !== 'undefined') {
            Charts.drawIndexKlineChart(cid, item.kline || []);
          }
        });
        if (typeof Charts !== 'undefined') {
          Charts.resizeTab('tab-dashboard');
        }
      });
    } catch (e) {
      grid.innerHTML = '<div class="index-charts-loading">指數行情載入失敗，請檢查網路後重試</div>';
    }
  },

  async _resolveSparklineCodes(max = 6) {
    const cfg = await Api.getConfig();
    const wl = cfg?.watchlist;
    if (Array.isArray(wl) && wl.length) {
      return wl.slice(0, max).map(c => String(c).trim()).filter(Boolean);
    }
    return ['000001', '600519', '000858'];
  },

  _strategyLabel(row) {
    const key = row.strategy || row.name;
    if (typeof SignalLabels !== 'undefined' && key) {
      return row.strategy_name || SignalLabels.strategyName(key, 'short');
    }
    return row.strategy_name || key || '-';
  },

  _signalItems(stockRow) {
    const raw = stockRow.signals || stockRow.strategies || [];
    return Array.isArray(raw) ? raw : [];
  },

  _setPanelHint(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text || '—';
  },

  _shortStrategyName(name) {
    if (typeof SignalLabels !== 'undefined' && SignalLabels.STRATEGIES[name]) {
      return SignalLabels.strategyName(name, 'chart');
    }
    if (typeof SignalLabels !== 'undefined') {
      return SignalLabels.label(name);
    }
    const s = String(name || '');
    return s.length > 14 ? s.slice(0, 12) + '…' : s;
  },

  async _leaderboardFromBacktest(limit = 10) {
    const rows = await this._getBacktestAgg(50);
    if (!rows.length) return [];
    const buckets = {};
    for (const r of rows) {
      const name = r.strategy;
      if (!name) continue;
      if (!buckets[name]) {
        buckets[name] = { strategy_name: name, sharpe_ratio: [], win_rate_pct: [] };
      }
      if (r.sharpe_ratio != null) buckets[name].sharpe_ratio.push(Number(r.sharpe_ratio));
      if (r.win_rate_pct != null) buckets[name].win_rate_pct.push(Number(r.win_rate_pct));
    }
    const avg = arr => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);
    return Object.values(buckets)
      .map(g => ({
        strategy_name: g.strategy_name,
        sharpe_ratio: avg(g.sharpe_ratio),
        win_rate_pct: avg(g.win_rate_pct),
      }))
      .filter(g => g.sharpe_ratio || g.win_rate_pct)
      .sort((a, b) => (b.sharpe_ratio || 0) - (a.sharpe_ratio || 0))
      .slice(0, limit);
  },

  /**
   * 監控股今日漲跌 — 橫向條形（按漲跌幅排序，一眼掃描）
   */
  async _loadSparklineChart() {
    const canvasId = 'dashSparklineChart';
    try {
      const codes = await this._resolveSparklineCodes(8);
      const d = await this._getSparklines(codes, 30);
      if (!d?.sparklines) {
        this._setPanelHint('dashSparklineHint', '暫無本地 K 線');
        Charts.setPlaceholder(canvasId, '請在「數據中心 → 下載入庫」同步行情');
        return;
      }

      const rows = [];
      for (const code of codes) {
        const sp = d.sparklines[code];
        if (!sp?.prices?.length) continue;
        const prices = sp.prices.map(Number).filter(Number.isFinite);
        if (prices.length < 2) continue;
        let chg = Number(sp.change_pct);
        if (!Number.isFinite(chg)) {
          const base = prices[0];
          chg = base > 0 ? (prices[prices.length - 1] / base - 1) * 100 : 0;
        }
        rows.push({ code, chg });
      }

      if (!rows.length) {
        this._setPanelHint('dashSparklineHint', '暫無有效行情');
        Charts.setPlaceholder(canvasId, '請在「數據中心 → 下載入庫」同步行情');
        return;
      }

      rows.sort((a, b) => b.chg - a.chg);
      const labels = rows.map(r => r.code);
      const data = rows.map(r => r.chg);
      const avg = data.reduce((a, b) => a + b, 0) / data.length;
      const up = data.filter(v => v > 0).length;
      this._setPanelHint('dashSparklineHint', `${rows.length} 檔 · 漲 ${up} 跌 ${rows.length - up} · 均 ${avg >= 0 ? '+' : ''}${avg.toFixed(2)}%`);

      Charts.clearPlaceholder(canvasId);
      Charts.drawHorizontalBarChart(canvasId, labels, data, '漲跌幅 (%)');
    } catch (e) {
      this._setPanelHint('dashSparklineHint', '載入失敗');
      Charts.setPlaceholder(canvasId, '載入失敗，請稍後重試');
    }
  },

  /**
   * 策略平均收益 — 按策略聚合近 30 次回測
   */
  async _loadBacktestHistory() {
    const canvasId = 'dashBacktestChart';
    try {
      const rows = await this._getBacktestAgg(30);
      if (!rows.length) {
        this._setPanelHint('dashBacktestHint', '尚無回測');
        Charts.setPlaceholder(canvasId, '尚無回測記錄，請到「策略回測」運行');
        return;
      }

      const buckets = {};
      for (const r of rows) {
        const name = r.strategy;
        if (!name) continue;
        if (!buckets[name]) buckets[name] = [];
        buckets[name].push(Number(r.total_return_pct) || 0);
      }
      const ranked = Object.entries(buckets)
        .map(([name, arr]) => ({
          name,
          avg: arr.reduce((a, b) => a + b, 0) / arr.length,
          n: arr.length,
        }))
        .sort((a, b) => b.avg - a.avg)
        .slice(0, 8);

      const best = ranked[0];
      this._setPanelHint(
        'dashBacktestHint',
        best
          ? `近 ${rows.length} 次回測 · 最佳 ${this._shortStrategyName(best.name)} ${best.avg >= 0 ? '+' : ''}${best.avg.toFixed(2)}%`
          : `近 ${rows.length} 次回測`,
      );

      Charts.clearPlaceholder(canvasId);
      Charts.drawHorizontalBarChart(
        canvasId,
        ranked.map(x => this._shortStrategyName(x.name)),
        ranked.map(x => x.avg),
        '平均收益率 (%)',
        { tooltips: ranked.map(x => `樣本 ${x.n} 次`) },
      );
    } catch (e) {
      this._setPanelHint('dashBacktestHint', '載入失敗');
      Charts.setPlaceholder(canvasId, '載入失敗，請稍後重試');
    }
  },

  /**
   * 多空信號 — 環形圖統計 + 強度 Top 標的（取代難讀的雷達圖）
   */
  async _loadSignalRadar() {
    const canvasId = 'dashSignalRadar';
    try {
      const d = await Api.getCurrentSignals();
      if (!d) {
        this._setPanelHint('dashSignalHint', '載入失敗');
        Charts.setPlaceholder(canvasId, '信號數據載入失敗');
        return;
      }

      const signals = d.signals || d.data || [];
      if (!signals.length) {
        this._setPanelHint('dashSignalHint', '非交易時段');
        Charts.setPlaceholder(canvasId, '暫無實時信號（開盤後刷新）');
        return;
      }

      let buy = 0;
      let sell = 0;
      let hold = 0;
      const stockScores = [];

      for (const s of signals) {
        const items = this._signalItems(s);
        let b = 0;
        let sl = 0;
        let h = 0;
        items.forEach(st => {
          if (st.signal === 'buy') b++;
          else if (st.signal === 'sell') sl++;
          else h++;
        });
        buy += b;
        sell += sl;
        hold += h;
        const net = b - sl;
        const strength = Number(s.strength ?? s.strength_score) || 0;
        stockScores.push({
          code: s.code || s.name || '?',
          score: net !== 0 ? net * (strength || 1) : strength * 0.3,
          buy: b,
          sell: sl,
        });
      }

      const top = [...stockScores]
        .sort((a, b) => Math.abs(b.score) - Math.abs(a.score))
        .slice(0, 6);

      this._setPanelHint(
        'dashSignalHint',
        `${signals.length} 檔 · 買入 ${buy} · 賣出 ${sell} · 觀望 ${hold}`,
      );

      if (buy + sell + hold === 0) {
        Charts.setPlaceholder(canvasId, '策略尚未產生買賣信號');
        return;
      }

      Charts.clearPlaceholder(canvasId);
      if (top.length >= 2 && (buy + sell) > 0) {
        Charts.drawHorizontalBarChart(
          canvasId,
          top.map(t => t.code),
          top.map(t => t.score),
          '信號傾向（正=偏多）',
          {
            suffix: '',
            formatValue: v => (v >= 0 ? '+' : '') + Number(v).toFixed(1),
            tooltips: top.map(t => `買 ${t.buy} / 賣 ${t.sell}`),
          },
        );
      } else {
        Charts.drawDoughnutChart(
          canvasId,
          ['買入', '賣出', '觀望'],
          [buy, sell, hold],
          '策略信號分佈',
        );
      }
    } catch (e) {
      this._setPanelHint('dashSignalHint', '載入失敗');
      Charts.setPlaceholder(canvasId, '信號數據載入失敗');
    }
  },

  /**
   * 加密貨幣實時行情卡片
   */
  async loadCryptoPrices() {
    const wrap = document.getElementById('cryptoPrices');
    if (!wrap) return;
    wrap.innerHTML = '<div class="crypto-loading"><span class="ld"></span> 加載中…</div>';
    try {
      const d = await Api.get('/api/crypto/realtime');
      const list = d?.data || [];
      if (!list.length) {
        wrap.innerHTML = '<div class="crypto-empty">暫無加密貨幣行情數據</div>';
        return;
      }
      wrap.innerHTML = list.map(c => {
        const chg = Number(c.change_pct) || 0;
        const cls = chg > 0 ? 'up' : (chg < 0 ? 'down' : 'flat');
        const sign = chg > 0 ? '+' : '';
        const price = Number(c.price) || 0;
        const priceStr = price >= 1000
          ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
          : price >= 1
            ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
            : price.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
        const vol = c.quote_volume || c.volume || 0;
        const volStr = vol >= 1e9 ? (vol / 1e9).toFixed(1) + 'B'
          : vol >= 1e6 ? (vol / 1e6).toFixed(1) + 'M'
          : vol >= 1e3 ? (vol / 1e3).toFixed(0) + 'K'
          : vol.toFixed(0);
        const sym = c.symbol || '';
        const logo = (typeof Utils !== 'undefined' && Utils.cryptoIconHtml)
          ? Utils.cryptoIconHtml(sym, 32)
          : '';
        return `
          <div class="crypto-card crypto-${cls}" role="button" tabindex="0" onclick="App.loadTab('crypto')" title="查看完整加密行情">
            <div class="crypto-card-head">
              <span class="crypto-icon">${logo}</span>
              <span class="crypto-name">${c.name || c.symbol}</span>
              <span class="crypto-badge ${cls}">${sign}${chg.toFixed(2)}%</span>
            </div>
            <div class="crypto-price">$${priceStr}</div>
            <div class="crypto-meta">24h 量: ${volStr}</div>
          </div>`;
      }).join('');
    } catch (e) {
      wrap.innerHTML = '<div class="crypto-empty">加密貨幣行情載入失敗</div>';
    }
  },

  /**
   * 行業板塊強弱 — 漲幅前 3 + 跌幅前 3
   */
  async _loadSectorBars() {
    const canvasId = 'dashSectorChart';
    try {
      const d = await Api.getSectors('industry', 30);
      if (!d?.sectors?.length) {
        this._setPanelHint('dashSectorHint', '數據源不可用');
        Charts.setPlaceholder(canvasId, '板塊數據暫不可用，請稍後刷新');
        return;
      }

      const sorted = [...d.sectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
      const top3 = sorted.slice(0, 3);
      const bottom3 = sorted.slice(-3).reverse();
      const seen = new Set();
      const unique = [...top3, ...bottom3].filter(s => {
        if (!s.name || seen.has(s.name)) return false;
        seen.add(s.name);
        return true;
      });

      const up = sorted.filter(s => (s.change_pct || 0) > 0).length;
      const avg = sorted.reduce((a, s) => a + (s.change_pct || 0), 0) / sorted.length;
      this._setPanelHint(
        'dashSectorHint',
        `${sorted.length} 個行業 · 上漲 ${up} · 均 ${avg >= 0 ? '+' : ''}${avg.toFixed(2)}%`,
      );

      Charts.clearPlaceholder(canvasId);
      Charts.drawHorizontalBarChart(
        canvasId,
        unique.map(s => (s.name || '-').slice(0, 8)),
        unique.map(s => s.change_pct || 0),
        '漲跌幅 (%)',
        { tooltips: unique.map(s => ((s.change_pct || 0) >= 0 ? '領漲' : '領跌')) },
      );
    } catch (e) {
      this._setPanelHint('dashSectorHint', '載入失敗');
      Charts.setPlaceholder(canvasId, '板塊數據載入失敗');
    }
  },

  /**
   * 策略夏普排行 — 橫向條形（tooltip 附勝率）
   */
  async _loadStrategyLeaderboard() {
    const canvasId = 'dashLeaderboardChart';
    try {
      const d = await Api.getLeaderboard('sharpe', 10);
      let strategies = (d?.results || d?.strategies || []).slice(0, 10);
      if (!strategies.length) {
        strategies = await this._leaderboardFromBacktest(10);
      }
      if (!strategies.length) {
        this._setPanelHint('dashLeaderboardHint', '暫無數據');
        Charts.setPlaceholder(canvasId, d?.hint || '請先運行回測以生成排行');
        return;
      }

      const sorted = [...strategies].sort((a, b) => (b.sharpe_ratio || 0) - (a.sharpe_ratio || 0));
      const labels = sorted.map(s => this._shortStrategyName(this._strategyLabel(s)));
      const sharpes = sorted.map(s => Number(s.sharpe_ratio) || 0);
      const best = sorted[0];
      this._setPanelHint(
        'dashLeaderboardHint',
        best
          ? `前 ${sorted.length} · ${this._shortStrategyName(this._strategyLabel(best))} 夏普 ${(best.sharpe_ratio || 0).toFixed(2)}`
          : `前 ${sorted.length}`,
      );

      Charts.clearPlaceholder(canvasId);
      Charts.drawHorizontalBarChart(
        canvasId,
        labels,
        sharpes,
        '夏普比率',
        {
          suffix: '',
          formatValue: v => Number(v).toFixed(2),
          tooltips: sorted.map(s => `勝率 ${(s.win_rate_pct || 0).toFixed(1)}%`),
        },
      );
    } catch (e) {
      this._setPanelHint('dashLeaderboardHint', '載入失敗');
      Charts.setPlaceholder(canvasId, '排行榜載入失敗');
    }
  },

  // ============================================================
  // 監控列表（保留原有功能）
  // ============================================================

  async loadRules() {
    const d = await Api.getAlertRules();
    if (!d) return;

    const entries = Object.entries(d.rules || {});
    const wlEl = document.getElementById('wlCount');
    if (wlEl) wlEl.textContent = entries.length + ' 只';

    if (entries.length === 0) {
      document.getElementById('watchlistTable').innerHTML =
        '<tr><td colspan="8"><div class="empty-state"><span class="empty-icon"><i class="ti ti-target"></i></span><p><strong>還沒有監控規則</strong></p><p>添加規則後，系統會在價格觸及目標時提醒你</p><button class="btn" onclick="showAddRule()" style="margin-top:8px">+ 添加第一個規則</button></div></td></tr>';
      return;
    }

    const codes = entries.map(([c]) => c);
    let sparklines = {};
    try {
      const sp = await Api.get('/api/sparkline?codes=' + codes.join(',') + '&days=20');
      if (sp && sp.sparklines) sparklines = sp.sparklines;
    } catch (e) { /* ignore */ }

    const iconHtml = (code, name) =>
      (typeof Utils !== 'undefined' && Utils.stockIconHtml)
        ? Utils.stockIconHtml(code, name, 32)
        : '';

    document.getElementById('watchlistTable').innerHTML = entries.map(([c, r]) => {
      const sp = sparklines[c] || {};
      const pct = sp.change_pct || 0;
      const cls = pct >= 0 ? 'u' : 'd';
      return `<tr>
        <td class="wl-logo">${iconHtml(c, r.name)}</td>
        <td class="wl-code">${c}</td>
        <td>${r.name || '-'}</td>
        <td class="r">${r.price_above || '-'}</td>
        <td class="r">${r.price_below || '-'}</td>
        <td class="r"><span class="b ${cls}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</span></td>
        <td><canvas id="sp_${c}" width="80" height="28" style="vertical-align:middle"></canvas></td>
        <td>
          <button class="btn s" style="padding:3px 8px;font-size:10px" onclick="Dashboard.editRule('${c}')">編輯</button>
          <button class="btn danger" style="padding:3px 8px;font-size:10px" onclick="Dashboard.deleteRule('${c}')">刪除</button>
        </td>
      </tr>`;
    }).join('');

    if (typeof Utils !== 'undefined' && Utils.hydrateStockIcons) {
      Utils.hydrateStockIcons(document.getElementById('watchlistTable'));
    }

    entries.forEach(([c]) => {
      const sp = sparklines[c];
      if (sp && sp.prices && sp.prices.length > 2) {
        this._drawSparkline('sp_' + c, sp.prices, sp.change_pct >= 0);
      }
    });
  },

  _drawSparkline(canvasId, prices, isUp) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const min = Math.min(...prices), max = Math.max(...prices);
    const range = max - min || 1;
    const color = isUp ? '#22c55e' : '#ef4444';

    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    prices.forEach((p, i) => {
      const x = (i / (prices.length - 1)) * w;
      const y = h - ((p - min) / range) * (h - 4) - 2;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, color + '30');
    grad.addColorStop(1, color + '05');
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    const lastY = h - ((prices[prices.length - 1] - min) / range) * (h - 4) - 2;
    ctx.beginPath();
    ctx.arc(w - 1, lastY, 2, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  },

  showAddRule() {
    this._showRuleModal(null, {});
  },

  async editRule(code) {
    const d = await Api.getAlertRules();
    if (d) this._showRuleModal(code, d.rules[code] || {});
  },

  _showRuleModal(code, rule) {
    const isEdit = !!code;
    Utils.showModal(`
      <h3>${isEdit ? '編輯' : '添加'}預警規則</h3>
      <div class="fg"><label>股票代碼</label>
        <div style="display:flex;gap:8px;align-items:center">
          <input id="mrCode" value="${code || ''}" ${isEdit ? 'readonly' : ''} style="flex:1">
          ${isEdit ? '' : '<button type="button" class="btn s" onclick="Dashboard.fillRuleFromPrice()">依現價填充</button>'}
        </div>
      </div>
      <div class="fg"><label>名稱</label><input id="mrName" value="${rule.name || ''}"></div>
      <div class="fg"><label>突破價</label><input id="mrAbove" type="number" step="0.01" value="${rule.price_above || ''}"></div>
      <div class="fg"><label>跌破價</label><input id="mrBelow" type="number" step="0.01" value="${rule.price_below || ''}"></div>
      <div class="fg"><label>漲跌幅閾值 (%)</label><input id="mrPct" type="number" step="0.1" value="${rule.change_pct || ''}"></div>
      <p class="state-loading-sub" style="margin:0 0 8px">「依現價填充」預設：突破 +3%、跌破 -3%、日內波動 5%</p>
      <div class="actions">
        <button class="btn s" onclick="Utils.closeModal()">取消</button>
        <button class="btn" onclick="Dashboard.saveRule()">保存</button>
      </div>
    `);
    if (!isEdit && typeof StockPicker !== 'undefined') {
      StockPicker.attach('mrCode', { mode: 'single', title: '選擇預警股票' });
    }
  },

  async saveRule() {
    const code = document.getElementById('mrCode').value.trim();
    if (!code) return Utils.toast('請輸入股票代碼');
    if (code.length !== 6 || !/^\d{6}$/.test(code)) return Utils.toast('股票代碼必須是 6 位數字');

    const rule = {
      name: document.getElementById('mrName').value,
      price_above: parseFloat(document.getElementById('mrAbove').value) || null,
      price_below: parseFloat(document.getElementById('mrBelow').value) || null,
      change_pct: parseFloat(document.getElementById('mrPct').value) || null,
    };

    const rules = {};
    rules[code] = rule;
    const d = await Api.updateAlertRules(rules);
    if (d) {
      Utils.toast('保存成功', 3000, 'success');
      Utils.closeModal();
      this.loadRules();
    }
  },

  async fillRuleFromPrice() {
    const code = document.getElementById('mrCode')?.value?.trim();
    if (!code || code.length !== 6 || !/^\d{6}$/.test(code)) {
      return Utils.toast('請先輸入 6 位股票代碼');
    }
    const d = await Api.suggestAlertRule(code, { above_pct: 3, below_pct: 3, change_pct: 5 });
    if (!d?.rule) {
      return Utils.toast('無法取得現價，請稍後重試', 3000, 'error');
    }
    document.getElementById('mrName').value = d.rule.name || '';
    document.getElementById('mrAbove').value = d.rule.price_above ?? '';
    document.getElementById('mrBelow').value = d.rule.price_below ?? '';
    document.getElementById('mrPct').value = d.rule.change_pct ?? '';
    Utils.toast(`已依現價 ${d.price} 填充`, 2500, 'success');
  },

  showAutoAddRules() {
    Utils.showModal(`
      <h3>🤖 智能批量添加預警規則</h3>
      <p style="color:var(--text-dim);font-size:13px;margin:0 0 12px">
        依最新價自動計算突破價、跌破價與日內漲跌幅閾值。
      </p>
      <div class="fg"><label>目標股票</label>
        <select id="arSource">
          <option value="missing">監控列表中尚未有規則的</option>
          <option value="watchlist">全部監控列表</option>
          <option value="custom">手動輸入代碼</option>
        </select>
      </div>
      <div class="fg h" id="arCodesWrap"><label>代碼（逗號分隔）</label>
        <input id="arCodes" placeholder="000001,600519">
      </div>
      <div class="fr" style="gap:10px">
        <div class="fg" style="flex:1"><label>突破 +%</label><input id="arAbovePct" type="number" step="0.5" value="3"></div>
        <div class="fg" style="flex:1"><label>跌破 -%</label><input id="arBelowPct" type="number" step="0.5" value="3"></div>
        <div class="fg" style="flex:1"><label>日內波動 %</label><input id="arChangePct" type="number" step="0.5" value="5"></div>
      </div>
      <div class="fg"><label><input type="checkbox" id="arSkipExisting" checked> 跳過已有規則</label></div>
      <div class="actions">
        <button class="btn s" onclick="Utils.closeModal()">取消</button>
        <button class="btn" id="arSubmitBtn" onclick="Dashboard.runAutoAddRules()">開始添加</button>
      </div>
    `);
    const sel = document.getElementById('arSource');
    const wrap = document.getElementById('arCodesWrap');
    const toggle = () => wrap.classList.toggle('h', sel.value !== 'custom');
    sel.addEventListener('change', toggle);
    toggle();
    if (typeof StockPicker !== 'undefined') {
      StockPicker.attach('arCodes', { mode: 'multi', title: '選擇批量預警股票' });
    }
  },

  async runAutoAddRules() {
    const btn = document.getElementById('arSubmitBtn');
    const source = document.getElementById('arSource')?.value || 'missing';
    const body = {
      source: source === 'custom' ? 'watchlist' : source,
      above_pct: parseFloat(document.getElementById('arAbovePct')?.value) || 3,
      below_pct: parseFloat(document.getElementById('arBelowPct')?.value) || 3,
      change_pct: parseFloat(document.getElementById('arChangePct')?.value) || 5,
      skip_existing: !!document.getElementById('arSkipExisting')?.checked,
    };
    if (source === 'custom') {
      const raw = document.getElementById('arCodes')?.value?.trim();
      body.codes = raw ? raw.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean) : [];
      if (!body.codes.length) return Utils.toast('請輸入至少一個股票代碼');
    }
    Utils.btnLoading(btn, true, '生成中...');
    try {
      const d = await Api.autoAddAlertRules(body);
      if (!d?.success) {
        Utils.toast(d?.message || '添加失敗', 3000, 'error');
        return;
      }
      Utils.closeModal();
      Utils.toast(d.message || '已添加', 3500, 'success');
      await this.loadRules();
    } finally {
      Utils.btnLoading(btn, false, '開始添加');
    }
  },

  async deleteRule(code) {
    if (!confirm(`確定刪除 ${code} 的預警規則？`)) return;
    const result = await Api.deleteAlertRule(code);
    if (result) {
      Utils.toast('已刪除', 3000, 'success');
      this.loadRules();
    }
  },
};

window.Dashboard = Dashboard;
