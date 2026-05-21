/**
 * charts.js — 圖表函數 (Chart.js + Lightweight Charts)
 */

const CHART_COLORS = ['#38bdf8', '#22c55e', '#f59e0b', '#ef4444', '#a78bfa', '#ec4899', '#06b6d4', '#84cc16'];

function _chartLabel(text) {
  if (typeof SignalLabels !== 'undefined' && SignalLabels.label) {
    return SignalLabels.label(text);
  }
  return text;
}

function _chartSeries(series) {
  return (series || []).map(s => ({
    ...s,
    label: _chartLabel(s.label),
  }));
}

function _applyChartJsStableDefaults() {
  if (typeof Chart === 'undefined' || Chart._sqStableDefaults) return;
  Chart.defaults.animation = false;
  Chart.defaults.animations = Chart.defaults.animations || {};
  if (Chart.defaults.animations.colors) Chart.defaults.animations.colors.duration = 0;
  if (Chart.defaults.animations.numbers) Chart.defaults.animations.numbers.duration = 0;
  Chart._sqStableDefaults = true;
}

const Charts = {
  _lwCharts: {},
  _lwFitOnResize: new Set(),

  _chartJsReady() {
    _applyChartJsStableDefaults();
    return typeof Chart !== 'undefined';
  },

  _lwReady() {
    return typeof LightweightCharts !== 'undefined';
  },

  /** v4: addCandlestickSeries；v5: addSeries(CandlestickSeries) */
  _addCandlestickSeries(chart, options = {}) {
    if (typeof chart.addCandlestickSeries === 'function') {
      return chart.addCandlestickSeries(options);
    }
    const Series = LightweightCharts.CandlestickSeries;
    if (!Series) throw new Error('LightweightCharts.CandlestickSeries 不可用');
    return chart.addSeries(Series, options);
  },

  /** v4: addHistogramSeries；v5: addSeries(HistogramSeries) */
  _addHistogramSeries(chart, options = {}) {
    if (typeof chart.addHistogramSeries === 'function') {
      return chart.addHistogramSeries(options);
    }
    const Series = LightweightCharts.HistogramSeries;
    if (!Series) throw new Error('LightweightCharts.HistogramSeries 不可用');
    return chart.addSeries(Series, options);
  },

  /** v4: addLineSeries；v5: addSeries(LineSeries) */
  _addLineSeries(chart, options = {}) {
    if (typeof chart.addLineSeries === 'function') {
      return chart.addLineSeries(options);
    }
    const Series = LightweightCharts.LineSeries;
    if (!Series) throw new Error('LightweightCharts.LineSeries 不可用');
    return chart.addSeries(Series, options);
  },

  _scheduleResize(canvas) {
    if (!canvas) return;
    const run = () => {
      const chart = Chart.getChart(canvas);
      if (chart) chart.resize();
    };
    requestAnimationFrame(() => requestAnimationFrame(run));
  },

  /** Tab 切換後重算圖表尺寸（避免在 display:none 時渲染成 0 高度） */
  resizeTab(tabOrId) {
    const root = typeof tabOrId === 'string' ? document.getElementById(tabOrId) : tabOrId;
    if (!root) return;

    if (this._chartJsReady()) {
      root.querySelectorAll('canvas').forEach(canvas => {
        const chart = Chart.getChart(canvas);
        if (chart) chart.resize();
      });
    }

    if (this._lwReady()) {
      root.querySelectorAll('[id^="idx-chart-"], [id^="tv-chart-"]').forEach(el => {
        const chart = this._lwCharts[el.id];
        if (!chart) return;
        const w = el.clientWidth || 280;
        const h = el.clientHeight || 200;
        chart.applyOptions({ width: w, height: h });
        if (this._lwFitOnResize.has(el.id)) {
          try { chart.timeScale().fitContent(); } catch (e) { /* ignore */ }
        }
      });
    }

    root.querySelectorAll('canvas').forEach(canvas => {
      if (canvas._treemapSectors?.length) {
        this.drawSectorTreemap(
          canvas.id,
          canvas._treemapSectors,
          canvas._treemapHeight || 280,
        );
      }
    });
  },

  setPlaceholder(canvasId, message) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const wrap = canvas.closest('.cw, .cw-tall, .cw-treemap');
    if (!wrap) return;
    let ph = wrap.querySelector('.chart-placeholder');
    if (!ph) {
      ph = document.createElement("d" + "iv");
      ph.className = 'chart-placeholder';
      wrap.appendChild(ph);
    }
    ph.textContent = message;
    canvas.style.visibility = 'hidden';
    canvas.style.position = 'absolute';
    canvas.style.pointerEvents = 'none';
  },

  clearPlaceholder(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    canvas.style.visibility = '';
    canvas.style.position = '';
    canvas.style.pointerEvents = '';
    canvas.closest('.cw, .cw-tall, .cw-treemap')?.querySelector('.chart-placeholder')?.remove();
  },

  getThemeColors() {
    const isDark = !document.documentElement.hasAttribute('data-theme') ||
                   document.documentElement.getAttribute('data-theme') === 'dark';
    return {
      bg: isDark ? '#1e293b' : '#ffffff',
      text: isDark ? '#94a3b8' : '#64748b',
      grid: isDark ? '#1e293b' : '#f1f5f9',
      crosshair: isDark ? '#475569' : '#cbd5e1',
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
      tooltipBg: isDark ? '#1e293b' : '#ffffff',
      tooltipBorder: isDark ? '#334155' : '#e2e8f0',
      tooltipText: isDark ? '#f8fafc' : '#0f172a',
      tooltipBody: isDark ? '#e2e8f0' : '#334155',
    };
  },

  /**
   * 通用 Chart.js 折線圖
   */
  drawLineChart(canvasId, series) {
    if (!this._chartJsReady()) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const maxLen = Math.max(...series.map(s => s.data.length));
    const labels = Array.from({ length: maxLen }, (_, j) => {
      const d = series[0].dates;
      if (d && j < d.length) return Utils.shortDate(d[j]);
      return j;
    });

    const colors = this.getThemeColors();
    const datasets = _chartSeries(series).map((s, i) => ({
      label: s.label,
      data: s.data,
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.1,
    }));

    new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: colors.text, font: { size: 10 } } },
          tooltip: {
            mode: 'index', intersect: false,
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
          },
        },
        scales: {
          x: { ticks: { color: colors.text, font: { size: 9 }, maxTicksLimit: 10 }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
        },
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
      },
    });
    this._scheduleResize(canvas);
  },

  /**
   * 通用 Chart.js 柱狀圖
   */
  drawBarChart(canvasId, data, labels, label) {
    if (!this._chartJsReady()) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = this.getThemeColors();
    const bgColors = data.map(v => v >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)');
    const bdColors = data.map(v => v >= 0 ? '#22c55e' : '#ef4444');

    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { labels, datasets: [{ label, data, borderColor: bdColors, backgroundColor: bgColors, borderWidth: 1 }] },
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
          x: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
        },
      },
    });
    this._scheduleResize(canvas);
  },

  /**
   * Chart.js K 線圖 (帶買賣信號標記) — 降級方案
   */
  drawKlineChart(canvasId, kline, signals, title) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !kline || !kline.length) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const data = kline.length > 200 ? kline.slice(-200) : kline;
    const labels = data.map(d => Utils.shortDate(d.date));
    const closes = data.map(d => d.close);
    const buyPoints = [], sellPoints = [];
    const dateIndex = {};
    data.forEach((d, i) => dateIndex[d.date] = i);

    (signals || []).forEach(s => {
      const idx = dateIndex[s.date];
      if (idx != null) {
        if (s.type === 'buy') buyPoints.push({ x: idx, y: s.price });
        else sellPoints.push({ x: idx, y: s.price });
      }
    });

    const colors = this.getThemeColors();
    const datasets = [
      { label: '收盤價', data: closes, borderColor: '#38bdf8', backgroundColor: 'transparent', borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
      { label: '買入', data: buyPoints, borderColor: 'transparent', backgroundColor: '#22c55e', pointRadius: 6, pointStyle: 'triangle', showLine: false },
      { label: '賣出', data: sellPoints, borderColor: 'transparent', backgroundColor: '#ef4444', pointRadius: 6, pointStyle: 'rectRot', showLine: false },
    ];

    new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: colors.text, font: { size: 10 } } },
          tooltip: {
            mode: 'index', intersect: false,
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
          },
          title: { display: !!title, text: title, color: colors.tooltipText, font: { size: 13 } },
        },
        scales: {
          x: { ticks: { color: colors.text, font: { size: 9 }, maxTicksLimit: 12 }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
        },
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
      },
    });
  },

  /**
   * TradingView Lightweight Charts — 專業 K 線圖 (蠟燭圖 + 成交量 + 信號標記)
   */
  drawLWKlineChart(containerId, klineData, signals, title) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    // Clean up existing chart
    if (this._lwCharts[containerId]) {
      this._lwCharts[containerId].remove();
      delete this._lwCharts[containerId];
    }

    if (!klineData || !klineData.length) {
      container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted)">暫無 K 線數據</div>';
      return;
    }

    if (typeof LightweightCharts === 'undefined') {
      container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted)">Lightweight Charts 未載入</div>';
      return;
    }

    const colors = this.getThemeColors();

    const chart = LightweightCharts.createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight || 400,
      layout: {
        background: { type: 'solid', color: colors.bg },
        textColor: colors.text,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: colors.crosshair, width: 1, style: 2 },
        horzLine: { color: colors.crosshair, width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: colors.grid,
      },
      timeScale: {
        borderColor: colors.grid,
        timeVisible: false,
      },
    });

    this._lwCharts[containerId] = chart;

    // 蠟燭圖系列
    const candleSeries = this._addCandlestickSeries(chart, {
      upColor: colors.upColor,
      downColor: colors.downColor,
      borderUpColor: colors.borderUpColor,
      borderDownColor: colors.borderDownColor,
      wickUpColor: colors.wickUpColor,
      wickDownColor: colors.wickDownColor,
    });

    const candleData = klineData.map(d => ({
      time: d.date,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    candleSeries.setData(candleData);

    // 成交量系列
    const volumeSeries = this._addHistogramSeries(chart, {
      color: '#38bdf8',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const volumeData = klineData.map(d => ({
      time: d.date,
      value: d.volume || 0,
      color: d.close >= d.open ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)',
    }));

    volumeSeries.setData(volumeData);

    // 買賣信號標記
    if (signals && signals.length) {
      const dateSet = new Set(klineData.map(d => d.date));
      const markers = signals
        .filter(s => dateSet.has(s.date))
        .map(s => ({
          time: s.date,
          position: s.type === 'buy' ? 'belowBar' : 'aboveBar',
          color: s.type === 'buy' ? '#22c55e' : '#ef4444',
          shape: s.type === 'buy' ? 'arrowUp' : 'arrowDown',
          text: s.type === 'buy' ? '買' : '賣',
        }))
        .sort((a, b) => a.time.localeCompare(b.time));

      if (markers.length) {
        try {
          if (typeof candleSeries.setMarkers === 'function') {
            candleSeries.setMarkers(markers);
          } else if (typeof LightweightCharts.createSeriesMarkers === 'function') {
            LightweightCharts.createSeriesMarkers(candleSeries, markers);
          }
        } catch (e) { /* v4/v5 API 差異 */ }
      }
    }

    chart.timeScale().fitContent();

    // 響應式調整
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        chart.applyOptions({
          width: entry.contentRect.width,
          height: entry.contentRect.height || 400,
        });
      }
    });
    ro.observe(container);
    container._resizeObserver = ro;

    return chart;
  },

  /**
   * 首頁指數迷你 K 線（Lightweight Charts，含成交量）
   */
  drawIndexKlineChart(containerId, klineData) {
    const container = document.getElementById(containerId);
    if (!container) return null;
    container.innerHTML = '';

    if (this._lwCharts[containerId]) {
      this._lwCharts[containerId].remove();
      delete this._lwCharts[containerId];
    }

    if (!klineData || !klineData.length) {
      container.innerHTML = '<div class="chart-placeholder">暫無 K 線數據</div>';
      return null;
    }

    if (!this._lwReady()) {
      container.innerHTML = '<div class="chart-placeholder">圖表庫載入中…</div>';
      return null;
    }

    const colors = this.getThemeColors();
    const chart = LightweightCharts.createChart(container, {
      width: container.clientWidth || 280,
      height: container.clientHeight || 200,
      layout: {
        background: { type: 'solid', color: colors.bg },
        textColor: colors.text,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: colors.crosshair, width: 1, style: 2, labelBackgroundColor: '#334155' },
        horzLine: { color: colors.crosshair, width: 1, style: 2, labelBackgroundColor: '#334155' },
      },
      rightPriceScale: {
        borderColor: colors.grid,
        scaleMargins: { top: 0.08, bottom: 0.22 },
      },
      timeScale: {
        borderColor: colors.grid,
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: { vertTouchDrag: false },
    });

    this._lwCharts[containerId] = chart;

    const candleSeries = this._addCandlestickSeries(chart, {
      upColor: colors.upColor,
      downColor: colors.downColor,
      borderUpColor: colors.borderUpColor,
      borderDownColor: colors.borderDownColor,
      wickUpColor: colors.wickUpColor,
      wickDownColor: colors.wickDownColor,
    });

    const candleData = klineData.map(d => ({
      time: d.date,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));
    candleSeries.setData(candleData);

    const volumeSeries = this._addHistogramSeries(chart, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    volumeSeries.setData(klineData.map(d => ({
      time: d.date,
      value: d.volume || 0,
      color: d.close >= d.open ? 'rgba(34,197,94,0.35)' : 'rgba(239,68,68,0.35)',
    })));

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        chart.applyOptions({
          width: entry.contentRect.width,
          height: entry.contentRect.height || 200,
        });
      }
    });
    ro.observe(container);
    container._resizeObserver = ro;

    return chart;
  },

  destroyIndexCharts(prefix = 'idx-chart-') {
    Object.keys(this._lwCharts).forEach(id => {
      if (!id.startsWith(prefix)) return;
      try {
        this._lwCharts[id].remove();
      } catch (e) { /* ignore */ }
      delete this._lwCharts[id];
    });
  },

  /**
   * 首頁 TradingView 監控股迷你圖（Lightweight Charts 線圖）
   */
  drawTVSparklineChart(containerId, dates, prices, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return null;
    container.innerHTML = '';

    if (this._lwCharts[containerId]) {
      this._lwCharts[containerId].remove();
      delete this._lwCharts[containerId];
    }

    if (!dates?.length || !prices?.length || dates.length !== prices.length) {
      container.innerHTML = '<div class="chart-placeholder">暫無走勢數據</div>';
      return null;
    }

    if (!this._lwReady()) {
      container.innerHTML = '<div class="chart-placeholder">圖表庫載入中…</div>';
      return null;
    }

    const colors = this.getThemeColors();
    const up = options.changePct == null ? prices[prices.length - 1] >= prices[0] : options.changePct >= 0;
    const lineColor = up ? colors.upColor : colors.downColor;
    const chart = LightweightCharts.createChart(container, {
      width: container.clientWidth || 260,
      height: container.clientHeight || 150,
      layout: {
        background: { type: 'solid', color: colors.bg },
        textColor: colors.text,
      },
      grid: {
        vertLines: { color: 'transparent' },
        horzLines: { color: colors.grid },
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: colors.crosshair, width: 1, style: 2 },
        horzLine: { color: colors.crosshair, width: 1, style: 2 },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.15, bottom: 0.12 },
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: { vertTouchDrag: false },
    });

    this._lwCharts[containerId] = chart;
    const line = this._addLineSeries(chart, {
      color: lineColor,
      lineWidth: 2,
      crosshairMarkerVisible: true,
      lastValueVisible: true,
      priceLineVisible: false,
    });
    line.setData(dates.map((date, i) => ({
      time: date,
      value: Number(prices[i]),
    })).filter(p => Number.isFinite(p.value)));
    chart.timeScale().fitContent();

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        chart.applyOptions({
          width: entry.contentRect.width,
          height: entry.contentRect.height || 150,
        });
      }
    });
    ro.observe(container);
    container._resizeObserver = ro;
    return chart;
  },

  /**
   * 熱力圖 (Canvas 2D)
   */
  drawHeatmap(canvasId, result) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const { x_values: xVals, y_values: yVals, matrix, param_x, param_y, best_params } = result;

    const cols = xVals.length, rows = yVals.length;
    const cellW = Math.max(50, Math.min(80, 560 / cols));
    const cellH = Math.max(40, Math.min(60, 400 / rows));
    const padL = 60, padT = 30, padR = 20, padB = 40;

    canvas.width = padL + cols * cellW + padR;
    canvas.height = padT + rows * cellH + padB;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 找 min/max
    let mn = Infinity, mx = -Infinity;
    matrix.forEach(row => row.forEach(v => {
      if (v > -9999) { mn = Math.min(mn, v); mx = Math.max(mx, v); }
    }));
    if (mn === Infinity) { mn = 0; mx = 1; }
    const range = mx - mn || 1;

    const isDark = !document.documentElement.hasAttribute('data-theme') ||
                   document.documentElement.getAttribute('data-theme') === 'dark';

    // 畫格子
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const v = matrix[y][x];
        const t = v <= -9999 ? 0 : (v - mn) / range;

        if (v <= -9999) {
          ctx.fillStyle = isDark ? '#1e293b' : '#f1f5f9';
        } else {
          const r = Math.round(239 * t + 15 * (1 - t));
          const g = Math.round(68 * t + 23 * (1 - t));
          const b = Math.round(68 * t + 42 * (1 - t));
          ctx.fillStyle = `rgb(${r},${g},${b})`;
        }

        ctx.fillRect(padL + x * cellW, padT + y * cellH, cellW - 1, cellH - 1);

        ctx.fillStyle = isDark ? '#e2e8f0' : '#0f172a';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        if (v > -9999) {
          ctx.fillText(v.toFixed(2), padL + x * cellW + cellW / 2, padT + y * cellH + cellH / 2);
        }
      }
    }

    // X 標籤
    ctx.fillStyle = isDark ? '#94a3b8' : '#64748b';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    xVals.forEach((v, i) => ctx.fillText(v, padL + i * cellW + cellW / 2, padT + rows * cellH + 15));
    ctx.fillText(param_x, padL + cols * cellW / 2, padT + rows * cellH + 32);

    // Y 標籤
    ctx.textAlign = 'right';
    yVals.forEach((v, i) => ctx.fillText(v, padL - 8, padT + i * cellH + cellH / 2));
    ctx.save();
    ctx.translate(12, padT + rows * cellH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.fillText(param_y, 0, 0);
    ctx.restore();

    // 高亮最佳
    if (best_params) {
      const bx = xVals.indexOf(best_params[param_x]);
      const by = yVals.indexOf(best_params[param_y]);
      if (bx >= 0 && by >= 0) {
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 3;
        ctx.strokeRect(padL + bx * cellW, padT + by * cellH, cellW - 1, cellH - 1);
      }
    }
  },

  /**
   * Chart.js 雷達圖
   */
  drawRadarChart(canvasId, labels, datasets) {
    if (!this._chartJsReady()) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = this.getThemeColors();
    const ds = _chartSeries(datasets).map((s, i) => ({
      label: s.label,
      data: s.data,
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + '25',
      borderWidth: 1.5,
      pointRadius: 2,
      pointBackgroundColor: CHART_COLORS[i % CHART_COLORS.length],
    }));

    new Chart(canvas.getContext('2d'), {
      type: 'radar',
      data: { labels, datasets: ds },
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
          r: {
            angleLines: { color: colors.grid },
            grid: { color: colors.grid },
            pointLabels: { color: colors.text, font: { size: 10 } },
            ticks: { color: colors.text, font: { size: 8 }, backdropColor: 'transparent' },
          },
        },
      },
    });
    this._scheduleResize(canvas);
  },

  /**
   * Chart.js 甜甜圈圖
   */
  drawDoughnutChart(canvasId, labels, data, title) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = this.getThemeColors();
    const bgColors = data.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);

    new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: bgColors,
          borderColor: colors.bg,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '55%',
        plugins: {
          legend: { position: 'right', labels: { color: colors.text, font: { size: 10 }, padding: 8 } },
          tooltip: {
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
          },
          title: { display: !!title, text: title, color: colors.tooltipText, font: { size: 13 } },
        },
      },
    });
  },

  /**
   * Chart.js 水平條形圖
   */
  drawHorizontalBarChart(canvasId, labels, data, label, opts = {}) {
    if (!this._chartJsReady()) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = this.getThemeColors();
    const suffix = opts.suffix != null ? opts.suffix : '%';
    const fmt = opts.formatValue || (v => Number(v).toFixed(2) + suffix);
    const bgColors = data.map(v => v >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)');
    const bdColors = data.map(v => v >= 0 ? '#22c55e' : '#ef4444');
    const tooltips = opts.tooltips || null;

    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { labels, datasets: [{ label: _chartLabel(label), data, borderColor: bdColors, backgroundColor: bgColors, borderWidth: 1 }] },
      options: {
        indexAxis: 'y',
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
            callbacks: tooltips ? {
              afterLabel: ctx => tooltips[ctx.dataIndex] || '',
            } : undefined,
          },
        },
        scales: {
          x: { ticks: { color: colors.text, font: { size: 9 }, callback: v => fmt(v) }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.text, font: { size: 10 }, maxRotation: 0 }, grid: { display: false } },
        },
      },
    });
    this._scheduleResize(canvas);
  },

  /**
   * Chart.js 面積圖（回撤水下圖）
   */
  drawAreaChart(canvasId, series) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const maxLen = Math.max(...series.map(s => s.data.length));
    const labels = Array.from({ length: maxLen }, (_, j) => {
      const d = series[0].dates;
      if (d && j < d.length) return Utils.shortDate(d[j]);
      return j;
    });

    const colors = this.getThemeColors();
    const datasets = _chartSeries(series).map((s, i) => {
      const color = s.color || CHART_COLORS[i % CHART_COLORS.length];
      return {
        label: s.label,
        data: s.data,
        borderColor: color,
        backgroundColor: color + '20',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.1,
        fill: s.fill !== undefined ? s.fill : true,
      };
    });

    new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: colors.text, font: { size: 10 } } },
          tooltip: {
            mode: 'index', intersect: false,
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
          },
        },
        scales: {
          x: { ticks: { color: colors.text, font: { size: 9 }, maxTicksLimit: 10 }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
        },
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
      },
    });
  },

  /**
   * 月度收益熱力圖 (Canvas 2D)
   * @param {string} canvasId
   * @param {Array} monthlyReturns - [{year, month(1-12), return_pct}]
   */
  drawMonthlyHeatmap(canvasId, monthlyReturns) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (!monthlyReturns || !monthlyReturns.length) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#64748b';
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('暫無月度收益數據', canvas.width / 2, canvas.height / 2);
      return;
    }

    // 按年分組
    const yearMap = {};
    monthlyReturns.forEach(m => {
      if (!yearMap[m.year]) yearMap[m.year] = {};
      yearMap[m.year][m.month] = m.return_pct;
    });
    const years = Object.keys(yearMap).sort();
    const months = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
    const monthLabels = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

    const cellW = 52, cellH = 32;
    const padL = 50, padT = 28, padR = 16, padB = 16;

    canvas.width = padL + months.length * cellW + padR;
    canvas.height = padT + years.length * cellH + padB;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const isDark = !document.documentElement.hasAttribute('data-theme') ||
                   document.documentElement.getAttribute('data-theme') === 'dark';

    // 找 min/max
    let mn = Infinity, mx = -Infinity;
    monthlyReturns.forEach(m => { mn = Math.min(mn, m.return_pct); mx = Math.max(mx, m.return_pct); });
    const absMax = Math.max(Math.abs(mn), Math.abs(mx)) || 1;

    const getColor = (v) => {
      if (v == null) return isDark ? '#1e293b' : '#f1f5f9';
      const t = (v + absMax) / (2 * absMax); // 0~1
      if (v >= 0) {
        const r = Math.round(34 + (1 - t) * 0);
        const g = Math.round(197 - (1 - t) * 80);
        const b = Math.round(94 - (1 - t) * 40);
        return `rgb(${r},${g},${b})`;
      } else {
        const r = Math.round(239 - t * 100);
        const g = Math.round(68 + t * 20);
        const b = Math.round(68 + t * 20);
        return `rgb(${r},${g},${b})`;
      }
    };

    // 畫格子
    for (let y = 0; y < years.length; y++) {
      for (let x = 0; x < months.length; x++) {
        const v = yearMap[years[y]][months[x]];
        ctx.fillStyle = getColor(v);
        ctx.fillRect(padL + x * cellW, padT + y * cellH, cellW - 1, cellH - 1);

        ctx.fillStyle = isDark ? '#e2e8f0' : '#0f172a';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        if (v != null) {
          ctx.fillText(v.toFixed(1) + '%', padL + x * cellW + cellW / 2, padT + y * cellH + cellH / 2);
        }
      }
    }

    // X 標籤
    ctx.fillStyle = isDark ? '#94a3b8' : '#64748b';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    monthLabels.forEach((v, i) => ctx.fillText(v, padL + i * cellW + cellW / 2, padT - 8));

    // Y 標籤
    ctx.textAlign = 'right';
    years.forEach((v, i) => ctx.fillText(v, padL - 8, padT + i * cellH + cellH / 2));
  },

  /**
   * Chart.js 時間線圖（散點圖模擬）
   */
  drawTimelineChart(canvasId, events, options) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = this.getThemeColors();
    const opts = Object.assign({ title: '', yLabel: '信號', xLabel: '日期' }, options);

    const buyData = events.filter(e => e.type === 'buy').map(e => ({ x: e.date, y: e.y || 0.5 }));
    const sellData = events.filter(e => e.type === 'sell').map(e => ({ x: e.date, y: e.y || 0.5 }));

    new Chart(canvas.getContext('2d'), {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: '買入信號',
            data: buyData,
            backgroundColor: '#22c55e',
            pointRadius: 5,
            pointStyle: 'triangle',
          },
          {
            label: '賣出信號',
            data: sellData,
            backgroundColor: '#ef4444',
            pointRadius: 5,
            pointStyle: 'rectRot',
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
          title: { display: !!opts.title, text: opts.title, color: colors.tooltipText, font: { size: 13 } },
        },
        scales: {
          x: {
            type: 'category',
            ticks: { color: colors.text, font: { size: 9 }, maxTicksLimit: 15 },
            grid: { color: colors.grid },
          },
          y: {
            display: false,
            min: 0,
            max: 1,
          },
        },
      },
    });
  },

  /**
   * 主力淨流入水平條形圖（金額，元 → 自動格式化）
   */
  drawMoneyHorizontalBar(canvasId, labels, values, label = '主力淨流入') {
    if (!this._chartJsReady()) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = this.getThemeColors();
    const yi = values.map(v => (Number(v) || 0) / 1e8);
    const bgColors = yi.map(v => v >= 0 ? 'rgba(34,197,94,0.65)' : 'rgba(239,68,68,0.65)');
    const bdColors = yi.map(v => v >= 0 ? '#22c55e' : '#ef4444');

    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { labels, datasets: [{ label, data: yi, borderColor: bdColors, backgroundColor: bgColors, borderWidth: 1 }] },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => {
                const raw = values[ctx.dataIndex];
                return `${label}: ${Utils.formatLargeNum(raw)}`;
              },
            },
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
          },
        },
        scales: {
          x: {
            ticks: {
              color: colors.text,
              font: { size: 9 },
              callback: v => `${v.toFixed(2)}亿`,
            },
            grid: { color: colors.grid },
          },
          y: { ticks: { color: colors.text, font: { size: 10 } }, grid: { display: false } },
        },
      },
    });
    this._scheduleResize(canvas);
  },

  /**
   * 漲跌幅 × 資金流向散點圖
   * points: [{ name, x: change_pct, y: main_net }]
   */
  drawChangeFlowScatter(canvasId, points) {
    if (!this._chartJsReady()) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas || !points?.length) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = this.getThemeColors();
    const data = points.map(p => ({
      x: Number(p.x) || 0,
      y: (Number(p.y) || 0) / 1e8,
      name: p.name || '',
    }));
    const maxAbs = Math.max(...data.map(d => Math.abs(d.y)), 0.01);

    new Chart(canvas.getContext('2d'), {
      type: 'scatter',
      data: {
        datasets: [{
          label: '板塊',
          data,
          pointRadius: data.map(d => 4 + Math.min(10, (Math.abs(d.y) / maxAbs) * 8)),
          pointBackgroundColor: data.map(d =>
            d.x >= 0 ? (d.y >= 0 ? 'rgba(34,197,94,0.75)' : 'rgba(250,204,21,0.75)')
              : (d.y >= 0 ? 'rgba(56,189,248,0.75)' : 'rgba(239,68,68,0.75)')),
          pointBorderColor: 'rgba(15,23,42,0.4)',
          pointBorderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => {
                const p = points[ctx.dataIndex];
                return [
                  p.name,
                  `漲跌: ${(p.x || 0).toFixed(2)}%`,
                  `主力: ${Utils.formatLargeNum(p.y)}`,
                ];
              },
            },
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
          },
        },
        scales: {
          x: {
            title: { display: true, text: '漲跌幅 (%)', color: colors.text, font: { size: 10 } },
            ticks: { color: colors.text, font: { size: 9 } },
            grid: { color: colors.grid },
          },
          y: {
            title: { display: true, text: '主力淨流入 (億)', color: colors.text, font: { size: 10 } },
            ticks: { color: colors.text, font: { size: 9 } },
            grid: { color: colors.grid },
          },
        },
      },
    });
    this._scheduleResize(canvas);
  },

  /**
   * 資金流向堆疊柱狀（主力/超大/大/中/小單）
   */
  drawFlowStackedBar(canvasId, flows) {
    if (!this._chartJsReady() || !flows?.length) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = this.getThemeColors();
    const labels = flows.map(f => Utils.shortDate(f.date || ''));
    const toYi = v => (Number(v) || 0) / 1e8;
    const keys = [
      { key: 'main_net', label: '主力', color: '#38bdf8' },
      { key: 'super_net', label: '超大單', color: '#a78bfa' },
      { key: 'big_net', label: '大單', color: '#22c55e' },
      { key: 'mid_net', label: '中單', color: '#f59e0b' },
      { key: 'small_net', label: '小單', color: '#94a3b8' },
    ];

    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: keys.map(k => ({
          label: k.label,
          data: flows.map(f => toYi(f[k.key])),
          backgroundColor: k.color + '99',
          borderColor: k.color,
          borderWidth: 1,
          stack: 'flow',
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: colors.text, font: { size: 9 } } },
          tooltip: {
            mode: 'index',
            intersect: false,
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
          },
        },
        scales: {
          x: { stacked: true, ticks: { color: colors.text, font: { size: 8 }, maxTicksLimit: 12 }, grid: { color: colors.grid } },
          y: {
            stacked: true,
            ticks: { color: colors.text, font: { size: 9 }, callback: v => `${v.toFixed(2)}亿` },
            grid: { color: colors.grid },
          },
        },
      },
    });
    this._scheduleResize(canvas);
  },

  _worstTreemapRatio(row, side) {
    if (!row.length || side <= 0) return Infinity;
    const sum = row.reduce((s, r) => s + r.area, 0);
    if (sum <= 0) return Infinity;
    const maxA = Math.max(...row.map(r => r.area));
    const minA = Math.min(...row.map(r => r.area));
    const len = sum / side;
    const w = side;
    return Math.max((len * len * maxA) / (w * w), (w * w) / (len * len * minA));
  },

  _treemapWeight(item) {
    const amount = Number(item.amount) || 0;
    if (amount > 0) return amount;
    const change = Math.abs(Number(item.change_pct) || 0);
    if (change > 0) return change + 0.5;
    const count = Number(item.stock_count)
      || (Number(item.rise_count) || 0) + (Number(item.fall_count) || 0);
    if (count > 0) return count;
    return 1;
  },

  _squarifyTreemap(items, totalValue, x, y, w, h) {
    const rects = [];
    if (!items.length || totalValue <= 0) return rects;
    const areas = items.map(it => (this._treemapWeight(it) / totalValue) * w * h);
    let remaining = areas.map((area, i) => ({ area, index: i }));
    let cx = x; let cy = y; let cw = w; let ch = h;

    while (remaining.length > 0) {
      const isWide = cw >= ch;
      const side = isWide ? ch : cw;
      let row = [remaining[0]];
      let bestRatio = this._worstTreemapRatio(row, side);
      let bestRow = [...row];
      for (let i = 1; i < remaining.length; i++) {
        row.push(remaining[i]);
        const ratio = this._worstTreemapRatio(row, side);
        if (ratio <= bestRatio) {
          bestRatio = ratio;
          bestRow = [...row];
        } else break;
      }
      const rowArea = bestRow.reduce((s, r) => s + r.area, 0);
      const rowLen = rowArea / side;
      let offset = 0;
      bestRow.forEach(r => {
        const itemLen = r.area / rowLen;
        if (isWide) rects[r.index] = { x: cx, y: cy + offset, w: rowLen, h: itemLen };
        else rects[r.index] = { x: cx + offset, y: cy, w: itemLen, h: rowLen };
        offset += itemLen;
      });
      if (isWide) { cx += rowLen; cw -= rowLen; }
      else { cy += rowLen; ch -= rowLen; }
      remaining = remaining.slice(bestRow.length);
    }
    return rects;
  },

  /**
   * 板塊 Treemap 熱力圖（面積=成交額或漲跌幅兜底，顏色=漲跌幅）
   */
  drawSectorTreemap(canvasId, sectors, height = 320) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const valid = (sectors || []).filter(s => s && s.name);
    canvas._treemapSectors = valid;
    canvas._treemapHeight = height;

    const wrap = canvas.parentElement;
    const W = Math.max(wrap?.clientWidth || 0, 320);
    const H = height;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    this.clearPlaceholder(canvasId);

    if (!valid.length) {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('暫無板塊數據', W / 2, H / 2);
      canvas._treemapRects = [];
      return;
    }

    valid.sort((a, b) => this._treemapWeight(b) - this._treemapWeight(a));
    const totalWeight = valid.reduce((s, it) => s + this._treemapWeight(it), 0);
    const rects = this._squarifyTreemap(valid, totalWeight, 2, 2, W - 4, H - 4);
    const drawn = [];

    valid.forEach((s, i) => {
      const rect = rects[i];
      if (!rect || rect.w < 1 || rect.h < 1) return;
      const changePct = Number(s.change_pct) || 0;
      const intensity = Math.min(Math.abs(changePct) / 5, 1);
      let r; let g; let b;
      if (changePct >= 0) {
        r = Math.round(34 + (220 - 34) * intensity);
        g = Math.round(197 - 100 * intensity);
        b = Math.round(94 - 60 * intensity);
      } else {
        r = Math.round(239 - 100 * intensity);
        g = Math.round(68 + 50 * (1 - intensity));
        b = Math.round(68 + 50 * (1 - intensity));
      }
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
      ctx.strokeStyle = 'rgba(0,0,0,0.2)';
      ctx.lineWidth = 1;
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      if (rect.w > 36 && rect.h > 22) {
        ctx.fillStyle = '#fff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const fontSize = Math.max(8, Math.min(12, rect.w / 7));
        ctx.font = `bold ${fontSize}px sans-serif`;
        const nameText = s.name.length > 5 ? `${s.name.slice(0, 5)}…` : s.name;
        ctx.fillText(nameText, rect.x + rect.w / 2, rect.y + rect.h / 2 - 6);
        ctx.font = `${fontSize - 1}px sans-serif`;
        ctx.fillText(
          typeof Utils !== 'undefined' ? Utils.formatPct(changePct) : `${changePct.toFixed(2)}%`,
          rect.x + rect.w / 2,
          rect.y + rect.h / 2 + 8,
        );
      }
      const hit = { ...rect, sectorName: s.name, changePct };
      drawn.push(hit);
    });

    canvas._treemapRects = drawn;
    if (!canvas._treemapBound) {
      canvas._treemapBound = true;
      canvas.onclick = (e) => {
        const box = canvas.getBoundingClientRect();
        const x = e.clientX - box.left;
        const y = e.clientY - box.top;
        for (const r of canvas._treemapRects || []) {
          if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
            if (typeof Data !== 'undefined' && Data.showSectorDetail) {
              Data.showSectorDetail(r.sectorName);
            }
            break;
          }
        }
      };
      canvas.onmousemove = (e) => {
        const box = canvas.getBoundingClientRect();
        const x = e.clientX - box.left;
        const y = e.clientY - box.top;
        let title = '';
        for (const r of canvas._treemapRects || []) {
          if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
            title = `${r.sectorName}: ${
              typeof Utils !== 'undefined' ? Utils.formatPct(r.changePct) : r.changePct
            }`;
            break;
          }
        }
        canvas.title = title;
      };
    }
  },

  /**
   * 清理所有 Lightweight Charts 實例
   */
  disposeAll() {
    for (const [id, chart] of Object.entries(this._lwCharts)) {
      try {
        chart.remove();
        const container = document.getElementById(id);
        if (container && container._resizeObserver) {
          container._resizeObserver.disconnect();
        }
      } catch {}
    }
    this._lwCharts = {};
  },

  /**
   * 主題變更時刷新所有圖表
   */
  refreshAll() {
    const colors = this.getThemeColors();

    // 更新所有已存在的 Chart.js 實例配色
    try {
      const instances = Chart.instances ? Object.values(Chart.instances) : [];
      instances.forEach(chart => {
        if (!chart || !chart.options) return;
        try {
          // 更新 legend 和 tooltip 顏色
          if (chart.options.plugins?.legend?.labels) {
            chart.options.plugins.legend.labels.color = colors.text;
          }
          if (chart.options.plugins?.tooltip) {
            chart.options.plugins.tooltip.backgroundColor = colors.tooltipBg;
            chart.options.plugins.tooltip.borderColor = colors.tooltipBorder;
            chart.options.plugins.tooltip.titleColor = colors.tooltipText;
            chart.options.plugins.tooltip.bodyColor = colors.tooltipBody;
          }
          // 更新軸顏色
          ['x', 'y'].forEach(axis => {
            if (chart.options.scales?.[axis]) {
              chart.options.scales[axis].ticks.color = colors.text;
              chart.options.scales[axis].grid.color = colors.grid;
            }
          });
          chart.update('none');
        } catch {}
      });
    } catch {}

    // Lightweight Charts 需要重建（因為背景色無法動態更新）
    for (const [id, chart] of Object.entries(this._lwCharts)) {
      try {
        chart.applyOptions({
          layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text },
          grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
          crosshair: {
            vertLine: { color: colors.crosshair },
            horzLine: { color: colors.crosshair },
          },
          rightPriceScale: { borderColor: colors.grid },
          timeScale: { borderColor: colors.grid },
        });
      } catch {}
    }
  },
};

window.Charts = Charts;
