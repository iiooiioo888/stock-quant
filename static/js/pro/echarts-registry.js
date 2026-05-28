/* global echarts */
(() => {
  /**
   * ECharts registry
   * - 以「pageId + chartId」管理實例，確保切頁會 dispose，避免記憶體/事件監聽累積
   * - 對外提供 get()/disposePage()/disposeAll()
   */
  const reg = {
    _byKey: new Map(), // key -> echartsInstance
    _key(pageId, chartId) {
      return `${String(pageId || 'global')}::${String(chartId || '')}`;
    },
    _safeDispose(inst) {
      if (!inst) return;
      try {
        if (typeof inst.dispose === 'function') inst.dispose();
      } catch (_) {}
    },
    get(pageId, chartId, el, initOpts = null) {
      if (!el || typeof echarts === 'undefined') return null;
      const key = this._key(pageId, chartId);
      const existed = this._byKey.get(key);
      if (existed) {
        try {
          if (typeof existed.isDisposed === 'function' && existed.isDisposed()) {
            this._byKey.delete(key);
          } else {
            return existed;
          }
        } catch (_) {
          this._byKey.delete(key);
        }
      }

      // 同一個 DOM 若已有 instance（例如舊碼自己 init 過），先 dispose 避免重疊
      try {
        const old = echarts.getInstanceByDom ? echarts.getInstanceByDom(el) : null;
        if (old) this._safeDispose(old);
      } catch (_) {}

      if (el.offsetWidth < 2 || el.offsetHeight < 2) return null;
      const inst = initOpts ? echarts.init(el, null, initOpts) : echarts.init(el);
      this._byKey.set(key, inst);
      return inst;
    },
    disposeKey(pageId, chartId) {
      const key = this._key(pageId, chartId);
      const inst = this._byKey.get(key);
      this._byKey.delete(key);
      this._safeDispose(inst);
    },
    disposePage(pageId) {
      const prefix = `${String(pageId || 'global')}::`;
      for (const [key, inst] of this._byKey.entries()) {
        if (!key.startsWith(prefix)) continue;
        this._byKey.delete(key);
        this._safeDispose(inst);
      }
    },
    disposeAll() {
      for (const inst of this._byKey.values()) this._safeDispose(inst);
      this._byKey.clear();
    },
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.ECharts = reg;
})();

