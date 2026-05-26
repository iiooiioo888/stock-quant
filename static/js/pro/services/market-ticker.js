/* global Api */

/**
 * 全球市場掛牌服務
 * - 啟動只拉 topbar（輕量），儀表盤進入時再拉 scope=all
 * - 輪詢僅更新頂欄，避免每次刷新觸發全量指數爬蟲
 */
(() => {
  const TOPBAR_ID = 'topbar-ticker-strip';
  const TOPBAR_DAYS = 14;

  function chartDays() {
    const d = Number(window.StockQPro?.Prefs?.get?.('chartDays'));
    return Number.isFinite(d) && d >= 30 ? d : 90;
  }

  function pollMs() {
    const sec = Number(window.StockQPro?.Prefs?.get?.('marketPollSec'));
    if (!Number.isFinite(sec) || sec <= 0) return 0;
    return sec * 1000;
  }

  const state = {
    quotes: [],
    payload: null,
    topbarLoading: false,
    fullLoading: false,
    timer: null,
    listeners: new Set(),
  };

  function notify() {
    const snap = state.payload || { indices: state.quotes, groups: {}, group_order: [], group_labels: {} };
    state.listeners.forEach((fn) => {
      try { fn(snap); } catch (_) {}
    });
  }

  async function fetchPayload(days = 90) {
    const data = await Api.get(
      `/api/indices/charts?days=${days}&scope=all`,
      { silent: true },
    ).catch(() => null);
    if (!data || !Array.isArray(data.indices)) {
      return { indices: [], groups: {}, group_order: [], group_labels: {}, providers: {} };
    }
    return data;
  }

  async function fetchTopbarQuotes() {
    const data = await Api.get(
      `/api/indices/charts?days=${TOPBAR_DAYS}&scope=topbar`,
      { silent: true },
    ).catch(() => null);
    return Array.isArray(data?.indices) ? data.indices : [];
  }

  function renderTopbar() {
    const D = window.StockQPro?.UI?.Dashboard;
    const root = document.getElementById(TOPBAR_ID);
    if (!D || !root) return;
    const list = state.quotes.length
      ? state.quotes
      : (state.payload?.indices || []).filter((q) => q.topbar !== false);
    D.updateTickerStrip(root, list, {
      compact: true,
      topbar: true,
      shortNames: true,
      incremental: true,
    });
  }

  async function refreshTopbar() {
    if (state.topbarLoading) return state.quotes;
    state.topbarLoading = true;
    try {
      state.quotes = await fetchTopbarQuotes();
      renderTopbar();
    } finally {
      state.topbarLoading = false;
    }
    return state.quotes;
  }

  async function ensureFullPayload(force = false) {
    if (state.fullLoading) {
      while (state.fullLoading) {
        // eslint-disable-next-line no-await-in-loop
        await new Promise((r) => setTimeout(r, 80));
      }
      return state.payload;
    }
    if (!force && state.payload?.indices?.length) return state.payload;

    state.fullLoading = true;
    try {
      state.payload = await fetchPayload(chartDays());
      if (!state.quotes.length) {
        state.quotes = (state.payload.indices || []).filter((q) => q.topbar !== false);
        renderTopbar();
      }
      notify();
    } finally {
      state.fullLoading = false;
    }
    return state.payload;
  }

  /** 全量刷新（設定變更或手動） */
  async function refresh() {
    await refreshTopbar();
    const onDashboard = window.StockQPro?.App?.current === 'dashboard';
    if (onDashboard) await ensureFullPayload();
    return state.payload || { indices: state.quotes };
  }

  function subscribe(fn) {
    if (typeof fn === 'function') state.listeners.add(fn);
    return () => state.listeners.delete(fn);
  }

  function setPollInterval(ms) {
    stopPolling();
    const interval = Number(ms);
    if (interval > 0) {
      state.timer = setInterval(() => refreshTopbar(), interval);
    }
  }

  function startPolling() {
    stopPolling();
    const ms = pollMs();
    if (ms > 0) setPollInterval(ms);
  }

  function stopPolling() {
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.services = window.StockQPro.services || {};
  const marketTicker = {
    refresh,
    refreshTopbar,
    ensureFullPayload,
    subscribe,
    getQuotes: () => state.quotes.slice(),
    getPayload: () => state.payload,
    startPolling,
    stopPolling,
    setPollInterval,
    chartDays,
  };
  window.StockQPro.services.marketTicker = marketTicker;
  window.StockQPro.MarketTicker = marketTicker;

  const boot = () => {
    if (typeof Api !== 'undefined' && Api.clearGetCache) {
      Api.clearGetCache('/api/indices/charts');
    }
    refreshTopbar().then(() => startPolling());
    window.addEventListener('stockq:prefs-changed', () => {
      if (Api.clearGetCache) Api.clearGetCache('/api/indices/charts');
      state.payload = null;
      refreshTopbar()
        .then(() => ensureFullPayload(true))
        .then(() => startPolling());
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
