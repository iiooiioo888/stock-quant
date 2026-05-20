/**
 * chart-pro.js — 全站專業圖表封裝（統一主題、Tab 初始化、增強視覺）
 */
const ProCharts = {
  _tabHooks: {},

  registerTab(tab, fn) {
    this._tabHooks[tab] = fn;
  },

  initTab(tab) {
    const fn = this._tabHooks[tab];
    if (fn) fn();
    requestAnimationFrame(() => {
      if (typeof Charts !== 'undefined') Charts.resizeTab('tab-' + tab);
    });
  },

  _destroy(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();
  },

  _theme() {
    return typeof Charts !== 'undefined' ? Charts.getThemeColors() : {
      text: '#94a3b8', grid: '#1e293b', tooltipBg: '#1e293b', tooltipBorder: '#334155',
      tooltipText: '#f8fafc', tooltipBody: '#e2e8f0',
    };
  },

  _baseOptions(extra = {}) {
    const colors = this._theme();
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      plugins: {
        legend: {
          labels: { color: colors.text, font: { size: 11 }, usePointStyle: true, padding: 14 },
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: colors.tooltipBg,
          borderColor: colors.tooltipBorder,
          borderWidth: 1,
          titleColor: colors.tooltipText,
          bodyColor: colors.tooltipBody,
          padding: 10,
          cornerRadius: 6,
        },
        ...(extra.plugins || {}),
      },
      scales: extra.scales || {
        x: { ticks: { color: colors.text, font: { size: 9 }, maxTicksLimit: 12 }, grid: { color: colors.grid } },
        y: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
      },
      ...extra,
    };
  },

  /** 多股對比 — 面積歸一化收益 */
  renderCompare(series) {
    if (!series?.length || typeof Charts === 'undefined') return;
    Charts.drawAreaChart('cmpChart', series.map((s, i) => ({
      ...s,
      color: CHART_COLORS[i % CHART_COLORS.length],
      fill: i === 0 ? 'origin' : false,
    })));
  },

  /** 回測歷史 — 收益分佈 / 夏普趨勢 / 回撤排行 */
  renderHistoryAnalytics(rows) {
    if (!rows?.length || typeof Chart === 'undefined') return;

    const returns = rows.map(r => r.total_return_pct).filter(v => v != null);
    if (returns.length && document.getElementById('histReturnChart')) {
      const edges = [-30, -20, -10, -5, 0, 5, 10, 20, 30, 50, 999];
      const counts = new Array(edges.length - 1).fill(0);
      returns.forEach(v => {
        for (let i = 0; i < edges.length - 1; i++) {
          if (v >= edges[i] && v < edges[i + 1]) {
            counts[i]++;
            return;
          }
        }
      });
      const labels = edges.slice(0, -1).map((lo, i) => {
        const hi = edges[i + 1];
        return hi >= 999 ? `≥${lo}%` : `${lo}~${hi}%`;
      });
      this._drawGradientBar('histReturnChart', counts, labels, '回測次數', '#38bdf8');
    }

    const sorted = [...rows].filter(r => r.created_at).sort((a, b) =>
      String(a.created_at).localeCompare(String(b.created_at)));
    if (sorted.length && document.getElementById('histSharpeChart')) {
      const labels = sorted.map(r => Utils.shortDate(String(r.created_at).slice(0, 10)));
      this._destroy('histSharpeChart');
      const colors = this._theme();
      new Chart(document.getElementById('histSharpeChart').getContext('2d'), {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: '夏普比率',
            data: sorted.map(r => r.sharpe_ratio || 0),
            borderColor: '#38bdf8',
            backgroundColor: 'rgba(56,189,248,0.15)',
            fill: true,
            tension: 0.35,
            pointRadius: 3,
            pointHoverRadius: 5,
          }],
        },
        options: this._baseOptions(),
      });
    }

    const byDd = [...rows].filter(r => r.max_drawdown_pct != null)
      .sort((a, b) => (b.max_drawdown_pct || 0) - (a.max_drawdown_pct || 0))
      .slice(0, 12);
    if (byDd.length && document.getElementById('histDrawdownChart')) {
      Charts.drawHorizontalBarChart(
        'histDrawdownChart',
        byDd.map(r => `${r.code}·${r.strategy}`),
        byDd.map(r => -(r.max_drawdown_pct || 0)),
        '最大回撤 (%)',
      );
    }
  },

  /** Walk-Forward — 柱狀 + 累積 OOS 曲線 */
  renderWalkForward(wins) {
    if (!wins?.length) return;
    const labels = wins.map(w => 'W' + w.window);
    const rets = wins.map(w => w.test_return_pct || 0);
    Charts.drawBarChart('wfChart', rets, labels, '樣本外收益率 (%)');

    let cum = 0;
    const cumData = rets.map(r => { cum += r; return cum; });
    const canvas = document.getElementById('wfCumChart');
    if (!canvas) return;
    this._destroy('wfCumChart');
    const colors = this._theme();
    new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: '累積 OOS 收益 (%)',
          data: cumData,
          borderColor: '#a78bfa',
          backgroundColor: 'rgba(167,139,250,0.2)',
          fill: true,
          tension: 0.3,
          pointRadius: 4,
        }],
      },
      options: this._baseOptions(),
    });
  },

  /** 實時行情 — 漲跌幅橫條 */
  renderMarketRealtime(rows) {
    if (!rows?.length) return;
    const sorted = [...rows].sort((a, b) =>
      (parseFloat(b.change_pct) || 0) - (parseFloat(a.change_pct) || 0));
    const top = sorted.slice(0, 12);
    const labels = top.map(r => (r.name || r.symbol || '').slice(0, 8));
    const data = top.map(r => parseFloat(r.change_pct) || 0);
    if (document.getElementById('rtMoversChart')) {
      Charts.drawHorizontalBarChart('rtMoversChart', labels, data, '漲跌幅 (%)');
    }
  },

  /** 個股資金 — 主力淨流 + 分單堆疊 */
  renderStockCapitalFlow(flows) {
    if (!flows?.length) return;
    const rev = [...flows].reverse();
    const labels = rev.map(f => Utils.shortDate(f.date || ''));
    const main = rev.map(f => f.main_net || 0);

    if (document.getElementById('cfNetChart')) {
      Charts.drawBarChart('cfNetChart', main, labels, '主力淨流入');
    }
    if (document.getElementById('cfStackChart')) {
      this._destroy('cfStackChart');
      const colors = this._theme();
      new Chart(document.getElementById('cfStackChart').getContext('2d'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: '超大單', data: rev.map(f => f.super_large ?? f.super_net ?? f.super_large_net ?? 0), backgroundColor: 'rgba(56,189,248,0.7)', stack: 's' },
            { label: '大單', data: rev.map(f => f.large ?? f.big_net ?? f.large_net ?? 0), backgroundColor: 'rgba(34,197,94,0.6)', stack: 's' },
            { label: '中單', data: rev.map(f => f.medium ?? f.mid_net ?? f.medium_net ?? 0), backgroundColor: 'rgba(245,158,11,0.5)', stack: 's' },
            { label: '小單', data: rev.map(f => f.small ?? f.small_net ?? 0), backgroundColor: 'rgba(148,163,184,0.5)', stack: 's' },
          ],
        },
        options: this._baseOptions({
          scales: {
            x: { stacked: true, ticks: { color: colors.text, font: { size: 9 }, maxTicksLimit: 10 }, grid: { color: colors.grid } },
            y: { stacked: true, ticks: { color: colors.text, font: { size: 9 }, callback: v => Utils.formatLargeNum(v) }, grid: { color: colors.grid } },
          },
        }),
      });
    }
  },

  /** 北向資金 — 滬深堆疊 + 合計折線 */
  renderNorthFlow(flows) {
    if (!flows?.length) return;
    const rev = [...flows].reverse();
    const labels = rev.map(f => Utils.shortDate(f.date || ''));

    if (document.getElementById('northStackChart')) {
      this._destroy('northStackChart');
      const colors = this._theme();
      new Chart(document.getElementById('northStackChart').getContext('2d'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: '滬股通', data: rev.map(f => f.sh_net || 0), backgroundColor: 'rgba(56,189,248,0.65)', stack: 'n' },
            { label: '深股通', data: rev.map(f => f.sz_net || 0), backgroundColor: 'rgba(168,85,247,0.65)', stack: 'n' },
          ],
        },
        options: this._baseOptions({
          scales: {
            x: { stacked: true, ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
            y: { stacked: true, ticks: { color: colors.text, font: { size: 9 }, callback: v => Utils.formatLargeNum(v) }, grid: { color: colors.grid } },
          },
        }),
      });
    }
    if (document.getElementById('northTotalChart')) {
      Charts.drawAreaChart('northTotalChart', [{
        label: '北向合計',
        data: rev.map(f => f.total_net || 0),
        dates: rev.map(f => f.date),
        color: '#22c55e',
        fill: 'origin',
      }]);
    }
    const trendId = 'dataNorthTrendChart';
    if (document.getElementById(trendId)) {
      this._destroy(trendId);
      const colors = this._theme();
      new Chart(document.getElementById(trendId).getContext('2d'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: '滬股通', data: rev.map(f => f.sh_net || 0), backgroundColor: 'rgba(56,189,248,0.65)', stack: 'n' },
            { label: '深股通', data: rev.map(f => f.sz_net || 0), backgroundColor: 'rgba(168,85,247,0.65)', stack: 'n' },
          ],
        },
        options: this._baseOptions({
          scales: {
            x: { stacked: true, ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
            y: { stacked: true, ticks: { color: colors.text, font: { size: 9 }, callback: v => Utils.formatLargeNum(v) }, grid: { color: colors.grid } },
          },
        }),
      });
      if (typeof Charts !== 'undefined') Charts._scheduleResize(document.getElementById(trendId));
    }
  },

  /** 數據中心 — 資金子 Tab（僅在可見時繪圖） */
  async loadCapitalTabCharts() {
    if (typeof Api === 'undefined' || typeof Charts === 'undefined') return;
    if (!document.getElementById('dataCapitalSectorChart')) return;
    const d = await Api.getDashboardMarketCharts(15);
    if (!d) return;
    const sector = d.sector_flow || [];
    if (sector.length) {
      Charts.drawMoneyHorizontalBar(
        'dataCapitalSectorChart',
        sector.map(s => s.name),
        sector.map(s => s.main_net),
      );
    }
    const matrix = d.sector_scatter || [];
    if (matrix.length && document.getElementById('dataSectorScatterChart')) {
      const points = matrix
        .filter(s => s.name && (s.change_pct != null || s.main_net != null))
        .map(s => ({ name: s.name, x: s.change_pct || 0, y: s.main_net || 0 }));
      if (points.length) Charts.drawChangeFlowScatter('dataSectorScatterChart', points);
    }
  },

  /** @deprecated 由 Data._onTabActivated + loadCapitalTabCharts / loadNorthFlow 驅動 */
  async loadDataMarketCharts() {
    if (typeof Api === 'undefined' || typeof Charts === 'undefined') return;
    const d = await Api.getDashboardMarketCharts(15);
    if (!d) return;

    const sector = d.sector_flow || [];
    if (sector.length && document.getElementById('dataCapitalSectorChart')) {
      Charts.drawMoneyHorizontalBar(
        'dataCapitalSectorChart',
        sector.map(s => s.name),
        sector.map(s => s.main_net),
      );
    }

    const north = d.north_flow || [];
    if (north.length && document.getElementById('dataNorthTrendChart')) {
      Charts.drawFlowStackedBar('dataNorthTrendChart', north);
    }

    const matrix = d.sector_scatter || [];
    if (matrix.length && document.getElementById('dataSectorScatterChart')) {
      const points = matrix
        .filter(s => s.name && (s.change_pct != null || s.main_net != null))
        .map(s => ({ name: s.name, x: s.change_pct || 0, y: s.main_net || 0 }));
      if (points.length) Charts.drawChangeFlowScatter('dataSectorScatterChart', points);
    }
  },

  /** 報告 — 多股夏普/收益對比 */
  renderReportPerf(items) {
    if (!items?.length || !document.getElementById('rptPerfChart')) return;
    const labels = items.map(i => i.code);
    this._destroy('rptPerfChart');
    const colors = this._theme();
    new Chart(document.getElementById('rptPerfChart').getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: '收益率 (%)',
            data: items.map(i => i.return_pct || 0),
            backgroundColor: items.map(i => (i.return_pct || 0) >= 0 ? 'rgba(34,197,94,0.65)' : 'rgba(239,68,68,0.65)'),
            yAxisID: 'y',
          },
          {
            label: '夏普',
            data: items.map(i => i.sharpe || 0),
            type: 'line',
            borderColor: '#38bdf8',
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 5,
            yAxisID: 'y1',
          },
        ],
      },
      options: this._baseOptions({
        scales: {
          x: { ticks: { color: colors.text }, grid: { color: colors.grid } },
          y: { position: 'left', title: { display: true, text: '收益率 (%)', color: colors.text }, ticks: { color: colors.text }, grid: { color: colors.grid } },
          y1: { position: 'right', title: { display: true, text: '夏普', color: colors.text }, ticks: { color: colors.text }, grid: { drawOnChartArea: false } },
        },
      }),
    });
  },

  /** 預警 — 按日統計 */
  renderAlertTrend(alerts) {
    if (!alerts?.length || !document.getElementById('alertTrendChart')) return;
    const dayMap = {};
    alerts.forEach(a => {
      const d = (a.triggered_at || '').substring(0, 10);
      if (d) dayMap[d] = (dayMap[d] || 0) + 1;
    });
    const dates = Object.keys(dayMap).sort().slice(-14);
    this._drawGradientBar('alertTrendChart', dates.map(d => dayMap[d]), dates.map(d => d.slice(5)), '預警次數', '#f59e0b');
  },

  /** 板塊輪動 — 排名變化橫條 */
  renderRotationChart(rotation) {
    if (!rotation?.length || !document.getElementById('rotationChart')) return;
    const top = [...rotation].sort((a, b) => Math.abs(b.rank_change) - Math.abs(a.rank_change)).slice(0, 12);
    Charts.drawHorizontalBarChart(
      'rotationChart',
      top.map(r => r.name || '-'),
      top.map(r => r.rank_change || 0),
      '排名變化（正=升溫）',
    );
  },

  /** 蒙特卡羅 — 半透明路徑帶 */
  renderMonteCarloFan(curves) {
    const canvas = document.getElementById('anMcChart');
    if (!canvas || !curves || typeof Chart === 'undefined') return;
    this._destroy('anMcChart');
    const colors = this._theme();
    const entries = Object.entries(curves).slice(0, 80);
    const maxLen = Math.max(...entries.map(([, data]) => data.length));
    const labels = Array.from({ length: maxLen }, (_, i) => i);

    new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: entries.map(([, data], i) => ({
          label: i === 0 ? '模擬路徑' : '',
          data,
          borderColor: `rgba(56,189,248,${0.15 + (i % 5) * 0.05})`,
          backgroundColor: 'transparent',
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.1,
        })),
      },
      options: this._baseOptions({
        plugins: {
          legend: { display: entries.length <= 5, labels: { color: colors.text } },
        },
      }),
    });
  },

  _drawGradientBar(canvasId, data, labels, datasetLabel, accent = '#38bdf8') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    this._destroy(canvasId);
    const colors = this._theme();
    const ctx = canvas.getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, canvas.offsetHeight || 200);
    grad.addColorStop(0, accent);
    grad.addColorStop(1, accent + '40');

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: datasetLabel,
          data,
          backgroundColor: grad,
          borderColor: accent,
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: this._baseOptions(),
    });
    if (typeof Charts !== 'undefined') Charts._scheduleResize(canvas);
  },
};

window.ProCharts = ProCharts;
