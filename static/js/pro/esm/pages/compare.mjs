import { getGlobals } from '../core/api-bridge.mjs';

export const pageId = 'compare';

const state = {
  inited: false,
  legacyReady: false,
};

async function ensureLegacyCompareLoaded() {
  const g = getGlobals();
  const loader = g?.StockQPro?.modules?.loadScript;

  if (g?.StockQPro?.pages?.compare?.init && g?.StockQPro?.pages?.compare?.onShow) {
    state.legacyReady = true;
    return g.StockQPro.pages.compare;
  }

  if (typeof loader !== 'function') {
    throw new Error('compare 模組載入器不可用（StockQPro.modules.loadScript）');
  }

  await loader('/static/js/pro/modules/compare-pro.js');

  const mod = g?.StockQPro?.pages?.compare;
  if (!mod?.init || !mod?.onShow) {
    throw new Error('compare legacy 模組載入失敗（pages.compare 未註冊）');
  }

  state.legacyReady = true;
  return mod;
}

export async function init() {
  if (state.inited) return;
  state.inited = true;
  const legacy = await ensureLegacyCompareLoaded();
  await Promise.resolve(legacy.init?.());
}

export async function onShow() {
  const legacy = await ensureLegacyCompareLoaded();
  await Promise.resolve(legacy.onShow?.());
}

export function unload() {
  const g = getGlobals();
  const legacy = g?.StockQPro?.pages?.compare;
  try { legacy?.unload?.(); } catch (_) {}
}

export function rebindWs() {
  // compare 頁目前不依賴 WS 重綁，保留空函數以符合 App 迭代呼叫介面
}

