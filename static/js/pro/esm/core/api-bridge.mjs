export function getGlobals() {
  const g = (typeof window !== 'undefined') ? window : globalThis;
  return {
    Api: g.Api,
    Utils: g.Utils,
    TaskCommon: g.TaskCommon,
    StockQPro: g.StockQPro,
  };
}

export function getProApp() {
  return getGlobals().StockQPro?.App || null;
}

export function toast(msg, type = 'info') {
  const { Utils } = getGlobals();
  const app = getProApp();
  const map = { success: 'ok', warning: 'warn', error: 'er', info: 'inf' };
  if (app?.toast) return app.toast(String(msg || ''), map[type] || 'inf');
  if (Utils?.toast) return Utils.toast(msg, 3000, type);
}

