/* global Utils */

/**
 * 多市場標的代碼正規化（對比 / 配置欄 / 組合回測共用）
 */
(() => {
  function normalizeCompareCode(raw) {
    const s = String(raw || '').trim().toUpperCase();
    if (!s) return '';
    if (/^\d{1,6}$/.test(s)) return s.padStart(6, '0');
    if (/^\d{6}\.(SS|SZ)$/i.test(s)) return s;
    if (/^\d{4,5}\.HK$/i.test(s)) return s.replace(/(\d+)\.HK/i, (_, d) => `${d.padStart(4, '0')}.HK`);
    if (s.startsWith('^') || s.includes('.') || s.includes('=') || /^[A-Z][A-Z0-9\-]{0,14}$/.test(s)) {
      return s;
    }
    const m = s.match(/(\d{6})/);
    if (m) return m[1];
    return s;
  }

  function isValidCompareSymbol(code) {
    const c = normalizeCompareCode(code);
    if (!c) return false;
    if (typeof Utils !== 'undefined' && Utils.isValidCode) return Utils.isValidCode(c);
    if (/^\d{6}$/.test(c)) return true;
    if (/^\d{4,5}\.HK$/i.test(c)) return true;
    if (/^[A-Z0-9.^=\-]{1,20}$/i.test(c)) return true;
    return false;
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.SymbolUtils = {
    normalizeCompareCode,
    isValidCompareSymbol,
  };
})();
