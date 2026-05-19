/**
 * charts.js — 圖表函數 (Chart.js + Lightweight Charts)
 */

const CHART_COLORS = ['#38bdf8', '#22c55e', '#f59e0b', '#ef4444', '#a78bfa', '#ec4899', '#06b6d4', '#84cc16'];

const Charts = {
  _lwCharts: {},

  _chartJsReady() {
    return typeof Chart !== 'undefined';
  },

  _lwReady() {
    return typeof LightweightCharts !== 'undefined';
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
    if (!this._chartJsReady()) return;
    const root = typeof tabOrId === 'string' ? document.getElementById(tabOrId) : tabOrId;
    if (!root) return;
    root.querySelectorAll('canvas').forEach(canvas => {
      const chart = Chart.getChart(canvas);
      if (chart) chart.resize();
    });
  },

  setPlaceholder(canvasId, message) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const wrap = canvas.closest('.cw, .cw-tall');
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
    canvas.closest('.cw, .cw-tall')?.querySelector('.chart-placeholder')?.remove();
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
    const datasets = series.map((s, i) => ({
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
    const candleSeries = chart.addCandlestickSeries({
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
    const volumeSeries = chart.addHistogramSeries({
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
          text: s.type === 'buy' ? 'B' : 'S',
        }))
        .sort((a, b) => a.time.localeCompare(b.time));

      if (markers.length) {
        candleSeries.setMarkers(markers);
      }
    }

    // 自動縮放
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
    const ds = datasets.map((s, i) => ({
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
  drawHorizontalBarChart(canvasId, labels, data, label) {
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
          },
        },
        scales: {
          x: { ticks: { color: colors.text, font: { size: 9 }, callback: v => v.toFixed(2) + '%' }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.text, font: { size: 10 } }, grid: { display: false } },
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
    const datasets = series.map((s, i) => {
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
