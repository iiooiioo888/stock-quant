/* global Utils */

// StockQ Pro UI component library (vanilla JS)
// Exposes: window.StockQPro.UI
(() => {
  const UI = {};

  // ─────────────────────────────────────────────────────────────
  // Core helpers
  // ─────────────────────────────────────────────────────────────
  const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v);

  UI.qs = (sel, root = document) => root.querySelector(sel);
  UI.qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  UI.id = (id) => document.getElementById(id);

  UI.escapeHtml = (s) => String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

  UI.h = (tag, props, ...children) => {
    const el = document.createElement(tag);

    const p = isObj(props) ? props : {};
    Object.entries(p).forEach(([k, v]) => {
      if (v == null) return;
      if (k === 'class' || k === 'className') el.className = String(v);
      else if (k === 'style' && isObj(v)) Object.assign(el.style, v);
      else if (k === 'dataset' && isObj(v)) Object.entries(v).forEach(([dk, dv]) => { el.dataset[dk] = String(dv); });
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'html') el.innerHTML = String(v);
      else el.setAttribute(k, String(v));
    });

    const flat = children.flat(Infinity).filter((c) => c !== false && c !== true && c != null);
    flat.forEach((c) => {
      if (c instanceof Node) el.appendChild(c);
      else el.appendChild(document.createTextNode(String(c)));
    });
    return el;
  };

  UI.clear = (el) => {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
  };

  UI.mount = (root, node) => {
    const r = (typeof root === 'string') ? UI.id(root) : root;
    if (!r) return null;
    UI.clear(r);
    if (node) r.appendChild(node);
    return r;
  };

  UI.on = (root, eventName, selector, handler) => {
    const r = (typeof root === 'string') ? UI.id(root) : root;
    if (!r) return () => {};
    const fn = (e) => {
      const t = e.target?.closest?.(selector);
      if (!t || !r.contains(t)) return;
      handler(e, t);
    };
    r.addEventListener(eventName, fn);
    return () => r.removeEventListener(eventName, fn);
  };

  // ─────────────────────────────────────────────────────────────
  // Primitive components (match pro.css)
  // ─────────────────────────────────────────────────────────────
  UI.Badge = ({ text, tone } = {}) => UI.h('span', { class: `badge ${tone ? `b-${tone}` : ''}`.trim() }, text ?? '');

  UI.Button = ({ text, tone, size, type = 'button', attrs, onClick } = {}) => {
    const cls = ['btn', size ? `btn-${size}` : '', tone ? `btn-${tone}` : ''].filter(Boolean).join(' ');
    return UI.h('button', { class: cls, type, ...(attrs || {}), onclick: onClick }, text ?? '');
  };

  UI.Panel = ({ title, right, body, noPad, compact } = {}) => {
    const pbClass = noPad ? 'pb no-pad' : (compact ? 'pb c' : 'pb');
    const phRight = Array.isArray(right) ? right : (right ? [right] : []);
    return UI.h('div', { class: 'pnl' },
      UI.h('div', { class: 'ph' },
        UI.h('div', { class: 'pt' }, title ?? ''),
        UI.h('div', { class: 'pa' }, ...phRight),
      ),
      UI.h('div', { class: pbClass }, ...(Array.isArray(body) ? body : [body]).filter(Boolean)),
    );
  };

  UI.FormRow = (...fields) => UI.h('div', { class: 'fr' }, ...fields);
  UI.FormGroup = ({ label, child } = {}) => UI.h('div', { class: 'fg' }, UI.h('label', {}, label ?? ''), child);

  UI.Switch = ({ id, checked, label, title, onChange } = {}) => {
    const inp = UI.h('input', {
      id,
      type: 'checkbox',
      ...(checked ? { checked: 'checked' } : {}),
      title: title || label || '',
      'aria-label': label || title || '',
      onchange: onChange,
    });
    return UI.h('div', { style: { display: 'flex', alignItems: 'center', gap: '6px' } },
      UI.h('label', { class: 'sw' }, inp, UI.h('span', { class: 'sw-s' })),
      UI.h('span', { style: { fontSize: '.68rem', color: 'var(--t2)' } }, label ?? ''),
    );
  };

  UI.Table = ({ head = [], rows = [], tbodyId, compact } = {}) => {
    const thead = UI.h('thead', {}, UI.h('tr', {}, ...head.map((h) => UI.h('th', {}, h))));
    const tbody = UI.h('tbody', tbodyId ? { id: tbodyId } : {}, ...(rows || []).map((r) => UI.h('tr', {}, ...(r || []).map((c) => UI.h('td', {}, c)))));
    const tbl = UI.h('table', { class: 'tbl' }, thead, tbody);
    const wrap = UI.h('div', { class: compact ? 'pb c' : 'pb c', style: { overflowX: 'auto' } }, tbl);
    return { wrap, tbl, tbody };
  };

  // ─────────────────────────────────────────────────────────────
  // Toasts
  // ─────────────────────────────────────────────────────────────
  UI.toast = (msg, type = 'ok', opts = {}) => {
    const c = UI.id(opts.containerId || 'toasts');
    if (!c) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    const icon = type === 'ok' ? '✓' : type === 'er' ? '✕' : 'ℹ';
    el.innerHTML = `<span>${icon}</span><span>${UI.escapeHtml(msg ?? '')}</span>`;
    c.appendChild(el);
    const ttl = Number(opts.ttlMs || 3000);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = '.3s'; }, ttl);
    setTimeout(() => el.remove(), ttl + 500);
  };

  // ─────────────────────────────────────────────────────────────
  // Modal helpers (work with existing .modal-ov markup)
  // ─────────────────────────────────────────────────────────────
  UI.modalOpen = (id) => {
    const el = UI.id(id);
    if (!el) return;
    el.classList.add('show');
    el.setAttribute('aria-hidden', 'false');
  };

  UI.modalClose = (id) => {
    const el = UI.id(id);
    if (!el) return;
    el.classList.remove('show');
    el.setAttribute('aria-hidden', 'true');
  };

  // Build a modal DOM node (optional; you can also keep static HTML)
  UI.Modal = ({ id, title, width, body, footer } = {}) => {
    const ov = UI.h('div', { class: 'modal-ov', id, 'aria-hidden': 'true' },
      UI.h('div', { class: 'modal', style: width ? { width: String(width) } : undefined },
        UI.h('div', { class: 'mh' },
          UI.h('span', { class: 'mt' }, title ?? ''),
          UI.h('button', { class: 'mc', type: 'button', 'data-close': id }, '×'),
        ),
        UI.h('div', { class: 'mb' }, ...(Array.isArray(body) ? body : [body]).filter(Boolean)),
        UI.h('div', { class: 'mf' }, ...(Array.isArray(footer) ? footer : [footer]).filter(Boolean)),
      ),
    );
    return ov;
  };

  // ─────────────────────────────────────────────────────────────
  // Strategy library building blocks
  // ─────────────────────────────────────────────────────────────
  UI.CatPill = ({ id, name, count, color, onClick, active } = {}) => (
    UI.h('button', { type: 'button', class: `cat-pill ${active ? 'on' : ''}`.trim(), dataset: { cat: id }, onclick: onClick },
      UI.h('span', { class: 'cp-dot', style: { background: color || 'var(--ac)' } }),
      UI.h('span', {}, name ?? ''),
      UI.h('span', { class: 'cp-cnt' }, count != null ? String(count) : ''),
    )
  );

  UI.StrategyCard = ({ num, name, desc, tier, status, active } = {}) => {
    const tierCls = tier === 'pro' ? 'tier-pro' : tier === 'ent' ? 'tier-ent' : 'tier-free';
    const runnable = status === 'implemented' || status === 'user';
    const statusCls = runnable ? 'is-ready' : 'is-planned';
    const badgeText = runnable ? '可回測' : '即將推出';
    return UI.h('div', { class: `strat-card ${statusCls} ${active ? 'active' : ''}`.trim() },
      UI.h('div', { class: 'strat-hdr' },
        UI.h('div', { class: 'strat-num' }, num != null ? `#${String(num).padStart(3, '0')}` : ''),
        UI.h('div', { class: 'strat-name' }, name ?? ''),
      ),
      UI.h('div', { class: 'strat-desc' }, desc ?? ''),
      UI.h('div', { class: 'strat-foot' },
        UI.h('span', { class: `strat-tier ${tierCls}` }, String(tier || 'free').toUpperCase()),
        UI.h('span', { class: `strat-status ${runnable ? 'ok' : 'plan'}` }, badgeText),
      ),
    );
  };

  // ─────────────────────────────────────────────────────────────
  // Init hooks
  // ─────────────────────────────────────────────────────────────
  UI.init = () => {
    // close modal when clicking overlay background
    UI.qsa('.modal-ov').forEach((ov) => {
      ov.addEventListener('click', (e) => {
        if (e.target === ov) UI.modalClose(ov.id);
      });
    });
    // wire data-close buttons
    UI.qsa('[data-close]').forEach((btn) => {
      btn.addEventListener('click', () => UI.modalClose(btn.getAttribute('data-close')));
    });
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.UI = UI;

  // auto-init after DOM ready (safe no-op if called twice)
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => UI.init());
  else UI.init();
})();

