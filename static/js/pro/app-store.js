/* global window */

/**
 * 輕量全域狀態（ES6 Proxy）— 取代零散的全域變數
 * 用法: StockQPro.Store.get('activeTaskId') / .set({ selectedSymbol: '600519' })
 */
(() => {
  const state = {
    page: 'dashboard',
    selectedSymbol: '',
    activeTaskId: null,
    selectedStrategyId: null,
  };

  const store = new Proxy(state, {
    set(target, prop, value) {
      const prev = target[prop];
      target[prop] = value;
      if (prev !== value) {
        try {
          window.dispatchEvent(
            new CustomEvent('stockq:store-changed', {
              detail: { key: prop, value, prev },
            }),
          );
        } catch (_) {}
      }
      return true;
    },
  });

  function get(key) {
    return store[key];
  }

  function set(partial) {
    if (!partial || typeof partial !== 'object') return { ...store };
    Object.keys(partial).forEach((k) => {
      store[k] = partial[k];
    });
    return { ...store };
  }

  function snapshot() {
    return { ...store };
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.Store = { get, set, snapshot };
})();
