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
    { id: 'third', label: '第三方' },
  ];

  const CHART_MODES = [
    { id: 'line', label: '走勢' },
    { id: 'candle', label: 'K 線' },
    { id: 'volume', label: '量價' },
  ];

  const STOCK_GROUPS = new Set(['a_share', 'hk_stock', 'us_stock']);
  const RENDER_PAGE = 36;

  const state = {
    catalog: null,
    quotesBySym: {},
    /** stocks=僅三地股票 | tradeable=有詳情 | all=完整 Universe */
    viewScope: 'stocks',
    listLimit: RENDER_PAGE,
    activeSector: 'all',
    activeTheme: 'all',
    // 1/2/3 級分類（l1=group；l2/l3 由後端提供，或前端推導）
    activeL1: 'all',
    activeL2: 'all',
    activeL3: 'all',
    query: '',
    detailSymbol: null,
    detailData: null,
    chartInst: null,
    detailTab: 'quote',
    chartMode: 'line',
    detailPrice: null,
    drawerMode: null,
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

  function normalizeAssetSymbol(symbol) {
    const fn = window.StockQPro?.SymbolUtils?.normalizeAssetSymbol;
    if (fn) return fn(symbol);
    return String(symbol || '').trim().toUpperCase();
  }

  function openAsset(symbol) {
    if (window.StockQPro?.App?.openAsset) {
      window.StockQPro.App.openAsset(symbol);
      return;
    }
    const sym = normalizeAssetSymbol(symbol);
    if (!sym) return;
    location.hash = `#/asset/${encodeURIComponent(sym)}`;
    window.StockQPro?.App?.navFromHash?.();
  }

  function filterSummaryText() {
    const parts = [];
    if (state.viewScope === 'stocks') parts.push('股票專區');
    else if (state.viewScope === 'tradeable') parts.push('可詳情');
    else parts.push('完整目錄');
    if (state.activeTheme && state.activeTheme !== 'all') {
      const pack = (state.catalog?.theme_packs || []).find((p) => p.id === state.activeTheme);
      parts.push(pack?.label || state.activeTheme);
    }
    if (state.activeL1 && state.activeL1 !== 'all') parts.push(state.activeL1);
    if (state.activeL2 && state.activeL2 !== 'all') parts.push(state.activeL2);
    if (state.activeL3 && state.activeL3 !== 'all') parts.push(state.activeL3);
    if (state.activeSector && state.activeSector !== 'all') {
      const labels = state.catalog?.sector_labels || state.catalog?.stock_sector_labels || {};
      parts.push(labels[state.activeSector] || state.activeSector);
    }
    if (state.query) parts.push(`「${state.query}」`);
    return parts.join(' · ');
  }

  function paintFilterSummary() {
    const el = UI.id('assets-filter-summary');
    if (el) el.textContent = filterSummaryText();
  }

  function ensureDrawerPortal() {
    const drawer = UI.id('assets-drawer');
    const backdrop = UI.id('assets-drawer-backdrop');
    if (backdrop && backdrop.parentElement !== document.body) document.body.appendChild(backdrop);
    if (drawer && drawer.parentElement !== document.body) document.body.appendChild(drawer);
  }

  function setDrawer(mode) {
    ensureDrawerPortal();
    state.drawerMode = mode;
    const drawer = UI.id('assets-drawer');
    const backdrop = UI.id('assets-drawer-backdrop');
    const tools = UI.id('assets-tools-panel');
    const detail = UI.id('assets-detail-view');
    const title = UI.id('assets-drawer-title');
    const desc = UI.id('assets-drawer-desc');
    const ft = UI.id('assets-drawer-ft');
    const toolsBtn = UI.id('assets-tools-open');
    const open = !!mode;
    if (drawer) {
      drawer.hidden = false;
      drawer.classList.toggle('assets-drawer--wide', mode === 'detail');
      drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
      if ('inert' in drawer) drawer.inert = !open;
    }
    if (backdrop) backdrop.hidden = false;
    if (tools) tools.classList.toggle('h', mode !== 'tools');
    if (detail) detail.classList.toggle('h', mode !== 'detail');
    if (ft) ft.hidden = mode !== 'tools';
    if (toolsBtn) {
      toolsBtn.classList.toggle('on', mode === 'tools');
      toolsBtn.setAttribute('aria-expanded', mode === 'tools' ? 'true' : 'false');
    }
    if (title) title.textContent = mode === 'detail' ? (state.detailSymbol || '資產詳情') : '篩選工具';
    if (desc) {
      desc.textContent = mode === 'detail'
        ? '行情、圖表與快捷操作'
        : '主題、行業與分層目錄';
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.body.classList.toggle('assets-drawer-open', open);
      });
    });
    if (!open) {
      disposeChart();
      window.setTimeout(() => {
        if (state.drawerMode) return;
        if (drawer) drawer.hidden = true;
        if (backdrop) backdrop.hidden = true;
      }, 240);
    } else {
      requestAnimationFrame(() => {
        try { state.chartInst?.resize?.(); } catch (_) {}
      });
    }
  }

  function closeDrawer({ resetHash = true } = {}) {
    const wasDetail = state.drawerMode === 'detail';
    setDrawer(null);
    if (wasDetail) {
      state.detailSymbol = null;
      state.detailData = null;
      if (resetHash && /^#\/asset\//.test(location.hash)) {
        location.hash = '#/assets';
      }
      renderList({ animate: false });
    }
  }

  function showList() {
    closeDrawer({ resetHash: true });
    renderList();
  }

  function resetToolsFilters() {
    state.viewScope = 'stocks';
    state.activeL1 = 'all';
    state.activeL2 = 'all';
    state.activeL3 = 'all';
    state.activeSector = 'all';
    state.activeTheme = 'all';
    state.listLimit = RENDER_PAGE;
    renderGroupPills();
    renderList();
  }

  function openToolsDrawer() {
    if (state.drawerMode === 'tools') {
      closeDrawer({ resetHash: false });
      return;
    }
    setDrawer('tools');
    renderGroupPills();
  }

  function showDetail(symbol) {
    const sym = normalizeAssetSymbol(symbol);
    if (state.detailSymbol !== sym) {
      state.detailTab = 'quote';
      state.chartMode = 'line';
      state.detailData = null;
    }
    state.detailSymbol = sym;
    setDrawer('detail');
    try { window.StockQPro?.WorkContext?.set?.(sym); } catch (_) {}
    renderDetail(sym);
    markSelectedCard(sym);
  }

  function markSelectedCard(symbol) {
    const root = UI.id('assets-grid');
    if (!root) return;
    root.querySelectorAll('.asset-card[data-asset-symbol]').forEach((el) => {
      el.classList.toggle('is-on', el.dataset.assetSymbol === symbol);
    });
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
    if (state.viewScope === 'stocks') {
      rows = rows.filter((r) => STOCK_GROUPS.has(r.group) && r.asset_class === 'stock');
    } else if (state.viewScope === 'tradeable') {
      rows = rows.filter((r) => r.detail_supported !== false);
    }
    if (state.activeSector && state.activeSector !== 'all') {
      rows = rows.filter((r) => (r.sector || r.sub_class || 'other') === state.activeSector);
    }
    if (state.activeTheme && state.activeTheme !== 'all') {
      rows = rows.filter((r) => Array.isArray(r.themes) && r.themes.includes(state.activeTheme));
    }
    if (state.activeL1 && state.activeL1 !== 'all') rows = rows.filter((r) => r.group === state.activeL1);
    if (state.activeL2 && state.activeL2 !== 'all') rows = rows.filter((r) => (r.l2 || r.asset_class) === state.activeL2);
    if (state.activeL3 && state.activeL3 !== 'all') rows = rows.filter((r) => String(r.l3 || '') === state.activeL3);
    const q = String(state.query || '').trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) =>
        String(r.symbol || '').toLowerCase().includes(q)
        || String(r.name || '').toLowerCase().includes(q)
        || String(r.sector_label || '').toLowerCase().includes(q)
        || String(r.exchange || '').toLowerCase().includes(q),
      );
    }
    return rows;
  }

  function scopeBaseRows() {
    const cat = state.catalog;
    if (!cat?.instruments) return [];
    let rows = cat.instruments;
    if (state.viewScope === 'stocks') {
      rows = rows.filter((r) => STOCK_GROUPS.has(r.group) && r.asset_class === 'stock');
    } else if (state.viewScope === 'tradeable') {
      rows = rows.filter((r) => r.detail_supported !== false);
    }
    if (state.activeSector && state.activeSector !== 'all') {
      rows = rows.filter((r) => (r.sector || r.sub_class || 'other') === state.activeSector);
    }
    if (state.activeTheme && state.activeTheme !== 'all') {
      rows = rows.filter((r) => Array.isArray(r.themes) && r.themes.includes(state.activeTheme));
    }
    return rows;
  }

  function bindGridClicks(root) {
    if (!root || root.dataset.boundCards === '1') return;
    root.dataset.boundCards = '1';
    root.addEventListener('click', (e) => {
      const add = e.target.closest('.asset-card-add-alloc');
      if (add) {
        e.preventDefault();
        e.stopPropagation();
        const card = add.closest('.asset-card[data-asset-symbol]');
        const symbol = card?.dataset.assetSymbol;
        if (!symbol) return;
        const name = card.querySelector('.asset-card-name')?.textContent || symbol;
        if (window.StockQPro?.Allocation?.add) {
          window.StockQPro.Allocation.add({ code: symbol, name, quantity: 100 });
          window.StockQPro.Allocation.setOpen?.(true);
        } else {
          window.StockQPro?.App?.toast?.('配置欄載入中，請稍後再試', 'inf');
        }
        return;
      }
      const card = e.target.closest('.asset-card[data-asset-symbol]');
      if (!card || !root.contains(card)) return;
      if (card.classList.contains('is-disabled')) {
        window.StockQPro?.App?.toast?.('此資產目前僅做 Universe 覆蓋（暫無詳情/定價介面）', 'inf');
        return;
      }
      openAsset(card.dataset.assetSymbol);
    });
  }

  function renderList(opts = {}) {
    const root = UI.id('assets-grid');
    const meta = UI.id('assets-meta');
    if (!root) return;

    const rows = filteredInstruments();
    const total = state.catalog?.total ?? rows.length;

    if (meta) {
      const l1 = state.activeL1 !== 'all' ? state.activeL1 : '';
      const l2 = state.activeL2 !== 'all' ? state.activeL2 : '';
      const l3 = state.activeL3 !== 'all' ? state.activeL3 : '';
      const themeLbl = state.activeTheme !== 'all'
        ? (state.catalog?.theme_packs || []).find((p) => p.id === state.activeTheme)?.label
        : '';
      const hint = [themeLbl, l1, l2, l3].filter(Boolean).join(' / ');
      meta.textContent = `顯示 ${rows.length} / ${total} 檔${hint ? ` · ${hint}` : ''}`;
    }
    paintFilterSummary();

    if (!rows.length) {
      UI.mount(root, UI.h('div', { class: 'assets-empty' }, '沒有符合條件的標的'));
      return;
    }

    bindGridClicks(root);
    const esc = UI.escapeHtml;
    const showAll = rows.length <= state.listLimit;
    const visible = showAll ? rows : rows.slice(0, state.listLimit);
    const hiddenN = rows.length - visible.length;

    const html = visible.map((inst) => {
      const q = state.quotesBySym[inst.symbol] || {};
      const norm = Dash?.normalizeQuote
        ? Dash.normalizeQuote({ ...inst, ...q, name: inst.name })
        : { name: inst.name, symbol: inst.symbol, priceText: '--', pctText: '--', toneClass: 'up' };
      const pctCls = norm.toneClass === 'down' ? 'down' : 'up';
      const canDetail = inst.detail_supported !== false;
      const src0 = Array.isArray(inst.price_sources) && inst.price_sources.length ? inst.price_sources[0] : null;
      const srcBadge = src0?.name ? `定價入口：${src0.name}` : '';
      const sectorLbl = inst.sector_label || '';
      const exchLbl = [inst.exchange, inst.currency].filter(Boolean).join(' · ');
      const on = state.detailSymbol === inst.symbol ? ' is-on' : '';
      const dis = canDetail ? '' : ' is-disabled';
      const footBadge = sectorLbl
        ? `<span class="badge b-gr">${esc(sectorLbl)}</span>`
        : `<span class="badge b-bl">${esc(exchLbl || srcBadge || inst.group_label || inst.group || '')}</span>`;
      return `<article class="asset-card asset-card--${pctCls}${dis}${on}" data-asset-symbol="${esc(inst.symbol)}" title="${esc(`${inst.name} (${inst.symbol})`)}">
        <div class="asset-card-top">
          <span class="asset-card-name">${esc(inst.name)}</span>
          <span class="asset-card-pct is-${pctCls}">${esc(norm.pctText)}</span>
        </div>
        <div class="asset-card-mid"><span class="asset-card-price">${esc(norm.priceText)}</span></div>
        <div class="asset-card-foot">
          <span class="asset-card-sym">${esc(inst.symbol)}</span>
          ${footBadge}
          <button type="button" class="asset-card-add-alloc" title="加入我的配置">+配置</button>
        </div>
      </article>`;
    }).join('');

    const more = hiddenN > 0
      ? `<div class="assets-load-more-wrap"><button type="button" class="btn btn-s" id="assets-load-more">載入更多（還有 ${hiddenN} 檔）</button></div>`
      : '';
    root.innerHTML = `<div class="assets-grid-inner">${html}${more}</div>`;
    const moreBtn = UI.id('assets-load-more');
    if (moreBtn) {
      moreBtn.addEventListener('click', () => {
        state.listLimit += RENDER_PAGE;
        renderList();
      });
    }
  }

  function renderThemePacks() {
    if (state.catalog?.theme_packs_locked) {
      return [
        UI.h('div', { class: 'assets-pills-row assets-pills-row--themes assets-theme-locked' },
          UI.h('span', { class: 'assets-theme-locked-msg' }, '主題包與行業標籤篩選需 Pro'),
          UI.h('button', {
            type: 'button',
            class: 'btn btn-s btn-ac',
            onClick: () => window.StockQPro?.App?.nav?.('pricing', { syncHash: true }),
          }, '查看方案'),
        ),
      ];
    }
    const packs = state.catalog?.theme_packs;
    if (!Array.isArray(packs) || !packs.length) return [];
    const pills = [
      UI.h('button', {
        type: 'button',
        class: `cat-pill cat-pill--theme ${state.activeTheme === 'all' ? 'on' : ''}`,
        title: '顯示全部股票專區標的',
        onClick: () => {
          state.activeTheme = 'all';
          renderGroupPills();
          renderList();
        },
      }, '全部主題'),
      ...packs.map((p) => UI.h('button', {
        type: 'button',
        class: `cat-pill cat-pill--theme ${state.activeTheme === p.id ? 'on' : ''}`,
        title: p.description || p.label,
        onClick: () => {
          state.viewScope = 'stocks';
          state.activeTheme = p.id;
          state.activeL1 = 'all';
          state.activeL2 = 'all';
          state.activeL3 = 'all';
          state.activeSector = 'all';
          renderGroupPills();
          renderList();
        },
      }, `${p.label} (${p.catalog_count ?? 0})`)),
    ];
    return [UI.h('div', { class: 'assets-pills-row assets-pills-row--themes' }, ...pills)];
  }

  function renderScopePills() {
    const cat = state.catalog;
    if (!cat) return [];
    const stockN = cat.stock_universe ?? cat.instruments?.filter(
      (r) => STOCK_GROUPS.has(r.group) && r.asset_class === 'stock',
    ).length ?? 0;
    const tradeN = cat.tradeable_count ?? cat.instruments?.filter((r) => r.detail_supported !== false).length ?? 0;
    const totalN = cat.total ?? cat.instruments?.length ?? 0;
    const scopes = [
      { id: 'stocks', label: `股票專區 (${stockN})` },
      { id: 'tradeable', label: `可詳情 (${tradeN})` },
      { id: 'all', label: `完整目錄 (${totalN})` },
    ];
    return scopes.map((s) => UI.h('button', {
      type: 'button',
      class: `cat-pill cat-pill--scope ${state.viewScope === s.id ? 'on' : ''}`,
      onClick: () => {
        state.viewScope = s.id;
        state.listLimit = RENDER_PAGE;
        state.activeL1 = 'all';
        state.activeL2 = 'all';
        state.activeL3 = 'all';
        state.activeSector = 'all';
        state.activeTheme = 'all';
        renderGroupPills();
        renderList();
      },
    }, s.label));
  }

  function renderSectorPills() {
    if (state.viewScope !== 'stocks' && state.viewScope !== 'tradeable') return [];
    const labels = state.catalog?.sector_labels || state.catalog?.stock_sector_labels || {};
    const counts = {};
    (state.catalog?.instruments || []).forEach((r) => {
      if (state.viewScope === 'stocks' && !(STOCK_GROUPS.has(r.group) && r.asset_class === 'stock')) return;
      if (state.viewScope === 'tradeable' && r.detail_supported === false) return;
      const sec = r.sector || 'other';
      counts[sec] = (counts[sec] || 0) + 1;
    });
    const keys = Object.keys(counts).sort(
      (a, b) => (counts[b] - counts[a]) || String(labels[a] || a).localeCompare(String(labels[b] || b), 'zh-Hant'),
    );
    if (keys.length < 2) return [];
    const pills = [
      UI.h('button', {
        type: 'button',
        class: `cat-pill ${state.activeSector === 'all' ? 'on' : ''}`,
        onClick: () => {
          state.activeSector = 'all';
          renderGroupPills();
          renderList();
        },
      }, '全部行業'),
      ...keys.map((k) => UI.h('button', {
        type: 'button',
        class: `cat-pill ${state.activeSector === k ? 'on' : ''}`,
        onClick: () => {
          state.activeSector = k;
          renderGroupPills();
          renderList();
        },
      }, `${labels[k] || k} (${counts[k]})`)),
    ];
    return [UI.h('div', { class: 'assets-pills-row assets-pills-row--sector' }, ...pills)];
  }

  function renderGroupPills() {
    const el = UI.id('assets-group-pills');
    if (!el || !state.catalog) return;
    const tree = state.catalog.hierarchy || null;
    const l1 = tree?.l1 || null;
    const l1Order = Array.isArray(tree?.l1_order) && tree.l1_order.length
      ? tree.l1_order
      : (state.catalog.group_order || Object.keys(state.catalog.groups || {}));

    let l1OrderFiltered = [...l1Order];
    if (state.viewScope === 'stocks') {
      l1OrderFiltered = l1Order.filter((gid) => STOCK_GROUPS.has(gid));
    }

    const baseRows = scopeBaseRows();
    const countByGroup = {};
    baseRows.forEach((r) => {
      const g = r.group || '';
      countByGroup[g] = (countByGroup[g] || 0) + 1;
    });
    const countInScope = (gid) => {
      if (!gid || gid === 'all') return baseRows.length;
      return countByGroup[gid] || 0;
    };

    const pillsL1 = [
      UI.h('button', {
        type: 'button',
        class: `cat-pill ${state.activeL1 === 'all' ? 'on' : ''}`,
        onClick: () => {
          state.activeL1 = 'all';
          state.activeL2 = 'all';
          state.activeL3 = 'all';
          renderGroupPills();
          renderList();
        },
      }, `本分類全部 (${countInScope('all')})`),
      ...l1OrderFiltered.map((gid) => {
        const g = (l1 && l1[gid]) ? l1[gid] : (state.catalog.groups || {})[gid] || {};
        const cnt = countInScope(gid) || g.count || 0;
        return UI.h('button', {
          type: 'button',
          class: `cat-pill ${state.activeL1 === gid ? 'on' : ''}`,
          onClick: () => {
            state.activeL1 = gid;
            state.activeL2 = 'all';
            state.activeL3 = 'all';
            renderGroupPills();
            renderList();
          },
        }, `${g.label || gid} (${cnt})`);
      }),
    ];

    const curL1 = state.activeL1 !== 'all' ? state.activeL1 : null;
    const l2Map = curL1 ? (l1?.[curL1]?.l2 || null) : null;
    const l2Order = curL1 && Array.isArray(l1?.[curL1]?.l2_order) ? l1[curL1].l2_order : (l2Map ? Object.keys(l2Map) : []);
    const l2Total = curL1 ? (l1?.[curL1]?.count || 0) : countInScope('all');

    const pillsL2 = (curL1 && l2Map)
      ? [
        UI.h('button', {
          type: 'button',
          class: `cat-pill ${state.activeL2 === 'all' ? 'on' : ''}`,
          onClick: () => {
            state.activeL2 = 'all';
            state.activeL3 = 'all';
            renderGroupPills();
            renderList();
          },
        }, `全部 (${l2Total})`),
        ...l2Order.map((k) => {
          const g = l2Map[k] || {};
          return UI.h('button', {
            type: 'button',
            class: `cat-pill ${state.activeL2 === k ? 'on' : ''}`,
            onClick: () => {
              state.activeL2 = k;
              state.activeL3 = 'all';
              renderGroupPills();
              renderList();
            },
          }, `${g.label || k} (${g.count || 0})`);
        }),
      ]
      : [];

    const curL2 = (curL1 && state.activeL2 !== 'all') ? state.activeL2 : null;
    const l3Map = (curL1 && curL2) ? (l2Map?.[curL2]?.l3 || null) : null;
    const l3Order = (curL1 && curL2 && Array.isArray(l2Map?.[curL2]?.l3_order))
      ? l2Map[curL2].l3_order
      : (l3Map ? Object.keys(l3Map) : []);
    const l3Total = (curL1 && curL2) ? (l2Map?.[curL2]?.count || 0) : l2Total;

    const pillsL3 = (curL1 && curL2 && l3Map)
      ? [
        UI.h('button', {
          type: 'button',
          class: `cat-pill ${state.activeL3 === 'all' ? 'on' : ''}`,
          onClick: () => {
            state.activeL3 = 'all';
            renderGroupPills();
            renderList();
          },
        }, `全部 (${l3Total})`),
        ...l3Order.map((k) => {
          const g = l3Map[k] || {};
          return UI.h('button', {
            type: 'button',
            class: `cat-pill ${state.activeL3 === k ? 'on' : ''}`,
            onClick: () => {
              state.activeL3 = k;
              renderGroupPills();
              renderList();
            },
          }, `${g.label || k} (${g.count || 0})`);
        }),
      ]
      : [];

    UI.mount(el, UI.h('div', { class: 'assets-tools-filters' },
      UI.h('p', { class: 'assets-tools-sec' }, '範圍'),
      UI.h('div', { class: 'assets-pills-row assets-pills-row--scope' }, ...renderScopePills()),
      UI.h('p', { class: 'assets-tools-sec' }, '主題包'),
      ...renderThemePacks(),
      UI.h('p', { class: 'assets-tools-sec' }, '行業 / 分層'),
      ...renderSectorPills(),
      UI.h('div', { class: 'assets-pills-row' }, ...pillsL1),
      pillsL2.length ? UI.h('div', { class: 'assets-pills-row', style: { marginTop: '6px' } }, ...pillsL2) : null,
      pillsL3.length ? UI.h('div', { class: 'assets-pills-row', style: { marginTop: '6px' } }, ...pillsL3) : null,
    ));
    paintFilterSummary();
  }

  function buildGroupsFromInstruments(instruments) {
    const rows = Array.isArray(instruments) ? instruments : [];
    const groups = {};
    rows.forEach((r) => {
      const gid = String(r?.group || '').trim() || 'unknown';
      const label = String(r?.group_label || '').trim() || gid;
      if (!groups[gid]) groups[gid] = { label, count: 0 };
      groups[gid].count += 1;
      // prefer first non-empty label
      if (!groups[gid].label && label) groups[gid].label = label;
    });
    const group_order = Object.keys(groups).sort((a, b) => {
      const la = String(groups[a]?.label || a);
      const lb = String(groups[b]?.label || b);
      return la.localeCompare(lb, 'zh-Hant');
    });
    return { groups, group_order };
  }

  function buildHierarchyFromInstruments(instruments, baseGroups, baseOrder) {
    const rows = Array.isArray(instruments) ? instruments : [];
    const l1 = {};
    const l1_order = Array.isArray(baseOrder) && baseOrder.length ? [...baseOrder] : [];

    const ensure = (obj, key, init) => {
      if (!obj[key]) obj[key] = init();
      return obj[key];
    };

    rows.forEach((r) => {
      const g1 = String(r?.group || '').trim() || 'unknown';
      const g1Label = String(r?.group_label || '').trim() || (baseGroups?.[g1]?.label) || g1;
      const l2Key = String(r?.l2 || r?.asset_class || 'other').trim() || 'other';
      const l2Label = String(r?.l2_label || '').trim() || l2Key;
      const l3Key = String(r?.l3 || 'other').trim() || 'other';
      const l3Label = String(r?.l3_label || '').trim() || l3Key;

      const n1 = ensure(l1, g1, () => ({ label: g1Label, count: 0, l2: {}, l2_order: [] }));
      n1.count += 1;
      if (!l1_order.includes(g1)) l1_order.push(g1);

      const n2 = ensure(n1.l2, l2Key, () => ({ label: l2Label, count: 0, l3: {}, l3_order: [] }));
      n2.count += 1;
      if (!n1.l2_order.includes(l2Key)) n1.l2_order.push(l2Key);

      const n3 = ensure(n2.l3, l3Key, () => ({ label: l3Label, count: 0 }));
      n3.count += 1;
      if (!n2.l3_order.includes(l3Key)) n2.l3_order.push(l3Key);
    });

    Object.keys(l1).forEach((g1) => {
      l1[g1].l2_order.sort((a, b) => String(l1[g1].l2[a]?.label || a).localeCompare(String(l1[g1].l2[b]?.label || b), 'zh-Hant'));
      Object.keys(l1[g1].l2).forEach((k2) => {
        l1[g1].l2[k2].l3_order.sort((a, b) => String(l1[g1].l2[k2].l3[a]?.label || a).localeCompare(String(l1[g1].l2[k2].l3[b]?.label || b), 'zh-Hant'));
      });
    });

    return { l1, l1_order };
  }

  function normalizeCatalog(raw) {
    const cat = (raw && typeof raw === 'object') ? { ...raw } : {};
    if (!Array.isArray(cat.instruments)) cat.instruments = [];
    if (typeof cat.total !== 'number') cat.total = cat.instruments.length;

    // Backward/forward compatibility:
    // - If backend doesn't ship groups metadata, infer from instruments.
    const hasGroups = cat.groups && typeof cat.groups === 'object' && Object.keys(cat.groups).length;
    const groupsLooksLikeCounts = hasGroups && Object.values(cat.groups).every((v) => typeof v === 'number');
    if (groupsLooksLikeCounts) {
      const labels = (cat.group_labels && typeof cat.group_labels === 'object') ? cat.group_labels : {};
      const next = {};
      Object.keys(cat.groups).forEach((gid) => {
        next[gid] = {
          label: labels[gid] || gid,
          count: Number(cat.groups[gid] || 0),
        };
      });
      cat.groups = next;
    }

    if (!hasGroups || groupsLooksLikeCounts) {
      const built = buildGroupsFromInstruments(cat.instruments);
      cat.groups = built.groups;
      cat.group_order = built.group_order;
    } else if (!Array.isArray(cat.group_order) || !cat.group_order.length) {
      cat.group_order = Object.keys(cat.groups);
    }

    if (!cat.hierarchy || !cat.hierarchy.l1) {
      const built = buildHierarchyFromInstruments(cat.instruments, cat.groups, cat.group_order);
      cat.hierarchy = { l1: built.l1, l1_order: built.l1_order };
    }
    return cat;
  }

  async function loadCatalog() {
    const root = UI.id('assets-grid');
    const pills = UI.id('assets-group-pills');
    const meta = UI.id('assets-meta');
    try {
      if (meta) meta.textContent = '載入中…';
      if (root) UI.mount(root, UI.h('div', { class: 'assets-loading' }, '載入資產庫中…'));
      if (pills) UI.mount(pills, UI.h('div', { class: 'assets-loading' }, '載入分類中…'));

      const data = await Api.getAssetsCatalog();
      state.catalog = normalizeCatalog(data);
      renderGroupPills();
      renderList();
    } catch (e) {
      state.catalog = { instruments: [], total: 0, groups: {}, group_order: [] };
      if (meta) meta.textContent = '資產庫載入失敗';
      if (pills) UI.mount(pills, UI.h('div', { class: 'assets-empty er' }, '分類載入失敗'));
      if (root) {
        UI.mount(root, UI.h('div', { class: 'assets-empty er' },
          `資產庫載入失敗：${e?.message || e}`,
          UI.h('div', { style: { marginTop: '10px' } },
            UI.h('button', { type: 'button', class: 'btn btn-s', onClick: () => loadCatalog() }, '重試'),
          ),
        ));
      }
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
    if (!dom) return;
    if (!window.echarts) {
      window.StockQPro?.charts?.ensureEcharts?.().then(() => renderMainChart(mode, kline)).catch(() => {});
      return;
    }
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

  function renderWidgetFrame(w) {
    if (!w?.src) return null;
    const host = UI.h('div', { class: 'asset-widget' },
      UI.h('h4', { class: 'asset-widget-title' }, w.title || '第三方元件'),
      UI.h('button', {
        type: 'button',
        class: 'asset-widget-load',
        onClick: (ev) => {
          const btn = ev.currentTarget;
          const frame = UI.h('iframe', {
            class: 'asset-widget-frame',
            src: w.src,
            title: w.title || '第三方',
            loading: 'lazy',
            referrerpolicy: 'no-referrer-when-downgrade',
          });
          btn.replaceWith(frame);
        },
      }, `載入 ${w.title || '第三方元件'}（較重，按需開啟）`),
    );
    return host;
  }

  function renderThirdPanel(d) {
    const widgets = Array.isArray(d.widgets) ? d.widgets : [];
    const frames = widgets.map(renderWidgetFrame).filter(Boolean);
    const links = Array.isArray(d.links) ? d.links : [];
    const blocks = [];
    if (frames.length) {
      blocks.push(renderSection('即時元件', UI.h('div', { class: 'asset-widget-stack' }, ...frames)));
    } else {
      blocks.push(UI.h('p', { class: 'assets-hint' }, '此標的尚未對應 TradingView 代碼，改用外部網站。'));
    }
    if (links.length) {
      blocks.push(renderSection('更多來源', renderLinks(links)));
    }
    return UI.h('div', { class: 'asset-panel asset-panel--third' }, ...blocks);
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
      third: renderThirdPanel,
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

    const live = state.detailPrice;
    const liveSrc = live?.source ? String(live.source) : '';
    const liveKind = live?.kind ? String(live.kind) : '';
    const liveTs = live?.ts ? new Date(Number(live.ts) * 1000) : null;
    const liveTsText = liveTs && !Number.isNaN(liveTs.getTime())
      ? liveTs.toLocaleString('zh-TW', { hour12: false })
      : '';
    const liveText = live?.loading
      ? '即時/估值：載入中…'
      : (live?.success
        ? `即時/估值：${liveSrc}${liveKind ? ` · ${liveKind}` : ''}${liveTsText ? ` · ${liveTsText}` : ''}`
        : (live?.message ? `即時/估值：${live.message}` : '即時/估值：—'));

    return UI.h('header', { class: 'asset-detail-hero' },
      UI.h('div', { class: 'asset-detail-hero-left' },
        UI.h('div', { class: 'asset-detail-title' },
          UI.h('h1', null, d.name || symbol),
          UI.h('div', { class: 'asset-detail-sub' },
            UI.h('span', { class: 'badge b-ac' }, d.group_label || d.group || '—'),
            UI.h('span', { class: 'mono asset-detail-code' }, symbol),
            d.market_label ? UI.h('span', { class: 'badge b-bl' }, d.market_label) : null,
          ),
          d.investment_thesis_locked
            ? UI.h('p', { class: 'asset-detail-thesis asset-detail-thesis--locked' },
              '投資邏輯一句話需 Pro · ',
              UI.h('button', {
                type: 'button',
                class: 'btn btn-s btn-ac',
                style: { display: 'inline', marginLeft: '6px' },
                onClick: () => window.StockQPro?.App?.nav?.('pricing', { syncHash: true }),
              }, '升級'),
            )
            : (d.investment_thesis || d.one_liner)
              ? UI.h('p', { class: 'asset-detail-thesis' }, d.investment_thesis || d.one_liner)
              : null,
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
        UI.h('div', { class: 'assets-hint', id: 'asset-detail-live-price' }, liveText),
        q.source ? UI.h('span', { class: 'ticker-card-src' }, q.source) : null,
      ),
    );
  }

  async function loadDetailPrice(symbol) {
    const sym = String(symbol || '').trim();
    if (!sym) return;
    state.detailPrice = { loading: true };
    // re-render hero only if already mounted
    if (UI.id('asset-detail-live-price')) {
      const el = UI.id('asset-detail-live-price');
      if (el) el.textContent = '即時/估值：載入中…';
    }
    try {
      const res = await Api.get(`/api/assets/price?symbol=${encodeURIComponent(sym)}`, { silent: true, noCache: true });
      state.detailPrice = res || { success: false, message: '暫無回應' };
      const el = UI.id('asset-detail-live-price');
      if (el) {
        const live = state.detailPrice;
        const liveSrc = live?.source ? String(live.source) : '';
        const liveKind = live?.kind ? String(live.kind) : '';
        const liveTs = live?.ts ? new Date(Number(live.ts) * 1000) : null;
        const liveTsText = liveTs && !Number.isNaN(liveTs.getTime())
          ? liveTs.toLocaleString('zh-TW', { hour12: false })
          : '';
        if (live?.success) {
          el.textContent = `即時/估值：${liveSrc}${liveKind ? ` · ${liveKind}` : ''}${liveTsText ? ` · ${liveTsText}` : ''}`;
          el.title = live?.pricing_note || '';
        } else {
          el.textContent = `即時/估值：${live?.message || '—'}`;
          el.title = live?.pricing_note || '';
        }
      }
    } catch (_) {
      state.detailPrice = { success: false, message: '載入失敗' };
      const el = UI.id('asset-detail-live-price');
      if (el) el.textContent = '即時/估值：載入失敗';
    }
  }

  function goWithSymbol(page, symbol) {
    try { window.StockQPro?.WorkContext?.set?.(symbol); } catch (_) {}
    window.StockQPro?.App?.nav?.(page, { syncHash: true });
  }

  function addToAllocation(symbol, name) {
    if (window.StockQPro?.Allocation?.add) {
      window.StockQPro.Allocation.add({ code: symbol, name, quantity: 100 });
      window.StockQPro.Allocation.setOpen?.(true);
    } else {
      window.StockQPro?.App?.toast?.('配置欄載入中，請稍後再試', 'inf');
    }
  }

  async function addToWatchlist(symbol) {
    try {
      await Api.post(`/api/watchlist/add?code=${encodeURIComponent(symbol)}`);
      window.StockQPro?.App?.toast?.(`已加入自選：${symbol}`, 'ok');
    } catch (e) {
      window.StockQPro?.App?.toast?.(e?.message || '加入自選失敗', 'err');
    }
  }

  function mountDetailShell(d, symbol) {
    const root = UI.id('assets-detail-root');
    if (!root) return;
    const title = UI.id('assets-drawer-title');
    if (title) title.textContent = d.name || symbol;

    UI.mount(root, UI.h('div', { class: 'asset-detail-wrap' },
      buildDetailHero(d, symbol),
      UI.h('div', { class: 'asset-detail-tools' },
        UI.h('button', {
          type: 'button', class: 'btn s',
          onClick: () => addToAllocation(symbol, d.name),
        }, '+ 配置'),
        UI.h('button', {
          type: 'button', class: 'btn s',
          onClick: () => addToWatchlist(symbol),
        }, '+ 自選'),
        UI.h('button', {
          type: 'button', class: 'btn s',
          onClick: () => goWithSymbol('backtest', symbol),
        }, '回測'),
        UI.h('button', {
          type: 'button', class: 'btn s',
          onClick: () => goWithSymbol('compare', symbol),
        }, '對比'),
        UI.h('button', {
          type: 'button', class: 'btn s',
          onClick: () => goWithSymbol('analysis', symbol),
        }, '分析'),
      ),
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
      if (!res) throw new Error('無詳情資料');
      const d = res.detail || res;
      if (!d || typeof d !== 'object') throw new Error('無詳情資料');
      state.detailData = d;
      state.detailPrice = null;
      mountDetailShell(d, sym);
      loadDetailPrice(sym);
    } catch (e) {
      state.detailData = null;
      UI.mount(root, UI.h('div', { class: 'assets-empty er' },
        `載入失敗：${e.message || e}`,
        UI.h('button', {
          type: 'button',
          class: 'btn btn-s',
          onClick: () => closeDrawer({ resetHash: true }),
        }, '關閉'),
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
          clearTimeout(search._t);
          search._t = setTimeout(() => renderList(), 180);
        });
      }
      ensureDrawerPortal();
      const toolsBtn = UI.id('assets-tools-open');
      if (toolsBtn && !toolsBtn.dataset.bound) {
        toolsBtn.dataset.bound = '1';
        toolsBtn.addEventListener('click', () => openToolsDrawer());
      }
      const summaryBtn = UI.id('assets-filter-summary');
      if (summaryBtn && !summaryBtn.dataset.bound) {
        summaryBtn.dataset.bound = '1';
        summaryBtn.addEventListener('click', () => {
          if (state.drawerMode !== 'tools') openToolsDrawer();
        });
      }
      const closeBtn = UI.id('assets-drawer-close');
      if (closeBtn && !closeBtn.dataset.bound) {
        closeBtn.dataset.bound = '1';
        closeBtn.addEventListener('click', () => closeDrawer({ resetHash: true }));
      }
      const doneBtn = UI.id('assets-tools-done');
      if (doneBtn && !doneBtn.dataset.bound) {
        doneBtn.dataset.bound = '1';
        doneBtn.addEventListener('click', () => closeDrawer({ resetHash: false }));
      }
      const resetBtn = UI.id('assets-tools-reset');
      if (resetBtn && !resetBtn.dataset.bound) {
        resetBtn.dataset.bound = '1';
        resetBtn.addEventListener('click', () => resetToolsFilters());
      }
      const backdrop = UI.id('assets-drawer-backdrop');
      if (backdrop && !backdrop.dataset.bound) {
        backdrop.dataset.bound = '1';
        backdrop.addEventListener('click', () => closeDrawer({ resetHash: true }));
      }
      if (!document.body.dataset.assetsDrawerEsc) {
        document.body.dataset.assetsDrawerEsc = '1';
        document.addEventListener('keydown', (ev) => {
          if (ev.key === 'Escape' && state.drawerMode) {
            closeDrawer({ resetHash: true });
          }
        });
      }
      if (!window.__assetsDrawerResizeBound) {
        window.__assetsDrawerResizeBound = true;
        window.addEventListener('resize', () => {
          if (state.drawerMode === 'detail') {
            try { state.chartInst?.resize?.(); } catch (_) {}
          }
        });
      }
      if (state.detailSymbol) {
        showDetail(state.detailSymbol);
        return;
      }
      if (!state.catalog) {
        loadCatalog();
      } else {
        renderGroupPills();
        renderList();
      }
    },

    openDetail(symbol) {
      showDetail(symbol);
    },

    showList,
    openTools: openToolsDrawer,
    unload() {
      closeDrawer({ resetHash: false });
    },
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.assets = Pages;
})();
