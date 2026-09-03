/* global */
(() => {
  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.data = {
    init() {
      return window.StockQPro?.LegacyBridge?.activate?.('data');
    },
    onShow() {
      return window.StockQPro?.LegacyBridge?.activate?.('data');
    },
  };
})();
