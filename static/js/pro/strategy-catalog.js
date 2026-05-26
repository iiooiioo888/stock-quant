/* global fetch, Api */

(() => {
  const $id = (id) => document.getElementById(id);

  const FALLBACK_CATS = [
    { id: 'trend', name: '趨勢跟蹤與動量', icon: '📈', color: '#e8b830' },
    { id: 'osc', name: '振盪與均值回歸', icon: '〰️', color: '#38bdf8' },
    { id: 'breakout', name: '突破與通道', icon: '🚀', color: '#f97316' },
    { id: 'micro', name: '微結構與量能', icon: '📊', color: '#22d3ee' },
    { id: 'execution', name: '演算法執行', icon: '⚙️', color: '#94a3b8' },
  ];

  const state = {
    catalog: null,
    activeCat: '',
    selectedStratId: 1,
    plan: 'pro', // local-only, pricing not wired
  };

  const tierBadgeClass = (tier) => {
    if (tier === 'free') return 'tier-free';
    if (tier === 'pro') return 'tier-pro';
    return 'tier-ent';
  };

  const tierToBacktestBadge = (tier) => {
    if (tier === 'free') return 'b-gn';
    if (tier === 'pro') return 'b-ac';
    return 'b-pu';
  };

  const escapeHtml = (s) => String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

  const isStratRunnable = (s) => {
    const st = s?.status || 'planned';
    return st === 'implemented' || st === 'user';
  };

  function applyCatalog(data) {
    state.catalog = data;
    window.StockQPro = window.StockQPro || {};
    window.StockQPro.catalog = data;
    const totalEl = $id('lib-total');
    if (totalEl) totalEl.textContent = `${data.strats.length} 策略`;
    return data;
  }

  function buildCatalogFromApiList(apiData) {
    const builtin = apiData?.builtin || [];
    const strats = builtin.map((b, i) => ({
      id: i + 1,
      name: b.display_name || b.name,
      desc: (b.description || '').split('—')[0].trim() || b.display_name || b.name,
      cat: 'trend',
      tier: 'free',
      backend_key: b.name,
      status: 'implemented',
    }));
    return { cats: FALLBACK_CATS, strats };
  }

  async function loadCatalogFromApi() {
    const apiData = typeof Api !== 'undefined' && Api.getStrategies
      ? await Api.getStrategies()
      : await fetch('/api/strategies/list').then((r) => {
        if (!r.ok) throw new Error(`strategies list ${r.status}`);
        return r.json();
      });
    return applyCatalog(buildCatalogFromApiList(apiData));
  }

  async function loadCatalog() {
    try {
      const r = await fetch('/static/data/strategy-catalog.json?v=stockq-pro-v6', { cache: 'no-cache' });
      if (!r.ok) throw new Error(`load catalog failed: ${r.status}`);
      const data = await r.json();
      if (!data?.strats?.length) throw new Error('empty catalog');
      return applyCatalog(data);
    } catch (e) {
      console.warn('[strategy-catalog] static JSON failed, using API fallback', e);
      return loadCatalogFromApi();
    }
  }

  function syncBacktestStrategyInput(backendKey) {
    const stratEl = $id('bt-strategy') || document.getElementById('btStrategy');
    if (stratEl && backendKey) stratEl.value = backendKey;
  }

  function ensureDefaultRunnableStrategy() {
    if (!state.catalog?.strats?.length) return;
    const current = state.catalog.strats.find((x) => x.id === state.selectedStratId);
    if (current && isStratRunnable(current) && current.backend_key) return;
    const first = state.catalog.strats.find((s) => isStratRunnable(s) && s.backend_key);
    if (first) useStrat(first.id, { silent: true });
  }

  function renderCatPills() {
    const el = $id('cat-pills');
    if (!el || !state.catalog) return;
    const { cats, strats } = state.catalog;
    const total = strats.length;
    el.innerHTML =
      `<div class="cat-pill ${state.activeCat === '' ? 'on' : ''}" data-cat=""><span style="font-size:.62rem">全部</span><span class="cp-cnt">${total}</span></div>` +
      cats.map((c) => {
        const cnt = strats.filter((s) => s.cat === c.id).length;
        return `<div class="cat-pill ${state.activeCat === c.id ? 'on' : ''}" data-cat="${c.id}"><span class="cp-dot" style="background:${c.color}"></span>${escapeHtml(c.icon)} ${escapeHtml(c.name.replace(/（.*）/,'').slice(0,18))}<span class="cp-cnt">${cnt}</span></div>`;
      }).join('');

    el.querySelectorAll('.cat-pill').forEach((p) => {
      p.addEventListener('click', () => {
        state.activeCat = p.getAttribute('data-cat') || '';
        renderLibrary();
      });
    });
  }

  function renderCard(s, cat) {
    const sel = s.id === state.selectedStratId;
    const tier = s.tier || 'free';
    const runnable = isStratRunnable(s);
    const statusCls = runnable ? 'is-ready' : 'is-planned';
    const accent = runnable ? 'var(--gn)' : 'var(--t3)';
    return `
      <div class="strat-card ${statusCls} ${sel ? 'active' : ''}" data-id="${s.id}">
        <div class="strat-accent" style="background:${accent}"></div>
        <div class="strat-hdr">
          <span class="strat-num">#${String(s.id).padStart(3,'0')}</span>
          <span class="strat-status ${runnable ? 'ok' : 'plan'}">${runnable ? '可回測' : '即將推出'}</span>
          <span class="strat-tier ${tierBadgeClass(tier)}">${tier.toUpperCase()}</span>
        </div>
        <div class="strat-name">${escapeHtml(s.name)}</div>
        <div class="strat-desc">${escapeHtml(s.desc || '')}</div>
        <div class="strat-foot">
          <span style="display:flex;align-items:center;gap:4px;font-size:.58rem;color:var(--t3)"><span style="width:5px;height:5px;border-radius:50%;background:${cat.color}"></span>${escapeHtml(cat.icon)}</span>
          <button class="strat-btn ${runnable ? 'strat-btn-ready' : 'strat-btn-planned'}" type="button" data-use="${s.id}" ${runnable ? '' : 'data-planned="1"'}>${runnable ? '使用策略' : '即將推出'}</button>
        </div>
      </div>
    `;
  }

  function showStratDetail(id) {
    const s = state.catalog?.strats?.find((x) => x.id === id);
    if (!s) return;
    const cat = state.catalog.cats.find((c) => c.id === s.cat) || state.catalog.cats[0];
    const runnable = isStratRunnable(s);

    const title = $id('sd-title');
    const body = $id('sd-body');
    const useBtn = $id('sd-use');
    if (title) title.innerHTML = `<span style="color:${cat.color}">${escapeHtml(cat.icon)}</span> 策略詳情`;
    if (body) body.innerHTML = `
      <div class="sd-cat"><div class="sd-cat-dot" style="background:${cat.color}"></div><span class="sd-cat-name">${escapeHtml(cat.name)}</span></div>
      <div class="sd-name">#${String(s.id).padStart(3,'0')} ${escapeHtml(s.name)}</div>
      <div class="sd-desc">${escapeHtml(s.desc || '')}</div>
      <div class="sd-meta">
        <div class="sd-meta-item"><div class="sd-meta-label">等級</div><div class="sd-meta-value"><span class="strat-tier ${tierBadgeClass(s.tier)}" style="font-size:.62rem">${String(s.tier || 'free').toUpperCase()}</span></div></div>
        <div class="sd-meta-item"><div class="sd-meta-label">類別</div><div class="sd-meta-value" style="font-size:.78rem">${escapeHtml(cat.icon)} ${escapeHtml(cat.name)}</div></div>
        <div class="sd-meta-item"><div class="sd-meta-label">策略 ID</div><div class="sd-meta-value" style="font-size:.78rem;font-family:var(--fm)">#${String(s.id).padStart(3,'0')}</div></div>
        <div class="sd-meta-item"><div class="sd-meta-label">狀態</div><div class="sd-meta-value"><span class="strat-status ${runnable ? 'ok' : 'plan'}">${runnable ? '可回測' : '即將推出'}</span></div></div>
      </div>
      ${runnable ? '' : `<div style="font-size:.72rem;color:var(--t3);line-height:1.7;padding:10px 12px;border-radius:var(--r);border:1px solid rgba(148,163,184,.2);background:rgba(148,163,184,.06)">此策略目前僅供瀏覽，回測功能將陸續開放。</div>`}
    `;

    if (useBtn) {
      useBtn.disabled = false;
      useBtn.textContent = runnable ? '使用此策略' : '即將推出';
      useBtn.className = runnable ? 'btn btn-ac btn-ready' : 'btn btn-planned';
      useBtn.onclick = () => {
        window.StockQPro?.App?.closeModal?.('m-strat');
        if (!runnable) {
          window.StockQPro?.App?.toast?.('此策略即將推出', 'inf');
          return;
        }
        useStrat(s.id);
      };
    }

    window.StockQPro?.App?.openModal?.('m-strat');
  }

  function useStrat(id, opts = {}) {
    const silent = !!opts.silent;
    state.selectedStratId = id;
    const s = state.catalog?.strats?.find((x) => x.id === id);
    if (!s) return;
    const cat = state.catalog.cats.find((c) => c.id === s.cat) || state.catalog.cats[0];
    window.StockQPro = window.StockQPro || {};
    window.StockQPro.selectedStrategy = {
      id: s.id,
      name: s.name,
      tier: s.tier || 'free',
      cat: s.cat,
      backend_key: s.backend_key || null,
      status: s.status || 'planned',
    };
    syncBacktestStrategyInput(s.backend_key);

    const nameEl = $id('bt-sel-name');
    const descEl = $id('bt-sel-desc');
    const dot = $id('bt-sel')?.querySelector('.cdot');
    const tierEl = $id('bt-sel-tier');

    if (nameEl) nameEl.textContent = `#${String(s.id).padStart(3,'0')} ${s.name}`;
    if (descEl) descEl.textContent = s.desc || '';
    if (dot) dot.style.background = cat.color;
    if (tierEl) {
      tierEl.textContent = String(s.tier || 'free').toUpperCase();
      tierEl.className = `badge ${tierToBacktestBadge(s.tier || 'free')}`;
    }

    if (!silent) {
      window.StockQPro?.App?.nav?.('backtest', { syncHash: true });
      window.StockQPro?.App?.toast?.(`已選擇「${s.name}」`, 'ok');
    }
  }

  function renderLibrary() {
    if (!state.catalog) return;
    const q = (($id('lib-search')?.value) || '').toLowerCase();
    const tier = ($id('lib-tier')?.value) || '';
    const statusFilter = ($id('lib-status')?.value) || '';
    const view = ($id('lib-view')?.value) || 'grid';
    const { cats, strats } = state.catalog;
    const runnableTotal = strats.filter(isStratRunnable).length;

    let filtered = strats.filter((s) => {
      if (state.activeCat && s.cat !== state.activeCat) return false;
      if (tier && s.tier !== tier) return false;
      if (statusFilter === 'implemented' && !isStratRunnable(s)) return false;
      if (q && !String(s.name || '').toLowerCase().includes(q) && !String(s.desc || '').toLowerCase().includes(q)) return false;
      return true;
    });

    const stats = $id('lib-stats');
    if (stats) {
      const runnableShown = filtered.filter(isStratRunnable).length;
      stats.innerHTML =
        `<div class="lib-legend" role="note" aria-label="策略狀態圖例">
          <span class="lib-legend-item"><span class="lib-legend-dot ok"></span>可回測</span>
          <span class="lib-legend-item"><span class="lib-legend-dot plan"></span>即將推出</span>
        </div>` +
        `<div class="lib-stat">顯示 <b style="color:var(--ac);margin:0 3px">${filtered.length}</b> / ${strats.length} 策略</div>` +
        `<div class="lib-stat">可回測 <b style="color:var(--gn);margin:0 3px">${runnableShown}</b> / ${runnableTotal}</div>` +
        `<div class="lib-stat">Free: <b style="color:var(--gn);margin:0 3px">${filtered.filter((s) => s.tier === 'free').length}</b></div>` +
        `<div class="lib-stat">Pro: <b style="color:var(--ac);margin:0 3px">${filtered.filter((s) => s.tier === 'pro').length}</b></div>` +
        `<div class="lib-stat">Ent: <b style="color:var(--pu);margin:0 3px">${filtered.filter((s) => s.tier === 'ent').length}</b></div>`;
    }

    renderCatPills();

    const content = $id('lib-content');
    if (!content) return;
    if (filtered.length === 0) {
      content.innerHTML = '<div style="text-align:center;padding:48px;color:var(--t3);font-size:.82rem">找不到符合條件的策略</div>';
      return;
    }

    if (view === 'cat') {
      const groups = {};
      filtered.forEach((s) => { (groups[s.cat] ||= []).push(s); });
      content.innerHTML = Object.entries(groups).map(([catId, ss]) => {
        const cat = cats.find((c) => c.id === catId) || cats[0];
        return `<div class="cat-section"><div class="cat-hdr"><span class="cat-hdr-icon">${escapeHtml(cat.icon)}</span><span class="cat-hdr-name">${escapeHtml(cat.name)}</span><span class="cat-hdr-cnt">${ss.length}</span></div><div class="strat-grid">${ss.map((s) => renderCard(s, cat)).join('')}</div></div>`;
      }).join('');
    } else if (view === 'list') {
      content.innerHTML =
        `<table class="tbl"><thead><tr><th>#</th><th>名稱</th><th>描述</th><th>狀態</th><th>類別</th><th>等級</th><th></th></tr></thead><tbody>` +
        filtered.map((s) => {
          const cat = cats.find((c) => c.id === s.cat) || cats[0];
          const runnable = isStratRunnable(s);
          return `<tr class="${runnable ? 'strat-row-ready' : 'strat-row-planned'}">
            <td style="color:var(--t3)">${String(s.id).padStart(3,'0')}</td>
            <td class="ac" style="cursor:pointer" data-detail="${s.id}">${escapeHtml(s.name)}</td>
            <td style="color:var(--t2);white-space:normal;max-width:340px">${escapeHtml(s.desc || '')}</td>
            <td><span class="strat-status ${runnable ? 'ok' : 'plan'}">${runnable ? '可回測' : '即將推出'}</span></td>
            <td><span style="display:inline-flex;align-items:center;gap:4px"><span style="width:6px;height:6px;border-radius:50%;background:${cat.color}"></span><span style="font-size:.6rem;color:var(--t3)">${escapeHtml(cat.name.slice(0,6))}</span></span></td>
            <td><span class="strat-tier ${tierBadgeClass(s.tier)}">${String(s.tier || 'free').toUpperCase()}</span></td>
            <td><button class="strat-btn ${runnable ? 'strat-btn-ready' : 'strat-btn-planned'}" type="button" data-use="${s.id}" ${runnable ? '' : 'data-planned="1"'}>${runnable ? '使用' : '即將推出'}</button></td>
          </tr>`;
        }).join('') +
        `</tbody></table>`;
    } else {
      content.innerHTML = `<div class="strat-grid">${filtered.map((s) => renderCard(s, cats.find((c) => c.id === s.cat) || cats[0])).join('')}</div>`;
    }

    // bind card + use buttons
    content.querySelectorAll('[data-id]').forEach((card) => {
      const id = Number(card.getAttribute('data-id'));
      card.addEventListener('click', () => showStratDetail(id));
    });
    content.querySelectorAll('[data-detail]').forEach((td) => {
      const id = Number(td.getAttribute('data-detail'));
      td.addEventListener('click', () => showStratDetail(id));
    });
    content.querySelectorAll('[data-use]').forEach((btn) => {
      const id = Number(btn.getAttribute('data-use'));
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (btn.getAttribute('data-planned') === '1') {
          window.StockQPro?.App?.toast?.('此策略即將推出', 'inf');
          return;
        }
        useStrat(id);
      });
    });
  }

  async function init() {
    if (!state.catalog) await loadCatalog();
    window.StockQPro = window.StockQPro || {};
    window.StockQPro.catalog = state.catalog;
    window.StockQPro.showStratDetail = showStratDetail;
    window.StockQPro.ensureDefaultStrategy = ensureDefaultRunnableStrategy;
    ensureDefaultRunnableStrategy();
    const q = $id('lib-search');
    const tier = $id('lib-tier');
    const status = $id('lib-status');
    const view = $id('lib-view');
    q?.addEventListener('input', () => renderLibrary());
    tier?.addEventListener('change', () => renderLibrary());
    status?.addEventListener('change', () => renderLibrary());
    view?.addEventListener('change', () => renderLibrary());
    renderLibrary();
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.strategies = { init };
  window.StockQPro.loadStrategyCatalog = loadCatalog;
})();

