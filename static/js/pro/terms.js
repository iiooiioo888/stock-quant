/**
 * UI 標準用詞（繁中）— 避免「官網」等場景不符稱呼
 */
(() => {
  const TERMS = {
    'nav.product': '產品介紹',
    'nav.docs': '項目文檔',
    'nav.dataSources': '數據源說明',
    'nav.manual': '使用手冊',
    'nav.console': '主控台',
    'nav.admin': '管理後台',
    'nav.app': '工作台',
    'page.productHome': '產品首頁',
    'ui.backtest': '策略回測',
    'ui.assets': '資產庫',
  };

  function t(key, fallback) {
    if (key in TERMS) return TERMS[key];
    return fallback != null ? fallback : key;
  }

  function applyTerms(root) {
    const el = root || document;
    el.querySelectorAll('[data-term]').forEach((node) => {
      const key = node.getAttribute('data-term');
      if (!key) return;
      const val = t(key);
      if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {
        node.placeholder = val;
      } else {
        node.textContent = val;
      }
    });
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.Terms = { t, applyTerms, TERMS };
})();
