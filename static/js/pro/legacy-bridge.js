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
    crypto: 'crypto',
    markets: 'markets',
  };

  const LEGACY_FRAGMENTS_V = 'data-ui-ib-20260528';
  const LS = 'legacy-pro-20260527';

  const SCRIPT = {
    store: `/static/js/local-store.js?v=${LS}`,
    charts: `/static/js/charts.js?v=${LS}`,
    chartPro: `/static/js/chart-pro.js?v=${LS}`,
    labels: `/static/js/signal-labels.js?v=${LS}`,
    picker: '/static/js/stock-picker.js?v=pf-grid-20260527',
    backtest: `/static/js/backtest.js?v=${LS}`,
    optimize: '/static/js/optimize.js?v=fix-comment-20260530',
    portfolio: '/static/js/portfolio.js?v=pf-method-20260527',
    signals: `/static/js/signals.js?v=${LS}`,
    heatmap: `/static/js/heatmap.js?v=${LS}`,
    stockContent: `/static/js/stock-content.js?v=${LS}`,
    data: '/static/js/data.js?v=data-ui-ib-20260528',
    analysis: `/static/js/analysis.js?v=${LS}`,
    scheduler: `/static/js/scheduler.js?v=${LS}`,
    crypto: `/static/js/crypto.js?v=${LS}`,
    connectivity: `/static/js/connectivity.js?v=${LS}`,
    app: '/static/js/app.js?v=fix-comment-20260530',
  };

  const CORE_SCRIPTS = [SCRIPT.store, SCRIPT.charts, SCRIPT.chartPro, SCRIPT.labels];

  const PAGE_SCRIPTS = {
    optimize: [...CORE_SCRIPTS, SCRIPT.picker, SCRIPT.backtest, SCRIPT.optimize, SCRIPT.app],
    walkforward: [...CORE_SCRIPTS, SCRIPT.picker, SCRIPT.backtest, SCRIPT.app],
    heatmap: [...CORE_SCRIPTS, SCRIPT.picker, SCRIPT.heatmap, SCRIPT.app],
    data: [...CORE_SCRIPTS, SCRIPT.data, SCRIPT.app],
    portfolio: [...CORE_SCRIPTS, SCRIPT.picker, SCRIPT.portfolio, SCRIPT.app],
    signals: [...CORE_SCRIPTS, SCRIPT.signals, SCRIPT.app],
    analysis: [...CORE_SCRIPTS, SCRIPT.picker, SCRIPT.analysis, SCRIPT.app],
    scheduler: [...CORE_SCRIPTS, SCRIPT.scheduler, SCRIPT.app],
    reports: [...CORE_SCRIPTS, SCRIPT.app],
    crypto: [...CORE_SCRIPTS, SCRIPT.crypto, SCRIPT.app],
    markets: [...CORE_SCRIPTS, SCRIPT.app],
    connectivity: [...CORE_SCRIPTS, SCRIPT.connectivity, SCRIPT.app],
  };

  const LEGACY_SCRIPTS = [
    SCRIPT.store, SCRIPT.charts, SCRIPT.chartPro, SCRIPT.labels, SCRIPT.picker,
    SCRIPT.backtest, SCRIPT.optimize, SCRIPT.portfolio, SCRIPT.signals, SCRIPT.heatmap,
    SCRIPT.stockContent, SCRIPT.data, SCRIPT.analysis, SCRIPT.scheduler, SCRIPT.crypto,
    SCRIPT.connectivity, SCRIPT.app,
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

    _loadScriptDirect(src) {
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

    _loadScript(src) {
      const run = () => this._loadScriptDirect(src);
      const SL = window.StockQPro?.StreamLoader;
      return SL ? SL.enqueue(run, 1) : run();
    },

    _ensureLegacyCss() {
      if (document.getElementById('legacy-in-pro-css')) return;
      const link = document.createElement('link');
      link.id = 'legacy-in-pro-css';
      link.rel = 'stylesheet';
      link.href = '/static/css/legacy-in-pro.css?v=data-ui-ib-20260528';
      document.head.appendChild(link);

      // Hotfix layer loaded AFTER legacy-in-pro.css to override safely.
      const hotfix = document.createElement('link');
      hotfix.id = 'legacy-hotfix-css';
      hotfix.rel = 'stylesheet';
      hotfix.href = '/static/css/legacy-hotfix.css?v=20260528';
      document.head.appendChild(hotfix);
    },

    ensurePageScripts(pageId) {
      const list = PAGE_SCRIPTS[pageId] || LEGACY_SCRIPTS;
      if (this._pageScriptReady && this._pageScriptReady[pageId]) {
        return this._pageScriptReady[pageId];
      }
      this._pageScriptReady = this._pageScriptReady || {};
      this._pageScriptReady[pageId] = (async () => {
        this._ensureLegacyCss();
        const charts = window.StockQPro?.charts;
        const SL = window.StockQPro?.StreamLoader;
        if (charts) {
          const chartFns = [
            () => charts.ensureChartJs(),
            () => charts.ensureLightweightCharts(),
          ];
          if (SL) await SL.runSequential(chartFns);
          else {
            for (const fn of chartFns) await fn();
          }
        }
        const scriptFns = list.map((src) => () => this._loadScript(src));
        if (SL) await SL.runSequential(scriptFns);
        else {
          for (const fn of scriptFns) await fn();
        }
        this._patchLegacyApp();
      })();
      return this._pageScriptReady[pageId];
    },

    ensureScripts() {
      if (this._scriptsReady) return this._scriptsReady;
      this._scriptsReady = this.ensurePageScripts('__all__');
      return this._scriptsReady;
    },

    _patchLegacyApp() {
      if (typeof App === 'undefined' || App._proPatched) return;
      const pro = window.StockQPro?.App;
      if (pro && pro !== App && pro._connectWS) {
        window.LegacyApp = App;
        App._connectWS = () => pro.reconnectWs();
        App.initWebSocket = async () => { pro.reconnectWs(); };
        App.reconnectWs = () => pro.reconnectWs();
        Object.defineProperty(App, '_ws', {
          configurable: true,
          get() { return pro._ws; },
          set(v) { pro._ws = v; },
        });
      }
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
      if (this._fragments && this._fragmentsVersion === LEGACY_FRAGMENTS_V) {
        return this._fragments;
      }
      this._fragments = null;
      const res = await fetch(`/static/partials/legacy-tabs.html?v=${LEGACY_FRAGMENTS_V}`, { cache: 'no-cache' });
      if (!res.ok) throw new Error('無法載入 legacy 片段');
      const html = await res.text();
      const wrap = document.createElement('div');
      wrap.innerHTML = html;
      this._fragments = {};
      wrap.querySelectorAll('[id^="tab-"]').forEach((el) => {
        const key = el.id.replace(/^tab-/, '');
        this._fragments[key] = el;
      });
      this._fragmentsVersion = LEGACY_FRAGMENTS_V;
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
      if (tabKey === 'data') this._initedTabs.delete('data');
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
      try {
        if (tab === 'data' && typeof Data !== 'undefined') {
          Data.init();
          Data.load?.();
        }
      } catch (_) {}
      try { if (tab === 'analysis' && typeof Analysis !== 'undefined') Analysis.init(); } catch (_) {}
      try {
        if (['optimize', 'walkforward', 'heatmap'].includes(tab) && typeof Backtest !== 'undefined') {
          Backtest.init();
        }
      } catch (_) {}
      try {
        if (['optimize', 'walkforward', 'heatmap', 'analysis'].includes(tab)
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
          if (typeof Portfolio !== 'undefined') {
            Portfolio.init?.();
            Portfolio.loadPresets?.();
            Portfolio.updateSummary?.();
          }
          try {
            if (typeof StockPicker !== 'undefined') StockPicker.initPortfolioLazy?.();
          } catch (_) {}
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
        await this.ensurePageScripts(pageId);
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
          if (inited) return Bridge.activate(pageId);
          inited = true;
          return Bridge.activate(pageId);
        },
        onShow() {
          return Bridge.activate(pageId);
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
