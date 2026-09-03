/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);
  let mounted = false;
  let unsubTicker = null;
  let loadPromise = null;
  let uiBound = false;

  function fmtK(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return '--';
    if (x >= 1e6) return `${(x / 1e6).toFixed(1)}M`;
    if (x >= 1e3) return `${(x / 1e3).toFixed(1)}K`;
    return String(Math.round(x));
  }

  function ensureLayout() {
    const root = $id('dashboard-root');
    const D = window.StockQPro?.UI?.Dashboard;
    const UI = window.StockQPro?.UI;
    if (!root || !D || !UI || mounted) return;
    UI.mount(root, D.buildPageLayout());
    mounted = true;
  }

  function setUpdatedAt() {
    const el = $id('dash-updated-at');
    if (!el) return;
    const now = new Date();
    el.textContent = `更新於 ${now.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
  }

  function renderKpis(health, latencyMs, cfg) {
    const row = $id('dash-kpi-row');
    const D = window.StockQPro?.UI?.Dashboard;
    if (!row || !D) return;
    const ready = health?.data_ready;
    const UI = window.StockQPro?.UI;
    if (!UI) return;
    UI.mount(row, [
      D.KpiCard({ label: 'API 延遲', value: `${latencyMs}ms`, tone: latencyMs < 200 ? 'gn' : 'ac' }),
      D.KpiCard({ label: '本地標的', value: fmtK(health?.total_stocks), hint: 'distinct codes' }),
      D.KpiCard({ label: '日 K 記錄', value: fmtK(health?.total_klines), hint: 'daily_kline' }),
      D.KpiCard({
        label: '數據狀態',
        value: ready ? '就緒' : '載入中',
        hint: health?.uptime || '',
        tone: ready ? 'gn' : 'ac',
      }),
      cfg?.cache_mb != null
        ? D.KpiCard({ label: '緩存', value: `${cfg.cache_mb} MB`, tone: 'bl' })
        : null,
    ].filter(Boolean));
  }

  function renderQuoteBoard(payload) {
    const D = window.StockQPro?.UI?.Dashboard;
    const UI = window.StockQPro?.UI;
    if (!D) return;

    const data = payload && typeof payload === 'object'
      ? payload
      : { indices: Array.isArray(payload) ? payload : [] };

    D.QuoteBoardGrouped('dash-quote-board', data);

    const badgeHost = $id('dash-provider-badges');
    if (badgeHost && UI && data.providers) {
      UI.mount(badgeHost, D.ProviderBadges(data.providers));
    }
  }

  async function load() {
    if (loadPromise) return loadPromise;

    loadPromise = (async () => {
      ensureLayout();
      window.StockQPro?.CurrencyManager?.init('currency-toggle');
      const t0 = performance.now();
      const mon = window.StockQPro?.services?.opsMonitor;
      const sopPromise = (async () => {
        const cached = mon?.getLast?.();
        if (cached) return cached;
        return mon?.tick?.()
          || window.StockQPro?.UI?.OpsStatus?.fetchSop?.()
          || (Api.getHealthSop?.() || Api.get('/api/health/sop', { silent: true })).catch(() => null);
      })();
      const [health, sopPayload, cfg] = await Promise.all([
        Api.get('/api/health', { silent: true }).catch(() => null),
        sopPromise,
        Api.getConfig().catch(() => null),
      ]);
      const latencyMs = Math.round(performance.now() - t0);

      const ticker = window.StockQPro?.services?.marketTicker;
      let payload = ticker?.getPayload?.() || null;
      if (!payload?.indices?.length && ticker?.ensureFullPayload) {
        payload = await ticker.ensureFullPayload().catch(() => null);
      } else if (!payload?.indices?.length && ticker?.refresh) {
        payload = await ticker.refresh().catch(() => null);
      }
      renderQuoteBoard(payload || { indices: ticker?.getQuotes?.() || [] });
      renderKpis(health, latencyMs, cfg);
      window.StockQPro?.UI?.Dashboard?.renderOpsStatus?.(sopPayload);
      setUpdatedAt();
    })();

    try {
      return await loadPromise;
    } finally {
      loadPromise = null;
    }
  }

  function showLoadIssue(msg) {
    const host = $id('dash-updated-at');
    if (host) host.textContent = msg || '部分資料未載入';
    console.warn(msg || '儀表盤載入異常');
  }

  const FLOW = [
    { p: 'data', n: '1 數據', d: '下載入庫' },
    { p: 'backtest', n: '2 回測', d: '選標的跑策略' },
    { p: 'optimize', n: '3 優化', d: '掃參數' },
    { p: 'compare', n: '4 對比', d: '多股／多策略' },
    { p: 'tasks', n: '5 任務', d: '看進度與結果' },
    { p: 'watchlist', n: '自選', d: '關注與提醒' },
    { p: 'assets', n: '資產庫', d: '個股詳情' },
    { p: 'scanner', n: '選股', d: '條件掃描' },
  ];

  const PAGE_NAMES = {
    dashboard: '總覽', tasks: '任務中心', watchlist: '自選股', scanner: '選股器',
    alerts: '預警', strategies: '策略庫', backtest: '策略回測', compare: '對比',
    portfolio: '持倉與淨值', backhistory: '回測歷史', optimize: '參數優化',
    walkforward: '滾動驗證', heatmap: '熱力圖', reports: '策略報告',
    assets: '資產庫', capitalflow: '資金流', data: '數據中心', analysis: '深度分析',
    signals: '信號', markets: '市場', crypto: '加密', scheduler: '定時',
    connectivity: '數據源', ai: 'AI', pricing: '定價', settings: '設定',
  };

  function renderFlow() {
    const host = $id('dash-flow');
    const recentHost = $id('dash-recent');
    if (host) {
      host.innerHTML = FLOW.map((f) => (
        `<button type="button" class="dash-flow-chip" data-flow="${f.p}">` +
        `<span class="dash-flow-n">${f.n}</span><span class="dash-flow-d">${f.d}</span>` +
        `</button>`
      )).join('');
    }
    if (recentHost) {
      const rec = (window.StockQPro?.Prefs?.get?.('recentPages') || [])
        .filter((p) => p && p !== 'dashboard');
      if (!rec.length) {
        recentHost.innerHTML = '';
      } else {
        recentHost.innerHTML = '<span class="dash-recent-lbl">最近</span>' + rec.map((p) => (
          `<button type="button" class="ctag" data-flow="${p}">${PAGE_NAMES[p] || p}</button>`
        )).join('');
      }
    }
  }

  function bindUiOnce() {
    if (uiBound) return;
    uiBound = true;

    document.getElementById('dash-open-cmd')?.addEventListener('click', () => {
      window.StockQPro?.App?._cmd?.open?.();
    });
    document.getElementById('dash-launch-in')?.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const raw = String(e.target.value || '').trim();
      if (!raw) return;
      window.StockQPro?.WorkContext?.set?.(raw);
      window.StockQPro?.WorkContext?.go?.('backtest');
    });
    document.getElementById('pg-dashboard')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-flow]');
      if (!btn) return;
      const p = btn.getAttribute('data-flow');
      if (!p) return;
      window.StockQPro?.WorkContext?.commitInput?.();
      window.StockQPro?.App?.nav?.(p, { syncHash: true });
      setTimeout(() => window.StockQPro?.WorkContext?.applyToPage?.(p), 80);
    });

    const ticker = window.StockQPro?.services?.marketTicker;
    if (ticker?.subscribe && !unsubTicker) {
      unsubTicker = ticker.subscribe((payload) => {
        if (window.StockQPro?.App?.current && window.StockQPro.App.current !== 'dashboard') return;
        if (!mounted) ensureLayout();
        renderQuoteBoard(payload);
        setUpdatedAt();
      });
    }
  }

  function init() {
    ensureLayout();
    bindUiOnce();
    renderFlow();
    try { window.StockQPro?.WorkContext?.render?.(); } catch (_) {}
    load().catch((err) => {
      showLoadIssue('部分資料未載入，可點刷新重試');
      console.warn('儀表盤載入失敗', err);
    });
  }

  function onShow() {
    renderFlow();
    const cached = window.StockQPro?.services?.opsMonitor?.getLast?.();
    if (cached) window.StockQPro?.UI?.Dashboard?.renderOpsStatus?.(cached);
    else window.StockQPro?.services?.opsMonitor?.tick?.().catch(() => {});
    const ticker = window.StockQPro?.services?.marketTicker;
    const cachedQuotes = ticker?.getPayload?.();
    if (cachedQuotes?.indices?.length) {
      renderQuoteBoard(cachedQuotes);
      setUpdatedAt();
    }
    load().catch((err) => console.warn('儀表盤刷新失敗', err));
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.dashboard = { init, onShow };
})();
