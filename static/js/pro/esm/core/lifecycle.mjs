export function normalizeLifecycle(mod) {
  if (!mod) return null;
  return {
    pageId: String(mod.pageId || '').trim(),
    init: typeof mod.init === 'function' ? mod.init.bind(mod) : null,
    onShow: typeof mod.onShow === 'function' ? mod.onShow.bind(mod) : null,
    unload: typeof mod.unload === 'function' ? mod.unload.bind(mod) : null,
    rebindWs: typeof mod.rebindWs === 'function' ? mod.rebindWs.bind(mod) : null,
  };
}

export function safeCall(fn) {
  try {
    const r = fn && fn();
    return Promise.resolve(r);
  } catch (e) {
    return Promise.reject(e);
  }
}

