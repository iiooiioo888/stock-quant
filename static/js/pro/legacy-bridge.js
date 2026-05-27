/* global Api, Utils, Charts, ProCharts, TaskCommon */

(() => {
  const PAGE_TO_TAB = {
    portfolio: 'portfolio',
    optimize: 'optimize',
    walkforward: 'walkforward',
    heatmap: 'heatmap',
    signals: 'signals',
    data: 'data',
    analysis: 'analysis',
    scheduler: 'scheduler',
    reports: 'reports',
    connectivity: 'connectivity',
    alerts: 'alerts',
    crypto: 'crypto',
    markets: 'markets',
  };

  const LEGACY_SCRIPTS = [
    '/static/js/local-store.js?v=legacy-pro-20260527',
    '/static/js/charts.js?v=legacy-pro-20260527',
    '/static/js/chart-pro.js?v=legacy-pro-20260527',
    '/static/js/signal-labels.js?v=legacy-pro-20260527',
    '/static/js/stock-picker.js?v=legacy-pro-20260527',
    '/static/js/backtest.js?v=legacy-pro-20260527',
    '/static/js/optimize.js?v=legacy-pro-20260527',
    '/static/js/portfolio.js?v=legacy-pro-20260527',
    '/static/js/signals.js?v=legacy-pro-20260527',
    '/static/js/heatmap.js?v=legacy-pro-20260527',
    '/static/js/stock-content.js?v=legacy-pro-20260527',
    '/static/js/data.js?v=legacy-pro-20260527',
    '/static/js/analysis.js?v=legacy-pro-20260527',
    '/static/js/scheduler.js?v=legacy-pro-20260527',
    '/static/js/crypto.js?v=legacy-pro-20260527',
    '/static/js/connectivity.js?v=legacy-pro-20260527',
    '/static/js/app.js?v=legacy-pro-20260527',
  ];

  const Bridge = {
    _fragments: null,
    _mountedPage: '',
    _scriptsReady: null,
    _modulesReady: false,
    _initedTabs: new Set(),

    isLegacyPage(pageId) {
      return Object.prototype.hasOwnProperty.call(PAGE_TO_TAB, pageId);
    },

    _loadScript(src) {
      return new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) {
          resolve();
          return;
        }
        const s = document.createElement('script');
        s.src = src;
        s.defer = true;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error(`load failed: ${src}`));
        document.body.appendChild(s);
      });
    },

    ensureScripts() {
      if (this._scriptsReady) return this._scriptsReady;
      this._scriptsReady = (async () => {
        for (const src of LEGACY_SCRIPTS) {
          await this._loadScript(src);
        }
        this._patchLegacyApp();
      })();
      return this._scriptsReady;
    },

    _patchLegacyApp() {
      if (typeof App === 'undefined' || App._proPatched) return;
      const origLoadTab = App.loadTab?.bind(App);
      App.loadTab = (tab, opts = {}) => {
        const proPage = PAGE_TO_TAB[tab] || tab;
        if (window.StockQPro?.App?.nav && Bridge.isLegacyPage(proPage)) {
          window.StockQPro.App.nav(proPage, { syncHash: true });
          return Bridge.activate(proPage, opts);
        }
        if (window.StockQPro?.App?.nav && ['tasks', 'backtest', 'compare', 'backhistory', 'scanner', 'watchlist', 'assets', 'dashboard', 'strategies', 'settings', 'ai'].includes(tab)) {
          const map = {
            history: 'backhistory',
            screener: 'scanner',
            'stock-detail': 'assets',
          };
          window.StockQPro.App.nav(map[tab] || tab, { syncHash: true });
          return;
        }
        return origLoadTab?.(tab, opts);
      };
      App._proPatched = true;
    },

    async ensureFragments() {
      if (this._fragments) return this._fragments;
      const res = await fetch('/static/partials/legacy-tabs.html', { cache: 'no-cache' });
      if (!res.ok) throw new Error('無法載入 legacy 片段');
      const html = await res.text();
      const wrap = document.createElement('div');
      wrap.innerHTML = html;
      this._fragments = {};
      wrap.querySelectorAll('[id^="tab-"]').forEach((el) => {
        const key = el.id.replace(/^tab-/, '');
        this._fragments[key] = el;
      });
      return this._fragments;
    },

    _clearMounts(exceptPage) {
      Object.keys(PAGE_TO_TAB).forEach((pageId) => {
        if (pageId === exceptPage) return;
        const mount = document.querySelector(`#pg-${pageId} .legacy-mount`);
        if (mount) mount.innerHTML = '';
      });
      this._mountedPage = exceptPage;
    },

    async _mount(pageId) {
      const tabKey = PAGE_TO_TAB[pageId];
      const mount = document.querySelector(`#pg-${pageId} .legacy-mount`);
      if (!tabKey || !mount) return false;

      await this.ensureFragments();
      const src = this._fragments[tabKey];
      if (!src) return false;

      this._clearMounts(pageId);
      const node = src.cloneNode(true);
      node.classList.remove('h');
      node.style.display = '';
      node.style.opacity = '';
      node.style.transform = '';
      mount.innerHTML = '';
      mount.appendChild(node);
      return true;
    },

    initModulesOnce(tab) {
      if (this._initedTabs.has(tab)) return;
      try { if (tab === 'portfolio' && typeof Portfolio !== 'undefined') Portfolio.init(); } catch (_) {}
      try { if (tab === 'signals' && typeof Signals !== 'undefined') Signals.init(); } catch (_) {}
      try { if (tab === 'data' && typeof Data !== 'undefined') Data.init(); } catch (_) {}
      try { if (tab === 'analysis' && typeof Analysis !== 'undefined') Analysis.init(); } catch (_) {}
      try {
        if (['optimize', 'walkforward', 'heatmap'].includes(tab) && typeof Backtest !== 'undefined') {
          Backtest.init();
        }
      } catch (_) {}
      try {
        if (['optimize', 'walkforward', 'heatmap', 'portfolio', 'analysis'].includes(tab)
          && typeof StockPicker !== 'undefined') {
          StockPicker.initAll();
        }
      } catch (_) {}
      try {
        if (tab === 'heatmap' && typeof App !== 'undefined' && App.initHeatmapStrategy) {
          App.initHeatmapStrategy();
        }
      } catch (_) {}
      this._initedTabs.add(tab);
    },

    _activateTabData(tab) {
      if (typeof App === 'undefined') return;
      switch (tab) {
        case 'portfolio':
          if (typeof Portfolio !== 'undefined') Portfolio.loadPresets?.();
          break;
        case 'alerts':
          App.loadAlerts?.();
          App.loadNotifyChannels?.();
          break;
        case 'crypto':
          if (typeof CryptoUI !== 'undefined') CryptoUI.load?.();
          break;
        case 'markets':
          Promise.all([App.loadMarkets?.(), App.loadMarketRealtime?.()].filter(Boolean));
          break;
        case 'connectivity':
          if (typeof ConnectivityPage !== 'undefined') ConnectivityPage.load?.();
          break;
        case 'signals':
          if (typeof Signals !== 'undefined') Signals.load?.();
          break;
        case 'data':
          if (typeof Data !== 'undefined') Data.load?.();
          break;
        case 'heatmap':
          if (typeof Heatmap !== 'undefined') Heatmap.initTab?.();
          break;
        case 'walkforward':
          App._onWalkforwardTab?.();
          break;
        case 'optimize':
          App._onOptimizeTab?.();
          break;
        case 'analysis':
          if (typeof Analysis !== 'undefined') Analysis.onTabShow?.();
          break;
        case 'reports':
          App._onReportsTab?.();
          break;
        case 'scheduler':
          if (typeof SchedulerTab !== 'undefined') SchedulerTab.load?.();
          else App._setupScheduler?.();
          break;
        default:
          break;
      }

      if (typeof Charts !== 'undefined') {
        requestAnimationFrame(() => {
          Charts.resizeTab(`tab-${tab}`);
          if (typeof ProCharts !== 'undefined') ProCharts.initTab?.(tab);
        });
      }
    },

    async activate(pageId, opts = {}) {
      if (!this.isLegacyPage(pageId)) return false;
      const tab = PAGE_TO_TAB[pageId];
      try {
        await this.ensureScripts();
        const ok = await this._mount(pageId);
        if (!ok) return false;
        this.initModulesOnce(tab);
        this._activateTabData(tab);

        if (opts.code && tab === 'optimize') {
          const el = document.getElementById('optCode');
          if (el) el.value = String(opts.code).trim();
        }
        return true;
      } catch (e) {
        window.StockQPro?.App?.toast?.(`載入模組失敗：${e?.message || e}`, 'er');
        return false;
      }
    },

    createPageHooks(pageId) {
      let inited = false;
      return {
        init() {
          if (inited) return;
          inited = true;
          Bridge.activate(pageId).catch(() => {});
        },
        onShow() {
          Bridge.activate(pageId).catch(() => {});
        },
      };
    },
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.LegacyBridge = Bridge;

  Object.keys(PAGE_TO_TAB).forEach((pageId) => {
    window.StockQPro.pages = window.StockQPro.pages || {};
    window.StockQPro.pages[pageId] = Bridge.createPageHooks(pageId);
  });
})();
