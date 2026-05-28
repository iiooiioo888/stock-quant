import { isEsmEnabledForPage } from '../core/env.mjs';
import { normalizeLifecycle } from '../core/lifecycle.mjs';
import { PAGE_ENTRIES } from './pages-map.mjs';
import { getOrSetPagePromise, setPage, getPage } from '../core/registry.mjs';

const V = 'stockq-esm-20260528';

function withVersion(url) {
  const src = String(url || '');
  if (!src) return src;
  const sep = src.includes('?') ? '&' : '?';
  return `${src}${sep}v=${encodeURIComponent(V)}`;
}

async function importEntry(url) {
  const u = withVersion(url);
  // eslint-disable-next-line no-new-func
  return await import(u);
}

export function isEnabled(pageId) {
  return isEsmEnabledForPage(pageId);
}

export async function ensurePage(pageId) {
  const pid = String(pageId || '').trim();
  if (!pid) return null;
  if (!isEnabled(pid)) return null;

  const url = PAGE_ENTRIES[pid];
  if (!url) throw new Error(`ESM entry not found for page: ${pid}`);

  return await getOrSetPagePromise(pid, async () => {
    if (getPage(pid)) return getPage(pid);
    const mod = await importEntry(url);
    const life = normalizeLifecycle(mod);
    if (!life?.pageId) throw new Error(`ESM page missing pageId: ${pid}`);
    setPage(life.pageId, mod);
    return mod;
  });
}

