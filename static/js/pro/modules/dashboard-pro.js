/* global Api, echarts */

(() => {
  const $id = (id) => document.getElementById(id);
  const charts = {};
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

  async function loadChartsBundle() {
    const D = window.StockQPro?.UI?.Dashboard;
    if (!D) return;
    const d = await Api.get('/api/dashboard/market-charts?days=20', { silent: true }).catch(() => null);
    if (!d) return;

    try {
      D.renderHeatmapCells('heatmap', d.sector_heatmap || []);

      const mf = Array.isArray(d.market_flow) ? d.market_flow : [];
      if (mf.length) {
        D.renderLineChart(
          'd-eq',
          '市場資金',
          mf.map((x) => x.date || x.time || ''),
          mf.map((x) => Number(x.value ?? x.net_inflow ?? x.net ?? 0)),
          'rgba(232,184,48,1)',
          charts,
        );
      }

      const nf = Array.isArray(d.north_flow) ? d.north_flow : [];
      if (nf.length) {
        D.renderLineChart(
          'd-dd',
          '北向資金',
          nf.map((x) => x.date || x.time || ''),
          nf.map((x) => Number(x.value ?? x.net_inflow ?? x.net ?? 0)),
          'rgba(96,165,250,1)',
          charts,
        );
      }
    } catch (err) {
      console.warn('儀表盤圖表渲染略過', err);
    }
  }

  async function load() {
    if (loadPromise) return loadPromise;

    loadPromise = (async () => {
      ensureLayout();
      const t0 = performance.now();
      const [health, cfg] = await Promise.all([
        Api.get('/api/health', { silent: true }).catch(() => null),
        Api.get('/api/config', { silent: true }).catch(() => null),
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
      setUpdatedAt();

      await loadChartsBundle();
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

  function bindUiOnce() {
    if (uiBound) return;
    uiBound = true;

    const ticker = window.StockQPro?.services?.marketTicker;
    if (ticker?.subscribe && !unsubTicker) {
      unsubTicker = ticker.subscribe((payload) => {
        if (!mounted) ensureLayout();
        renderQuoteBoard(payload);
        setUpdatedAt();
      });
    }
  }

  function init() {
    ensureLayout();
    bindUiOnce();
    page._ready = true;
    load().catch((err) => {
      showLoadIssue('部分資料未載入，可點刷新重試');
      console.warn('儀表盤載入失敗', err);
    });
  }

  function onShow() {
    const ticker = window.StockQPro?.services?.marketTicker;
    if (ticker?.ensureFullPayload) {
      ticker.ensureFullPayload().then(() => load()).catch((err) => console.warn('儀表盤刷新失敗', err));
    } else {
      load().catch((err) => console.warn('儀表盤刷新失敗', err));
    }
  }

  window.addEventListener('resize', () => Object.values(charts).forEach((c) => c && c.resize()));

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.dashboard = { init, onShow };
})();
