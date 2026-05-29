/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);
  let _plans = [];
  let _paymentNote = '';
  let _featureLabels = {};
  let _featureOrder = [];
  let _me = null;
  let _authBound = false;

  function isLoggedIn() {
    return !!Api?._token && !Api?.isTokenExpired?.(Api._token);
  }

  function toast(msg, type = 'info') {
    window.StockQPro?.App?.toast?.(msg, type === 'error' ? 'er' : type === 'success' ? 'ok' : 'inf');
  }

  function fmtMoney(plan) {
    if (plan.contact_sales) return '聯繫報價';
    if (!plan.price_monthly) return '免費';
    const cur = plan.currency === 'USD' ? '$' : `${plan.currency} `;
    return `${cur}${plan.price_monthly}<span>/月</span>`;
  }

  function usageBar(label, used, limit) {
    const u = Number(used) || 0;
    const l = Number(limit) || 0;
    if (l <= 0) return `${label}：方案不含`;
    return `${label}：${u} / ${l}`;
  }

  function renderAccount() {
    const el = $id('pricing-account');
    if (!el) return;
    if (!isLoggedIn()) {
      el.hidden = true;
      el.innerHTML = '';
      return;
    }
    el.hidden = false;
    if (!_me) {
      el.innerHTML = '<span>載入帳戶方案…</span>';
      return;
    }
    const lim = _me.limits || {};
    const use = _me.usage || {};
    const statusLbl = _me.status === 'trialing' ? ' · 試用中' : '';
    let expLbl = '';
    if (_me.expires_at) {
      try {
        const d = new Date(_me.expires_at);
        if (!Number.isNaN(d.getTime())) {
          expLbl = ` · 到期 ${d.toLocaleDateString()}`;
        }
      } catch (_) { /* ignore */ }
    }
    el.innerHTML = `
      <div>當前方案：<strong>${_me.plan_name || _me.plan_id || 'Free'}</strong>${statusLbl}${expLbl}</div>
      <div class="pricing-usage">
        <span>${usageBar('回測', use.backtests_today, lim.daily_backtests)}</span>
        <span>${usageBar('組合', use.portfolio_runs_today, lim.daily_portfolio_runs)}</span>
        <span>${usageBar('優化', use.optimize_runs_today, lim.daily_optimize_runs)}</span>
      </div>`;
  }

  function allFeatureIds() {
    if (_featureOrder.length) return [..._featureOrder];
    const set = new Set(Object.keys(_featureLabels || {}));
    _plans.forEach((p) => (p.features || []).forEach((f) => set.add(f.id || f)));
    return [...set].sort();
  }

  function planHas(plan, fid) {
    return (plan.features || []).some((f) => (f.id || f) === fid);
  }

  function renderCompare() {
    const feats = allFeatureIds();
    const labels = {};
    Object.assign(labels, _featureLabels);
    _plans.forEach((p) => {
      (p.features || []).forEach((f) => {
        const id = f.id || f;
        if (!labels[id]) labels[id] = f.label || id;
      });
    });
    const head = _plans.map((p) => `<th>${p.name}</th>`).join('');
    const rows = feats.map((fid) => {
      const cells = _plans.map((p) => {
        const ok = planHas(p, fid);
        return `<td class="${ok ? 'yes' : 'no'}">${ok ? '✓' : '—'}</td>`;
      }).join('');
      return `<tr><td>${labels[fid] || fid}</td>${cells}</tr>`;
    }).join('');
    return `
      <h3 class="pt" style="font-size:.78rem;margin:12px 0 8px">功能對照</h3>
      <table class="pricing-compare" aria-label="方案功能對照">
        <thead><tr><th>功能</th>${head}</tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function ctaForPlan(plan) {
    const pid = plan.id;
    const current = _me?.plan_id || 'free';
    if (pid === current) {
      return '<button type="button" class="btn btn-s" disabled>當前方案</button>';
    }
    if (plan.contact_sales) {
      return '<button type="button" class="btn btn-s" data-pricing-contact="1">聯繫銷售</button>';
    }
    if (pid === 'free') {
      return '<button type="button" class="btn btn-s" data-pricing-downgrade="free">恢復 Free</button>';
    }
    if (pid === 'pro') {
      return '<button type="button" class="btn btn-ac" data-pricing-upgrade="pro">升級 Pro</button>';
    }
    return '';
  }

  function renderCards() {
    return _plans.map((plan) => {
      const lim = plan.limits || {};
      const hi = plan.highlight ? ' pricing-card--hi' : '';
      const feats = (plan.features || []).slice(0, 8).map((f) => {
        const label = f.label || f.id || f;
        return `<li>${label}</li>`;
      }).join('');
      const more = (plan.features || []).length > 8
        ? `<li>+${plan.features.length - 8} 項…</li>` : '';
      return `
      <article class="pricing-card${hi}" data-plan="${plan.id}">
        <div class="pricing-card-hd">
          <div class="pricing-card-name">${plan.name}</div>
          ${plan.highlight ? '<span class="badge b-ac">推薦</span>' : ''}
        </div>
        <p class="pricing-card-tag">${plan.tagline || ''}</p>
        <div class="pricing-price">${fmtMoney(plan)}</div>
        <p class="pricing-limits">
          回測 ${lim.daily_backtests}/日 · 組合 ${lim.daily_portfolio_runs}/日 ·
          並行 ${lim.concurrent_tasks} · 自選 ${lim.max_watchlist} · 配置 ${lim.max_allocation_positions} 檔
        </p>
        <ul class="pricing-feats">${feats}${more}</ul>
        <div class="pricing-card-ft">${ctaForPlan(plan)}</div>
      </article>`;
    }).join('');
  }

  function render() {
    const root = $id('pricing-root');
    if (!root) return;
    if (!_plans.length) {
      root.innerHTML = '<p class="placeholder-msg">無法載入方案，請稍後重試。</p>';
      return;
    }
    root.innerHTML = `
      ${_paymentNote ? `<div class="pricing-note">${_paymentNote}</div>` : ''}
      <div class="pricing-grid">${renderCards()}</div>
      ${renderCompare()}
    `;
    bindActions(root);
    renderAccount();
  }

  async function loadMe() {
    if (!isLoggedIn()) {
      _me = null;
      renderAccount();
      return;
    }
    try {
      const data = await Api.getBillingMe();
      _me = data;
      render();
    } catch (e) {
      _me = null;
      renderAccount();
    }
  }

  async function loadPlans() {
    const data = await Api.getBillingPlans();
    _plans = Array.isArray(data?.plans) ? data.plans : [];
    _paymentNote = String(data?.payment_note || '').trim();
    _featureLabels = (data?.feature_labels && typeof data.feature_labels === 'object') ? data.feature_labels : {};
    _featureOrder = Array.isArray(data?.feature_order) ? data.feature_order : [];
    render();
    await loadMe();
  }

  async function upgradePro() {
    if (!isLoggedIn()) {
      Api.showLoginModal?.(false);
      return;
    }
    try {
      const res = await Api.billingCheckout('pro');
      _me = res;
      toast(res?.message || '已開通 Pro', 'success');
      await loadMe();
      await Api.refreshBillingBadge?.();
      window.dispatchEvent(new CustomEvent('stockq:auth-changed', { detail: { loggedIn: true } }));
    } catch (e) {
      const d = e?.detail || e?.message || String(e);
      const msg = typeof d === 'object' ? (d.message || JSON.stringify(d)) : d;
      if (String(msg).includes('contact_sales') || String(e?.message).includes('機構')) {
        toast('機構版請聯繫銷售開通', 'info');
        return;
      }
      toast(msg || '升級失敗', 'error');
    }
  }

  function bindActions(root) {
    root.querySelectorAll('[data-pricing-upgrade]').forEach((btn) => {
      btn.addEventListener('click', () => upgradePro());
    });
    root.querySelectorAll('[data-pricing-contact]').forEach((btn) => {
      btn.addEventListener('click', () => {
        toast('機構版：請透過官網或管理員開通定制方案', 'info');
      });
    });
    root.querySelectorAll('[data-pricing-downgrade]').forEach((btn) => {
      btn.addEventListener('click', () => {
        toast('如需降級請聯繫支援或在管理後台調整', 'info');
      });
    });
  }

  function bindAuth() {
    if (_authBound) return;
    _authBound = true;
    window.addEventListener('stockq:auth-changed', () => {
      loadMe().catch(() => {});
    });
  }

  async function init() {
    bindAuth();
    const root = $id('pricing-root');
    if (root) root.innerHTML = '<p class="placeholder-msg">載入方案中…</p>';
    try {
      await loadPlans();
    } catch (e) {
      if (root) root.innerHTML = `<p class="placeholder-msg">載入失敗：${e?.message || e}</p>`;
    }
  }

  async function onShow() {
    await loadMe();
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.pricing = { init, onShow };
})();
