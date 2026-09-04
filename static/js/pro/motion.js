/**
 * StockQ Motion — 輕量動畫層（Web Animations API + 可選 anime.js）
 */
(() => {
  const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches === true;

  function animate(el, keyframes, opts = {}) {
    if (document.hidden) return Promise.resolve();
    if (!el || typeof el.animate !== 'function') return Promise.resolve();
    if (el.children && el.children.length > 12) return Promise.resolve();
    if (reduced()) {
      const last = Array.isArray(keyframes) ? keyframes[keyframes.length - 1] : keyframes;
      if (last && typeof last === 'object') Object.assign(el.style, last);
      return Promise.resolve();
    }
    const anim = el.animate(keyframes, {
      duration: opts.duration ?? 280,
      easing: opts.easing ?? 'cubic-bezier(0.22, 1, 0.36, 1)',
      fill: opts.fill ?? 'both',
      delay: opts.delay ?? 0,
    });
    return anim.finished.catch(() => {});
  }

  function fadeIn(el, opts) {
    return animate(el, [
      { opacity: 0, transform: 'translateY(6px)' },
      { opacity: 1, transform: 'translateY(0)' },
    ], opts);
  }

  function stagger(nodes, opts = {}) {
    if (reduced()) return;
    const max = opts.max ?? 3;
    const list = Array.from(nodes || []).slice(0, max);
    const step = opts.step ?? 18;
    list.forEach((el, i) => {
      fadeIn(el, { ...opts, delay: (opts.delay || 0) + i * step });
    });
  }

  async function ensureAnime() {
    const loader = window.StockQPro?.charts?.ensureAnime;
    if (loader) return loader();
    return typeof window.anime === 'function' ? window.anime : null;
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.Motion = { reduced, animate, fadeIn, stagger, ensureAnime };
})();
