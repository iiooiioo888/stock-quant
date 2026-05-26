/**
 * local-store.js — 本機瀏覽器資料（localStorage 統一命名空間）
 *
 * 鍵名：stockq:local_v1
 * 用途：最近瀏覽、收藏、上次 Tab/代碼、介面狀態（與 sq_token 分開）
 */
const LocalStore = {
  STORAGE_KEY: 'stockq:local_v1',
  VERSION: 1,

  DEFAULTS: {
    recentStocks: [],
    recentMax: 30,
    favorites: [],
    lastTab: 'dashboard',
    lastStockCode: '',
    lastBacktest: { code: '', strategy: 'dual_ma' },
    lastAnalysis: { code: '', strategy: 'dual_ma' },
    sdIndexSearch: '',
    theme: 'dark',
    sidebarCollapsed: false,
    tipDismissed: false,
    compareChips: [],
    compareCustomPresets: [],
    formDrafts: {},
  },

  _cache: null,

  load() {
    if (this._cache) return { ...this._cache };
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        this._cache = { ...this.DEFAULTS, ...parsed };
        return { ...this._cache };
      }
    } catch (e) {
      console.warn('LocalStore.load failed', e);
    }
    this._cache = { ...this.DEFAULTS };
    this._migrateLegacyKeys(this._cache);
    return { ...this._cache };
  },

  save(partial = {}) {
    const next = { ...this.load(), ...partial };
    next.recentMax = Math.min(50, Math.max(5, Number(next.recentMax) || this.DEFAULTS.recentMax));
    if (!Array.isArray(next.recentStocks)) next.recentStocks = [];
    if (!Array.isArray(next.favorites)) next.favorites = [];
    if (!Array.isArray(next.compareChips)) next.compareChips = [];
    if (!Array.isArray(next.compareCustomPresets)) next.compareCustomPresets = [];
    if (!next.formDrafts || typeof next.formDrafts !== 'object') next.formDrafts = {};
    this._cache = next;
    try {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(next));
    } catch (e) {
      console.warn('LocalStore.save failed (quota?)', e);
    }
    this._dispatchChange();
    return { ...next };
  },

  get(key) {
    return this.load()[key];
  },

  set(key, value) {
    return this.save({ [key]: value });
  },

  _migrateLegacyKeys(target) {
    if (target._legacyMigrated) return;
    const theme = localStorage.getItem('theme');
    if (theme === 'light' || theme === 'dark') target.theme = theme;
    if (localStorage.getItem('sidebarCollapsed') === 'true') target.sidebarCollapsed = true;
    if (localStorage.getItem('tipDismissed') === 'true') target.tipDismissed = true;
    try {
      const cmp = localStorage.getItem('stockq:compare_chips');
      if (cmp) target.compareChips = JSON.parse(cmp);
    } catch (_) {}
    target._legacyMigrated = true;
    this._cache = target;
    try {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(target));
    } catch (_) {}
  },

  init() {
    this.load();
    this._migrateLegacyKeys(this._cache || this.load());
  },

  _dispatchChange() {
    try {
      window.dispatchEvent(new CustomEvent('stockq:local-changed', { detail: this.load() }));
    } catch (_) {}
  },

  /** 最近瀏覽（去重，最新在前） */
  pushRecentStock(item) {
    const code = String(item?.code || '').trim();
    if (!code) return this.load().recentStocks;
    const name = String(item?.name || '').trim();
    const market = item?.market || '';
    const now = Date.now();
    const max = this.get('recentMax') || this.DEFAULTS.recentMax;
    let list = (this.get('recentStocks') || []).filter(s => String(s.code) !== code);
    list.unshift({ code, name, market, ts: now });
    if (list.length > max) list = list.slice(0, max);
    this.save({ recentStocks: list, lastStockCode: code });
    return list;
  },

  getRecentStocks(limit) {
    const n = limit == null ? this.get('recentMax') : limit;
    return (this.get('recentStocks') || []).slice(0, n);
  },

  clearRecentStocks() {
    return this.save({ recentStocks: [] });
  },

  toggleFavorite(code) {
    const c = String(code || '').trim();
    if (!c) return false;
    let favs = [...(this.get('favorites') || [])];
    const i = favs.indexOf(c);
    if (i >= 0) {
      favs.splice(i, 1);
      this.save({ favorites: favs });
      return false;
    }
    favs.unshift(c);
    if (favs.length > 100) favs = favs.slice(0, 100);
    this.save({ favorites: favs });
    return true;
  },

  isFavorite(code) {
    return (this.get('favorites') || []).includes(String(code || '').trim());
  },

  /** 表單草稿（如篩選條件） */
  setDraft(key, value) {
    const drafts = { ...(this.get('formDrafts') || {}) };
    drafts[key] = value;
    return this.save({ formDrafts: drafts });
  },

  getDraft(key, fallback = null) {
    const drafts = this.get('formDrafts') || {};
    return drafts[key] !== undefined ? drafts[key] : fallback;
  },

  exportJson() {
    return JSON.stringify(this.load(), null, 2);
  },

  importJson(text, merge = true) {
    const data = JSON.parse(text);
    if (!merge) {
      this._cache = null;
      return this.save({ ...this.DEFAULTS, ...data });
    }
    return this.save(data);
  },

  clearAll() {
    this._cache = null;
    localStorage.removeItem(this.STORAGE_KEY);
    this._dispatchChange();
    return { ...this.DEFAULTS };
  },
};

window.LocalStore = LocalStore;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => LocalStore.init());
} else {
  LocalStore.init();
}
