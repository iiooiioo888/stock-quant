/* global */
(() => {
  const PAGES = ['optimize', 'walkforward', 'heatmap'];

  function hooks(pageId) {
    return {
      init() {
        return window.StockQPro?.LegacyBridge?.activate?.(pageId);
      },
      onShow() {
        return window.StockQPro?.LegacyBridge?.activate?.(pageId);
      },
    };
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  PAGES.forEach((pid) => {
    window.StockQPro.pages[pid] = hooks(pid);
  });
})();
