/* global Api */

(() => {
  const state = {
    catalog: null,
    builtin: [],
    activeCat: '',
    query: '',
    implOnly: false,
    pageSize: 36,
    visible: 36,
    lastTotal: 0,
  };

  function prefersReducedMotion() {
    try {
      return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (_) {
      return false;
    }
  }

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

  function animateNumber(el, to, fmt = (v) => String(v)) {
    if (!el) return;
    const target = Number(to);
    if (!Number.isFinite(target) || prefersReducedMotion()) {
      el.textContent = fmt(target);
      return;
    }
    const fromRaw = Number(String(el.textContent || '').replace(/[^\d.-]/g, ''));
    const from = Number.isFinite(fromRaw) ? fromRaw : 0;
    const start = performance.now();
    const dur = 650;
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    const tick = (now) => {
      const p = Math.min(1, (now - start) / dur);
      const v = from + (target - from) * ease(p);
      el.textContent = fmt(Math.round(v));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function markLoadedTime() {
    const el = document.getElementById('home-loaded-at');
    if (!el) return;
    const iso = new Date().toISOString();
    el.setAttribute('datetime', iso);
    el.textContent = iso.replace('T', ' ').replace('Z', 'Z');
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
    if (stocks) {
      const n = Number(health.total_stocks ?? 0);
      if (Number.isFinite(n) && n < 1e6) animateNumber(stocks, n, (v) => fmtKlines(v));
      else stocks.textContent = fmtKlines(n);
    }
    if (klines) {
      const n = Number(health.total_klines ?? 0);
      if (Number.isFinite(n) && n < 1e7) animateNumber(klines, n, (v) => fmtKlines(v));
      else klines.textContent = fmtKlines(n);
    }
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
    const desc = document.getElementById('home-builtin-desc');
    if (!row || !chips || !state.builtin.length) return;
    row.hidden = false;
    const n = state.builtin.length;
    if (desc) {
      desc.textContent = `共 ${n} 種內建策略已接入回測引擎，點選策略名稱可直達回測頁預填。`;
    }
    chips.innerHTML = state.builtin.map((b) => {
      const label = escapeHtml(b.display_name || b.name);
      const key = escapeHtml(b.name || '');
      return `<a class="home-builtin-chip" href="/app#/backtest" role="listitem" data-strategy="${key}" title="${escapeHtml(b.description || b.name)}">${label}</a>`;
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
      <div class="home-lib-stat"><span class="v ac" data-anim="total">0</span><span class="l">策略目錄</span></div>
      <div class="home-lib-stat"><span class="v gn" data-anim="impl">0</span><span class="l">目錄可回測</span></div>
      <div class="home-lib-stat"><span class="v bl" data-anim="engine">0</span><span class="l">引擎內建</span></div>
      <div class="home-lib-stat"><span class="v" data-anim="cats">0</span><span class="l">大類別</span></div>
    `;
    animateNumber(el.querySelector('[data-anim="total"]'), total);
    animateNumber(el.querySelector('[data-anim="impl"]'), impl);
    animateNumber(el.querySelector('[data-anim="engine"]'), engine);
    animateNumber(el.querySelector('[data-anim="cats"]'), cats);
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

  function revealNewItems(root) {
    if (!root) return;
    const items = root.querySelectorAll('.reveal-item:not(.is-in)');
    if (!items.length) return;
    if (prefersReducedMotion()) {
      items.forEach((el) => el.classList.add('is-in'));
      return;
    }
    // lightweight: no IntersectionObserver dependency for older browsers
    let i = 0;
    const step = () => {
      const el = items[i++];
      if (el) el.classList.add('is-in');
      if (i < items.length) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function renderCard(s, cat) {
    const impl = isImplemented(s);
    const tier = s.tier || 'free';
    const href = impl ? '/app#/backtest' : '/app#/strategies';
    return `
      <a class="strat-card reveal-item ${impl ? 'is-impl is-ready' : 'is-planned'}" href="${href}" data-id="${s.id}">
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

  function updatePagerUi(listLen, totalLen) {
    const actions = document.getElementById('home-strat-actions');
    const meta = document.getElementById('home-strat-meta');
    const btnMore = document.getElementById('home-strat-more');
    if (!actions || !meta || !btnMore) return;

    const shown = Math.min(state.visible, listLen);
    actions.hidden = listLen <= state.pageSize;
    meta.textContent = `已顯示 ${shown} / ${listLen}（全目錄 ${totalLen}）`;
    btnMore.disabled = shown >= listLen;
    btnMore.textContent = shown >= listLen ? '已顯示全部' : `顯示更多（+${Math.min(state.pageSize, listLen - shown)}）`;
  }

  function renderGrid() {
    const grid = document.getElementById('home-strat-grid');
    const foot = document.getElementById('home-strat-foot');
    if (!grid || !state.catalog) return;
    grid.classList.remove('is-loading');

    const list = filteredStrats();
    state.lastTotal = list.length;
    if (state.visible > list.length) state.visible = list.length || state.pageSize;
    if (!list.length) {
      grid.innerHTML = '<p style="color:var(--t3);font-size:.74rem;padding:20px 0;text-align:center">沒有符合條件的策略</p>';
    } else {
      const page = list.slice(0, Math.max(state.pageSize, state.visible));
      grid.innerHTML = page.map((s) => {
        const cat = state.catalog.cats.find((c) => c.id === s.cat) || state.catalog.cats[0];
        return renderCard(s, cat);
      }).join('');
      revealNewItems(grid);
    }

    if (foot) {
      const shown = Math.min(state.visible, list.length);
      foot.textContent = `顯示 ${shown} / ${list.length} 條策略 · 點擊卡片進入工作台`;
    }
    updatePagerUi(list.length, state.catalog.strats.length);
  }

  function bindToolbar() {
    const search = document.getElementById('home-lib-search');
    const implOnly = document.getElementById('home-lib-impl-only');
    if (search) {
      search.addEventListener('input', () => {
        state.query = search.value;
        state.visible = state.pageSize;
        renderGrid();
      });
    }
    if (implOnly) {
      implOnly.addEventListener('change', () => {
        state.implOnly = implOnly.checked;
        state.visible = state.pageSize;
        renderGrid();
      });
    }
    const more = document.getElementById('home-strat-more');
    if (more && !more._bound) {
      more._bound = true;
      more.addEventListener('click', () => {
        state.visible += state.pageSize;
        renderGrid();
        // keep user's context near controls
        more.focus();
      });
    }
    const top = document.getElementById('home-strat-top');
    if (top && !top._bound) {
      top._bound = true;
      top.addEventListener('click', () => {
        document.getElementById('home-cat-pills')?.scrollIntoView?.({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
      });
    }
  }

  function setGridLoading(on) {
    const grid = document.getElementById('home-strat-grid');
    if (!grid) return;
    grid.classList.toggle('is-loading', !!on);
    if (on) {
      grid.innerHTML = '策略目錄載入中…';
      grid.setAttribute('aria-busy', 'true');
    } else {
      grid.removeAttribute('aria-busy');
    }
  }

  async function initStrategyLibrary() {
    const grid = document.getElementById('home-strat-grid');
    if (!grid) return;
    setGridLoading(true);
    try {
      await loadCatalog();
      await loadBuiltin();
      renderLibStats();
      renderBuiltinChips();
      renderCatPills();
      bindToolbar();
      setGridLoading(false);
      state.visible = state.pageSize;
      renderGrid();
    } catch (e) {
      grid.classList.remove('is-loading');
      grid.innerHTML = `<p style="color:var(--rd);font-size:.74rem;padding:20px 0;text-align:center">策略庫載入失敗：${escapeHtml(e.message)}</p>`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    try { if (typeof Api !== 'undefined' && Api.init) Api.init(); } catch (_) {}
    markLoadedTime();
    loadStats();
    initStrategyLibrary();
  });
})();
