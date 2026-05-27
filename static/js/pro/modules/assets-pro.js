/* global Api, echarts */

/**
 * 資產庫 — 12 分組目錄 + 全球標的詳情（K 線 / 財報 / 新聞）
 */
(() => {
  const UI = window.StockQPro?.UI;
  const Dash = window.StockQPro?.UI?.Dashboard;
  if (!UI) return;

  const FIN_LABELS = {
    pe_ttm: '市盈率 TTM',
    pb: '市淨率',
    roe: 'ROE (%)',
    eps: '每股收益',
    bvps: '每股淨資產',
    total_mv: '總市值',
    circulating_mv: '流通市值',
    gross_margin: '毛利率 (%)',
    net_margin: '淨利率 (%)',
    debt_ratio: '資產負債率 (%)',
    dividend_yield: '股息率 (%)',
    revenue: '營收',
    net_profit: '淨利潤',
    update_date: '更新日期',
    realtime_price: '即時價',
    realtime_change_pct: '即時漲跌 (%)',
  };

  const STAT_LABELS = {
    open: '今開',
    high: '最高',
    low: '最低',
    prev_close: '昨收',
    volume: '成交量',
    period_high: '區間最高',
    period_low: '區間最低',
    return_1w: '近 1 週',
    return_1m: '近 1 月',
    return_3m: '近 3 月',
    return_6m: '近 6 月',
    ma20: 'MA20',
    ma60: 'MA60',
    dist_ma20_pct: '距 MA20',
    dist_ma60_pct: '距 MA60',
    avg_volume_20: '20 日均量',
    bars: 'K 線根數',
  };

  const DETAIL_TABS = [
    { id: 'quote', label: '行情' },
    { id: 'chart', label: '圖表' },
    { id: 'info', label: '資訊' },
    { id: 'financials', label: '財報' },
    { id: 'news', label: '動態' },
  ];

  const CHART_MODES = [
    { id: 'line', label: '走勢' },
    { id: 'candle', label: 'K 線' },
    { id: 'volume', label: '量價' },
  ];

  const state = {
    catalog: null,
    quotesBySym: {},
    activeGroup: 'all',
    query: '',
    detailSymbol: null,
    detailData: null,
    chartInst: null,
    detailTab: 'quote',
    chartMode: 'line',
  };

  function fmtMv(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    if (n >= 1e12) return `${(n / 1e12).toFixed(2)} 萬億`;
    if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 億`;
    if (n >= 1e4) return `${(n / 1e4).toFixed(2)} 萬`;
    return n.toLocaleString();
  }

  function fmtFinVal(key, val) {
    if (val == null || val === '') return '—';
    if (key === 'total_mv' || key === 'circulating_mv' || key === 'revenue' || key === 'net_profit') {
      return fmtMv(val);
    }
    const n = Number(val);
    if (Number.isFinite(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
    return String(val);
  }

  function openAsset(symbol) {
    if (!symbol) return;
    location.hash = `#/asset/${encodeURIComponent(symbol)}`;
    window.StockQPro?.App?.navFromHash?.();
  }

  function setAssetsView(mode) {
    const list = UI.id('assets-list-view');
    const detail = UI.id('assets-detail-view');
    if (mode === 'detail') {
      if (list) list.classList.add('h');
      if (detail) {
        detail.classList.remove('h');
        detail.style.removeProperty('display');
      }
    } else {
      if (list) list.classList.remove('h');
      if (detail) {
        detail.classList.add('h');
        detail.style.removeProperty('display');
      }
    }
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.openAsset = openAsset;

  function showList() {
    state.detailSymbol = null;
    state.detailData = null;
    setAssetsView('list');
    disposeChart();
    renderList();
  }

  function showDetail(symbol) {
    const sym = String(symbol || '').trim();
    if (state.detailSymbol !== sym) {
      state.detailTab = 'quote';
      state.chartMode = 'line';
      state.detailData = null;
    }
    state.detailSymbol = sym;
    setAssetsView('detail');
    renderDetail(sym);
  }

  function fmtVol(v) {
    const n = Number(v);
    if (!Number.isFinite(n) || n <= 0) return '—';
    if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 億股`;
    if (n >= 1e4) return `${(n / 1e4).toFixed(2)} 萬股`;
    return n.toLocaleString();
  }

  function fmtPct(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
  }

  function disposeChart() {
    if (state.chartInst) {
      try { state.chartInst.dispose(); } catch (_) {}
      state.chartInst = null;
    }
  }

  function parseKlineSeries(kline) {
    const dates = [];
    const closes = [];
    const ohlc = [];
    const vols = [];
    (kline || []).forEach((k) => {
      const d = k.date || k.time || k.t;
      const c = Number(k.close ?? k.c);
      if (!d || !Number.isFinite(c)) return;
      dates.push(d);
      closes.push(c);
      vols.push(Number(k.volume ?? 0) || 0);
      ohlc.push([
        Number(k.open ?? k.o ?? c),
        Number(k.close ?? k.c ?? c),
        Number(k.low ?? k.l ?? c),
        Number(k.high ?? k.h ?? c),
      ]);
    });
    return { dates, closes, ohlc, vols, ok: dates.length >= 2 };
  }

  function setDetailTab(tab) {
    state.detailTab = tab;
    document.querySelectorAll('[data-asset-tab]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-asset-tab') === tab);
    });
    paintDetailPanel();
  }

  function setChartMode(mode) {
    state.chartMode = mode;
    document.querySelectorAll('[data-chart-mode]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-chart-mode') === mode);
    });
    if (state.detailTab === 'chart' && state.detailData?.kline) {
      requestAnimationFrame(() => renderMainChart(mode, state.detailData.kline));
    }
  }

  function filteredInstruments() {
    const cat = state.catalog;
    if (!cat?.instruments) return [];
    let rows = cat.instruments;
    if (state.activeGroup && state.activeGroup !== 'all') {
      rows = rows.filter((r) => r.group === state.activeGroup);
    }
    const q = String(state.query || '').trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) =>
        String(r.symbol || '').toLowerCase().includes(q)
        || String(r.name || '').toLowerCase().includes(q),
      );
    }
    return rows;
  }

  function renderList() {
    const root = UI.id('assets-grid');
    const meta = UI.id('assets-meta');
    if (!root) return;

    const rows = filteredInstruments();
    const total = state.catalog?.total ?? rows.length;

    if (meta) {
      meta.textContent = `顯示 ${rows.length} / ${total} 檔 · 12 分組資產庫`;
    }

    if (!rows.length) {
      UI.mount(root, UI.h('div', { class: 'assets-empty' }, '沒有符合條件的標的'));
      return;
    }

    const cards = rows.map((inst) => {
      const q = state.quotesBySym[inst.symbol] || {};
      const norm = Dash?.normalizeQuote
        ? Dash.normalizeQuote({ ...inst, ...q, name: inst.name })
        : { name: inst.name, symbol: inst.symbol, priceText: '--', pctText: '--', toneClass: 'up' };
      const pctCls = norm.toneClass === 'down' ? 'down' : 'up';
      return UI.h('article', {
        class: `asset-card asset-card--${pctCls}`,
        dataset: { assetSymbol: inst.symbol },
        title: `${inst.name} (${inst.symbol})`,
        onClick: () => openAsset(inst.symbol),
      },
        UI.h('div', { class: 'asset-card-top' },
          UI.h('span', { class: 'asset-card-name' }, inst.name),
          UI.h('span', { class: `asset-card-pct is-${pctCls}` }, norm.pctText),
        ),
        UI.h('div', { class: 'asset-card-mid' },
          UI.h('span', { class: 'asset-card-price' }, norm.priceText),
          UI.h('div', { class: 'asset-card-spark', html: Dash?.sparklineSvg?.(norm.kline, norm.dir) || '' }),
        ),
        UI.h('div', { class: 'asset-card-foot' },
          UI.h('span', { class: 'asset-card-sym' }, inst.symbol),
          UI.h('span', { class: 'badge b-bl' }, inst.group_label || inst.group),
        ),
      );
    });

    UI.mount(root, UI.h('div', { class: 'assets-grid-inner' }, ...cards));
  }

  function renderGroupPills() {
    const el = UI.id('assets-group-pills');
    if (!el || !state.catalog) return;
    const groups = state.catalog.groups || {};
    const order = state.catalog.group_order || Object.keys(groups);
    const pills = [
      UI.h('button', {
        type: 'button',
        class: `cat-pill ${state.activeGroup === 'all' ? 'on' : ''}`,
        onClick: () => { state.activeGroup = 'all'; renderGroupPills(); renderList(); },
      }, `全部 (${state.catalog.total || 0})`),
      ...order.map((gid) => {
        const g = groups[gid] || {};
        const cnt = g.count || 0;
        return UI.h('button', {
          type: 'button',
          class: `cat-pill ${state.activeGroup === gid ? 'on' : ''}`,
          onClick: () => { state.activeGroup = gid; renderGroupPills(); renderList(); },
        }, `${g.label || gid} (${cnt})`);
      }),
    ];
    UI.mount(el, UI.h('div', { class: 'assets-pills-row' }, ...pills));
  }

  async function loadCatalog() {
    const data = await Api.getAssetsCatalog();
    state.catalog = data;
    renderGroupPills();
    renderList();
  }

  async function loadQuotes() {
    try {
      const days = Number(window.StockQPro?.Prefs?.get?.('chartDays')) || 90;
      const data = await Api.getIndicesCharts(days, 'all');
      const map = {};
      (data.indices || []).forEach((item) => {
        if (item.symbol) map[item.symbol] = item;
      });
      state.quotesBySym = map;
      renderList();
    } catch (e) {
      console.warn('資產庫報價載入失敗', e);
    }
  }

  function kpiCell(key, disp, raw) {
    const tone = (String(key).startsWith('return_') || String(key).startsWith('dist_'))
      && Number.isFinite(Number(raw))
      ? (Number(raw) >= 0 ? 'up' : 'down')
      : '';
    return UI.h('div', { class: 'asset-kpi' },
      UI.h('span', { class: 'asset-kpi-label' }, STAT_LABELS[key] || key),
      UI.h('span', { class: `asset-kpi-val${tone ? ` is-${tone}` : ''}` },
        typeof disp === 'number' ? disp.toLocaleString(undefined, { maximumFractionDigits: 4 }) : String(disp)),
    );
  }

  function renderKpiGroups(stats, quote) {
    const s = stats || {};
    const groups = [
      {
        title: '當日行情',
        items: [
          ['open', s.open, s.open],
          ['high', s.high, s.high],
          ['low', s.low, s.low],
          ['prev_close', s.prev_close, s.prev_close],
          ['volume', fmtVol(s.volume), s.volume],
        ],
      },
      {
        title: '區間統計',
        items: [
          ['period_high', s.period_high, s.period_high],
          ['period_low', s.period_low, s.period_low],
          ['avg_volume_20', fmtVol(s.avg_volume_20), s.avg_volume_20],
          ['bars', s.bars != null ? `${s.bars} 根` : null, s.bars],
        ],
      },
      {
        title: '漲跌幅',
        items: [
          ['return_1w', fmtPct(s.return_1w), s.return_1w],
          ['return_1m', fmtPct(s.return_1m), s.return_1m],
          ['return_3m', fmtPct(s.return_3m), s.return_3m],
          ['return_6m', fmtPct(s.return_6m), s.return_6m],
        ],
      },
      {
        title: '技術參考',
        items: [
          ['ma20', s.ma20, s.ma20],
          ['ma60', s.ma60, s.ma60],
          ['dist_ma20_pct', fmtPct(s.dist_ma20_pct), s.dist_ma20_pct],
          ['dist_ma60_pct', fmtPct(s.dist_ma60_pct), s.dist_ma60_pct],
        ],
      },
    ];

    const blocks = groups.map((g) => {
      const cells = g.items
        .filter(([, disp]) => disp != null && disp !== '—')
        .map(([key, disp, raw]) => kpiCell(key, disp, raw));
      if (!cells.length) return null;
      return UI.h('div', { class: 'asset-kpi-group' },
        UI.h('div', { class: 'asset-kpi-group-title' }, g.title),
        UI.h('div', { class: 'asset-kpi-group-grid' }, ...cells),
      );
    }).filter(Boolean);

    if (!blocks.length) {
      return UI.h('div', { class: 'assets-empty' }, '暫無行情統計');
    }
    const cur = quote?.currency ? `計價：${quote.currency}` : '';
    return UI.h('div', { class: 'asset-detail-kpi-groups' },
      cur ? UI.h('p', { class: 'assets-hint', style: { marginBottom: '8px' } }, cur) : null,
      ...blocks,
    );
  }

  function renderMainChart(mode, kline) {
    const dom = UI.id('asset-detail-chart');
    if (!dom || !window.echarts) return;
    disposeChart();

    const { dates, closes, ohlc, vols, ok } = parseKlineSeries(kline);
    if (!ok) {
      dom.innerHTML = '<div class="assets-empty">暫無 K 線數據</div>';
      return;
    }

    state.chartInst = echarts.init(dom, null, { renderer: 'canvas' });
    const axisStyle = { color: '#94a3b8', fontSize: 10 };
    const split = { lineStyle: { color: 'rgba(148,163,184,.12)' } };

    if (mode === 'volume') {
      state.chartInst.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', axisPointer: { link: [{ xAxisIndex: 'all' }] } },
        axisPointer: { link: [{ xAxisIndex: 'all' }] },
        grid: [
          { left: 52, right: 16, top: 20, height: '52%' },
          { left: 52, right: 16, top: '72%', height: '18%' },
        ],
        xAxis: [
          { type: 'category', data: dates, axisLabel: { show: false }, gridIndex: 0 },
          { type: 'category', data: dates, axisLabel: axisStyle, gridIndex: 1 },
        ],
        yAxis: [
          { scale: true, axisLabel: axisStyle, splitLine: split, gridIndex: 0 },
          { scale: true, axisLabel: axisStyle, splitLine: split, gridIndex: 1 },
        ],
        series: [
          {
            type: 'line',
            data: closes,
            xAxisIndex: 0,
            yAxisIndex: 0,
            smooth: true,
            symbol: 'none',
            lineStyle: { width: 2, color: '#60a5fa' },
            areaStyle: { color: 'rgba(96,165,250,.1)' },
          },
          {
            type: 'bar',
            data: vols,
            xAxisIndex: 1,
            yAxisIndex: 1,
            itemStyle: { color: 'rgba(96,165,250,.45)' },
          },
        ],
      });
    } else if (mode === 'candle') {
      state.chartInst.setOption({
        backgroundColor: 'transparent',
        grid: { left: 52, right: 16, top: 20, bottom: 40 },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: dates, axisLabel: axisStyle },
        yAxis: { scale: true, axisLabel: axisStyle, splitLine: split },
        series: [{
          type: 'candlestick',
          data: ohlc,
          itemStyle: { color: '#f87171', color0: '#34d399', borderColor: '#f87171', borderColor0: '#34d399' },
        }],
      });
    } else {
      state.chartInst.setOption({
        backgroundColor: 'transparent',
        grid: { left: 52, right: 16, top: 20, bottom: 40 },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: axisStyle },
        yAxis: { scale: true, axisLabel: axisStyle, splitLine: split },
        series: [{
          type: 'line',
          data: closes,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2, color: '#60a5fa' },
          areaStyle: { color: 'rgba(96,165,250,.12)' },
        }],
      });
    }
    state.chartInst.resize();
  }

  function detailTabBtn({ id, label }) {
    return UI.h('button', {
      type: 'button',
      class: `assets-tab${state.detailTab === id ? ' on' : ''}`,
      dataset: { assetTab: id },
      onClick: () => setDetailTab(id),
    }, label);
  }

  function chartModeBtn({ id, label }) {
    return UI.h('button', {
      type: 'button',
      class: `chart-mode-pill${state.chartMode === id ? ' on' : ''}`,
      dataset: { chartMode: id },
      onClick: () => setChartMode(id),
    }, label);
  }

  function renderFinTable(rows) {
    return UI.h('table', { class: 'assets-fin-table' },
      UI.h('tbody', null,
        ...rows.map(([k, v]) => UI.h('tr', null, UI.h('th', null, k), UI.h('td', null, v || '—'))),
      ),
    );
  }

  function renderSection(title, body) {
    return UI.h('section', { class: 'asset-detail-section' },
      UI.h('h3', { class: 'asset-section-title' }, title),
      body,
    );
  }

  function renderQuotePanel(d) {
    return UI.h('div', { class: 'asset-panel asset-panel--quote' },
      renderKpiGroups(d.stats, d.quote),
    );
  }

  function renderChartPanel(d) {
    return UI.h('div', { class: 'asset-panel asset-panel--chart' },
      UI.h('p', { class: 'assets-hint' },
        `數據來源：${d.kline_source || '—'} · ${d.stats?.bars || 0} 根 K 線 · ${d.stats?.period_days || '—'} 日`,
      ),
    );
  }

  function renderInfoPanel(d) {
    const blocks = [];
    const intro = (d.profile?.intro || '').trim();
    if (intro) {
      blocks.push(renderSection('公司簡介', UI.h('p', { class: 'assets-profile' }, intro.slice(0, 2000))));
    }
    blocks.push(renderSection('標的資訊', renderFinTable([
      ['名稱', d.name || d.profile?.name],
      ['代碼', d.symbol],
      ['市場', d.market_label || d.profile?.market_label],
      ['交易所', d.profile?.exchange],
      ['行業', d.profile?.industry],
      ['上市日期', d.profile?.list_date],
    ])));

    const fin = d.financials || {};
    const finRows = ['pe_ttm', 'pb', 'total_mv', 'roe', 'dividend_yield']
      .filter((k) => fin[k] != null)
      .map((k) => [FIN_LABELS[k] || k, fmtFinVal(k, fin[k])]);
    if (finRows.length) {
      blocks.push(renderSection('估值快照', renderFinTable(finRows)));
    }

    const links = Array.isArray(d.links) ? d.links : [];
    if (links.length) {
      blocks.push(renderSection('外部連結', renderLinks(links)));
    }

    return UI.h('div', { class: 'asset-panel asset-panel--info' }, ...blocks);
  }

  function renderNewsPanel(d) {
    const blocks = [];
    blocks.push(renderSection('新聞與資訊', renderNews(d.news)));
    return UI.h('div', { class: 'asset-panel asset-panel--news' }, ...blocks);
  }

  function paintDetailPanel() {
    const d = state.detailData;
    if (!d) return;

    const chartBlock = UI.id('assets-detail-chart-block');
    const body = UI.id('assets-detail-body');
    if (!body) return;

    if (chartBlock) {
      chartBlock.classList.toggle('h', state.detailTab !== 'chart');
    }

    if (state.detailTab === 'chart') {
      requestAnimationFrame(() => renderMainChart(state.chartMode, d.kline));
      UI.mount(body, renderChartPanel(d));
      return;
    }

    disposeChart();
    const panels = {
      quote: renderQuotePanel,
      info: renderInfoPanel,
      financials: (data) => UI.h('div', { class: 'asset-panel' }, renderFinancials(data.financials, data.market)),
      news: renderNewsPanel,
    };
    const render = panels[state.detailTab];
    UI.mount(body, render ? render(d) : UI.h('div', { class: 'assets-empty' }, '暫無內容'));
  }

  function buildDetailHero(d, symbol) {
    const q = d.quote || {};
    const pct = Number(q.change_pct);
    const up = Number.isFinite(pct) ? pct >= 0 : true;
    const pctCls = up ? 'up' : 'down';
    const price = Number(q.price);
    const priceText = Number.isFinite(price)
      ? price.toLocaleString(undefined, { maximumFractionDigits: 4 })
      : '—';
    const pctText = Number.isFinite(pct) ? `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` : '—';
    const change = Number(q.change);
    const changeText = Number.isFinite(change)
      ? `${change >= 0 ? '+' : ''}${change.toLocaleString(undefined, { maximumFractionDigits: 4 })}`
      : '';

    return UI.h('header', { class: 'asset-detail-hero' },
      UI.h('div', { class: 'asset-detail-hero-left' },
        UI.h('button', {
          type: 'button',
          class: 'btn btn-s btn-bl asset-back-btn',
          onClick: () => {
            location.hash = '#/assets';
            showList();
          },
        }, '← 返回資產庫'),
        UI.h('div', { class: 'asset-detail-title' },
          UI.h('h1', null, d.name || symbol),
          UI.h('div', { class: 'asset-detail-sub' },
            UI.h('span', { class: 'badge b-ac' }, d.group_label || d.group || '—'),
            UI.h('span', { class: 'mono asset-detail-code' }, symbol),
            d.market_label ? UI.h('span', { class: 'badge b-bl' }, d.market_label) : null,
          ),
        ),
      ),
      UI.h('div', { class: `asset-detail-quote is-${pctCls}` },
        UI.h('div', { class: 'asset-detail-quote-main' },
          UI.h('span', { class: 'asset-detail-price' }, priceText),
          q.currency ? UI.h('span', { class: 'asset-detail-ccy' }, q.currency) : null,
        ),
        UI.h('div', { class: 'asset-detail-quote-sub' },
          UI.h('span', { class: 'asset-detail-pct' }, pctText),
          changeText ? UI.h('span', { class: 'asset-detail-chg' }, changeText) : null,
        ),
        q.source ? UI.h('span', { class: 'ticker-card-src' }, q.source) : null,
      ),
    );
  }

  function mountDetailShell(d, symbol) {
    const root = UI.id('assets-detail-root');
    if (!root) return;

    UI.mount(root, UI.h('div', { class: 'asset-detail-wrap' },
      buildDetailHero(d, symbol),
      UI.h('nav', { class: 'asset-detail-tabs', 'aria-label': '資產詳情分頁' },
        ...DETAIL_TABS.map((t) => detailTabBtn(t)),
      ),
      UI.h('div', { class: 'asset-detail-body' },
        UI.h('div', { id: 'assets-detail-chart-block', class: 'asset-detail-chart-block h' },
          UI.h('div', { class: 'asset-chart-toolbar' },
            UI.h('span', { class: 'asset-chart-toolbar-label' }, '圖表類型'),
            UI.h('div', { class: 'asset-chart-mode-row' },
              ...CHART_MODES.map((m) => chartModeBtn(m)),
            ),
          ),
          UI.h('div', { id: 'asset-detail-chart', class: 'asset-detail-chart' }),
        ),
        UI.h('div', { id: 'assets-detail-body', class: 'assets-tab-panel' }),
      ),
    ));

    paintDetailPanel();
  }

  function renderLinks(links) {
    const items = Array.isArray(links) ? links : [];
    if (!items.length) {
      return UI.h('div', { class: 'assets-empty' }, '暫無外部連結');
    }
    return UI.h('ul', { class: 'assets-links-list' },
      ...items.map((lnk) => UI.h('li', null,
        UI.h('a', { href: lnk.url, target: '_blank', rel: 'noopener', class: 'assets-link-item' },
          UI.h('span', { class: 'assets-link-title' }, lnk.title || lnk.url),
          UI.h('span', { class: 'assets-link-src' }, lnk.source || ''),
        ),
      )),
    );
  }

  function renderFinancials(fin, market) {
    if (!fin || !fin.has_data) {
      const hint = market === 'hk_stock'
        ? '暫無結構化財報（可至「資訊」分頁查看估值快照與外部連結）'
        : '暫無財報數據（A 股將自動從東財補齊，請稍後重試）';
      return UI.h('div', { class: 'assets-empty' }, hint);
    }
    const rows = Object.keys(FIN_LABELS)
      .filter((k) => fin[k] != null && k !== 'has_data' && k !== 'code')
      .map((k) => UI.h('tr', null,
        UI.h('th', null, FIN_LABELS[k] || k),
        UI.h('td', null, fmtFinVal(k, fin[k])),
      ));
    const src = fin.source ? UI.h('p', { class: 'assets-hint' }, `數據來源：${fin.source}${fin.update_date ? ` · 更新 ${fin.update_date}` : ''}`) : null;
    return UI.h('div', null,
      src,
      UI.h('table', { class: 'assets-fin-table' },
        UI.h('tbody', null, ...rows),
      ),
    );
  }

  function renderNews(news) {
    const items = Array.isArray(news) ? news : [];
    if (!items.length) {
      return UI.h('div', { class: 'assets-empty' }, '暫無新聞');
    }
    return UI.h('ul', { class: 'assets-news-list' },
      ...items.map((n) => {
        const title = n.title || '—';
        const inner = UI.h('div', { class: 'assets-news-item' },
          UI.h('div', { class: 'assets-news-title' }, title),
          UI.h('div', { class: 'assets-news-meta' },
            n.source ? UI.h('span', null, n.source) : null,
            n.time ? UI.h('span', null, ` · ${n.time}`) : null,
          ),
        );
        if (n.url) {
          return UI.h('li', null, UI.h('a', { href: n.url, target: '_blank', rel: 'noopener' }, inner));
        }
        return UI.h('li', null, inner);
      }),
    );
  }

  async function renderDetail(symbol) {
    const root = UI.id('assets-detail-root');
    if (!root) return;
    const sym = String(symbol || '').trim();

    if (state.detailData && state.detailSymbol === sym && root.querySelector('.asset-detail-wrap')) {
      paintDetailPanel();
      return;
    }

    UI.mount(root, UI.h('div', { class: 'assets-loading' }, '載入中…'));

    try {
      const days = Number(window.StockQPro?.Prefs?.get?.('chartDays')) || 180;
      const res = await Api.getAssetDetail(sym, days);
      const d = res.detail || res;
      state.detailData = d;
      mountDetailShell(d, sym);
    } catch (e) {
      state.detailData = null;
      UI.mount(root, UI.h('div', { class: 'assets-empty er' },
        `載入失敗：${e.message || e}`,
        UI.h('button', {
          type: 'button',
          class: 'btn btn-s',
          onClick: () => showList(),
        }, '返回列表'),
      ));
    }
  }

  const Pages = {
    init() {
      const search = UI.id('assets-search');
      if (search && !search.dataset.bound) {
        search.dataset.bound = '1';
        search.addEventListener('input', () => {
          state.query = search.value;
          renderList();
        });
      }
      const backBtn = document.querySelector('[data-assets-back]');
      if (backBtn && !backBtn.dataset.bound) {
        backBtn.dataset.bound = '1';
        backBtn.addEventListener('click', () => {
          location.hash = '#/assets';
          showList();
        });
      }
      if (state.detailSymbol) {
        showDetail(state.detailSymbol);
        return;
      }
      if (!state.catalog) {
        loadCatalog().then(() => loadQuotes());
      } else {
        renderGroupPills();
        renderList();
      }
    },

    openDetail(symbol) {
      showDetail(symbol);
    },

    showList,
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.assets = Pages;

  document.addEventListener('click', (e) => {
    const card = e.target.closest('.ticker-card[data-symbol]');
    if (!card?.dataset?.symbol) return;
    if (e.target.closest('a')) return;
    openAsset(card.dataset.symbol);
  });
})();
