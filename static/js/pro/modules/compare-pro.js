/* global Api, echarts */

(() => {
  const $id = (id) => document.getElementById(id);
  const LS_KEY = 'sq_cmp_stocks';
  const MAX_STOCKS = 8;
  const HOT_A_SHARE = [
    { code: '600519', name: '貴州茅台' },
    { code: '600036', name: '招商銀行' },
    { code: '000001', name: '平安銀行' },
    { code: '000858', name: '五糧液' },
    { code: '601318', name: '中國平安' },
    { code: '300750', name: '寧德時代' },
    { code: '002594', name: '比亞迪' },
    { code: '600900', name: '長江電力' },
  ];

  const STOCK_COLORS = ['#e8b830', '#60a5fa', '#34d399', '#f472b6', '#a78bfa', '#fb923c', '#22d3ee', '#94a3b8'];

  const METRIC_LABELS = {
    total_return_pct: '總收益 %',
    sharpe_ratio: '夏普比率',
    sortino_ratio: 'Sortino',
    calmar_ratio: 'Calmar',
    max_drawdown_pct: '最大回撤 %',
    win_rate_pct: '勝率 %',
    annual_return_pct: '年化收益 %',
    total_trades: '交易次數',
  };

  let chart = null;
  let bound = false;
  let namesMap = {};
  let catalogAshare = [];
  let searchTimer = null;
  let pickMode = 'hot';

  const state = {
    mode: 'strategies',
    chips: [],
    strategyResults: null,
    stockComparison: null,
    running: false,
  };

  function normalizeCode(raw) {
    const s = String(raw || '').trim();
    if (/^\d{1,6}$/.test(s)) return s.padStart(6, '0');
    const m = s.match(/(\d{6})/);
    if (m) return m[1];
    if (s.includes('.')) return s.split('.')[0].replace(/\D/g, '').padStart(6, '0').slice(-6);
    return s;
  }

  function isValidAshare(code) {
    return /^\d{6}$/.test(code);
  }

  function resolveName(code) {
    const hit = state.chips.find((c) => c.code === code);
    if (hit?.name) return hit.name;
    return namesMap[code] || catalogAshare.find((x) => x.code === code)?.name || code;
  }

  function quoteUp() {
    return getComputedStyle(document.documentElement).getPropertyValue('--quote-up').trim() || '#f87171';
  }

  function quoteDown() {
    return getComputedStyle(document.documentElement).getPropertyValue('--quote-down').trim() || '#34d399';
  }

  function saveChips() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(state.chips));
    } catch (_) { /* ignore */ }
  }

  function loadChipsFromStorage() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) return;
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return;
      state.chips = arr
        .map((x) => ({ code: normalizeCode(x.code), name: x.name || '' }))
        .filter((x) => isValidAshare(x.code))
        .slice(0, MAX_STOCKS);
    } catch (_) { /* ignore */ }
  }

  function renderChips() {
    const el = $id('cmp-chips');
    if (!el) return;
    if (!state.chips.length) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML = state.chips.map((c, i) => `
      <span class="cmp-chip" data-idx="${i}">
        <span class="cmp-chip-code">${c.code}</span>
        <span class="cmp-chip-name" title="${(c.name || '').replace(/"/g, '&quot;')}">${c.name || c.code}</span>
        <button type="button" class="cmp-chip-x" data-rm="${c.code}" aria-label="移除 ${c.code}">×</button>
      </span>`).join('');
    el.querySelectorAll('[data-rm]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        removeChip(btn.getAttribute('data-rm'));
      });
    });
    saveChips();
  }

  function addChip(code, name = '', opts = {}) {
    const c = normalizeCode(code);
    if (!isValidAshare(c)) {
      window.StockQPro?.App?.toast?.('請輸入 6 位 A 股代碼', 'er');
      return false;
    }
    const n = name || resolveName(c) || c;
    if (state.chips.some((x) => x.code === c)) {
      if (!opts.silent) window.StockQPro?.App?.toast?.(`${c} 已在列表中`, 'inf');
      return false;
    }
    const max = state.mode === 'strategies' ? 1 : MAX_STOCKS;
    if (state.chips.length >= max) {
      if (state.mode === 'strategies') {
        state.chips = [{ code: c, name: n }];
      } else {
        window.StockQPro?.App?.toast?.(`最多選擇 ${MAX_STOCKS} 檔`, 'inf');
        return false;
      }
    } else {
      state.chips.push({ code: c, name: n });
    }
    renderChips();
    if (!opts.silent) window.StockQPro?.App?.toast?.(`已加入 ${c} ${n}`, 'ok');
    return true;
  }

  function removeChip(code) {
    const c = normalizeCode(code);
    state.chips = state.chips.filter((x) => x.code !== c);
    renderChips();
  }

  function clearChips() {
    state.chips = [];
    renderChips();
  }

  function primaryCode() {
    return state.chips[0]?.code || '';
  }

  function setMode(mode) {
    state.mode = mode === 'stocks' ? 'stocks' : 'strategies';
    document.querySelectorAll('[data-cmp-mode]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-cmp-mode') === state.mode);
    });
    const hint = $id('cmp-mode-hint');
    if (hint) {
      hint.textContent = state.mode === 'stocks'
        ? `選 2～${MAX_STOCKS} 檔股票，對比區間相對收益走勢`
        : '選 1 檔股票，對比全部可回測策略表現';
    }
    document.querySelectorAll('.cmp-ctl-strat').forEach((el) => {
      el.style.display = state.mode === 'strategies' ? '' : 'none';
    });
    document.querySelectorAll('.cmp-ctl-stock').forEach((el) => {
      el.style.display = state.mode === 'stocks' ? '' : 'none';
    });
    if (state.mode === 'strategies' && state.chips.length > 1) {
      state.chips = [state.chips[0]];
      renderChips();
      window.StockQPro?.App?.toast?.('多策略模式僅保留第一檔標的', 'inf');
    }
    updateSummaryBadge();
    if (state.mode === 'strategies' && state.strategyResults) renderStrategies();
    else if (state.mode === 'stocks' && state.stockComparison) renderStocks();
    else clearCharts();
  }

  function updateSummaryBadge() {
    const el = $id('cmp-summary-badge');
    if (!el) return;
    const n = state.chips.length;
    if (state.mode === 'stocks') {
      el.textContent = n ? `${n} 檔股票` : '未選標的';
    } else {
      const code = primaryCode();
      el.textContent = code ? `${code} · 策略對比` : '未選標的';
    }
  }

  function initChart() {
    const el = $id('cmp-ch');
    if (!el) return null;
    if (chart) {
      chart.resize();
      return chart;
    }
    chart = echarts.init(el, null, { renderer: 'canvas' });
    return chart;
  }

  function clearCharts() {
    const ch = chart || initChart();
    if (ch) ch.clear();
    const hd = $id('cmp-metric-hd');
    if (hd) hd.textContent = '';
    const stats = $id('cmp-stats-row');
    if (stats) stats.innerHTML = '';
    const tb = $id('cmp-tb');
    const thead = $id('cmp-thead');
    if (tb) tb.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--t3);padding:28px">選擇標的後點擊「執行對比」</td></tr>';
    if (thead) thead.innerHTML = '';
  }

  function metricLabel(key) {
    return METRIC_LABELS[key] || key;
  }

  function formatMetricValue(key, v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '--';
    if (String(key).includes('pct')) return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
    if (key === 'total_trades') return String(Math.round(n));
    return n.toFixed(3);
  }

  function valueClass(key, v) {
    const n = Number(v);
    if (key === 'max_drawdown_pct') return 'neg';
    if (key === 'total_trades') return '';
    return n >= 0 ? 'pos' : 'neg';
  }

  function sortRows(rows, metric, order) {
    const sorted = [...rows].sort((a, b) => Number(b[metric] ?? 0) - Number(a[metric] ?? 0));
    return order === 'asc' ? sorted.reverse() : sorted;
  }

  function renderStats(rows, metric) {
    const el = $id('cmp-stats-row');
    if (!el || !rows.length) {
      if (el) el.innerHTML = '';
      return;
    }
    const vals = rows.map((r) => Number(r[metric] ?? 0)).filter((x) => Number.isFinite(x));
    if (!vals.length) {
      el.innerHTML = '';
      return;
    }
    const best = vals.reduce((a, b) => (b > a ? b : a), vals[0]);
    const worst = vals.reduce((a, b) => (b < a ? b : a), vals[0]);
    const avg = vals.reduce((s, x) => s + x, 0) / vals.length;
    const cards = [
      { lbl: '最佳', val: best },
      { lbl: '最差', val: worst },
      { lbl: '平均', val: avg },
      { lbl: '樣本數', val: rows.length, raw: true },
    ];
    el.innerHTML = cards.map((c) => {
      const txt = c.raw ? String(c.val) : formatMetricValue(metric, c.val);
      const cls = c.raw ? '' : valueClass(metric, c.val);
      return `<div class="cmp-stat-card"><div class="cmp-stat-lbl">${c.lbl}</div><div class="cmp-stat-val ${cls}">${txt}</div></div>`;
    }).join('');
  }

  function baseChartOpts() {
    return {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'JetBrains Mono, DM Sans, sans-serif' },
    };
  }

  function renderStrategyBar(rows, metric, isPct) {
    const ch = initChart();
    if (!ch) return;
    const names = rows.map((r) => r.label);
    const values = rows.map((r) => r.v);
    ch.setOption({
      ...baseChartOpts(),
      grid: { top: 28, right: 24, bottom: 24, left: 108, containLabel: false },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: '#252842',
        borderColor: '#2d3158',
        textStyle: { color: '#eeeef2', fontSize: 11 },
        formatter: (params) => {
          const p = Array.isArray(params) ? params[0] : params;
          const row = rows[p?.dataIndex];
          if (!row) return '';
          return [
            `<b>${row.label}</b>`,
            `${metricLabel(metric)}: ${formatMetricValue(metric, row.v)}`,
            `夏普: ${formatMetricValue('sharpe_ratio', row.sharpe)}`,
            `回撤: ${formatMetricValue('max_drawdown_pct', row.max_dd)}`,
            `勝率: ${formatMetricValue('win_rate_pct', row.win_rate)}`,
          ].join('<br/>');
        },
      },
      xAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: '#1e2138' } },
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: {
          color: '#5c5b72',
          fontSize: 10,
          formatter: isPct ? (v) => `${v}%` : '{value}',
        },
      },
      yAxis: {
        type: 'category',
        data: names,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#9b9ab4', fontSize: 10, width: 96, overflow: 'truncate' },
      },
      dataZoom: rows.length > 12 ? [{ type: 'slider', yAxisIndex: 0, width: 12, right: 4 }] : [],
      series: [{
        type: 'bar',
        data: values.map((v) => ({
          value: v,
          itemStyle: {
            color: isPct
              ? (v >= 0 ? quoteUp() : quoteDown())
              : new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: '#3b3f5c' },
                { offset: 1, color: '#e8b830' },
              ]),
          },
        })),
        barMaxWidth: 22,
        label: {
          show: rows.length <= 16,
          position: 'right',
          fontSize: 10,
          color: '#9b9ab4',
          formatter: (p) => formatMetricValue(metric, p.value),
        },
        markLine: isPct ? {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#5c5b72', type: 'dashed' },
          data: [{ xAxis: 0 }],
        } : undefined,
      }],
    }, true);
  }

  function renderStrategyScatter(rows) {
    const ch = initChart();
    if (!ch) return;
    const data = rows.map((r) => {
      const ret = Number(r.raw?.total_return_pct ?? r.v) || 0;
      return {
        name: r.label,
        value: [Number(r.sharpe) || 0, ret, Number(r.trades) || 0],
        itemStyle: { color: ret >= 0 ? quoteUp() : quoteDown() },
      };
    });
    ch.setOption({
      ...baseChartOpts(),
      grid: { top: 36, right: 28, bottom: 48, left: 56 },
      tooltip: {
        trigger: 'item',
        backgroundColor: '#252842',
        borderColor: '#2d3158',
        formatter: (p) => {
          const d = p.data;
          return `<b>${d.name}</b><br/>夏普: ${formatMetricValue('sharpe_ratio', d.value[0])}<br/>收益: ${formatMetricValue('total_return_pct', d.value[1])}<br/>交易: ${d.value[2]}`;
        },
      },
      xAxis: {
        name: '夏普',
        nameLocation: 'middle',
        nameGap: 28,
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: { color: '#5c5b72', fontSize: 10 },
      },
      yAxis: {
        name: '總收益 %',
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: { color: '#5c5b72', fontSize: 10, formatter: '{value}%' },
      },
      series: [{
        type: 'scatter',
        symbolSize: (val) => Math.min(36, Math.max(10, Math.sqrt(val[2] || 1) * 3)),
        data,
        emphasis: { focus: 'self', scale: 1.2 },
      }],
    }, true);
  }

  function renderStrategyNav(rows) {
    const ch = initChart();
    if (!ch) return;
    const withNav = rows.filter((r) => r.nav && r.nav.length > 1);
    if (!withNav.length) {
      renderStrategyBar(rows, $id('cmp-metric')?.value || 'total_return_pct', true);
      return;
    }
    const top = [...withNav].sort((a, b) => Number(b.v) - Number(a.v)).slice(0, 5);
    let dates = top[0].dates || [];
    if (!dates.length && top[0].nav.length) {
      dates = top[0].nav.map((_, i) => String(i));
    }
    ch.setOption({
      ...baseChartOpts(),
      color: STOCK_COLORS,
      legend: { top: 4, textStyle: { color: '#9b9ab4', fontSize: 10 }, type: 'scroll' },
      grid: { top: 48, right: 20, bottom: 56, left: 52 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#252842',
        borderColor: '#2d3158',
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { color: '#5c5b72', fontSize: 9, hideOverlap: true },
        axisLine: { lineStyle: { color: '#1e2138' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: { color: '#5c5b72', fontSize: 10 },
      },
      series: top.map((r, i) => ({
        name: r.label,
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        data: r.nav,
      })),
    }, true);
  }

  function renderStrategyTable(rows, metric) {
    const thead = $id('cmp-thead');
    const tb = $id('cmp-tb');
    if (!tb) return;
    if (thead) {
      thead.innerHTML = `<tr>
        <th class="cmp-rank">#</th>
        <th>策略</th>
        <th>${metricLabel(metric)}</th>
        <th>夏普</th>
        <th>回撤</th>
        <th>勝率</th>
        <th>交易</th>
      </tr>`;
    }
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--t3);padding:24px">無資料</td></tr>';
      return;
    }
    tb.innerHTML = rows.map((r, i) => {
      const rankCls = i < 3 ? 'cmp-rank top' : 'cmp-rank';
      return `<tr>
        <td class="${rankCls}">${i + 1}</td>
        <td title="${r.key || ''}">${r.label}</td>
        <td class="${valueClass(metric, r.v)}">${formatMetricValue(metric, r.v)}</td>
        <td>${formatMetricValue('sharpe_ratio', r.sharpe)}</td>
        <td class="neg">${formatMetricValue('max_drawdown_pct', r.max_dd)}</td>
        <td>${formatMetricValue('win_rate_pct', r.win_rate)}</td>
        <td>${formatMetricValue('total_trades', r.trades)}</td>
      </tr>`;
    }).join('');
  }

  function renderStrategies() {
    const raw = state.strategyResults;
    if (!raw?.length) {
      clearCharts();
      return;
    }
    const metric = $id('cmp-metric')?.value || 'total_return_pct';
    const sortOrder = $id('cmp-sort')?.value || 'desc';
    const topN = Number($id('cmp-topn')?.value || 0);
    const chartType = $id('cmp-chart-type')?.value || 'bar';
    const isPct = String(metric).includes('pct');

    let rows = raw.map((r) => ({
      label: r.strategy_name || r.strategy || '—',
      key: r.strategy || '',
      v: Number(r[metric] ?? 0),
      sharpe: Number(r.sharpe_ratio ?? 0),
      max_dd: Number(r.max_drawdown_pct ?? 0),
      win_rate: Number(r.win_rate_pct ?? 0),
      trades: Number(r.total_trades ?? 0),
      nav: r.nav || [],
      dates: r.dates || [],
      raw: r,
    }));
    rows = sortRows(rows, 'v', sortOrder);
    if (topN > 0) rows = rows.slice(0, topN);

    const hd = $id('cmp-metric-hd');
    const code = primaryCode();
    if (hd) {
      hd.innerHTML = `<span class="lib-legend-item"><b>${code}</b></span>
        <span class="lib-legend-item">指標：${metricLabel(metric)}</span>
        <span class="lib-legend-item">共 ${raw.length} 策略 · 顯示 ${rows.length}</span>`;
    }

    renderStats(rows, metric);
    if (chartType === 'scatter') renderStrategyScatter(rows);
    else if (chartType === 'nav') renderStrategyNav(rows);
    else renderStrategyBar(rows, metric, isPct);
    renderStrategyTable(rows, metric);
  }

  function renderStocks() {
    const comp = state.stockComparison;
    const ch = initChart();
    if (!ch || !comp || !Object.keys(comp).length) {
      clearCharts();
      return;
    }
    const codes = Object.keys(comp);
    const dates = comp[codes[0]]?.dates || [];
    const normalize = $id('cmp-normalize')?.checked !== false;

    const series = codes.map((code, i) => {
      const item = comp[code];
      let data = item.relative_return || [];
      if (!normalize && item.close) data = item.close;
      return {
        name: `${code} ${resolveName(code)}`,
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        data,
      };
    });

    ch.setOption({
      ...baseChartOpts(),
      color: STOCK_COLORS,
      legend: { top: 4, type: 'scroll', textStyle: { color: '#9b9ab4', fontSize: 10 } },
      grid: { top: 44, right: 24, bottom: 56, left: 52 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#252842',
        borderColor: '#2d3158',
        valueFormatter: (v) => (normalize ? `${Number(v).toFixed(2)}%` : Number(v).toFixed(2)),
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLabel: { color: '#5c5b72', fontSize: 9, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        scale: true,
        name: normalize ? '相對收益 %' : '收盤價',
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: {
          color: '#5c5b72',
          formatter: normalize ? '{value}%' : '{value}',
        },
      },
      series,
    }, true);

    const hd = $id('cmp-metric-hd');
    if (hd) {
      hd.innerHTML = `<span class="lib-legend-item">區間：${dates[0] || '—'} → ${dates[dates.length - 1] || '—'}</span>
        <span class="lib-legend-item">${normalize ? '歸一化累計收益' : '收盤價'}</span>
        <span class="lib-legend-item">${codes.length} 檔</span>`;
    }

    renderStockStats(codes, comp, normalize);
    renderStockTable(codes, comp, normalize);
  }

  function renderStockStats(codes, comp, normalize) {
    const el = $id('cmp-stats-row');
    if (!el) return;
    const rets = codes.map((code) => {
      const rel = comp[code]?.relative_return || [];
      const last = rel.length ? rel[rel.length - 1] : 0;
      return { code, name: resolveName(code), ret: last };
    });
    const best = [...rets].sort((a, b) => b.ret - a.ret)[0];
    const worst = [...rets].sort((a, b) => a.ret - b.ret)[0];
    el.innerHTML = [
      { lbl: '區間最佳', val: best ? `${best.code} ${formatMetricValue('total_return_pct', best.ret)}` : '—', cls: 'pos' },
      { lbl: '區間最弱', val: worst ? `${worst.code} ${formatMetricValue('total_return_pct', worst.ret)}` : '—', cls: 'neg' },
      { lbl: '對比檔數', val: codes.length, cls: '', raw: true },
    ].map((c) => `<div class="cmp-stat-card"><div class="cmp-stat-lbl">${c.lbl}</div><div class="cmp-stat-val ${c.cls}">${c.val}</div></div>`).join('');
  }

  function renderStockTable(codes, comp, normalize) {
    const thead = $id('cmp-thead');
    const tb = $id('cmp-tb');
    if (!tb) return;
    if (thead) {
      thead.innerHTML = `<tr>
        <th>代碼</th><th>名稱</th>
        <th>${normalize ? '區間收益' : '最新價'}</th>
        <th>數據點</th>
        <th></th>
      </tr>`;
    }
    tb.innerHTML = codes.map((code) => {
      const item = comp[code];
      const rel = item?.relative_return || [];
      const last = rel.length ? rel[rel.length - 1] : 0;
      const close = item?.close?.length ? item.close[item.close.length - 1] : '--';
      const val = normalize ? last : close;
      const cls = normalize ? valueClass('total_return_pct', val) : '';
      const txt = normalize ? formatMetricValue('total_return_pct', val) : close;
      return `<tr>
        <td class="ac">${code}</td>
        <td>${resolveName(code)}</td>
        <td class="${cls}">${txt}</td>
        <td>${rel.length}</td>
        <td><button type="button" class="btn s" data-cmp-bt="${code}">回測</button></td>
      </tr>`;
    }).join('');
    tb.querySelectorAll('[data-cmp-bt]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const code = btn.getAttribute('data-cmp-bt');
        window.StockQPro?.App?.nav?.('backtest', { syncHash: true });
        window.StockQPro?.backtestSymbol?.setSymbol?.(code, resolveName(code));
      });
    });
  }

  async function runStrategies() {
    const code = primaryCode();
    if (!code) return window.StockQPro?.App?.toast?.('請先加入一檔股票', 'er');
    const btn = $id('cmp-run');
    if (btn) btn.disabled = true;
    state.running = true;
    const hd = $id('cmp-metric-hd');
    if (hd) hd.textContent = '多策略回測執行中，請稍候…';
    try {
      const d = await Api.runMultiBacktest(code);
      const resolved = await Api.resolveTaskResponse(d, { timeoutMs: 600000 });
      const r = Api.extractResult(resolved);
      if (!Array.isArray(r)) throw new Error('未取得對比結果');
      state.strategyResults = r;
      renderStrategies();
      window.StockQPro?.App?.toast?.(`已完成 ${r.length} 個策略對比`, 'ok');
    } catch (e) {
      state.strategyResults = null;
      clearCharts();
      window.StockQPro?.App?.toast?.(`對比失敗：${e?.message || e}`, 'er');
    } finally {
      state.running = false;
      if (btn) btn.disabled = false;
      updateSummaryBadge();
    }
  }

  async function runStocks() {
    const codes = state.chips.map((c) => c.code);
    if (codes.length < 2) return window.StockQPro?.App?.toast?.('多股模式請至少選擇 2 檔', 'er');
    const days = Number($id('cmp-days')?.value || 250);
    const btn = $id('cmp-run');
    if (btn) btn.disabled = true;
    state.running = true;
    try {
      const d = await Api.compareStocks(codes, days);
      if (!d?.success) throw new Error(d?.error || '對比失敗');
      state.stockComparison = d.comparison || {};
      const missing = d.missing || [];
      if (missing.length) {
        window.StockQPro?.App?.toast?.(`部分標的無數據：${missing.join(', ')}`, 'inf');
      }
      renderStocks();
      window.StockQPro?.App?.toast?.(`已載入 ${d.loaded || 0}/${d.total || codes.length} 檔`, 'ok');
    } catch (e) {
      state.stockComparison = null;
      clearCharts();
      window.StockQPro?.App?.toast?.(`對比失敗：${e?.message || e}`, 'er');
    } finally {
      state.running = false;
      if (btn) btn.disabled = false;
      updateSummaryBadge();
    }
  }

  async function run() {
    if (state.running) return;
    if (state.mode === 'stocks') await runStocks();
    else await runStrategies();
  }

  function exportChartPng() {
    const ch = chart || initChart();
    if (!ch) return;
    try {
      const url = ch.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#0f1117' });
      const a = document.createElement('a');
      a.href = url;
      a.download = `compare_${state.mode}_${Date.now()}.png`;
      a.click();
      window.StockQPro?.App?.toast?.('已匯出 PNG', 'ok');
    } catch (e) {
      window.StockQPro?.App?.toast?.(`匯出失敗：${e?.message || e}`, 'er');
    }
  }

  function exportCsv() {
    if (state.mode === 'strategies' && state.strategyResults?.length) {
      const metric = $id('cmp-metric')?.value || 'total_return_pct';
      const header = ['strategy', 'strategy_key', metric, 'sharpe_ratio', 'max_drawdown_pct', 'win_rate_pct', 'total_trades'];
      const lines = [header.join(',')];
      state.strategyResults.forEach((r) => {
        lines.push([
          r.strategy_name || r.strategy,
          r.strategy,
          r[metric],
          r.sharpe_ratio,
          r.max_drawdown_pct,
          r.win_rate_pct,
          r.total_trades,
        ].map((v) => {
          const s = String(v ?? '');
          return s.includes(',') ? `"${s.replace(/"/g, '""')}"` : s;
        }).join(','));
      });
      Api.downloadBlob(lines.join('\n'), `strategy_compare_${primaryCode()}_${Date.now()}.csv`, 'text/csv;charset=utf-8');
      window.StockQPro?.App?.toast?.('已匯出 CSV', 'ok');
      return;
    }
    if (state.mode === 'stocks' && state.stockComparison) {
      const codes = Object.keys(state.stockComparison);
      const dates = state.stockComparison[codes[0]]?.dates || [];
      const header = ['date', ...codes];
      const lines = [header.join(',')];
      dates.forEach((dt, i) => {
        lines.push([dt, ...codes.map((c) => state.stockComparison[c]?.relative_return?.[i] ?? '')].join(','));
      });
      Api.downloadBlob(lines.join('\n'), `stocks_compare_${Date.now()}.csv`, 'text/csv;charset=utf-8');
      window.StockQPro?.App?.toast?.('已匯出 CSV', 'ok');
      return;
    }
    window.StockQPro?.App?.toast?.('尚無可匯出資料', 'inf');
  }

  function switchPickMode(mode) {
    pickMode = mode;
    document.querySelectorAll('[data-cmp-pick]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-cmp-pick') === mode);
    });
    document.querySelectorAll('[data-cmp-pick-panel]').forEach((pane) => {
      pane.classList.toggle('on', pane.getAttribute('data-cmp-pick-panel') === mode);
    });
    if (mode === 'watch') loadWatchlist();
    if (mode === 'catalog' && !catalogAshare.length) loadCatalog();
    if (mode === 'hot') renderHot();
  }

  function renderPickList(containerId, items, emptyText) {
    const el = $id(containerId);
    if (!el) return;
    if (!items.length) {
      el.innerHTML = `<div class="bt-pick-empty">${emptyText}</div>`;
      return;
    }
    el.innerHTML = items.map((it) => `
      <button type="button" class="bt-pick-item" data-code="${it.code}" data-name="${(it.name || '').replace(/"/g, '&quot;')}">
        <span class="bt-pick-item-code">${it.code}</span>
        <span class="bt-pick-item-name">${it.name || it.code}</span>
        ${it.extra ? `<span class="bt-pick-item-extra">${it.extra}</span>` : ''}
      </button>`).join('');
    el.querySelectorAll('.bt-pick-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        addChip(btn.getAttribute('data-code'), btn.getAttribute('data-name'));
      });
    });
  }

  async function loadNames() {
    try {
      const d = await Api.get('/api/stocks/names');
      namesMap = d?.names || {};
    } catch (_) {
      namesMap = {};
    }
  }

  async function loadCatalog() {
    const el = $id('cmp-pick-catalog');
    if (el) el.innerHTML = '<div class="bt-pick-empty">載入中…</div>';
    try {
      const d = await Api.getAssetsCatalog();
      const list = (d?.instruments || [])
        .filter((i) => i.group === 'a_share' && i.asset_class === 'stock')
        .map((i) => {
          const code = normalizeCode(i.symbol);
          return { code, name: i.name || code };
        })
        .filter((i) => isValidAshare(i.code));
      const seen = new Set();
      catalogAshare = list.filter((i) => {
        if (seen.has(i.code)) return false;
        seen.add(i.code);
        return true;
      });
      if (!catalogAshare.length && Object.keys(namesMap).length) {
        catalogAshare = Object.entries(namesMap)
          .map(([code, name]) => ({ code: normalizeCode(code), name: name || code }))
          .filter((i) => isValidAshare(i.code));
      }
      renderPickList('cmp-pick-catalog', catalogAshare.slice(0, 80), '資產庫暫無 A 股');
    } catch (_) {
      if (Object.keys(namesMap).length) {
        catalogAshare = Object.entries(namesMap)
          .map(([code, name]) => ({ code: normalizeCode(code), name: name || code }))
          .filter((i) => isValidAshare(i.code));
        renderPickList('cmp-pick-catalog', catalogAshare.slice(0, 80), '資產庫暫無 A 股');
      } else if (el) {
        el.innerHTML = '<div class="bt-pick-empty">載入失敗</div>';
      }
    }
  }

  async function loadWatchlist() {
    const el = $id('cmp-pick-watch');
    if (el) el.innerHTML = '<div class="bt-pick-empty">載入中…</div>';
    let items = [];
    try {
      const d = await Api.getWatchlist();
      items = (d?.items || []).map((x) => ({ code: x.code, name: x.name }));
    } catch (_) { /* ignore */ }
    items = items.filter((x) => isValidAshare(normalizeCode(x.code)));
    renderPickList('cmp-pick-watch', items, '自選為空');
  }

  function renderHot() {
    renderPickList('cmp-pick-hot', HOT_A_SHARE, '');
  }

  async function runSearch() {
    const q = String($id('cmp-search-q')?.value || '').trim();
    const el = $id('cmp-pick-search');
    if (!q) {
      if (el) el.innerHTML = '<div class="bt-pick-empty">輸入關鍵字</div>';
      return;
    }
    if (el) el.innerHTML = '<div class="bt-pick-empty">搜索中…</div>';
    try {
      const d = await Api.getStockUniverse('a_share', 30, 0, q);
      const rows = (d?.stocks || []).map((s) => ({
        code: normalizeCode(s.code),
        name: s.name || namesMap[s.code] || s.code,
        extra: s.industry || '',
      })).filter((x) => isValidAshare(x.code));
      renderPickList('cmp-pick-search', rows, '未找到');
    } catch (_) {
      const local = Object.entries(namesMap)
        .filter(([code, name]) => code.includes(q) || String(name).includes(q))
        .slice(0, 30)
        .map(([code, name]) => ({ code: normalizeCode(code), name }));
      renderPickList('cmp-pick-search', local.filter((x) => isValidAshare(x.code)), '搜索失敗');
    }
  }

  function onCodeInput() {
    const raw = String($id('cmp-code-input')?.value || '').trim();
    const c = normalizeCode(raw);
    if (isValidAshare(c) && raw.length === 6) {
      addChip(c, resolveName(c), { silent: true });
      const sug = $id('cmp-code-suggest');
      if (sug) sug.hidden = true;
      if ($id('cmp-code-input')) $id('cmp-code-input').value = '';
      return;
    }
    if (raw.length < 1) {
      const sug = $id('cmp-code-suggest');
      if (sug) sug.hidden = true;
      return;
    }
    const hits = Object.entries(namesMap)
      .filter(([code, name]) => code.startsWith(raw) || String(name).includes(raw))
      .slice(0, 8)
      .map(([code, name]) => ({ code: normalizeCode(code), name }));
    const sug = $id('cmp-code-suggest');
    if (!sug) return;
    if (!hits.length) {
      sug.hidden = true;
      return;
    }
    sug.hidden = false;
    sug.innerHTML = hits.map((h) => `
      <button type="button" class="bt-suggest-item" data-code="${h.code}" data-name="${h.name}">
        <span>${h.code}</span> ${h.name}
      </button>`).join('');
    sug.querySelectorAll('.bt-suggest-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        addChip(btn.getAttribute('data-code'), btn.getAttribute('data-name'));
        sug.hidden = true;
        if ($id('cmp-code-input')) $id('cmp-code-input').value = '';
      });
    });
  }

  function bindControls() {
    if (bound) return;
    bound = true;

    document.querySelectorAll('[data-cmp-mode]').forEach((btn) => {
      btn.addEventListener('click', () => setMode(btn.getAttribute('data-cmp-mode')));
    });
    document.querySelectorAll('[data-cmp-pick]').forEach((btn) => {
      btn.addEventListener('click', () => switchPickMode(btn.getAttribute('data-cmp-pick') || 'hot'));
    });

    $id('cmp-add-btn')?.addEventListener('click', () => {
      const c = normalizeCode($id('cmp-code-input')?.value);
      if (isValidAshare(c)) {
        addChip(c, resolveName(c));
        if ($id('cmp-code-input')) $id('cmp-code-input').value = '';
      } else {
        window.StockQPro?.App?.toast?.('請輸入有效代碼', 'er');
      }
    });
    $id('cmp-code-input')?.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(onCodeInput, 200);
    });
    $id('cmp-code-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const c = normalizeCode($id('cmp-code-input')?.value);
        if (isValidAshare(c)) {
          addChip(c, resolveName(c));
          if ($id('cmp-code-input')) $id('cmp-code-input').value = '';
        }
      }
    });
    $id('cmp-search-btn')?.addEventListener('click', runSearch);
    $id('cmp-search-q')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runSearch();
    });
    $id('cmp-clear-chips')?.addEventListener('click', clearChips);
    $id('cmp-use-bt')?.addEventListener('click', () => {
      const sym = window.StockQPro?.backtestSymbol;
      const c = sym?.getSymbol?.() || '';
      if (c) addChip(c, sym?.normalizeCode ? resolveName(c) : '');
      else window.StockQPro?.App?.toast?.('請先在回測頁選擇標的', 'inf');
    });
    $id('cmp-pick-assets-nav')?.addEventListener('click', () => {
      window.StockQPro?.App?.nav?.('assets', { syncHash: true });
    });

    $id('cmp-run')?.addEventListener('click', run);
    $id('cmp-export-png')?.addEventListener('click', exportChartPng);
    $id('cmp-export-csv')?.addEventListener('click', exportCsv);

    ['cmp-metric', 'cmp-sort', 'cmp-topn', 'cmp-chart-type'].forEach((id) => {
      $id(id)?.addEventListener('change', () => {
        if (state.strategyResults?.length) renderStrategies();
      });
    });
    $id('cmp-days')?.addEventListener('change', () => {
      if (state.stockComparison) runStocks();
    });
    $id('cmp-normalize')?.addEventListener('change', () => {
      if (state.stockComparison) renderStocks();
    });
  }

  async function init() {
    bindControls();
    loadChipsFromStorage();
    if (!state.chips.length) {
      addChip('600519', '貴州茅台', { silent: true });
    } else {
      renderChips();
    }
    await loadNames();
    setMode(state.mode);
    renderHot();
    clearCharts();
    updateSummaryBadge();
    setTimeout(() => chart?.resize(), 80);
  }

  function onShow() {
    setTimeout(() => chart?.resize(), 60);
  }

  function unload() {
    /* keep chart instance */
  }

  window.addEventListener('resize', () => chart?.resize());

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.compare = { init, onShow, unload };
})();
