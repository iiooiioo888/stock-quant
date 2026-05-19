/**
 * analysis.js — 深度分析 Tab
 *
 * 修復：適配 index.html 的實際 DOM 結構
 *   - 輸入: #anCode, #anStrategy
 *   - 結果容器: #anResult, #anStats
 *   - 圖表: #anDistChart, #anMcChart, #anRollingChart
 *   - 方法名: tradeAnalysis(), monteCarlo(), rollingMetrics()
 */

const Analysis = {
  _cache: null,    // 緩存最近一次回測結果
  _cacheKey: '',   // 緩存 key (code+strategy)

  init() {},

  async _getBacktestResult(code, strategy) {
    const key = `${code}|${strategy}`;
    if (this._cache && this._cacheKey === key) {
      return { success: true, result: this._cache };
    }
    const d = await Api.runBacktest({ code, strategy });
    if (d && d.success) {
      this._cache = d.result;
      this._cacheKey = key;
    }
    return d;
  },

  async tradeAnalysis() {
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼');

    document.getElementById('anResult').classList.add('h');
    Utils.toast('正在回測分析...');

    const d = await this._getBacktestResult(code, strategy);
    if (!d || !d.success) return Utils.toast('回測失敗', 3000, 'error');

    const r = d.result || this._cache;
    const trades = r.trade_details || [];
    if (!trades.length) return Utils.toast('無交易記錄');

    const wins = trades.filter(t => t.return_pct > 0);
    const losses = trades.filter(t => t.return_pct <= 0);
    const returns = trades.map(t => t.return_pct);
    const holdDays = trades.map(t => t.hold_days);

    let maxWinStreak = 0, maxLoseStreak = 0, curWin = 0, curLose = 0;
    trades.forEach(t => {
      if (t.return_pct > 0) { curWin++; curLose = 0; maxWinStreak = Math.max(maxWinStreak, curWin); }
      else { curLose++; curWin = 0; maxLoseStreak = Math.max(maxLoseStreak, curLose); }
    });

    const avgWin = wins.length ? wins.reduce((s, t) => s + t.return_pct, 0) / wins.length : 0;
    const avgLoss = losses.length ? losses.reduce((s, t) => s + t.return_pct, 0) / losses.length : 0;
    const avgHold = holdDays.reduce((s, d) => s + d, 0) / holdDays.length;
    const expectancy = (wins.length / trades.length) * avgWin + (losses.length / trades.length) * avgLoss;

    document.getElementById('anStats').innerHTML = `
      <div class="c"><h3>總交易</h3><div class="v">${trades.length}</div></div>
      <div class="c"><h3>盈利 / 虧損</h3><div class="v gn">${wins.length} / <span class="rd">${losses.length}</span></div></div>
      <div class="c"><h3>勝率</h3><div class="v">${((wins.length / trades.length) * 100).toFixed(1)}%</div></div>
      <div class="c"><h3>期望值</h3><div class="v ${expectancy >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(expectancy)}</div></div>
      <div class="c"><h3>平均盈利</h3><div class="v gn">${Utils.formatPct(avgWin)}</div></div>
      <div class="c"><h3>平均虧損</h3><div class="v rd">${Utils.formatPct(avgLoss)}</div></div>
      <div class="c"><h3>盈虧比</h3><div class="v">${avgLoss !== 0 ? Math.abs(avgWin / avgLoss).toFixed(2) : '∞'}</div></div>
      <div class="c"><h3>平均持有</h3><div class="v">${avgHold.toFixed(1)}天</div></div>
      <div class="c"><h3>最長連勝</h3><div class="v gn">${maxWinStreak}</div></div>
      <div class="c"><h3>最長連虧</h3><div class="v rd">${maxLoseStreak}</div></div>
      <div class="c"><h3>最大單筆盈利</h3><div class="v gn">${Utils.formatPct(Math.max(...returns))}</div></div>
      <div class="c"><h3>最大單筆虧損</h3><div class="v rd">${Utils.formatPct(Math.min(...returns))}</div></div>`;

    // 收益分佈圖
    const buckets = {};
    const bucketSize = 5;
    returns.forEach(r => {
      const b = Math.floor(r / bucketSize) * bucketSize;
      buckets[b] = (buckets[b] || 0) + 1;
    });
    const bLabels = Object.keys(buckets).sort((a, b) => a - b).map(k => k + '%');
    const bData = Object.keys(buckets).sort((a, b) => a - b).map(k => buckets[k]);
    Charts.drawBarChart('anDistChart', bData, bLabels, '交易次數');

    // 顯示結果，只顯示收益分佈
    document.getElementById('anResult').classList.remove('h');
    document.querySelectorAll('#anResult .sec').forEach((el, i) => {
      el.classList.toggle('h', i !== 0); // 只顯示第一個 sec（anStats 上面的）
    });
    // 收益分佈 canvas 的父 sec
    const distCanvas = document.getElementById('anDistChart');
    if (distCanvas) distCanvas.closest('.sec')?.classList.remove('h');

    Utils.toast('交易分析完成');
  },

  async monteCarlo() {
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼');

    document.getElementById('anResult').classList.add('h');
    Utils.toast('蒙特卡羅模擬中...');

    const d = await this._getBacktestResult(code, strategy);
    if (!d || !d.success || !d.result?.trade_details?.length) {
      return Utils.toast('回測失敗或無交易', 3000, 'error');
    }

    const trades = d.result.trade_details;
    const returns = trades.map(t => t.return_pct / 100);
    const nTrades = trades.length;
    const nSims = 1000;

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
      if (sim < 20) allPaths.push(path);
    }

    finalValues.sort((a, b) => a - b);
    const p5 = finalValues[Math.floor(nSims * 0.05)];
    const p50 = finalValues[Math.floor(nSims * 0.5)];
    const p95 = finalValues[Math.floor(nSims * 0.95)];
    const mean = finalValues.reduce((s, v) => s + v, 0) / nSims;
    const lossProb = (finalValues.filter(v => v < 1).length / nSims) * 100;

    document.getElementById('anStats').innerHTML = `
      <div class="c"><h3>模擬次數</h3><div class="v">${nSims}</div></div>
      <div class="c"><h3>5% 分位</h3><div class="v rd">${Utils.formatPct((p5 - 1) * 100)}</div></div>
      <div class="c"><h3>中位數</h3><div class="v">${Utils.formatPct((p50 - 1) * 100)}</div></div>
      <div class="c"><h3>95% 分位</h3><div class="v gn">${Utils.formatPct((p95 - 1) * 100)}</div></div>
      <div class="c"><h3>均值</h3><div class="v">${Utils.formatPct((mean - 1) * 100)}</div></div>
      <div class="c"><h3>虧損概率</h3><div class="v rd">${lossProb.toFixed(1)}%</div></div>`;

    // 模擬路徑圖
    const pathLabels = Array.from({ length: nTrades + 1 }, (_, i) => String(i));
    const pathSeries = allPaths.map((path, i) => ({
      label: `路徑 ${i + 1}`, data: path, dates: pathLabels,
    }));
    Charts.drawLineChart('anMcChart', pathSeries);

    // 顯示結果，只顯示蒙特卡羅
    document.getElementById('anResult').classList.remove('h');
    document.querySelectorAll('#anResult .sec').forEach(el => el.classList.add('h'));
    document.getElementById('anMcChart')?.closest('.sec')?.classList.remove('h');

    Utils.toast('蒙特卡羅模擬完成');
  },

  async rollingMetrics() {
    const code = document.getElementById('anCode')?.value?.trim();
    const strategy = document.getElementById('anStrategy')?.value || 'dual_ma';
    if (!code) return Utils.toast('請輸入股票代碼');

    document.getElementById('anResult').classList.add('h');
    Utils.toast('計算滾動指標中...');

    const d = await this._getBacktestResult(code, strategy);
    if (!d || !d.success || !d.result?.nav || d.result.nav.length < 60) {
      return Utils.toast('數據不足（需要至少 60 個數據點）');
    }

    const nav = d.result.nav;
    const dates = d.result.dates || nav.map((_, i) => String(i));
    const windowSize = 60;

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

      let peak = windowNav[0], maxDD = 0;
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

    document.getElementById('anStats').innerHTML = `
      <div class="c"><h3>最新滾動夏普</h3><div class="v">${rollingSharpe[rollingSharpe.length - 1]?.toFixed(2) || '-'}</div></div>
      <div class="c"><h3>最新滾動波動率</h3><div class="v">${rollingVol[rollingVol.length - 1]?.toFixed(2) || '-'}%</div></div>
      <div class="c"><h3>最新滾動回撤</h3><div class="v rd">${rollingDD[rollingDD.length - 1]?.toFixed(2) || '-'}%</div></div>
      <div class="c"><h3>窗口</h3><div class="v">${windowSize}天</div></div>`;

    // 滾動夏普圖
    Charts.drawLineChart('anRollingChart', [
      { label: '滾動夏普', data: rollingSharpe, dates: rollingLabels },
      { label: '波動率 (%)', data: rollingVol, dates: rollingLabels },
      { label: '回撤 (%)', data: rollingDD, dates: rollingLabels },
    ]);

    // 顯示結果，只顯示滾動指標
    document.getElementById('anResult').classList.remove('h');
    document.querySelectorAll('#anResult .sec').forEach(el => el.classList.add('h'));
    document.getElementById('anRollingChart')?.closest('.sec')?.classList.remove('h');

    Utils.toast('滾動指標計算完成');
  },
};

window.Analysis = Analysis;
