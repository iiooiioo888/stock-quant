/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);
  const Prefs = () => window.StockQPro?.Prefs;

  function updatePreview() {
    const box = $id('set-color-preview');
    if (!box) return;
    const up = box.querySelector('.settings-preview-chip.up');
    const down = box.querySelector('.settings-preview-chip.down');
    if (up) up.textContent = '+1.28%';
    if (down) down.textContent = '-0.85%';
  }

  function readForm() {
    const scheme = document.querySelector('input[name="set-quote-scheme"]:checked')?.value
      || Prefs()?.DEFAULTS?.quoteColorScheme;
    return {
      quoteColorScheme: scheme,
      chartDays: Number($id('set-chart-days')?.value) || 90,
      marketPollSec: Number($id('set-poll-sec')?.value),
      compactTopbar: !!$id('set-compact-topbar')?.checked,
    };
  }

  function fillForm(p) {
    const scheme = p.quoteColorScheme || 'cn-red-up';
    document.querySelectorAll('input[name="set-quote-scheme"]').forEach((el) => {
      el.checked = el.value === scheme;
    });
    if ($id('set-chart-days')) $id('set-chart-days').value = String(p.chartDays ?? 90);
    if ($id('set-poll-sec')) $id('set-poll-sec').value = String(p.marketPollSec ?? 90);
    if ($id('set-compact-topbar')) $id('set-compact-topbar').checked = p.compactTopbar !== false;
    updatePreview();
  }

  async function loadServerConfig() {
    const cfg = await Api.getConfig().catch(() => ({}));
    if (cfg && typeof cfg === 'object') {
      if (cfg.backtest_commission != null && $id('set-commission')) {
        $id('set-commission').value = Number(cfg.backtest_commission) * 100;
      }
      if (cfg.task_max_workers != null && $id('set-max-parallel')) {
        $id('set-max-parallel').value = Number(cfg.task_max_workers);
      }
      const tv = $id('set-src-tv');
      const ib = $id('set-src-ib');
      if (tv) tv.textContent = cfg.tradingview_enabled === false ? '關閉' : '啟用';
      if (ib) ib.textContent = cfg.ib_enabled ? '已連線配置' : '未啟用';
    }
    return cfg;
  }

  function load() {
    const p = Prefs()?.load?.() || {};
    fillForm(p);
    return loadServerConfig();
  }

  function save() {
    const partial = readForm();
    Prefs()?.save?.(partial);
    window.StockQPro?.MarketTicker?.setPollInterval?.(partial.marketPollSec * 1000);
    window.StockQPro?.MarketTicker?.refresh?.();
    window.StockQPro?.App?.toast?.('偏好已保存（本機）', 'ok');
  }

  async function clearCaches() {
    try {
      if (typeof Api.clearGetCache === 'function') Api.clearGetCache();
      await Api.post('/api/cache/clear', {}).catch(() => null);
      window.StockQPro?.App?.toast?.('已清除前端與服務端緩存', 'ok');
    } catch (_) {
      window.StockQPro?.App?.toast?.('清除緩存失敗', 'er');
    }
  }

  function bindSchemePreview() {
    document.querySelectorAll('input[name="set-quote-scheme"]').forEach((el) => {
      el.addEventListener('change', () => {
        Prefs()?.save?.(readForm());
        updatePreview();
      });
    });
  }

  function init() {
    if ($id('set-save-btn') && !$id('set-save-btn').dataset.bound) {
      $id('set-save-btn').dataset.bound = '1';
      $id('set-save-btn').addEventListener('click', () => save());
      $id('set-reload-btn')?.addEventListener('click', () => {
        load().catch(() => window.StockQPro?.App?.toast?.('載入設定失敗', 'er'));
      });
      $id('set-clear-cache')?.addEventListener('click', () => clearCaches());
      $id('set-reset-prefs')?.addEventListener('click', () => {
        localStorage.removeItem(Prefs()?.STORAGE_KEY || 'stockq:pro_prefs_v1');
        if (Prefs()) Prefs().save({ ...Prefs().DEFAULTS });
        fillForm(Prefs().DEFAULTS);
        window.StockQPro?.App?.toast?.('已恢復預設偏好', 'ok');
      });
      bindSchemePreview();
    }
    load().catch(() => window.StockQPro?.App?.toast?.('載入設定失敗', 'er'));
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.settings = { init, load, save };
})();
