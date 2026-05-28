const LS_ESM_ALL = 'sq_esm_all';
const LS_ESM_PAGES = 'sq_esm_pages';

function _parseList(v) {
  const s = String(v || '').trim();
  if (!s) return new Set();
  return new Set(
    s.split(',')
      .map((x) => String(x || '').trim())
      .filter(Boolean),
  );
}

function _getQuery() {
  try {
    return new URLSearchParams(String(location.search || ''));
  } catch (_) {
    return new URLSearchParams();
  }
}

export function getEsmConfig() {
  const q = _getQuery();

  // Highest priority: explicit off
  const esmQ = q.get('esm');
  if (esmQ === '0' || esmQ === 'false' || esmQ === 'off') {
    return { forceLegacy: true, forceAll: false, pages: new Set() };
  }

  // Explicit on: esm=1 (all) or esm=<pageId>
  if (esmQ === '1' || esmQ === 'true' || esmQ === 'on' || esmQ === 'all') {
    return { forceLegacy: false, forceAll: true, pages: new Set() };
  }
  if (esmQ && esmQ !== '0') {
    return { forceLegacy: false, forceAll: false, pages: new Set([esmQ]) };
  }

  // Optional: esmPages=tasks,compare
  const esmPagesQ = q.get('esmPages');
  if (esmPagesQ) {
    return { forceLegacy: false, forceAll: false, pages: _parseList(esmPagesQ) };
  }

  // LocalStorage flags
  try {
    if (localStorage.getItem(LS_ESM_ALL) === '1') {
      return { forceLegacy: false, forceAll: true, pages: new Set() };
    }
    const pages = _parseList(localStorage.getItem(LS_ESM_PAGES));
    if (pages.size) return { forceLegacy: false, forceAll: false, pages };
  } catch (_) {}

  return { forceLegacy: false, forceAll: false, pages: new Set() };
}

export function isEsmEnabledForPage(pageId) {
  const pid = String(pageId || '').trim();
  if (!pid) return false;
  const cfg = getEsmConfig();
  if (cfg.forceLegacy) return false;
  if (cfg.forceAll) return true;
  return cfg.pages.has(pid);
}

