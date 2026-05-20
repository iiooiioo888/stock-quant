/**
 * dashboard.js — 儀表盤 Tab（含迷你走勢圖 + 多種圖表）
 */

const Dashboard = {
  _dataReady: false,
  _pollTimer: null,
  _pollCount: 0,
  _maxPolls: 30,

  async load() {
    this._pollCount = 0;
    this._dataReady = false;
    const health = await Api.getHealth();
    await Promise.allSettled([
      this.loadStats(health),
      this.loadRules(),
      this.loadDashboardCharts(),
    ]);
    this._checkDataReady(health);
  },

  /** Tab 顯示時補繪/重算圖表尺寸 */
  ensureCharts() {
    const ids = [
      'dashSparklineChart', 'dashBacktestChart', 'dashSignalRadar', 'dashSectorChart', 'dashLeaderboardChart',
      'dashSectorFlowChart', 'dashSectorScatterChart', 'dashMarketFlowChart', 'dashNorthFlowChart', 'dashConceptSectorChart',
      'dashMomentumRankChart', 'dashVolatilityRankChart', 'dashDrawdownRankChart', 'dashRiskScatterChart',
    ];
    const indexGrid = document.getElementById('indexChartsGrid');
    if (indexGrid && !indexGrid.querySelector('.index-chart-card')) {
      this._loadMajorIndicesCharts();
    }
    const missing = ids.some(id => {
      const el = document.getElementById(id);
      return el && !Chart.getChart(el);
    });
    if (missing) {
      this.loadDashboardCharts();
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
    const d = cachedHealth || await Api.getHealth();
    if (!d) return;
    if (d.data_ready) {
      this._dataReady = true;
      this._hideDataLoading();
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

  _hideDataLoading() {
    const el = document.getElementById('dataLoadingBanner');
    if (el) el.style.display = 'none';
    this.loadStats();
    this.loadRules();
    this.loadDashboardCharts();
  },

  async loadStats(cachedHealth) {
    const d = cachedHealth || await Api.getHealth();
    if (!d) return;

    document.getElementById('statsGrid').innerHTML = `
      <div class="dash-kpi dash-kpi--blue stat-card">
        <span class="dash-kpi-icon" aria-hidden="true">📊</span>
        <div class="dash-kpi-body">
          <span class="dash-kpi-label">監控股票</span>
          <span class="dash-kpi-value bl"><span class="dash-kpi-num">${d.total_stocks || 0}</span></span>
          <span class="dash-kpi-hint stat-hint">正在追蹤</span>
        </div>
      </div>
      <div class="dash-kpi dash-kpi--green stat-card">
        <span class="dash-kpi-icon" aria-hidden="true">📁</span>
        <div class="dash-kpi-body">
          <span class="dash-kpi-label">數據條數</span>
          <span class="dash-kpi-value"><span class="dash-kpi-num">${(d.total_klines || 0).toLocaleString()}</span></span>
          <span class="dash-kpi-hint stat-hint">歷史 K 線</span>
        </div>
      </div>
      <div class="dash-kpi dash-kpi--red stat-card">
        <span class="dash-kpi-icon" aria-hidden="true">🔔</span>
        <div class="dash-kpi-body">
          <span class="dash-kpi-label">累計預警</span>
          <span class="dash-kpi-value rd"><span class="dash-kpi-num">${d.total_alerts || 0}</span></span>
          <span class="dash-kpi-hint stat-hint">已觸發</span>
        </div>
      </div>
      <div class="dash-kpi dash-kpi--purple stat-card">
        <span class="dash-kpi-icon" aria-hidden="true">💾</span>
        <div class="dash-kpi-body">
          <span class="dash-kpi-label">數據庫</span>
          <span class="dash-kpi-value"><span class="dash-kpi-num">${d.db_size_mb || 0}</span><span class="dash-kpi-unit">MB</span></span>
          <span class="dash-kpi-hint stat-hint">存儲佔用</span>
        </div>
      </div>`;

    document.getElementById('sysStatus').textContent = '運行 ' + (d.uptime || '');
  },

  async _waitChartLibs(maxMs = 8000) {
    const start = Date.now();
    while (Date.now() - start < maxMs) {
      if (typeof Chart !== 'undefined') return true;
      await new Promise(r => setTimeout(r, 80));
    }
    return false;
  },

  /**
   * 載入儀表盤所有新增圖表
   */
  async loadDashboardCharts() {
    const ready = await this._waitChartLibs();
    if (!ready) {
      setTimeout(() => this.loadDashboardCharts(), 400);
      return;
    }
    await Promise.allSettled([
      this._loadMajorIndicesCharts(),
      this._loadTradingViewWall(),
      this._loadMarketCharts(),
      this._loadSparklineChart(),
      this._loadBacktestHistory(),
      this._loadSignalRadar(),
      this._loadSectorBars(),
      this._loadStrategyLeaderboard(),
    ]);
    if (typeof Charts !== 'undefined') {
      Charts.resizeTab('tab-dashboard');
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
      setTimeout(() => this._loadTradingViewWall(), 400);
      return;
    }

    try {
      const codes = await this._resolveSparklineCodes(8);
      const d = await Api.get(`/api/sparkline?codes=${codes.join(',')}&days=90`);
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
          <article class="tv-chart-card">
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
          label: '股票',
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
      setTimeout(() => this._loadMajorIndicesCharts(), 400);
      return;
    }

    try {
      const d = await Api.getIndicesCharts(90);
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
    return row.strategy_name || row.strategy || row.name || '-';
  },

  _signalItems(stockRow) {
    const raw = stockRow.signals || stockRow.strategies || [];
    return Array.isArray(raw) ? raw : [];
  },

  async _leaderboardFromBacktest(limit = 10) {
    const d = await Api.getBacktestHistory('', '', 200);
    if (!d?.results?.length) return [];
    const buckets = {};
    for (const r of d.results) {
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
   * 市場總覽迷你圖 — 組合淨值走勢
   */
  async _loadSparklineChart() {
    const canvasId = 'dashSparklineChart';
    try {
      const codes = await this._resolveSparklineCodes(6);
      const d = await Api.get(`/api/sparkline?codes=${codes.join(',')}&days=60`);
      if (!d || !d.sparklines) {
        Charts.setPlaceholder(canvasId, '暫無行情數據，請在「下載入庫」同步 K 線');
        return;
      }

      const series = [];
      for (const [code, sp] of Object.entries(d.sparklines)) {
        const prices = sp.prices;
        if (!prices || prices.length < 3) continue;
        const base = Number(prices[0]);
        if (!base || base <= 0) continue;
        const normalized = prices.map(p => ((Number(p) / base) - 1) * 100);
        series.push({
          label: code,
          data: normalized,
          dates: sp.dates || normalized.map((_, i) => String(i)),
        });
      }
      if (series.length) {
        Charts.clearPlaceholder(canvasId);
        Charts.drawLineChart(canvasId, series);
        Charts._scheduleResize?.(document.getElementById(canvasId));
      } else {
        Charts.setPlaceholder(canvasId, '暫無行情數據，請在「下載入庫」同步 K 線');
      }
    } catch (e) {
      Charts.setPlaceholder(canvasId, '載入失敗，請稍後重試');
    }
  },

  /**
   * 最近回測表現 — 最近 5 次回測的收益率柱狀圖
   */
  async _loadBacktestHistory() {
    const canvasId = 'dashBacktestChart';
    try {
      const d = await Api.getBacktestHistory('', '', 5);
      if (!d || !d.results || !d.results.length) {
        Charts.setPlaceholder(canvasId, '尚無回測記錄，請先運行策略回測');
        return;
      }

      const results = d.results.reverse();
      const labels = results.map(r => (r.code || '').substring(0, 6) + '\n' + (r.strategy || ''));
      const data = results.map(r => r.total_return_pct || 0);

      Charts.clearPlaceholder(canvasId);
      Charts.drawBarChart(canvasId, data, labels, '收益率 (%)');
    } catch (e) {
      Charts.setPlaceholder(canvasId, '載入失敗，請稍後重試');
    }
  },

  /**
   * 信號強度分佈 — 雷達圖顯示 top 5 股票的多維信號強度
   */
  async _loadSignalRadar() {
    const canvasId = 'dashSignalRadar';
    try {
      const d = await Api.getCurrentSignals();
      if (!d) {
        Charts.setPlaceholder(canvasId, '信號數據載入失敗');
        return;
      }

      const signals = d.signals || d.data || [];
      if (!signals.length) {
        Charts.setPlaceholder(canvasId, '暫無實時信號（非交易時段或尚未計算）');
        return;
      }

      const top5 = [...signals]
        .sort((a, b) => Math.abs(Number(b.strength) || 0) - Math.abs(Number(a.strength) || 0))
        .slice(0, 5);
      const labels = ['綜合強度', '買入占比', '賣出占比', '策略覆蓋', '觀望占比'];

      const datasets = top5.map((s, i) => {
        const items = this._signalItems(s);
        const buyCount = items.filter(st => st.signal === 'buy').length;
        const sellCount = items.filter(st => st.signal === 'sell').length;
        const holdCount = items.filter(st => st.signal === 'hold').length;
        const total = items.length || 1;
        const strength = Math.abs(Number(s.strength ?? s.strength_score) || 0);
        const maxStrategies = 19;

        return {
          label: s.code || s.name || ('股票' + (i + 1)),
          data: [
            Math.min(100, strength),
            Math.min(100, (buyCount / total) * 100),
            Math.min(100, (sellCount / total) * 100),
            Math.min(100, (items.length / maxStrategies) * 100),
            Math.min(100, (holdCount / total) * 100),
          ],
        };
      });

      Charts.clearPlaceholder(canvasId);
      Charts.drawRadarChart(canvasId, labels, datasets);
      Charts._scheduleResize?.(document.getElementById(canvasId));
    } catch (e) {
      Charts.setPlaceholder(canvasId, '信號數據載入失敗');
    }
  },

  /**
   * 資金與板塊圖表（單次 API）
   */
  async _loadMarketCharts() {
    const meta = document.getElementById('marketChartsMeta');
    try {
      const d = await Api.getDashboardMarketCharts(20);
      if (!d) {
        if (meta) meta.textContent = '數據暫不可用';
        return;
      }

      const parts = [];
      if (d.sector_flow?.length) parts.push('板塊資金');
      if (d.market_flow?.length) parts.push('大盤');
      if (d.north_flow?.length) parts.push('北向');
      const srcs = d.sources ? Object.values(d.sources).filter(Boolean) : [];
      const srcHint = srcs.length ? ` · ${[...new Set(srcs)].join('/')}` : '';
      if (meta) {
        meta.textContent = parts.length
          ? `${parts.join(' · ')} · 近 ${d.days || 20} 日${srcHint}`
          : '外部數據源連線中，請稍後刷新';
      }

      this._renderSectorFlowChart(d.sector_flow);
      this._renderSectorScatterChart(d.sector_scatter);
      this._renderMarketFlowChart(d.market_flow);
      this._renderNorthFlowChart(d.north_flow);
      this._renderSectorTreemap(d.sector_heatmap, d.sector_scatter);
      this._renderConceptSectorChart(d.concept_sectors);
    } catch (e) {
      if (meta) meta.textContent = '資金與板塊數據載入失敗';
    }
  },

  _renderSectorFlowChart(sectors) {
    const id = 'dashSectorFlowChart';
    if (!sectors?.length) {
      Charts.setPlaceholder(id, '板塊資金流向暫不可用');
      return;
    }
    const topIn = [...sectors].sort((a, b) => (b.main_net || 0) - (a.main_net || 0)).slice(0, 5);
    const topOut = [...sectors].sort((a, b) => (a.main_net || 0) - (b.main_net || 0)).slice(0, 5);
    const merged = [...topIn, ...topOut.filter(s => !topIn.find(x => x.name === s.name))].slice(0, 10);
    Charts.clearPlaceholder(id);
    Charts.drawMoneyHorizontalBar(
      id,
      merged.map(s => s.name),
      merged.map(s => s.main_net || 0),
      '主力淨流入',
    );
  },

  _renderSectorScatterChart(sectors) {
    const id = 'dashSectorScatterChart';
    if (!sectors?.length) {
      Charts.setPlaceholder(id, '漲跌×資金數據不足');
      return;
    }
    const points = sectors
      .filter(s => s.name && (s.change_pct != null || s.main_net != null))
      .slice(0, 50)
      .map(s => ({ name: s.name, x: s.change_pct || 0, y: s.main_net || 0 }));
    Charts.clearPlaceholder(id);
    Charts.drawChangeFlowScatter(id, points);
  },

  _renderMarketFlowChart(flows) {
    const id = 'dashMarketFlowChart';
    if (!flows?.length) {
      Charts.setPlaceholder(id, '大盤資金流向暫不可用');
      return;
    }
    Charts.clearPlaceholder(id);
    Charts.drawFlowStackedBar(id, flows);
  },

  _renderNorthFlowChart(flows) {
    const id = 'dashNorthFlowChart';
    if (!flows?.length) {
      Charts.setPlaceholder(id, '北向資金暫不可用');
      return;
    }
    const sh = flows.filter(f => String(f.code || '').includes('沪'));
    const sz = flows.filter(f => String(f.code || '').includes('深'));
    const dates = [...new Set(flows.map(f => f.date))].sort();
    const shMap = Object.fromEntries(sh.map(f => [f.date, (f.main_net || 0) / 1e8]));
    const szMap = Object.fromEntries(sz.map(f => [f.date, (f.main_net || 0) / 1e8]));
    Charts.clearPlaceholder(id);
    Charts.drawLineChart(id, [
      { label: '滬股通', data: dates.map(d => shMap[d] ?? null), dates },
      { label: '深股通', data: dates.map(d => szMap[d] ?? null), dates },
    ]);
  },

  _ensureTreemapCanvas() {
    const wrap = document.getElementById('dashSectorTreemapWrap');
    if (!wrap) return null;
    let canvas = document.getElementById('dashSectorTreemap');
    if (!canvas) {
      wrap.innerHTML = '';
      canvas = document.createElement('canvas');
      canvas.id = 'dashSectorTreemap';
      wrap.appendChild(canvas);
    }
    return canvas;
  },

  _mergeSectorHeatmap(primary, fallback) {
    const map = new Map();
    for (const s of (primary || [])) {
      if (s?.name) map.set(s.name, { ...s });
    }
    for (const s of (fallback || [])) {
      if (!s?.name || map.has(s.name)) continue;
      map.set(s.name, { ...s });
    }
    return [...map.values()];
  },

  _renderSectorTreemap(sectors, fallbackSectors) {
    const canvasId = 'dashSectorTreemap';
    this._ensureTreemapCanvas();
    const merged = this._mergeSectorHeatmap(sectors, fallbackSectors);
    if (!merged.length) {
      Charts.setPlaceholder(canvasId, '板塊熱力圖暫不可用，請檢查網路後刷新');
      return;
    }
    Charts.drawSectorTreemap(canvasId, merged.slice(0, 40), 280);
  },

  _renderConceptSectorChart(sectors) {
    const id = 'dashConceptSectorChart';
    if (!sectors?.length) {
      Charts.setPlaceholder(id, '概念板塊暫不可用');
      return;
    }
    const sorted = [...sectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
    const top = sorted.slice(0, 5);
    const bottom = sorted.slice(-5).reverse();
    const unique = [...top, ...bottom].filter((s, i, arr) => arr.findIndex(x => x.name === s.name) === i).slice(0, 10);
    Charts.clearPlaceholder(id);
    Charts.drawHorizontalBarChart(id, unique.map(s => s.name), unique.map(s => s.change_pct || 0), '漲跌幅 (%)');
  },

  /**
   * 行業板塊漲跌 — 水平條形圖
   */
  async _loadSectorBars() {
    const canvasId = 'dashSectorChart';
    try {
      const d = await Api.getSectors('industry', 10);
      if (!d || !d.sectors || !d.sectors.length) {
        Charts.setPlaceholder(canvasId, '板塊數據暫不可用（外部數據源連線失敗）');
        return;
      }

      // 分開漲幅前5和跌幅前5，按漲跌幅排序
      const sorted = [...d.sectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
      const top5 = sorted.slice(0, 5);
      const bottom5 = sorted.slice(-5).reverse();

      // 合併顯示
      const all = [...top5, ...bottom5];
      // 去重
      const seen = new Set();
      const unique = all.filter(s => {
        if (seen.has(s.name)) return false;
        seen.add(s.name);
        return true;
      }).slice(0, 10);

      const labels = unique.map(s => s.name || '-');
      const data = unique.map(s => s.change_pct || 0);

      Charts.clearPlaceholder(canvasId);
      Charts.drawHorizontalBarChart(canvasId, labels, data, '漲跌幅 (%)');
    } catch (e) {
      Charts.setPlaceholder(canvasId, '板塊數據載入失敗');
    }
  },

  /**
   * 策略勝率排行 — top 10 策略的勝率和夏普
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
        Charts.setPlaceholder(canvasId, d?.hint || '排行榜暫無數據，請先運行回測或更新排行榜');
        return;
      }
      const labels = strategies.map(s => this._strategyLabel(s));
      const winRates = strategies.map(s => s.win_rate_pct || 0);
      const sharpes = strategies.map(s => s.sharpe_ratio || 0);

      // 用雙軸柱狀圖：勝率 + 夏普
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      Charts.clearPlaceholder(canvasId);
      const old = Chart.getChart(canvas);
      if (old) old.destroy();

      const colors = Charts.getThemeColors();
      new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: '勝率 (%)',
              data: winRates,
              backgroundColor: 'rgba(56,189,248,0.6)',
              borderColor: '#38bdf8',
              borderWidth: 1,
              yAxisID: 'y',
            },
            {
              label: '夏普比率',
              data: sharpes,
              backgroundColor: 'rgba(167,139,250,0.6)',
              borderColor: '#a78bfa',
              borderWidth: 1,
              yAxisID: 'y1',
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: colors.text, font: { size: 10 } } },
            tooltip: {
              backgroundColor: colors.tooltipBg,
              borderColor: colors.tooltipBorder,
              borderWidth: 1,
              titleColor: colors.tooltipText,
              bodyColor: colors.tooltipBody,
            },
          },
          scales: {
            x: { ticks: { color: colors.text, font: { size: 9 }, maxRotation: 45 }, grid: { color: colors.grid } },
            y: {
              type: 'linear',
              position: 'left',
              ticks: { color: colors.text, font: { size: 9 }, callback: v => v + '%' },
              grid: { color: colors.grid },
              title: { display: true, text: '勝率', color: colors.text },
            },
            y1: {
              type: 'linear',
              position: 'right',
              ticks: { color: colors.text, font: { size: 9 } },
              grid: { drawOnChartArea: false },
              title: { display: true, text: '夏普', color: colors.text },
            },
          },
        },
      });
      Charts._scheduleResize(canvas);
    } catch (e) {
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
        '<tr><td colspan="7"><div class="empty-state"><span class="empty-icon">🎯</span><p><strong>還沒有監控規則</strong></p><p>添加規則後，系統會在價格觸及目標時提醒你</p><button class="btn" onclick="showAddRule()" style="margin-top:8px">+ 添加第一個規則</button></div></td></tr>';
      return;
    }

    const codes = entries.map(([c]) => c);
    let sparklines = {};
    try {
      const sp = await Api.get('/api/sparkline?codes=' + codes.join(',') + '&days=20');
      if (sp && sp.sparklines) sparklines = sp.sparklines;
    } catch (e) { /* ignore */ }

    document.getElementById('watchlistTable').innerHTML = entries.map(([c, r]) => {
      const sp = sparklines[c] || {};
      const pct = sp.change_pct || 0;
      const cls = pct >= 0 ? 'u' : 'd';
      return `<tr>
        <td style="font-weight:600">${c}</td>
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
