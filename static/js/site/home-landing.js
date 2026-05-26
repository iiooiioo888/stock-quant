/* global Api */

(() => {
  const state = {
    catalog: null,
    builtin: [],
    activeCat: '',
    query: '',
    implOnly: false,
  };

  function fmtKlines(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return '--';
    if (x >= 1e6) return `${(x / 1e6).toFixed(1)}M`;
    if (x >= 1e3) return `${(x / 1e3).toFixed(1)}K`;
    return String(Math.round(x));
  }

  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function tierBadgeClass(tier) {
    if (tier === 'free') return 'tier-free';
    if (tier === 'pro') return 'tier-pro';
    return 'tier-ent';
  }

  function isImplemented(s) {
    const st = s.status || 'planned';
    return st === 'implemented' || st === 'user';
  }

  async function loadStats() {
    const health = await fetch('/api/health').then((r) => r.json()).catch(() => null);
    if (!health) return;
    const stocks = document.getElementById('home-st-stocks');
    const klines = document.getElementById('home-st-klines');
    const ver = document.getElementById('home-st-ver');
    const uptime = document.getElementById('home-st-uptime');
    if (stocks) stocks.textContent = fmtKlines(health.total_stocks ?? 0);
    if (klines) klines.textContent = fmtKlines(health.total_klines ?? 0);
    if (ver && health.version) ver.textContent = `v${health.version}`;
    if (uptime && health.uptime) uptime.textContent = health.uptime;
  }

  function buildCatalogFromBuiltin() {
    const strats = state.builtin.map((b, i) => ({
      id: i + 1,
      name: b.display_name || b.name,
      desc: b.description || b.display_name || b.name,
      cat: 'trend',
      tier: 'free',
      backend_key: b.name,
      status: 'implemented',
    }));
    return {
      cats: [{ id: 'trend', name: '趨勢', icon: '📈', color: '#e8b830' }],
      strats,
    };
  }

  async function loadCatalog() {
    try {
      const r = await fetch('/static/data/strategy-catalog.json?v=stockq-site-v2', { cache: 'no-cache' });
      if (!r.ok) throw new Error(`catalog ${r.status}`);
      const data = await r.json();
      if (!data?.strats?.length) throw new Error('empty catalog');
      state.catalog = data;
      return state.catalog;
    } catch (_) {
      if (!state.builtin.length) await loadBuiltin();
      state.catalog = buildCatalogFromBuiltin();
      return state.catalog;
    }
  }

  async function loadBuiltin() {
    const data = await fetch('/api/strategies/list').then((r) => r.json()).catch(() => null);
    state.builtin = data?.builtin || [];
    return state.builtin;
  }

  function renderBuiltinChips() {
    const row = document.getElementById('home-builtin-row');
    const chips = document.getElementById('home-builtin-chips');
    if (!row || !chips || !state.builtin.length) return;
    row.hidden = false;
    chips.innerHTML = state.builtin.map((b) => {
      const label = escapeHtml(b.display_name || b.name);
      return `<a class="home-builtin-chip" href="/app#/backtest" title="${escapeHtml(b.description || b.name)}">${label}</a>`;
    }).join('');
  }

  function renderLibStats() {
    const el = document.getElementById('home-lib-stats');
    if (!el || !state.catalog) return;
    const total = state.catalog.strats.length;
    const impl = state.catalog.strats.filter(isImplemented).length;
    const cats = state.catalog.cats.length;
    const engine = state.builtin.length;
    el.innerHTML = `
      <div class="home-lib-stat"><span class="v ac">${total}</span><span class="l">策略目錄</span></div>
      <div class="home-lib-stat"><span class="v gn">${impl}</span><span class="l">目錄可回測</span></div>
      <div class="home-lib-stat"><span class="v bl">${engine}</span><span class="l">引擎內建</span></div>
      <div class="home-lib-stat"><span class="v">${cats}</span><span class="l">大類別</span></div>
    `;
  }

  function renderCatPills() {
    const el = document.getElementById('home-cat-pills');
    if (!el || !state.catalog) return;
    const { cats, strats } = state.catalog;
    const total = strats.length;
    el.innerHTML =
      `<div class="cat-pill ${state.activeCat === '' ? 'on' : ''}" data-cat=""><span style="font-size:.62rem">全部</span><span class="cp-cnt">${total}</span></div>` +
      cats.map((c) => {
        const cnt = strats.filter((s) => s.cat === c.id).length;
        const short = c.name.replace(/（.*）/, '').slice(0, 16);
        return `<div class="cat-pill ${state.activeCat === c.id ? 'on' : ''}" data-cat="${c.id}"><span class="cp-dot" style="background:${c.color}"></span>${escapeHtml(c.icon)} ${escapeHtml(short)}<span class="cp-cnt">${cnt}</span></div>`;
      }).join('');

    el.querySelectorAll('.cat-pill').forEach((p) => {
      p.addEventListener('click', () => {
        state.activeCat = p.getAttribute('data-cat') || '';
        renderCatPills();
        renderGrid();
      });
    });
  }

  function filteredStrats() {
    const q = state.query.trim().toLowerCase();
    return state.catalog.strats.filter((s) => {
      if (state.activeCat && s.cat !== state.activeCat) return false;
      if (state.implOnly && !isImplemented(s)) return false;
      if (!q) return true;
      return String(s.name).toLowerCase().includes(q) || String(s.desc || '').toLowerCase().includes(q);
    });
  }

  function renderCard(s, cat) {
    const impl = isImplemented(s);
    const tier = s.tier || 'free';
    const href = impl ? '/app#/backtest' : '/app#/strategies';
    return `
      <a class="strat-card ${impl ? 'is-impl is-ready' : 'is-planned'}" href="${href}" data-id="${s.id}">
        <div class="strat-accent" style="position:absolute;top:0;left:0;bottom:0;width:3px;background:${impl ? 'var(--gn)' : 'var(--t3)'}"></div>
        <div class="strat-hdr">
          <span class="strat-num">#${String(s.id).padStart(3, '0')}</span>
          <span class="strat-status ${impl ? 'ok' : 'plan'}">${impl ? '可回測' : '即將推出'}</span>
        </div>
        <div class="strat-name">${escapeHtml(s.name)}</div>
        <div class="strat-desc">${escapeHtml(s.desc || '')}</div>
        <div class="strat-foot">
          <span class="strat-tier ${tierBadgeClass(tier)}">${tier.toUpperCase()}</span>
          <span class="strat-btn" style="pointer-events:none">${impl ? '去回測' : '預覽'}</span>
        </div>
      </a>
    `;
  }

  function renderGrid() {
    const grid = document.getElementById('home-strat-grid');
    const foot = document.getElementById('home-strat-foot');
    if (!grid || !state.catalog) return;

    const list = filteredStrats();
    if (!list.length) {
      grid.innerHTML = '<p style="color:var(--t3);font-size:.74rem;padding:20px 0;text-align:center">沒有符合條件的策略</p>';
    } else {
      grid.innerHTML = list.map((s) => {
        const cat = state.catalog.cats.find((c) => c.id === s.cat) || state.catalog.cats[0];
        return renderCard(s, cat);
      }).join('');
    }

    if (foot) {
      foot.textContent = `顯示 ${list.length} / ${state.catalog.strats.length} 條策略 · 點擊卡片進入工作台`;
    }
  }

  function bindToolbar() {
    const search = document.getElementById('home-lib-search');
    const implOnly = document.getElementById('home-lib-impl-only');
    if (search) {
      search.addEventListener('input', () => {
        state.query = search.value;
        renderGrid();
      });
    }
    if (implOnly) {
      implOnly.addEventListener('change', () => {
        state.implOnly = implOnly.checked;
        renderGrid();
      });
    }
  }

  async function initStrategyLibrary() {
    const grid = document.getElementById('home-strat-grid');
    if (!grid) return;
    try {
      await Promise.all([loadCatalog(), loadBuiltin()]);
      renderLibStats();
      renderBuiltinChips();
      renderCatPills();
      bindToolbar();
      renderGrid();
    } catch (e) {
      grid.innerHTML = `<p style="color:var(--rd);font-size:.74rem">策略庫載入失敗：${escapeHtml(e.message)}</p>`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    try { if (typeof Api !== 'undefined' && Api.init) Api.init(); } catch (_) {}
    loadStats();
    initStrategyLibrary();
  });
})();
