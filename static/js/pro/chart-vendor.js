/* global echarts, Chart, LightweightCharts */

/**
 * 圖表庫按需載入（避免首屏同步拉取 ECharts + Chart.js + Lightweight Charts）
 */
(() => {
  const V = 'stockq-chart-v2';
  const _pending = {};

  function scriptAlreadyLoaded(match) {
    return Array.from(document.scripts).some((s) => s.src && s.src.includes(match));
  }

  function loadScript(src) {
    const base = String(src || '').split('?')[0];
    const url = `${base}?v=${encodeURIComponent(V)}`;
    if (_pending[url]) return _pending[url];

    const key = src.replace(/\?.*$/, '');
    if (key.includes('echarts') && typeof echarts !== 'undefined') return Promise.resolve();
    if (key.includes('chart.js') && typeof Chart !== 'undefined') return Promise.resolve();
    if (key.includes('lightweight-charts') && typeof LightweightCharts !== 'undefined') {
      return Promise.resolve();
    }
    if (key.includes('anime') && typeof window.anime === 'function') return Promise.resolve();
    if (scriptAlreadyLoaded(key)) return Promise.resolve();

    const run = () => new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = url;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error(`chart vendor load failed: ${url}`));
      document.head.appendChild(s);
    });
    const SL = window.StockQPro?.StreamLoader;
    _pending[url] = SL ? SL.enqueue(run, 1) : run();
    return _pending[url];
  }

  async function ensureEcharts() {
    if (typeof echarts !== 'undefined') return echarts;
    await loadScript('/static/vendor/echarts.min.js');
    return echarts;
  }

  async function ensureChartJs() {
    if (typeof Chart !== 'undefined') return Chart;
    await loadScript('/static/vendor/chart.umd.min.js');
    return Chart;
  }

  async function ensureLightweightCharts() {
    if (typeof LightweightCharts !== 'undefined') return LightweightCharts;
    await loadScript('/static/vendor/lightweight-charts.standalone.production.js');
    return LightweightCharts;
  }

  async function ensureAnime() {
    if (typeof window.anime === 'function') return window.anime;
    try {
      await loadScript('/static/vendor/anime.min.js');
    } catch (_) {
      await loadScript('https://cdn.jsdelivr.net/npm/animejs@3.2.2/lib/anime.min.js');
    }
    return window.anime;
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.charts = {
    ensureEcharts,
    ensureChartJs,
    ensureLightweightCharts,
    ensureAnime,
    loadScript,
  };
})();
