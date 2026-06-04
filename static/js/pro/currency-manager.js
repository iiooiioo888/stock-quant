/* global Api */

/**
 * 多幣種結算 — 儀表盤切換器、Intl 格式化、防抖請求
 */
(() => {
  const SUPPORTED = ['MOP', 'HKD', 'CNY', 'USD'];
  const LABELS = { MOP: 'MOP 🇲🇴', HKD: 'HKD 🇭🇰', CNY: 'CNY 🇨🇳', USD: 'USD 🇺🇸' };
  const LOCALE = { MOP: 'zh-MO', HKD: 'zh-HK', CNY: 'zh-CN', USD: 'en-US' };

  let debounceTimer = null;
  let lastSummary = null;

  function readStored() {
    try {
      const p = window.StockQPro?.Prefs?.get?.('preferredCurrency');
      if (p && SUPPORTED.includes(String(p).toUpperCase())) return String(p).toUpperCase();
    } catch (_) {}
    return (localStorage.getItem('pref_currency') || 'MOP').toUpperCase();
  }

  function store(curr) {
    localStorage.setItem('pref_currency', curr);
    try {
      window.StockQPro?.Prefs?.save?.({ preferredCurrency: curr });
    } catch (_) {}
  }

  const CurrencyManager = {
    current: readStored(),
    lastSummary: null,

    init(hostId = 'currency-toggle') {
      const host = document.getElementById(hostId);
      if (!host || host.dataset.bound === '1') return;
      host.dataset.bound = '1';
      host.classList.add('currency-toggle');
      host.innerHTML = SUPPORTED.map(
        (c) => `<button type="button" class="currency-btn" data-c="${c}">${LABELS[c]}</button>`,
      ).join('')
        + '<span class="fx-timestamp">匯率更新至: <time id="fx-time">--:--</time></span>'
        + '<p class="fx-disclaimer">即時匯率僅供參考，結算以券商為準</p>';
      host.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-c]');
        if (!btn) return;
        this.switch(btn.getAttribute('data-c'));
      });
      this.render();
      this.loadData();
      window.addEventListener('stockq:auth-changed', () => this.loadData());
    },

    render() {
      document.querySelectorAll('.currency-btn').forEach((btn) => {
        btn.classList.toggle('active', btn.getAttribute('data-c') === this.current);
      });
    },

    format(value, currency = null) {
      const c = (currency || this.current || 'MOP').toUpperCase();
      const loc = LOCALE[c] || 'zh-MO';
      const n = Number(value);
      if (!Number.isFinite(n)) return '--';
      try {
        return new Intl.NumberFormat(loc, {
          style: 'currency',
          currency: c,
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(n);
      } catch (_) {
        return `${c} ${n.toFixed(2)}`;
      }
    },

    switch(curr) {
      const c = String(curr || '').toUpperCase();
      if (!SUPPORTED.includes(c) || c === this.current) return;
      this.current = c;
      store(c);
      this.render();
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => this.loadData(), 300);
      Api.put?.('/api/user/preferred-currency', { preferred_currency: c }).catch(() => {});
    },

    async loadData() {
      const summaryEl = document.getElementById('portfolio-total-value');
      const pnlEl = document.getElementById('portfolio-daily-pnl');
      const allocEl = document.getElementById('portfolio-allocation');
      const fxTime = document.getElementById('fx-time');
      try {
        if (!(typeof Api !== 'undefined' && Api._token)) return;
        const data = await Api.get(`/api/portfolio/summary?currency=${this.current}`, { silent: true });
        if (!data?.success) return;
        this.lastSummary = data;
        lastSummary = data;
        if (summaryEl) summaryEl.textContent = this.format(data.total_value);
        if (pnlEl) {
          const pnl = Number(data.daily_pnl);
          pnlEl.textContent = `${pnl >= 0 ? '+' : ''}${this.format(pnl)}`;
          pnlEl.classList.toggle('is-up', pnl >= 0);
          pnlEl.classList.toggle('is-down', pnl < 0);
        }
        if (allocEl && data.allocation) {
          allocEl.innerHTML = Object.entries(data.allocation)
            .map(([k, v]) => `<span class="alloc-pill"><b>${k}</b> ${v}%</span>`)
            .join('');
        }
        if (fxTime && data.fx_updated) {
          fxTime.textContent = new Date(data.fx_updated).toLocaleTimeString('zh-TW', {
            hour: '2-digit',
            minute: '2-digit',
          });
        }
        window.dispatchEvent(new CustomEvent('portfolio:currencyChange', { detail: data }));
        this._loadTrend();
      } catch (err) {
        if (summaryEl) summaryEl.textContent = '--';
        console.warn('portfolio summary', err);
      }
    },

    _renderTrendChart(chartHost, series, replace) {
      if (!series.length || typeof echarts === 'undefined') return null;
      let chart = echarts.getInstanceByDom(chartHost);
      if (!chart) chart = echarts.init(chartHost, null, { renderer: 'canvas' });
      chart.setOption({
        grid: { left: 48, right: 16, top: 24, bottom: 28 },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: series.map((x) => x.date) },
        yAxis: { type: 'value', scale: true },
        series: [{
          type: 'line',
          smooth: true,
          data: series.map((x) => x.value),
          areaStyle: { opacity: 0.12 },
          lineStyle: { width: 2, color: 'var(--ac)' },
          itemStyle: { color: 'var(--ac)' },
        }],
      }, replace);
      return chart;
    },

    async _loadTrend() {
      const chartHost = document.getElementById('portfolio-trend-chart');
      if (!chartHost) return;
      chartHost.setAttribute('aria-busy', 'true');
      try {
        const days = Number(window.StockQPro?.Prefs?.get?.('chartDays')) || 90;
        const q = `currency=${encodeURIComponent(this.current)}&days=${days}`;
        const stream = window.StockQPro?.FetchStream;
        if (stream?.fetchStream) {
          const series = [];
          await stream.fetchStream(
            `/api/portfolio/trend/stream?${q}`,
            (chunk) => {
              if (Array.isArray(chunk)) series.push(...chunk);
              if (series.length) this._renderTrendChart(chartHost, series, series.length <= 50);
            },
          );
          if (series.length) this._renderTrendChart(chartHost, series, true);
          return;
        }
        const data = await Api.get(`/api/portfolio/trend?${q}`, { silent: true });
        const series = data?.series || [];
        this._renderTrendChart(chartHost, series, true);
      } catch (e) {
        console.warn('portfolio trend', e);
      } finally {
        chartHost.removeAttribute('aria-busy');
      }
    },
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.CurrencyManager = CurrencyManager;

  window.addEventListener('portfolio:currencyChange', (ev) => {
    lastSummary = ev.detail;
  });
})();
