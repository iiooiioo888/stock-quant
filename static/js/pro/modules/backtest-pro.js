/* global Api, echarts */

(() => {
  const $id = (id) => document.getElementById(id);
  const charts = {};
  let running = false;
  let lastResult = null;
  let activeTab = 'equity';

  const CHART_IDS = ['bt-chart-equity', 'bt-chart-dd', 'bt-chart-kline'];

  function nowHHMM() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  function logLine(msg, cls = '') {
    const log = $id('bt-log');
    if (!log) return;
    const t = nowHHMM();
    const div = document.createElement('div');
    div.className = 'll';
    div.innerHTML = `<span class="lt">${t}</span><span class="lm ${cls}">${msg}</span>`;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function badgeClassSigned(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return '';
    return x >= 0 ? 'pos' : 'neg';
  }

  function fmtNum(n, digits = 2) {
    const x = Number(n);
    if (!Number.isFinite(x)) return '--';
    return x.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  }

  function fmtPctSigned(n, digits = 2) {
    const x = Number(n);
    if (!Number.isFinite(x)) return '--';
    return `${x >= 0 ? '+' : ''}${x.toFixed(digits)}%`;
  }

  function fmtMoney(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return '--';
    const sign = x >= 0 ? '+' : '';
    return `${sign}¥${Math.abs(x).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }

  function dlRow(label, value, cls = '') {
    return `<div class="bt-dl-row"><span class="bt-dl-k">${label}</span><span class="bt-dl-v ${cls}">${value}</span></div>`;
  }

  function section(title, rowsHtml) {
    return `<div class="bt-section"><div class="bt-section-hd">${title}</div><div class="bt-dl">${rowsHtml}</div></div>`;
  }

  function computeTradeStats(trades) {
    const list = Array.isArray(trades) ? trades : [];
    let totalPnl = 0;
    let winPnl = 0;
    let lossPnl = 0;
    let winCount = 0;
    let lossCount = 0;
    let holdSum = 0;
    let best = null;
    let worst = null;
    list.forEach((t) => {
      const pnl = Number(t.pnl);
      const ret = Number(t.return_pct);
      const hold = Number(t.hold_days);
      if (Number.isFinite(pnl)) totalPnl += pnl;
      if (Number.isFinite(hold)) holdSum += hold;
      if (Number.isFinite(ret)) {
        if (ret >= 0) {
          winCount += 1;
          if (Number.isFinite(pnl)) winPnl += pnl;
        } else {
          lossCount += 1;
          if (Number.isFinite(pnl)) lossPnl += pnl;
        }
        if (!best || ret > Number(best.return_pct)) best = t;
        if (!worst || ret < Number(worst.return_pct)) worst = t;
      }
    });
    const n = list.length;
    return {
      totalPnl,
      winPnl,
      lossPnl,
      winCount,
      lossCount,
      avgHold: n ? holdSum / n : null,
      best,
      worst,
      avgWin: winCount ? winPnl / winCount : null,
      avgLoss: lossCount ? lossPnl / lossCount : null,
    };
  }

  function buildVerdict(r, ts) {
    const ret = Number(r.total_return_pct);
    const sharpe = Number(r.sharpe_ratio);
    const dd = Number(r.max_drawdown_pct);
    const code = r.code || '';
    const strat = r.strategy || '';
    let tone = '';
    if (Number.isFinite(ret) && Number.isFinite(sharpe)) {
      if (ret > 5 && sharpe > 1) tone = '策略在樣本內表現較佳';
      else if (ret > 0 && sharpe > 0) tone = '策略小幅盈利，可考慮參數優化';
      else if (ret <= 0 && sharpe < 0) tone = '策略在該區間跑輸，建議調參或換標的';
      else tone = '收益與風險調整後表現一般，需結合行情解讀';
    } else {
      tone = '回測已完成，請結合下方指標綜合判斷';
    }
    const ddHint = Number.isFinite(dd) ? `最大回撤 ${dd.toFixed(2)}%` : '';
    const tradeHint = ts && r.total_trades != null
      ? `共 ${r.total_trades} 筆交易，勝率 ${fmtNum(r.win_rate_pct, 1)}%`
      : '';
    return `${code} · ${strat}：${tone}。${[ddHint, tradeHint].filter(Boolean).join('；')}。`;
  }

  function toggleDataPanel(show) {
    const empty = $id('bt-empty');
    const panel = $id('bt-data-panel');
    const chartUi = document.querySelectorAll('.bt-tabs, .bt-chart-pane, .bt-block-title');
    if (empty) {
      empty.hidden = !!show;
      empty.style.display = show ? 'none' : '';
    }
    if (panel) {
      panel.hidden = !show;
      /* 須覆寫 HTML 內聯 display:none，否則僅移除 hidden 仍不可見 */
      panel.style.display = show ? 'block' : 'none';
    }
    chartUi.forEach((el) => {
      if (!el) return;
      if (!show) el.style.display = 'none';
      else if (!el.classList.contains('bt-chart-pane')) el.style.display = '';
    });
  }

  function getChart(id) {
    const el = $id(id);
    if (!el || typeof echarts === 'undefined') return null;
    if (charts[id]) {
      try {
        if (typeof charts[id].isDisposed === 'function' && !charts[id].isDisposed()) return charts[id];
      } catch (_) { /* re-init */ }
      delete charts[id];
    }
    if (el.offsetWidth < 2 || el.offsetHeight < 2) return null;
    charts[id] = echarts.init(el);
    return charts[id];
  }

  function resizeCharts() {
    CHART_IDS.forEach((id) => {
      const c = charts[id];
      if (c) c.resize();
    });
  }

  function buildEquityCurve(r) {
    if (Array.isArray(r.equity_curve) && r.equity_curve.length) {
      return r.equity_curve.map((x) => ({
        date: x.date || x.time || x.t || '',
        value: Number(x.value ?? x.equity ?? x.nav ?? 0),
      }));
    }
    const dates = Array.isArray(r.dates) ? r.dates : [];
    const nav = Array.isArray(r.nav) ? r.nav : [];
    const n = Math.min(dates.length, nav.length);
    const out = [];
    for (let i = 0; i < n; i += 1) {
      out.push({ date: String(dates[i]), value: Number(nav[i]) });
    }
    return out;
  }

  function buildDrawdownSeries(curve) {
    let peak = -Infinity;
    return curve.map((p) => {
      const v = Number(p.value);
      if (v > peak) peak = v;
      const dd = peak > 0 ? ((peak - v) / peak) * 100 : 0;
      return { date: p.date, dd: -Number(dd.toFixed(4)) };
    });
  }

  function axisCommon() {
    return {
      axisLine: { lineStyle: { color: '#1e2138' } },
      axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 8 },
      axisTick: { show: false },
    };
  }

  function tooltipCommon() {
    return {
      trigger: 'axis',
      backgroundColor: '#252842',
      borderColor: '#2d3158',
      textStyle: { color: '#eeeef2', fontFamily: 'JetBrains Mono', fontSize: 10 },
    };
  }

  function dataZoomCommon() {
    return [
      { type: 'inside' },
      {
        type: 'slider',
        height: 16,
        bottom: 0,
        borderColor: '#252842',
        fillerColor: 'rgba(232,184,48,.08)',
        handleStyle: { color: '#e8b830' },
        textStyle: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 8 },
      },
    ];
  }

  function renderEquityChart(curve) {
    const ch = getChart('bt-chart-equity');
    if (!ch || !curve.length) return;
    const xs = curve.map((x) => x.date);
    const ys = curve.map((x) => x.value);
    const initial = ys[0] || 1;
    const retPct = ys.map((v) => ((v / initial - 1) * 100));
    ch.setOption({
      grid: { top: 28, right: 48, bottom: 36, left: 56 },
      legend: { top: 0, textStyle: { color: '#8b8aa3', fontSize: 10 }, data: ['淨值', '累計收益%'] },
      tooltip: {
        ...tooltipCommon(),
        formatter(params) {
          const rows = Array.isArray(params) ? params : [params];
          return rows.map((p) => `${p.seriesName}: ${fmtNum(p.value, p.seriesName.includes('%') ? 2 : 0)}`).join('<br/>');
        },
      },
      dataZoom: dataZoomCommon(),
      xAxis: { type: 'category', data: xs, ...axisCommon() },
      yAxis: [
        { type: 'value', scale: true, name: '淨值', splitLine: { lineStyle: { color: '#1d2033' } }, axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 9 } },
        { type: 'value', scale: true, name: '%', splitLine: { show: false }, axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 9, formatter: '{value}%' } },
      ],
      series: [
        { name: '淨值', type: 'line', data: ys, smooth: true, showSymbol: false, lineStyle: { color: '#e8b830', width: 2 }, areaStyle: { color: 'rgba(232,184,48,.06)' } },
        { name: '累計收益%', type: 'line', yAxisIndex: 1, data: retPct, smooth: true, showSymbol: false, lineStyle: { color: '#5b9bd5', width: 1.2, type: 'dashed' } },
      ],
    }, true);
  }

  function renderDrawdownChart(curve) {
    const ch = getChart('bt-chart-dd');
    if (!ch || !curve.length) return;
    const dd = buildDrawdownSeries(curve);
    ch.setOption({
      grid: { top: 14, right: 12, bottom: 36, left: 52 },
      tooltip: tooltipCommon(),
      dataZoom: dataZoomCommon(),
      xAxis: { type: 'category', data: dd.map((x) => x.date), ...axisCommon() },
      yAxis: { type: 'value', max: 0, axisLine: { show: false }, splitLine: { lineStyle: { color: '#1d2033' } }, axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 9, formatter: '{value}%' } },
      series: [{ name: '回撤', type: 'line', data: dd.map((x) => x.dd), showSymbol: false, lineStyle: { color: '#e85d6c', width: 1.5 }, areaStyle: { color: 'rgba(232,93,108,.12)' } }],
    }, true);
  }

  function renderKlineChart(r) {
    const ch = getChart('bt-chart-kline');
    if (!ch) return;
    const kline = Array.isArray(r.kline) ? r.kline : [];
    if (!kline.length) {
      ch.clear();
      ch.setOption({
        title: { text: '無 K 線數據', left: 'center', top: 'middle', textStyle: { color: '#5c5b72', fontSize: 12 } },
      });
      return;
    }
    const xs = kline.map((x) => x.date || '');
    const ohlc = kline.map((x) => [Number(x.open), Number(x.close), Number(x.low), Number(x.high)]);
    const vol = kline.map((x) => Number(x.volume || 0));
    const signals = Array.isArray(r.signals) ? r.signals : [];
    const markPoints = signals.map((s) => {
      const isBuy = s.type === 'buy';
      const idx = xs.indexOf(s.date);
      return {
        name: isBuy ? '買' : '賣',
        coord: [idx >= 0 ? idx : s.date, Number(s.price)],
        value: isBuy ? '買' : '賣',
        itemStyle: { color: isBuy ? '#e85d6c' : '#3ecf8e' },
      };
    }).filter((m) => m.coord[0] !== -1 || typeof m.coord[0] === 'string');

    ch.setOption({
      grid: [{ top: 24, right: 12, bottom: 72, left: 52, height: '58%' }, { top: '72%', right: 12, bottom: 28, left: 52, height: '16%' }],
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, ...tooltipCommon() },
      dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }, { type: 'slider', xAxisIndex: [0, 1], height: 16, bottom: 4, borderColor: '#252842' }],
      xAxis: [
        { type: 'category', data: xs, ...axisCommon(), gridIndex: 0 },
        { type: 'category', data: xs, ...axisCommon(), gridIndex: 1, axisLabel: { show: false } },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: '#1d2033' } }, axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 9 } },
        { scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
      ],
      series: [
        { type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: '#e85d6c', color0: '#3ecf8e', borderColor: '#e85d6c', borderColor0: '#3ecf8e' }, markPoint: { data: markPoints, symbolSize: 28, label: { fontSize: 9 } } },
        { type: 'bar', data: vol, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: 'rgba(91,155,213,.35)' } },
      ],
    }, true);
  }

  function renderHeroKpis(r) {
    const el = $id('bt-hero');
    if (!el) return;
    const ret = Number(r.total_return_pct);
    const retCls = badgeClassSigned(ret);
    const cards = [
      {
        lbl: '總收益率',
        val: fmtPctSigned(ret),
        sub: `年化 ${fmtPctSigned(r.annual_return_pct)}`,
        mod: retCls === 'pos' ? 'up' : retCls === 'neg' ? 'down' : 'neutral',
      },
      {
        lbl: '最大回撤',
        val: `-${fmtNum(r.max_drawdown_pct)}%`,
        sub: r.max_drawdown_recovery_days != null ? `恢復約 ${r.max_drawdown_recovery_days} 天` : '恢復天數 --',
        mod: 'risk',
      },
      {
        lbl: '夏普比率',
        val: fmtNum(r.sharpe_ratio),
        sub: `Sortino ${fmtNum(r.sortino_ratio)} · Calmar ${fmtNum(r.calmar_ratio)}`,
        mod: 'risk',
      },
      {
        lbl: '勝率',
        val: `${fmtNum(r.win_rate_pct, 1)}%`,
        sub: `盈利 ${r.won_trades ?? 0} 筆 / 虧損 ${r.lost_trades ?? 0} 筆`,
        mod: Number(r.win_rate_pct) >= 50 ? 'up' : 'down',
      },
    ];
    el.innerHTML = cards.map((c) => `
      <div class="bt-hero-card bt-hero-card--${c.mod}">
        <div class="bt-hero-lbl">${c.lbl}</div>
        <div class="bt-hero-val">${c.val}</div>
        <div class="bt-hero-sub">${c.sub}</div>
      </div>`).join('');
  }

  function renderFundsBar(r, curve) {
    const el = $id('bt-funds');
    if (!el) return;
    const initial = Number(r.initial_cash);
    const final = Number(r.final_value);
    const pnl = Number.isFinite(initial) && Number.isFinite(final) ? final - initial : null;
    const pnlCls = pnl != null && pnl >= 0 ? 'pos' : 'neg';
    const start = curve[0]?.date || '--';
    const end = curve[curve.length - 1]?.date || '--';
    el.innerHTML = `
      <div class="bt-fund-item">
        <div class="bt-fund-lbl">初始資金</div>
        <div class="bt-fund-val">¥${fmtNum(initial, 0)}</div>
      </div>
      <span class="bt-fund-arrow" aria-hidden="true">→</span>
      <div class="bt-fund-item">
        <div class="bt-fund-lbl">最終淨值</div>
        <div class="bt-fund-val">¥${fmtNum(final, 0)}</div>
      </div>
      <div class="bt-fund-pnl">
        <div class="bt-fund-lbl">絕對盈虧</div>
        <div class="bt-fund-val ${pnlCls}">${pnl != null ? fmtMoney(pnl) : '--'}</div>
      </div>
      <div class="bt-fund-item" style="margin-left:auto;text-align:right">
        <div class="bt-fund-lbl">回測區間 · ${curve.length} 交易日</div>
        <div class="bt-fund-val" style="font-size:.72rem;font-weight:500">${start} ~ ${end}</div>
      </div>`;
  }

  function renderVizBars(r, ts) {
    const el = $id('bt-viz');
    if (!el) return;
    const winRate = Number(r.win_rate_pct);
    const wr = Number.isFinite(winRate) ? Math.min(100, Math.max(0, winRate)) : 0;
    const total = (r.won_trades || 0) + (r.lost_trades || 0);
    const winW = total > 0 ? ((r.won_trades || 0) / total) * 100 : wr;
    const lossW = 100 - winW;
    const plr = Number(r.profit_loss_ratio);
    const plrText = Number.isFinite(plr) ? (plr >= 1 ? '盈虧結構偏健康' : '單筆虧損偏大，注意止損') : '';
    el.innerHTML = `
      <div class="bt-viz-card">
        <div class="bt-viz-title">勝率分佈</div>
        <div class="bt-bar-track">
          <div class="bt-bar-win" style="width:${winW}%"></div>
          <div class="bt-bar-loss" style="width:${lossW}%"></div>
        </div>
        <div class="bt-bar-legend">
          <span class="pos">盈利 ${r.won_trades ?? 0} 筆 (${fmtNum(winW, 1)}%)</span>
          <span class="neg">虧損 ${r.lost_trades ?? 0} 筆 (${fmtNum(lossW, 1)}%)</span>
        </div>
      </div>
      <div class="bt-viz-card">
        <div class="bt-viz-title">盈虧比 · 累計實現盈虧</div>
        <div class="bt-bar-legend" style="margin-top:0">
          <span>盈虧比 <strong>${fmtNum(plr)}</strong></span>
          <span class="${ts.totalPnl >= 0 ? 'pos' : 'neg'}">合計 ${fmtMoney(ts.totalPnl)}</span>
        </div>
        <div class="bt-bar-legend" style="margin-top:6px;color:var(--t4)">
          <span>均贏 ${ts.avgWin != null ? fmtMoney(ts.avgWin) : '--'}</span>
          <span>均虧 ${ts.avgLoss != null ? fmtMoney(ts.avgLoss) : '--'}</span>
        </div>
        <div style="margin-top:6px;font-size:.62rem;color:var(--t4)">${plrText}</div>
      </div>`;
  }

  function renderSections(r, ts, curve) {
    const el = $id('bt-sections');
    if (!el) return;
    const ea = r.equity_analysis || {};
    const limit = r.limit_filter || {};
    const t1 = r.t1_filter || {};
    const retRows = [
      dlRow('總收益率', fmtPctSigned(r.total_return_pct), badgeClassSigned(r.total_return_pct)),
      dlRow('年化收益', fmtPctSigned(r.annual_return_pct), badgeClassSigned(r.annual_return_pct)),
      dlRow('最終淨值', `¥${fmtNum(r.final_value, 0)}`, ''),
      dlRow('月勝率', `${fmtNum(r.monthly_win_rate, 1)}%`, ''),
      dlRow('水下時間占比', ea.underwater_pct != null ? `${fmtNum(ea.underwater_pct, 1)}%` : '--', ''),
    ].join('');
    const riskRows = [
      dlRow('最大回撤', `-${fmtNum(r.max_drawdown_pct)}%`, 'neg'),
      dlRow('年化波動', `${fmtNum(r.annual_volatility)}%`, ''),
      dlRow('VaR (95%)', `${fmtNum(r.var_95)}%`, 'neg'),
      dlRow('CVaR (95%)', `${fmtNum(r.cvar_95)}%`, 'neg'),
      dlRow('最大水下天數', ea.max_underwater_days != null ? `${ea.max_underwater_days} 天` : '--', ''),
    ].join('');
    const tradeRowsList = [
      dlRow('交易次數', String(r.total_trades ?? '--'), ''),
      dlRow('平均持倉', ts.avgHold != null ? `${fmtNum(ts.avgHold, 1)} 天` : '--', ''),
      dlRow('最佳單筆', ts.best ? fmtPctSigned(ts.best.return_pct) : '--', 'pos'),
      dlRow('最差單筆', ts.worst ? fmtPctSigned(ts.worst.return_pct) : '--', 'neg'),
      dlRow('滑點 / 佣金', `${fmtNum((r.slippage_pct || 0) * 100, 2)}% / 已含`, ''),
      dlRow('T+1 / 漲跌停', `${r.enable_t1 ? '開' : '關'} / ${r.enable_limit ? '開' : '關'}`, ''),
    ];
    const limitBlk = (limit.blocked_buys || 0) + (limit.blocked_sells || 0);
    const t1Blk = t1.blocked_sells || 0;
    if (limitBlk > 0 || t1Blk > 0) {
      const extra = [
        limitBlk > 0 ? `漲跌停攔截 ${limitBlk} 次` : '',
        t1Blk > 0 ? `T+1 攔截 ${t1Blk} 次` : '',
      ].filter(Boolean).join('；');
      tradeRowsList.push(dlRow('規則攔截', extra, ''));
    }
    const tradeRows = tradeRowsList.join('');
    el.innerHTML = [
      section('收益概覽', retRows),
      section('風險指標', riskRows),
      section('交易統計', tradeRows),
    ].join('');
  }

  function renderDataPanel(r, curve) {
    const ts = computeTradeStats(r.trade_details);
    const verdict = $id('bt-verdict');
    if (verdict) {
      const retCls = badgeClassSigned(r.total_return_pct);
      verdict.className = `bt-verdict ${retCls || ''}`;
      verdict.textContent = buildVerdict(r, ts);
    }
    renderHeroKpis(r);
    renderFundsBar(r, curve);
    renderVizBars(r, ts);
    renderSections(r, ts, curve);
    toggleDataPanel(true);
  }

  function renderTrades(r) {
    const tb = $id('bt-trades-tb');
    const sumEl = $id('bt-trades-summary');
    if (!tb) return;
    const intraday = r?.timeframe && r.timeframe !== '1d';
    const theadRow = tb.closest('table')?.querySelector('thead tr');
    if (theadRow) {
      const ths = theadRow.querySelectorAll('th');
      if (ths[0]) ths[0].textContent = intraday ? '買入時間' : '買入日';
      if (ths[2]) ths[2].textContent = intraday ? '賣出時間' : '賣出日';
      if (ths[4]) ths[4].textContent = intraday ? '持倉 K 線' : '持倉天';
    }
    const trades = Array.isArray(r.trade_details) ? r.trade_details : [];
    const ts = computeTradeStats(trades);
    if (sumEl) {
      sumEl.textContent = trades.length
        ? `交易明細（共 ${trades.length} 筆，展示最近 30 筆 · 合計 ${fmtMoney(ts.totalPnl)}）`
        : '交易明細';
    }
    if (!trades.length) {
      tb.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:16px;color:var(--t3)">本輪無完整買賣配對</td></tr>';
      return;
    }
    tb.innerHTML = trades.slice(-30).reverse().map((t) => {
      const ret = Number(t.return_pct);
      const cls = ret >= 0 ? 'pos' : 'neg';
      return `<tr>
        <td>${t.buy_date || '--'}</td>
        <td class="r">${fmtNum(t.buy_price)}</td>
        <td>${t.sell_date || '--'}</td>
        <td class="r">${fmtNum(t.sell_price)}</td>
        <td>${t.hold_days ?? '--'}</td>
        <td class="${cls}">${fmtNum(t.pnl)}</td>
        <td class="${cls}">${fmtNum(ret)}%</td>
      </tr>`;
    }).join('');
  }

  function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('[data-bt-tab]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-bt-tab') === tab);
    });
    document.querySelectorAll('.bt-chart-pane').forEach((pane) => {
      const id = pane.id || '';
      const show = id === `bt-chart-${tab}`;
      pane.style.display = show ? 'block' : 'none';
      pane.classList.toggle('on', show);
    });
    requestAnimationFrame(() => resizeCharts());
  }

  function normalizeResult(raw) {
    if (typeof Api !== 'undefined' && Api.normalizeBacktestResult) {
      return Api.normalizeBacktestResult(raw);
    }
    return raw && typeof raw === 'object' ? raw : null;
  }

  function renderAll(raw) {
    const r = normalizeResult(raw);
    if (!r) {
      logLine('回測結果無法解析', 'er');
      return;
    }
    lastResult = r;
    const curve = buildEquityCurve(r);
    if (!curve.length) {
      logLine('警告：回測結果無權益曲線數據', 'er');
    }

    toggleDataPanel(true);

    renderDataPanel(r, curve);
    switchTab(activeTab);
    renderEquityChart(curve);
    renderDrawdownChart(curve);
    renderKlineChart(r);
    renderTrades(r);
    const meta = $id('bt-meta');
    if (meta) {
      const tf = r.timeframe_label || r.timeframe || '日線';
      const barWord = (r.timeframe && r.timeframe !== '1d') ? '根 K 線' : '個交易日';
      meta.textContent = `${r.code || ''} · ${r.strategy || ''} · ${tf} · ${curve.length} ${barWord}`;
    }
    requestAnimationFrame(() => {
      resizeCharts();
      setTimeout(() => {
        renderEquityChart(curve);
        renderDrawdownChart(curve);
        renderKlineChart(r);
        resizeCharts();
      }, 80);
      setTimeout(resizeCharts, 280);
    });
  }

  function getSelectedCode() {
    const sym = window.StockQPro?.backtestSymbol;
    if (sym?.getSymbol) return sym.getSymbol();
    return String($id('bt-code')?.value || $id('bt-code-input')?.value || '').trim();
  }

  function ensureLoggedIn() {
    if (typeof Api !== 'undefined' && Api.isLoggedIn && Api.isLoggedIn()) return true;
    Api?.showLoginModal?.(false);
    window.StockQPro?.App?.toast?.('請先登錄後再執行回測（點擊頂欄「登錄」）', 'inf');
    return false;
  }

  async function run() {
    const code = getSelectedCode();
    if (!code || !/^\d{6}$/.test(code)) {
      return window.StockQPro?.App?.toast?.('請先選擇有效的 A 股代碼', 'er');
    }
    if (!ensureLoggedIn()) return;
    if (running) return;
    running = true;

    const btn = $id('bt-run-btn');
    if (btn) btn.disabled = true;
    const bar = $id('bt-bar');
    if (bar) bar.style.width = '0%';
    logLine(`載入 ${code}…`);

    const sel = window.StockQPro?.selectedStrategy;
    const backendKey = sel?.backend_key || 'dual_ma';
    if (!sel || !sel.backend_key) {
      logLine('未選擇可回測策略，使用預設 dual_ma', '');
    }
    if (sel?.status && sel.status !== 'implemented' && sel.status !== 'user') {
      window.StockQPro?.App?.toast?.('此策略尚未開放回測', 'inf');
      running = false;
      if (btn) btn.disabled = false;
      return;
    }

    const cash = Number($id('bt-capital')?.value || 0) || undefined;
    const slippagePct = (Number($id('bt-slip')?.value || 0) || 0) / 100.0;
    const commission = (Number($id('bt-comm')?.value || 0) || 0) / 100.0;
    const enableT1 = !!$id('bt-t1')?.checked;
    const enableLimit = !!$id('bt-limit')?.checked;
    const timeframe = String($id('bt-timeframe')?.value || '1d').trim() || '1d';

    const forceRefresh = !!$id('bt-force')?.checked;

    const body = {
      code,
      strategy: backendKey,
      params: null,
      cash,
      commission,
      slippage_pct: slippagePct,
      enable_t1: enableT1,
      enable_limit: enableLimit,
      timeframe,
      benchmark: false,
      force_refresh: forceRefresh,
    };

    try {
      logLine(`提交任務：${backendKey} · ${timeframe}`, 'ok');
      if (bar) bar.style.width = '20%';
      const d = await Api.runAdvancedBacktest(body);
      if (!d) {
        const msg = (typeof Api !== 'undefined' && Api.isLoggedIn && !Api.isLoggedIn())
          ? '未登錄或登錄已過期，請重新登錄'
          : '回測提交失敗';
        throw new Error(msg);
      }
      if (!d?.success) throw new Error(d?.error || d?.detail || '回測提交失敗');

      if (d.is_duplicate) logLine(d.message || '相同回測正在執行中…', '');
      const bgMode = !!$id('bt-bg')?.checked;
      if (d.async && d.task_id) {
        const shortId = String(d.task_id).slice(0, 8);
        logLine(`任務已提交 #${shortId}…`, 'ok');
        if (bgMode) {
          if (bar) bar.style.width = '100%';
          window.StockQPro?.App?.toast?.('已提交背景任務，正在跳轉任務中心', 'ok');
          window.StockQPro?.App?.nav?.('tasks', { syncHash: true });
          return;
        }
        logLine('等待任務完成（可勾選「背景執行」改為非阻塞）…', '');
      }
      if (bar) bar.style.width = '45%';

      const resolved = await Api.resolveTaskResponse(d);
      if (resolved?.from_cache && !forceRefresh) {
        logLine('使用緩存結果（參數與 K 線版本未變）', '');
      }
      const r = normalizeResult(Api.extractResult(resolved) ?? resolved?.result);
      if (!r) throw new Error('未取得回測結果');
      const resultCode = String(r.code || '').replace(/\D/g, '').slice(-6);
      if (resultCode && resultCode !== code) {
        logLine(`警告：結果代碼 ${resultCode} 與請求 ${code} 不一致，請勾選「強制重算」`, 'er');
      }
      if (bar) bar.style.width = '92%';

      renderAll(r);
      logLine('回測完成', 'ok');
      if (bar) bar.style.width = '100%';
    } catch (e) {
      logLine(`回測失敗：${e?.message || e}`, 'er');
      window.StockQPro?.App?.toast?.(`回測失敗：${e?.message || e}`, 'er');
    } finally {
      running = false;
      if (btn) btn.disabled = false;
    }
  }

  function collectRunParams() {
    const code = getSelectedCode();
    const sel = window.StockQPro?.selectedStrategy;
    return {
      code,
      strategy: sel?.backend_key || 'dual_ma',
      strategy_name: sel?.name || sel?.backend_key,
      cash: Number($id('bt-capital')?.value || 0) || undefined,
      slippage_pct: (Number($id('bt-slip')?.value || 0) || 0) / 100.0,
      commission: (Number($id('bt-comm')?.value || 0) / 100.0),
      enable_t1: !!$id('bt-t1')?.checked,
      enable_limit: !!$id('bt-limit')?.checked,
      timeframe: String($id('bt-timeframe')?.value || '1d').trim() || '1d',
    };
  }

  function exportResultJson() {
    if (!lastResult) {
      window.StockQPro?.App?.toast?.('請先完成一次回測', 'inf');
      return;
    }
    const code = lastResult.code || 'stock';
    Api.downloadBlob(JSON.stringify(lastResult, null, 2), `backtest_${code}_${Date.now()}.json`, 'application/json');
    window.StockQPro?.App?.toast?.('已匯出 JSON', 'ok');
  }

  function exportTradesCsv() {
    const trades = lastResult?.trade_details || lastResult?.trades;
    if (!Array.isArray(trades) || !trades.length) {
      return window.StockQPro?.App?.toast?.('無交易明細可匯出', 'inf');
    }
    const header = ['buy_date', 'buy_price', 'sell_date', 'sell_price', 'hold_days', 'pnl', 'return_pct'];
    const lines = [header.join(',')];
    trades.forEach((t) => {
      lines.push(header.map((k) => {
        const v = t[k];
        const s = v == null ? '' : String(v);
        return s.includes(',') ? `"${s}"` : s;
      }).join(','));
    });
    const code = lastResult.code || 'stock';
    Api.downloadBlob(lines.join('\n'), `trades_${code}_${Date.now()}.csv`, 'text/csv;charset=utf-8');
    window.StockQPro?.App?.toast?.('已匯出交易 CSV', 'ok');
  }

  function exportActiveChartPng() {
    const id = activeTab === 'kline' ? 'bt-chart-kline' : (activeTab === 'drawdown' ? 'bt-chart-dd' : 'bt-chart-equity');
    const ch = charts[id];
    if (!ch) return window.StockQPro?.App?.toast?.('請先完成回測並切換到有圖表的標籤', 'inf');
    try {
      const url = ch.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#0f1117' });
      const a = document.createElement('a');
      a.href = url;
      a.download = `backtest_${activeTab}_${Date.now()}.png`;
      a.click();
      window.StockQPro?.App?.toast?.('已匯出圖表 PNG', 'ok');
    } catch (e) {
      window.StockQPro?.App?.toast?.(`匯出失敗：${e?.message || e}`, 'er');
    }
  }

  async function copyParams() {
    const p = collectRunParams();
    const text = JSON.stringify(p, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      window.StockQPro?.App?.toast?.('已複製回測參數', 'ok');
    } catch (_) {
      window.StockQPro?.App?.toast?.('複製失敗，請手動複製', 'er');
    }
  }

  function openOptimize() {
    const code = getSelectedCode();
    window.StockQPro?.App?.nav?.('optimize', { syncHash: true });
    if (code && window.StockQPro?.LegacyBridge?.activate) {
      window.StockQPro.LegacyBridge.activate('optimize', { code }).catch(() => {});
    }
  }

  function bindOnce() {
    const root = $id('pg-backtest');
    if (!root || root.dataset.bound) return;
    root.dataset.bound = '1';

    $id('bt-run-btn')?.addEventListener('click', run);
    $id('bt-clear-log')?.addEventListener('click', () => {
      const log = $id('bt-log');
      if (log) log.innerHTML = '<div class="ll"><span class="lt">--:--</span><span class="lm">就緒</span></div>';
    });
    $id('bt-opt-btn')?.addEventListener('click', openOptimize);
    $id('bt-save-btn')?.addEventListener('click', () => window.StockQPro?.App?.toast?.('已自動寫入回測歷史', 'ok'));
    $id('bt-export-btn')?.addEventListener('click', exportResultJson);
    $id('bt-export-csv-btn')?.addEventListener('click', exportTradesCsv);
    $id('bt-export-png-btn')?.addEventListener('click', exportActiveChartPng);
    $id('bt-copy-params-btn')?.addEventListener('click', () => copyParams());
    $id('bt-tasks-btn')?.addEventListener('click', () => {
      window.StockQPro?.App?.nav?.('tasks', { syncHash: true });
    });

    document.querySelectorAll('[data-bt-tab]').forEach((btn) => {
      btn.addEventListener('click', () => switchTab(btn.getAttribute('data-bt-tab') || 'equity'));
    });
  }

  async function init() {
    bindOnce();
    toggleDataPanel(false);
    try {
      if (!window.StockQPro?.catalog?.strats?.length && window.StockQPro?.loadStrategyCatalog) {
        await window.StockQPro.loadStrategyCatalog();
      }
      window.StockQPro?.ensureDefaultStrategy?.();
    } catch (_) { /* catalog optional */ }
    window.StockQPro?.backtestSymbol?.init?.().catch(() => {});
  }

  function onShow() {
    requestAnimationFrame(() => resizeCharts());
  }

  /** 從任務中心跳轉時展示已有回測結果 */
  function showResult(r, task) {
    const norm = normalizeResult(r);
    if (!norm) return;
    lastResult = norm;
    r = norm;
    const p = task?.params || {};
    const code = p.code || r.code;
    if (code) {
      if (window.StockQPro?.backtestSymbol?.setSymbol) {
        window.StockQPro.backtestSymbol.setSymbol(code);
      } else {
        const el = $id('bt-code');
        if (el) el.value = code;
      }
    }
    const stratEl = $id('bt-strategy') || document.getElementById('btStrategy');
    if (stratEl && p.strategy) stratEl.value = p.strategy;
    if (task?.task_type === 'backtest_multi' && Array.isArray(r)) {
      renderAll(r[0] || r);
    } else {
      renderAll(r);
    }
    logLine('已載入任務結果', 'ok');
    switchTab('equity');
  }

  window.addEventListener('resize', () => resizeCharts());

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.backtest = { init, onShow, showResult };
})();
