/* global StockQPro */
(() => {
  const ROOT = '/static/js/pro/modules/';
  const V = 'stockq-pro-lazy-20260527';

  const PAGE_SCRIPTS = {
    backtest: [
      '/static/js/pro/stock-pick-data.js',
      `${ROOT}backtest-symbol-picker.js`,
      `${ROOT}backtest-pro.js`,
    ],
    compare: [`${ROOT}compare-pro.js`],
    watchlist: [`${ROOT}watchlist-pro.js`],
    scanner: [`${ROOT}scanner-pro.js`],
    backhistory: [`${ROOT}backhistory-pro.js`],
    assets: [`${ROOT}assets-pro.js`],
    ai: [`${ROOT}ai-assistant.js`],
    settings: [`${ROOT}settings-pro.js`],
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
    _pending[url] = new Promise((resolve, reject) => {
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
    return _pending[url];
  }

  async function ensurePage(pageId) {
    const pid = String(pageId || '').trim();
    const list = PAGE_SCRIPTS[pid];
    if (!list || !list.length) return;
    for (const src of list) {
      await loadScript(src);
    }
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.modules = { ensurePage, loadScript, PAGE_SCRIPTS };
})();
