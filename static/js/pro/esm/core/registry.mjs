const _pages = new Map(); // pageId -> module
const _pagePromises = new Map(); // pageId -> Promise<module>

export function hasPage(pageId) {
  return _pages.has(String(pageId || '').trim());
}

export function getPage(pageId) {
  return _pages.get(String(pageId || '').trim()) || null;
}

export function setPage(pageId, mod) {
  const pid = String(pageId || '').trim();
  if (!pid || !mod) return;
  _pages.set(pid, mod);
}

export function getOrSetPagePromise(pageId, factory) {
  const pid = String(pageId || '').trim();
  if (!pid) return Promise.resolve(null);
  if (_pagePromises.has(pid)) return _pagePromises.get(pid);
  const p = Promise.resolve().then(factory);
  _pagePromises.set(pid, p);
  return p;
}

export function listPages() {
  return Array.from(_pages.keys());
}

