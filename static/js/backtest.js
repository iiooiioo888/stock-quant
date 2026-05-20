/**
 * backtest.js — 回測 Tab（支持進階回測 + 分析）
 */

const Backtest = {
  _lastResult: null,
  _running: false,
  _codesLoaded: false,

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
    this.loadStockOptions();
  },

  getCode() {
    return document.getElementById('btCode')?.value?.trim() || '';
  },

  setCode(code) {
    const c = String(code || '').trim();
    const inp = document.getElementById('btCode');
    const sel = document.getElementById('btCodeSelect');
    if (inp) inp.value = c;
    if (sel) {
      const hit = c && [...sel.options].some(o => o.value === c);
      sel.value = hit ? c : '';
    }
  },

  _bindCodeControls() {
    const sel = document.getElementById('btCodeSelect');
    const inp = document.getElementById('btCode');
    if (!sel || !inp || sel.dataset.bound) return;
    sel.dataset.bound = '1';
    sel.addEventListener('change', () => {
      if (sel.value) this.setCode(sel.value);
    });
    inp.addEventListener('input', () => {
      const v = inp.value.trim();
      if (v && [...sel.options].some(o => o.value === v)) sel.value = v;
      else if (!v) sel.value = '';
      else sel.value = '';
    });
  },

  async loadStockOptions() {
    const sel = document.getElementById('btCodeSelect');
    if (!sel) return;

    const map = new Map();
    const add = (code, name, group) => {
      const c = String(code || '').trim();
      if (!c || map.has(c)) return;
      map.set(c, { code: c, name: name || c, group });
    };

    this._DEFAULT_STOCKS.forEach(s => add(s.code, s.name, 'demo'));

    try {
      const [cfg, rules, stocks] = await Promise.all([
        Api.getConfig(),
        Api.getAlertRules(),
        Api.getStocks(),
      ]);
      (cfg?.watchlist || []).forEach(code => {
        const r = rules?.rules?.[code];
        add(code, r?.name, 'watchlist');
      });
      if (rules?.rules) {
        Object.entries(rules.rules).forEach(([code, r]) => add(code, r?.name, 'watchlist'));
      }
      const list = stocks?.stocks || [];
      const cap = 400;
      if (list.length && list.length <= cap) {
        list.forEach(s => add(s.code, s.name, 'db'));
      } else if (list.length > cap) {
        list.slice(0, cap).forEach(s => add(s.code, s.name, 'db'));
      }
    } catch (e) {
      console.warn('載入股票列表失敗:', e);
    }

    const groups = { demo: '示範股票', watchlist: '監控列表', db: '本地數據' };
    const byGroup = { demo: [], watchlist: [], db: [] };
    [...map.values()].sort((a, b) => a.code.localeCompare(b.code)).forEach(item => {
      const g = byGroup[item.group] ? item.group : 'db';
      byGroup[g].push(item);
    });

    let html = '<option value="">— 從列表選擇 —</option>';
    Object.keys(groups).forEach(key => {
      if (!byGroup[key].length) return;
      html += `<optgroup label="${groups[key]}">`;
      html += byGroup[key].map(s =>
        `<option value="${s.code}">${s.code} ${s.name}</option>`,
      ).join('');
      html += '</optgroup>';
    });
    sel.innerHTML = html;
    this._codesLoaded = true;

    const current = this.getCode();
    if (current) this.setCode(current);
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
