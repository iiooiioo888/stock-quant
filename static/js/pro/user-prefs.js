/* global Api */

/**
 * 工作台用戶偏好（localStorage）— 漲跌配色、K 線天數、掛牌刷新等
 */
(() => {
  const STORAGE_KEY = 'stockq:pro_prefs_v1';

  const DEFAULTS = {
    /** cn-red-up | us-green-up */
    quoteColorScheme: 'cn-red-up',
    chartDays: 90,
    marketPollSec: 90,
    compactTopbar: true,
    /** 頂欄掛牌：自訂 symbols（空/未設置 = 使用後端預設 topbar） */
    topbarSymbols: [],
    /** 資產庫進入詳情時預設分頁 */
    assetDetailTab: 'chart',
    /** HKD | MOP | USD | CNY */
    preferredCurrency: 'MOP',
    /** 右側個人資產配置欄 */
    allocationRailOpen: true,
    allocationWeightMode: 'market_value',
    allocationPortfolioStrategy: 'dual_ma',
  };

  const SCHEME_ATTR = {
    'cn-red-up': 'cn',
    'us-green-up': 'us',
  };

  let cache = null;

  function load() {
    if (cache) return { ...cache };
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        cache = { ...DEFAULTS, ...JSON.parse(raw) };
        return { ...cache };
      }
    } catch (_) {}
    cache = { ...DEFAULTS };
    return { ...cache };
  }

  function save(partial = {}) {
    cache = { ...load(), ...partial };
    if (!SCHEME_ATTR[cache.quoteColorScheme]) {
      cache.quoteColorScheme = DEFAULTS.quoteColorScheme;
    }
    cache.chartDays = Math.min(365, Math.max(30, Number(cache.chartDays) || DEFAULTS.chartDays));
    cache.marketPollSec = Math.max(0, Number(cache.marketPollSec) ?? DEFAULTS.marketPollSec);
    if (!Array.isArray(cache.topbarSymbols)) cache.topbarSymbols = [];
    cache.topbarSymbols = cache.topbarSymbols
      .map((s) => String(s || '').trim().toUpperCase())
      .filter(Boolean)
      .slice(0, 36);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cache));
    apply();
    dispatchChange();
    return { ...cache };
  }

  function get(key) {
    return load()[key];
  }

  function apply() {
    const p = load();
    const attr = SCHEME_ATTR[p.quoteColorScheme] || 'cn';
    document.documentElement.setAttribute('data-quote-colors', attr);
    document.documentElement.setAttribute('data-topbar-compact', p.compactTopbar ? '1' : '0');
  }

  function dispatchChange() {
    try {
      window.dispatchEvent(new CustomEvent('stockq:prefs-changed', { detail: load() }));
    } catch (_) {}
  }

  function quoteCssVar(dir) {
    return dir === 'down' ? 'var(--quote-down)' : 'var(--quote-up)';
  }

  function heatmapStyle(changePct) {
    const v = Number(changePct);
    if (!Number.isFinite(v)) {
      return { color: 'var(--t3)', background: 'var(--bg2)' };
    }
    const intensity = Math.min(Math.abs(v) / 5, 1);
    const up = v >= 0;
    const bgVar = up ? '--quote-up-heat' : '--quote-down-heat';
    return {
      color: up ? 'var(--quote-up)' : 'var(--quote-down)',
      background: `color-mix(in srgb, var(${up ? '--quote-up' : '--quote-down'}) ${Math.round(8 + intensity * 22)}%, transparent)`,
    };
  }

  function init() {
    apply();
  }

  const Prefs = {
    DEFAULTS,
    STORAGE_KEY,
    load,
    save,
    get,
    apply,
    init,
    quoteCssVar,
    heatmapStyle,
    isCnRedUp() {
      return load().quoteColorScheme !== 'us-green-up';
    },
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.Prefs = Prefs;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Prefs.init());
  } else {
    Prefs.init();
  }
})();
