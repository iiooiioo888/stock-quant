/* global Api, echarts */

(() => {
  const $id = (id) => document.getElementById(id);
  const charts = {};
  let loaded = false;

  function ensureHeatmapTile() {
    const row = $id('cf-heatmap-row');
    if (!row || row.querySelector('.pnl')) return;
    const D = window.StockQPro?.UI?.Dashboard;
    const UI = window.StockQPro?.UI;
    if (!D || !UI) return;
    UI.mount(row, D.HeatmapTile({ id: 'cf-heatmap', title: '板塊熱力' }));
  }

  function ensureChartTiles() {
    const grid = $id('cf-charts-grid');
    if (!grid || grid.querySelector('.pnl')) return;
    const D = window.StockQPro?.UI?.Dashboard;
    const UI = window.StockQPro?.UI;
    if (!D || !UI) return;
    UI.mount(grid, [
      D.ChartTile({ id: 'cf-eq', title: '市場資金流向', badge: '20D' }),
      D.ChartTile({ id: 'cf-dd', title: '北向資金', badge: '20D' }),
    ]);
  }

  async function load() {
    await window.StockQPro?.charts?.ensureEcharts?.();
    ensureChartTiles();
    ensureHeatmapTile();

    const d = await Api.get('/api/dashboard/market-charts?days=20', { silent: true }).catch(() => null);
    if (!d) return;

    const D = window.StockQPro?.UI?.Dashboard;
    if (!D) return;

    try {
      D.renderHeatmapCells('cf-heatmap', d.sector_heatmap || []);

      const mf = Array.isArray(d.market_flow) ? d.market_flow : [];
      if (mf.length) {
        D.renderLineChart(
          'cf-eq',
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
          'cf-dd',
          '北向資金',
          nf.map((x) => x.date || x.time || ''),
          nf.map((x) => Number(x.value ?? x.net_inflow ?? x.net ?? 0)),
          'rgba(96,165,250,1)',
          charts,
        );
      }
    } catch (err) {
      console.warn('資金流圖表渲染略過', err);
    }

    loaded = true;
  }

  function bindUiOnce() {
    const btn = $id('cf-refresh-btn');
    if (btn && !btn._cfBound) {
      btn._cfBound = true;
      btn.addEventListener('click', () => {
        loaded = false;
        load().catch((err) => console.warn('資金流刷新失敗', err));
      });
    }
  }

  function init() {
    bindUiOnce();
    load().catch((err) => console.warn('資金流載入失敗', err));
  }

  function onShow() {
    bindUiOnce();
    if (!loaded) {
      load().catch((err) => console.warn('資金流載入失敗', err));
    } else {
      Object.values(charts).forEach((c) => c && c.resize());
    }
  }

  window.addEventListener('resize', () => Object.values(charts).forEach((c) => c && c.resize()));

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.capitalflow = { init, onShow };
})();
