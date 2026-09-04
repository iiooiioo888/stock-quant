/* global StockQPro */
(() => {
  const ROOT = '/static/js/pro/modules/';
  const V = 'gui-ux-20260903k';

  const PAGE_CHARTS = {
    capitalflow: ['echarts'],
    compare: ['echarts'],
    backtest: ['echarts'],
    watchlist: ['echarts'],
  };

  const PAGE_SCRIPTS = {
    dashboard: [
      '/static/js/pro/currency-manager.js',
      `${ROOT}dashboard-pro.js`,
    ],
    tasks: [`${ROOT}tasks-pro.js`],
    strategies: ['/static/js/pro/strategy-catalog.js'],
    compare: [`${ROOT}compare-pro.js`],
    watchlist: [`${ROOT}watchlist-pro.js`],
    scanner: [`${ROOT}scanner-pro.js`],
    backhistory: [`${ROOT}backhistory-pro.js`],
    assets: [`${ROOT}assets-pro.js`],
    capitalflow: [`${ROOT}capitalflow-pro.js`],
    ai: [`${ROOT}ai-assistant.js`],
    settings: [`${ROOT}settings-pro.js`],
    pricing: [`${ROOT}pricing-pro.js`],
    backtest: [
      '/static/js/pro/stock-pick-data.js',
      `${ROOT}backtest-symbol-picker.js`,
      `${ROOT}backtest-pro.js`,
    ],
  };

  const _loaded = new Set();
  const _pending = {};

  function withVersion(src) {
    const sep = src.includes('?') ? '&' : '?';
    return `${src}${sep}v=${encodeURIComponent(V)}`;
  }

  function loadScript(src) {
    const url = withVersion(src);
    if (_loaded.has(url)) return Promise.resolve();
    if (_pending[url]) return _pending[url];

    const run = () => new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = url;
      s.async = true;
      s.onload = () => {
        _loaded.add(url);
        resolve();
      };
      s.onerror = () => reject(new Error(`module load failed: ${url}`));
      document.body.appendChild(s);
    });

    const SL = window.StockQPro?.StreamLoader;
    _pending[url] = SL
      ? SL.enqueue(run, 2, 'nav')
      : run();

    return _pending[url];
  }

  async function ensureCharts(pageId) {
    const charts = PAGE_CHARTS[pageId];
    if (!charts?.length) return;
    const cv = window.StockQPro?.charts;
    if (!cv) return;
    const SL = window.StockQPro?.StreamLoader;
    const tasks = charts.map((kind) => async () => {
      if (kind === 'echarts') await cv.ensureEcharts();
    });
    if (SL) await SL.runSequential(tasks);
    else {
      for (const t of tasks) await t();
    }
  }

  async function ensurePage(pageId) {
    const pid = String(pageId || '').trim();
    await ensureCharts(pid);

    // ESM gray release: delegate to ESM loader when enabled for this page.
    // This keeps legacy PAGE_SCRIPTS untouched for rollback safety.
    try {
      const ESM = window.__StockQProESM__;
      if (ESM?.isEnabled?.(pid)) {
        await ESM.ensurePage(pid);
        return;
      }
    } catch (e) {
      // If ESM path fails, bubble up so App can toast the error.
      throw e;
    }

    const list = PAGE_SCRIPTS[pid];
    if (!list?.length) return;
    const SL = window.StockQPro?.StreamLoader;
    const fns = list.map((src) => () => loadScript(src));
    if (SL) await SL.runSequential(fns);
    else {
      for (const fn of fns) await fn();
    }
  }

  async function prefetch(pageId) {
    const pid = String(pageId || 'dashboard').trim();
    try {
      await ensurePage(pid);
    } catch (err) {
      console.warn('[module-loader] prefetch', pid, err);
    }
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.modules = {
    ensurePage,
    ensureCharts,
    prefetch,
    loadScript,
    PAGE_SCRIPTS,
    PAGE_CHARTS,
  };
})();
