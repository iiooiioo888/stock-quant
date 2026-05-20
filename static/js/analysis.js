/**
 * analysis.js — 深度分析 Tab（調用後端同步分析 API）
 */

const Analysis = {
  init() {},

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
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'warning');

    document.getElementById('anResult')?.classList.add('h');
    Utils.toast('正在回測並分析交易...', 2000, 'info');

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
  },

  async monteCarlo() {
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'warning');

    document.getElementById('anResult')?.classList.add('h');
    Utils.toast('蒙特卡羅模擬中...', 2000, 'info');

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
  },

  async rollingMetrics() {
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'warning');

    document.getElementById('anResult')?.classList.add('h');
    Utils.toast('計算滾動指標中...', 2000, 'info');

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
  },
};

window.Analysis = Analysis;
