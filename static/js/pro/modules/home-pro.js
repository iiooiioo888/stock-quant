/* global Api */

(() => {
  let bound = false;

  function fmtKlines(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return '--';
    if (x >= 1e6) return `${(x / 1e6).toFixed(1)}M`;
    if (x >= 1e3) return `${(x / 1e3).toFixed(1)}K`;
    return String(Math.round(x));
  }

  function bindNav() {
    if (bound) return;
    bound = true;
    const root = document.getElementById('pg-home');
    if (!root) return;
    root.querySelectorAll('[data-go]').forEach((el) => {
      el.addEventListener('click', () => {
        const p = el.getAttribute('data-go');
        if (p) window.StockQPro?.App?.nav?.(p, { syncHash: true });
      });
    });
    root.querySelectorAll('.home-feat[data-go]').forEach((card) => {
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          card.click();
        }
      });
      card.setAttribute('tabindex', '0');
      card.setAttribute('role', 'button');
    });
  }

  async function loadStats() {
    const health = await Api.get('/api/health', { silent: true }).catch(() => null);
    if (!health) return;

    const stocks = document.getElementById('home-st-stocks');
    const klines = document.getElementById('home-st-klines');
    const ver = document.getElementById('home-st-ver');
    const uptime = document.getElementById('home-st-uptime');

    if (stocks) stocks.textContent = fmtKlines(health.total_stocks ?? 0);
    if (klines) klines.textContent = fmtKlines(health.total_klines ?? 0);
    if (ver && health.version) ver.textContent = `v${health.version}`;
    if (uptime && health.uptime) uptime.textContent = health.uptime;
  }

  function init() {
    bindNav();
    loadStats();
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.home = { init };
})();
