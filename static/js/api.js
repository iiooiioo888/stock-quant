/**
 * api.js — API 客戶端封裝（含 Token 管理）
 * 性能優化：請求合併、智能緩存、預取、壓縮傳輸
 */

const API_BASE = '';

const Api = {
  _token: null,
  _loggingIn: false,
  _getCache: new Map(),
  _inflight: new Map(),
  _exclusive: new Map(),
  _debouncedGetTimers: new Map(),
  
  // 性能優化配置
  _optimization: {
    enableCompression: true,      // 啟用數據壓縮
    enablePrefetch: true,         // 啟用預取
    enableBatching: true,         // 啟用批量請求
    maxConcurrent: 5,             // 最大並發數
    retryBaseDelay: 500,          // 重試基礎延遲 (ms)
  },
  _activeRequests: 0,
  _requestQueue: [],
  
  /** GET 緩存 TTL（毫秒）- 擴展版 */
  _cacheTtl: {
    '/api/health': 3000,
    '/api/health/detailed': 8000,
    '/api/health/sop': 5000,
    '/api/strategies/list': 120000,
    '/api/config': 120000,
    '/api/stocks': 30000,
    '/api/indices/charts': 120000,
    '/api/tasks': 2500,
    '/api/tasks/queue': 2500,
    '/api/sparkline': 60000,
    '/api/kline': 10000,
  },

  /**
   * 解析 JWT payload（不驗簽，僅讀 exp）
   */
  isTokenExpired(token) {
    if (!token) return true;
    try {
      const part = String(token).split('.')[1];
      if (!part) return true;
      const b64 = part.replace(/-/g, '+').replace(/_/g, '/');
      const payload = JSON.parse(atob(b64));
      if (!payload.exp) return false;
      return payload.exp * 1000 < Date.now() - 5000;
    } catch {
      return true;
    }
  },

  /**
   * 初始化：從 localStorage 載入 token
   */
  init() {
    const stored = SecureStore.getItem('sq_token');
    if (stored && this.isTokenExpired(stored)) {
      SecureStore.removeItem('sq_token');
      this._token = null;
    } else {
      this._token = stored;
    }
    this._updateAuthUI();
    try {
      window.dispatchEvent(new CustomEvent('stockq:auth-changed', {
        detail: { loggedIn: !!this._token },
      }));
    } catch (_) {}
  },

  /**
   * 重連 WebSocket（Pro 與 legacy 僅保留單一連線）
   */
  reconnectWebSocket() {
    const pro = window.StockQPro?.App;
    if (pro?.reconnectWs) {
      pro.reconnectWs();
      return;
    }
    if (typeof App !== 'undefined' && App._connectWS) {
      App._wsRetry = 0;
      App._connectWS();
    }
  },

  /**
   * 保存 token
   */
  setToken(token) {
    if (token && this.isTokenExpired(token)) {
      token = null;
    }
    this._token = token;
    if (token) {
      SecureStore.setItem('sq_token', token);
    } else {
      SecureStore.removeItem('sq_token');
    }
    this._updateAuthUI();
    this.reconnectWebSocket();
    try {
      window.dispatchEvent(new CustomEvent('stockq:auth-changed', {
        detail: { loggedIn: !!token },
      }));
    } catch (_) {}
  },

  /**
   * 當前是否有 token
   */
  isLoggedIn() {
    return !!this._token;
  },

  /**
   * 更新 header 的登錄狀態 UI
   */
  _billingCache: null,

  _updateAuthUI() {
    const el = document.getElementById('authStatus');
    const pill = document.getElementById('auth-pill');
    if (this._token) {
      if (el) {
        el.innerHTML = '<span style="color:var(--green)">●</span> 已登錄';
        el.title = '點擊開設定，連點登出';
        el.style.cursor = 'pointer';
      }
      if (pill) {
        const plan = this._billingCache?.plan_name || this._billingCache?.plan_id || '';
        const letter = (this._billingCache?.username || 'U').slice(0, 1).toUpperCase();
        pill.textContent = plan ? letter : letter;
        pill.title = plan ? `${plan} · 點擊開設定，連點登出` : '已登錄 · 點擊開設定，連點登出';
        pill.dataset.plan = plan || '';
      }
      this.refreshBillingBadge?.();
    } else {
      this._billingCache = null;
      if (el) {
        el.innerHTML = '<span style="color:var(--red)">●</span> 未登錄';
        el.title = '點擊登錄';
        el.style.cursor = 'pointer';
      }
      if (pill) {
        pill.textContent = '訪';
        pill.title = '點擊登錄';
        delete pill.dataset.plan;
      }
      const badge = document.getElementById('plan-badge');
      if (badge) {
        badge.hidden = true;
        badge.textContent = '';
      }
    }
  },

  async refreshBillingBadge() {
    if (!this._token) return;
    try {
      const me = await this.get('/api/auth/me', { silent: true, timeout: 12000 });
      const bill = me?.user?.billing;
      if (bill) {
        this._billingCache = {
          plan_id: bill.plan_id,
          plan_name: bill.plan_name,
          username: me?.user?.username,
        };
        const pill = document.getElementById('auth-pill');
        const badge = document.getElementById('plan-badge');
        if (pill && bill.plan_name) {
          pill.title = `${bill.plan_name} · 點擊開設定，連點登出`;
          pill.dataset.plan = bill.plan_id || '';
        }
        if (badge) {
          if (bill.plan_id && bill.plan_id !== 'free') {
            badge.hidden = false;
            badge.textContent = bill.plan_name || bill.plan_id;
            badge.title = '當前訂閱方案';
          } else {
            badge.hidden = true;
            badge.textContent = '';
          }
        }
      }
    } catch (_) { /* ignore */ }
  },

  /**
   * 顯示登錄 Modal
   */
  showLoginModal(isRegister = false) {
    const title = isRegister ? '註冊賬號' : '登錄';
    const btnText = isRegister ? '註冊' : '登錄';
    const switchText = isRegister ? '已有賬號？去登錄' : '沒有賬號？去註冊';
    const switchAction = isRegister ? 'Api.showLoginModal(false)' : 'Api.showLoginModal(true)';

    Utils.showModal(`
      <h3>${title}</h3>
      <div class="fg"><label>用戶名</label><input id="loginUsername" placeholder="至少 3 個字符"></div>
      <div class="fg"><label>密碼</label><input id="loginPassword" type="password" placeholder="至少 6 個字符"></div>
      <div id="loginError" style="color:var(--red);font-size:12px;margin-top:4px;display:none"></div>
      <div class="actions">
        <button class="btn s" onclick="Utils.closeModal()">取消</button>
        <button class="btn s" style="font-size:11px" onclick="${switchAction}">${switchText}</button>
        <button class="btn" id="loginSubmitBtn" onclick="Api.doLogin(${isRegister})">${btnText}</button>
      </div>
    `);

    // Enter 鍵提交
    const pwInput = document.getElementById('loginPassword');
    if (pwInput) {
      pwInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') Api.doLogin(isRegister);
      });
    }
  },

  /**
   * 執行登錄/註冊
   */
  async doLogin(isRegister = false) {
    if (this._loginRunning) return;
    const username = document.getElementById('loginUsername')?.value?.trim();
    const password = document.getElementById('loginPassword')?.value;
    const errorEl = document.getElementById('loginError');

    if (!username || !password) {
      if (errorEl) { errorEl.textContent = '請填寫用戶名和密碼'; errorEl.style.display = 'block'; }
      return;
    }

    this._loginRunning = true;
    const loginBtn = document.getElementById('loginSubmitBtn');
    Utils.btnLoading(loginBtn, true, '處理中...');
    const endpoint = isRegister ? '/api/auth/register' : '/api/auth/login';
    try {
      const resp = await fetch(API_BASE + endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await resp.json();

      if (!resp.ok) {
        if (errorEl) { errorEl.textContent = data.detail || '操作失敗'; errorEl.style.display = 'block'; }
        return;
      }

      this.setToken(data.token);
      Utils.closeModal();
      Utils.toast(`${isRegister ? '註冊' : '登錄'}成功`, 3000, 'success');
      this.refreshBillingBadge?.();

      if (typeof App !== 'undefined' && App._initQuickStats) {
        App._initQuickStats();
      }

      // 刷新當前頁面數據
      if (typeof Dashboard !== 'undefined') Dashboard.load();
    } catch (e) {
      if (errorEl) { errorEl.textContent = '網絡錯誤: ' + e.message; errorEl.style.display = 'block'; }
    } finally {
      this._loginRunning = false;
      const loginBtn = document.getElementById('loginSubmitBtn');
      Utils.btnLoading(loginBtn, false, isRegister ? '註冊' : '登錄');
    }
  },

  /**
   * 登出
   */
  logout() {
    this.setToken(null);
    Utils.toast('已登出', 3000, 'success');
    if (typeof Dashboard !== 'undefined') Dashboard.load();
  },

  parseErrorBody(err, status) {
    if (!err) return 'HTTP ' + status;
    if (typeof err.msg === 'string') {
      return err.trace_id ? err.msg + ' (' + err.trace_id + ')' : err.msg;
    }
    if (err.detail) {
      return typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
    }
    return 'HTTP ' + status;
  },

  _billingDetail(err) {
    const d = err?.detail;
    return d && typeof d === 'object' && !Array.isArray(d) ? d : null;
  },

  /** 403/429 計費相關：提示並可跳轉定價頁 */
  handleBillingGate(err, status, opts) {
    opts = opts || {};
    const detail = this._billingDetail(err);
    if (!detail?.code) return false;
    const billingCodes = ['feature_locked', 'plan_required', 'quota_exceeded', 'limit_exceeded'];
    if (!billingCodes.includes(detail.code)) return false;

    const msg = detail.message || '請升級方案以使用此功能';
    if (!opts.silent) {
      const kind = detail.code === 'quota_exceeded' ? 'warning' : 'warning';
      if (typeof Utils !== 'undefined') {
        Utils.toast(msg, 4500, kind);
      }
      const nav = () => {
        try {
          window.StockQPro?.App?.nav?.('pricing', { syncHash: true });
        } catch (_) { /* ignore */ }
      };
      if (detail.code !== 'quota_exceeded') {
        setTimeout(nav, 600);
      } else {
        setTimeout(async () => {
          if (await Utils.confirm(`${msg}\n\n是否前往方案頁查看配額？`)) nav();
        }, 200);
      }
    }
    return true;
  },

  handleApiError(err, status, opts) {
    opts = opts || {};
    if ((status === 403 || status === 429) && this.handleBillingGate(err, status, opts)) {
      return err?.detail?.message || this.parseErrorBody(err, status);
    }
    const msg = this.parseErrorBody(err, status);
    if (!opts.silent && typeof Utils !== 'undefined') {
      Utils.toast('請求失敗: ' + msg, 3000, 'error');
    }
    return msg;
  },

  /**
   * 帶超時與指數退避重試的 fetch（用於關鍵 API）
   */
  async fetchWithRetry(url, options = {}) {
    const {
      retries = 3,
      timeout = 8000,
      retryDelayMs = 1000,
      silent = false,
      ...fetchOpts
    } = options;
    let lastErr;
    for (let i = 0; i < retries; i += 1) {
      try {
        const signal = typeof AbortSignal !== 'undefined' && AbortSignal.timeout
          ? AbortSignal.timeout(timeout)
          : undefined;
        const resp = await fetch(url, { ...fetchOpts, signal });
        return resp;
      } catch (e) {
        lastErr = e;
        if (i >= retries - 1) break;
        await new Promise((r) => setTimeout(r, retryDelayMs * (i + 1)));
      }
    }
    throw lastErr;
  },

  /**
   * 通用 GET/POST 請求
   */
  async request(path, options = null) {
    const silent = !!(options && options.silent);
    const opts = options ? { ...options } : {};
    const retries = opts.retries != null ? opts.retries : 3;
    const timeout = opts.timeout != null ? opts.timeout : 15000;
    delete opts.silent;
    delete opts.retries;
    delete opts.timeout;
    try {
      const headers = {};
      if (this._token) {
        headers['Authorization'] = 'Bearer ' + this._token;
      }
      if (opts.headers) {
        Object.assign(headers, opts.headers);
      }

      const resp = await this.fetchWithRetry(API_BASE + path, {
        ...opts,
        headers,
        retries,
        timeout,
        silent,
      });

      if (resp.status === 401) {
        this.setToken(null);
        if (!silent) this.showLoginModal();
        return null;
      }

      if (resp.status === 429) {
        if (!silent && typeof Utils !== 'undefined') {
          Utils.toast('請求過於頻繁，請稍後再試', 3000, 'warning');
        }
        return { _rateLimited: true };
      }

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        this.handleApiError(err, resp.status, { silent });
        return null;
      }
      return await resp.json();
    } catch (e) {
      if (!silent) {
        Utils.toast('請求失敗: ' + e.message, 3000, 'error');
      }
      return null;
    }
  },

  /**
   * GET 請求（內存緩存 + 飛行中請求合併）
   */
  async get(path, opts = {}) {
    const basePath = path.split('?')[0];
    const ttl = opts.noCache ? 0 : (this._cacheTtl[basePath] || 0);
    const reqOpts = opts.silent ? { silent: true } : null;
    const cacheKey = path.includes('?') ? path : basePath;
    if (ttl > 0) {
      const hit = this._getCache.get(cacheKey);
      if (hit && Date.now() - hit.ts < ttl) {
        return hit.data;
      }
      if (this._inflight.has(cacheKey)) {
        return this._inflight.get(cacheKey);
      }
    }
    const p = this.request(path, reqOpts);
    if (ttl > 0) {
      this._inflight.set(cacheKey, p);
      p.then((data) => {
        if (data != null && !data._rateLimited) {
          this._getCache.set(cacheKey, { ts: Date.now(), data });
        }
      }).finally(() => this._inflight.delete(cacheKey));
    }
    return p;
  },

  clearGetCache(prefix = '') {
    if (!prefix) {
      this._getCache.clear();
      return;
    }
    for (const key of this._getCache.keys()) {
      if (key.startsWith(prefix)) this._getCache.delete(key);
    }
  },

  /**
   * 同 key 僅允許一個進行中 Promise（長任務防重複提交）
   */
  async runExclusive(key, fn) {
    if (this._exclusive.has(key)) return this._exclusive.get(key);
    const p = Promise.resolve().then(fn).finally(() => this._exclusive.delete(key));
    this._exclusive.set(key, p);
    return p;
  },

  /**
   * 去抖 GET（WS/輪詢觸發時合併請求）
   */
  debouncedGet(path, delayMs = 1500, opts = {}) {
    const prev = this._debouncedGetTimers.get(path);
    if (prev) clearTimeout(prev.timer);
    return new Promise((resolve) => {
      const timer = setTimeout(async () => {
        this._debouncedGetTimers.delete(path);
        resolve(await this.get(path, opts));
      }, delayMs);
      this._debouncedGetTimers.set(path, { timer });
    });
  },

  /**
   * POST JSON
   */
  async post(path, body = {}, opts = {}) {
    return this.request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      silent: !!opts.silent,
    });
  },

  /** 寫操作前檢查登錄；未登錄時彈出登錄框 */
  ensureLoggedIn() {
    if (this.isLoggedIn()) return true;
    this.showLoginModal(false);
    return false;
  },

  /**
   * PUT JSON
   */
  async put(path, body = {}) {
    return this.request(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },

  /**
   * DELETE
   */
  async delete(path) {
    return this.request(path, { method: 'DELETE' });
  },

  // ====== 快捷方法 ======

  async getHealth() { return this.get('/api/health'); },

  /** 輕量運維 SOP（與 ops check 同規則） */
  async getHealthSop() { return this.get('/api/health/sop', { silent: true }); },

  /** 下載 A 股日 K 到本地庫（異步任務） */
  async downloadStocks(codes) {
    return this.post('/api/stocks/download', codes ?? null);
  },

  /** 增量更新本地日 K */
  async updateStocks(codes, force = false) {
    return this.post(`/api/stocks/update?force=${force}`, codes ?? null);
  },
  async getStatus() { return this.get('/api/status'); },
  async getStocks(limit = 300, opts = {}) {
    const cap = Math.min(20000, Math.max(1, Number(limit) || 300));
    let url = `/api/stocks?limit=${cap}`;
    if (opts.cursor) url += `&cursor=${encodeURIComponent(opts.cursor)}`;
    else if (opts.offset != null) url += `&offset=${Number(opts.offset) || 0}`;
    return this.get(url);
  },

  /** 分頁拉取股票庫（市值 TOP，最多 maxCount 條） */
  async fetchStockUniverseAll(maxCount = 20000, pageSize = 1000) {
    const cap = Math.min(20000, Math.max(1, Number(maxCount) || 20000));
    const step = Math.min(2000, Math.max(100, Number(pageSize) || 1000));
    const all = [];
    let total = 0;
    let offset = 0;
    while (offset < cap) {
      const chunk = Math.min(step, cap - offset);
      const d = await this.getStockUniverse('all', chunk, offset, '');
      if (!d?.stocks?.length) break;
      total = d.total ?? total;
      all.push(...d.stocks);
      offset += d.stocks.length;
      if (d.stocks.length < chunk || (total > 0 && offset >= total)) break;
    }
    return { stocks: all, total: total || all.length };
  },

  async getKline(code, start, end, limit = 500) {
    let url = `/api/stocks/${code}/kline?limit=${limit}`;
    if (start) url += `&start=${start}`;
    if (end) url += `&end=${end}`;
    return this.get(url);
  },

  async compareStocks(codes, days = 250, opts = {}) {
    const body = { codes, days };
    if (opts.benchmark) body.benchmark = opts.benchmark;
    if (opts.index) body.index = opts.index;
    if (opts.withStats === false) body.with_stats = false;
    return this.post('/api/stocks/compare', body);
  },

  async runTradeAnalysis({ code, strategy, params }) {
    return this.post('/api/backtest/trade-analysis', { code, strategy, params });
  },

  async runMonteCarlo({ code, strategy, params, n_simulations = 1000, days = 252 }) {
    return this.post('/api/backtest/monte-carlo', {
      code, strategy, params, n_simulations, days,
    });
  },

  async runRollingMetrics({ code, strategy, params, window = 60 }) {
    return this.post('/api/backtest/rolling-metrics', { code, strategy, params, window });
  },

  async runBacktest(params) {
    let url = `/api/backtest?code=${params.code}&strategy=${params.strategy}`;
    if (params.stop_loss_pct) url += `&stop_loss_pct=${params.stop_loss_pct}`;
    if (params.take_profit_pct) url += `&take_profit_pct=${params.take_profit_pct}`;
    if (params.benchmark) url += `&benchmark=true`;
    return this.request(url, { method: 'POST' });
  },

  async runAdvancedBacktest(body) { return this.post('/api/backtest/advanced', body); },
  async runMultiBacktest(code) { return this.post(`/api/backtest/multi?code=${code}`); },

  async runOptimize(params) {
    const {
      code,
      strategy,
      method,
      objective,
      n_trials = 50,
      top_n,
      stop_loss_pct,
      take_profit_pct,
      trailing_stop_pct,
      circuit_breaker_dd,
      max_position_pct,
      slippage_pct,
      risk,
    } = params || {};
    let url = `/api/optimize?code=${encodeURIComponent(code)}&strategy=${encodeURIComponent(strategy)}&method=${encodeURIComponent(method)}&objective=${encodeURIComponent(objective)}&n_trials=${n_trials}`;
    if (top_n != null) url += `&top_n=${top_n}`;
    const q = (k, v) => {
      if (v != null && v !== '') url += `&${k}=${encodeURIComponent(v)}`;
    };
    q('stop_loss_pct', stop_loss_pct);
    q('take_profit_pct', take_profit_pct);
    q('trailing_stop_pct', trailing_stop_pct);
    q('circuit_breaker_dd', circuit_breaker_dd);
    q('max_position_pct', max_position_pct);
    q('slippage_pct', slippage_pct);
    const body = {};
    if (risk && typeof risk === 'object') body.risk = risk;
    return this.request(url, {
      method: 'POST',
      headers: Object.keys(body).length ? { 'Content-Type': 'application/json' } : {},
      body: Object.keys(body).length ? JSON.stringify(body) : undefined,
    });
  },

  async runAutoOptimize(body = {}) { return this.post('/api/auto-optimize', body); },
  async runPortfolio(body) { return this.post('/api/portfolio', body); },

  async runPresetPortfolio(name, cash) {
    let url = `/api/portfolio/preset/${name}`;
    if (cash) url += `?cash=${cash}`;
    return this.request(url, { method: 'POST' });
  },

  async getConfig() {
    const d = await this.get('/api/config');
    if (d && typeof Utils !== 'undefined' && Utils.applyStockLogoConfig) {
      Utils.applyStockLogoConfig(d.stock_logo_api_enabled);
    }
    return d;
  },
  async getPortfolioPresets() { return this.get('/api/portfolio/presets'); },

  async getAlerts(limit = 50, code = null, offset = 0) {
    let url = `/api/alerts?limit=${limit}&offset=${Number(offset) || 0}`;
    if (code) url += `&code=${code}`;
    return this.get(url);
  },

  async getAlertRules() { return this.get('/api/alerts/rules'); },
  async updateAlertRules(rules) { return this.put('/api/alerts/rules', rules); },
  async deleteAlertRule(code) { return this.delete(`/api/alerts/rules/${code}`); },
  async suggestAlertRule(code, opts = {}) {
    const q = new URLSearchParams({ code });
    if (opts.above_pct != null) q.set('above_pct', opts.above_pct);
    if (opts.below_pct != null) q.set('below_pct', opts.below_pct);
    if (opts.change_pct != null) q.set('change_pct', opts.change_pct);
    return this.get(`/api/alerts/rules/suggest?${q}`);
  },
  async autoAddAlertRules(body) {
    return this.post('/api/alerts/rules/auto', body || {});
  },

  async getWatchlist() {
    return this.get('/api/watchlist');
  },

  async addToWatchlist(code, name = '', opts = {}) {
    const q = new URLSearchParams({ code, name: name || '' });
    if (opts.auto_rule) q.set('auto_rule', 'true');
    if (opts.above_pct != null) q.set('above_pct', opts.above_pct);
    if (opts.below_pct != null) q.set('below_pct', opts.below_pct);
    if (opts.change_pct != null) q.set('change_pct', opts.change_pct);
    return this.post(`/api/watchlist/add?${q}`);
  },

  async removeFromWatchlist(code) {
    return this.delete(`/api/watchlist/${encodeURIComponent(code)}`);
  },

  async getBacktestHistory(code, strategy, limit = 50, offset = 0) {
    let url = `/api/backtest/history?limit=${limit}&offset=${offset}`;
    if (code) url += `&code=${encodeURIComponent(code)}`;
    if (strategy) url += `&strategy=${encodeURIComponent(strategy)}`;
    return this.get(url);
  },

  async getBacktestCompare(ids) {
    const list = (ids || []).map((x) => Number(x)).filter((n) => Number.isFinite(n) && n > 0);
    if (!list.length) return { results: [], total: 0 };
    return this.get(`/api/backtest/compare?ids=${list.join(',')}`);
  },

  async getBacktestResultDetail(resultId) {
    const id = Number(resultId);
    if (!Number.isFinite(id) || id <= 0) return null;
    return this.get(`/api/backtest/result/${id}`);
  },

  /** 解析任務/緩存回傳的 result（兼容 JSON 字串與嵌套） */
  normalizeBacktestResult(raw) {
    if (raw == null) return null;
    let r = raw;
    if (typeof r === 'string') {
      try {
        r = JSON.parse(r);
      } catch {
        return null;
      }
    }
    if (r && typeof r === 'object' && r.result != null && typeof r.result === 'object') {
      r = r.result;
    }
    if (r && typeof r === 'object' && r.data && r.total_return_pct == null && r.data.total_return_pct != null) {
      r = r.data;
    }
    return r && typeof r === 'object' ? r : null;
  },

  /** 帶 Token 下載檔案（匯出 CSV/JSON） */
  async downloadAuthenticated(path, filename) {
    const headers = {};
    if (this._token) headers.Authorization = `Bearer ${this._token}`;
    const resp = await fetch(API_BASE + path, { headers });
    if (!resp.ok) {
      let errBody = { detail: resp.statusText };
      try {
        errBody = await resp.json();
      } catch (_) { /* ignore */ }
      if (resp.status === 403 || resp.status === 429) {
        this.handleBillingGate(errBody, resp.status, {});
      }
      const d = errBody?.detail;
      const msg = typeof d === 'object' && d?.message
        ? d.message
        : (typeof d === 'string' ? d : (errBody.error || resp.statusText));
      throw new Error(msg || `下載失敗 (${resp.status})`);
    }
    const blob = await resp.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename || 'export.dat';
    a.click();
    URL.revokeObjectURL(a.href);
  },

  downloadBlob(content, filename, mime = 'text/plain;charset=utf-8') {
    const blob = content instanceof Blob ? content : new Blob([content], { type: mime });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },

  async runWalkForward(params) {
    let url = `/api/walkforward?code=${params.code}&strategy=${params.strategy}&train_days=${params.train}&test_days=${params.test}&n_trials=${params.trials}`;
    return this.request(url, { method: 'POST' });
  },

  async runHeatmap(params) {
    const px = (params.paramX || '').trim();
    const py = (params.paramY || '').trim();
    if (!px || !py) {
      if (typeof Utils !== 'undefined') Utils.toast('請選擇參數 X 和 Y', 3000, 'warning');
      return null;
    }
    const url = `/api/heatmap?code=${encodeURIComponent(params.code)}&strategy=${encodeURIComponent(params.strategy)}`
      + `&param_x=${encodeURIComponent(px)}&param_y=${encodeURIComponent(py)}&grid_size=${params.grid || 8}`;
    return this.request(url, { method: 'POST' });
  },

  async getHeatmapParams(strategy) { return this.get(`/api/heatmap/params/${strategy}`); },

  async screenStocks(filters) { return this.post('/api/screener/screen', { filters }); },
  async getStockList(market = 'all') { return this.get(`/api/screener/stocks?market=${market}`); },
  async getNotifyChannels() { return this.get('/api/notify/channels'); },
  async testNotify() { return this.post('/api/notify/test'); },
  async getSchedulerJobs() { return this.get('/api/scheduler/jobs'); },
  async getSchedulerCatalog() { return this.get('/api/scheduler/catalog'); },
  async setupScheduler() { return this.post('/api/scheduler/setup'); },
  async runSchedulerJob(jobId) { return this.post(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/run`); },
  async enableSchedulerJob(jobId) { return this.post(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/enable`); },
  async disableSchedulerJob(jobId) { return this.post(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/disable`); },

  // 任務管理
  async getTasks(taskType, status, limit, opts = {}) {
    let url = '/api/tasks?limit=' + (limit || 50);
    if (taskType) url += '&task_type=' + taskType;
    if (status) url += '&status=' + status;
    return this.get(url, opts);
  },
  async getTaskTypes(opts = {}) {
    return this.get('/api/tasks/types', opts);
  },
  async getTaskQueue(opts = {}) { return this.get('/api/tasks/queue', opts); },

  async pollTask(taskId, options = {}) {
    const interval = options.interval || 1500;
    const timeout = options.timeout || 600000;
    const onProgress = options.onProgress;
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const d = await this.getTask(taskId, { silent: true, noCache: true });
      if (d?._rateLimited) {
        await new Promise(r => setTimeout(r, Math.max(interval, 2000)));
        continue;
      }
      const task = d?.task;
      if (!task) return null;
      if (onProgress) onProgress(task);
      if (task.status === 'completed') return task;
      if (task.status === 'failed' || task.status === 'cancelled') {
        throw new Error(task.error || ('任務' + task.status));
      }
      await new Promise(r => setTimeout(r, interval));
    }
    throw new Error('任務等待超時');
  },

  /** 從 resolveTaskResponse 的返回值取出 result（兼容 list / dict） */
  extractResult(resolved) {
    if (!resolved) return null;
    const r = resolved.result ?? resolved.results ?? resolved.task?.result;
    return r ?? null;
  },

  /** 若為 async 響應則輪詢至完成，返回含 result 的 task 或原響應 */
  async resolveTaskResponse(d, options = {}) {
    if (!d?.success) return d;
    if (d.from_cache && (d.result || d.results)) {
      if (typeof Utils !== 'undefined') {
        Utils.toast('⚡ 使用緩存結果', 2000, 'info');
      }
      return d;
    }
    const taskId = d.task_id;
    if (!taskId) return d;
    const needsPoll = d.async || d.is_duplicate || (!d.result && !d.results && taskId);
    if (!needsPoll) return d;
    const task = await this.pollTask(taskId, options);
    const result = task?.result;
    return { ...d, task, result, results: result };
  },

  async getTask(taskId, opts = {}) { return this.get('/api/tasks/' + taskId, opts); },
  async getCacheStats() { return this.get('/api/cache/stats'); },
  async clearCache(code) {
    let url = '/api/cache/clear';
    if (code) url += '?code=' + encodeURIComponent(code);
    return this.post(url);
  },
  async cancelTask(taskId) { return this.post('/api/tasks/' + taskId + '/cancel'); },
  async cleanupTasks() { return this.post('/api/tasks/cleanup'); },
  async enableScheduler() { return this.post('/api/scheduler/enable'); },
  async disableScheduler() { return this.post('/api/scheduler/disable'); },
  async getCurrentSignals() { return this.get('/api/signals/current'); },

  async getSignalHistory(code, strategy, days = 30) {
    let url = `/api/signals/history?days=${days}`;
    if (code) url += `&code=${encodeURIComponent(code)}`;
    if (strategy) url += `&strategy=${encodeURIComponent(strategy)}`;
    return this.get(url);
  },

  async getSignalStrength(code) { return this.get(`/api/signals/strength?code=${encodeURIComponent(code)}`); },
  async getStockUniverseStats() { return this.get('/api/stock-universe/stats'); },
  async getStockUniverse(market = 'all', limit = 50, offset = 0, keyword = '') {
    let q = `market=${encodeURIComponent(market)}&limit=${limit}&offset=${offset}`;
    if (keyword) q += `&keyword=${encodeURIComponent(keyword)}`;
    return this.get(`/api/stock-universe?${q}`);
  },
  async syncStockUniverse(maxCount = null) {
    const q = maxCount ? `?max_count=${maxCount}` : '';
    return this.post(`/api/stock-universe/sync${q}`);
  },
  async enrichStockUniverseIntros(limit = null) {
    const q = limit != null ? `?limit=${limit}` : '';
    return this.post(`/api/stock-universe/enrich-intros${q}`);
  },
  async getSectors(type = 'industry', topN = 30) { return this.get(`/api/data/sectors?sector_type=${type}&top_n=${topN}`); },
  async getSectorStocks(name, type = 'industry') { return this.get(`/api/data/sector/${encodeURIComponent(name)}/stocks?sector_type=${type}`); },
  async getSectorRotation(days = 10) { return this.get(`/api/data/sectors/rotation?days=${days}`); },
  async getSectorTrend(name, days = 20) { return this.get(`/api/data/sector/${encodeURIComponent(name)}/trend?days=${days}`); },
  async getSectorHeatmap(type = 'industry') { return this.get(`/api/data/sectors/heatmap?sector_type=${type}`); },
  async saveSectorSnapshot(type = 'industry') { return this.post(`/api/data/sectors/snapshot?sector_type=${type}`); },
  async getSectorCapitalFlow(name) { return this.get(`/api/data/sector/${encodeURIComponent(name)}/capital-flow`); },
  async getSectorsCapitalFlowRank(topN = 20) { return this.get(`/api/data/sectors/capital-flow?top_n=${topN}`); },
  async getSectorsChangeFlow(type = 'industry', topN = 40) {
    return this.get(`/api/data/sectors/change-flow?sector_type=${type}&top_n=${topN}`);
  },
  async getDashboardMarketCharts(days = 20) { return this.get(`/api/dashboard/market-charts?days=${days}`); },
  async getCapitalFlow(code, days = 30) { return this.get(`/api/data/capital-flow?code=${code}&days=${days}`); },
  async getMarketFlow() { return this.get('/api/data/market-flow'); },
  async getNorthFlow(days = 30) { return this.get(`/api/data/north-flow?days=${days}`); },

  async getDragonTiger(date = null) {
    let url = '/api/data/dragon-tiger';
    if (date) url += `?date=${date}`;
    return this.get(url);
  },

  async getDragonTigerHistory(code, days = 30) { return this.get(`/api/data/dragon-tiger/${code}/history?days=${days}`); },
  async getFundamentals(code) { return this.get(`/api/data/fundamentals?code=${code}`); },
  async screenFundamentals(filters) { return this.post('/api/data/fundamentals/screen', { filters }); },

  async getRealtime(codes) {
    let url = '/api/realtime';
    if (codes) url += `?codes=${codes}`;
    return this.get(url);
  },

  async getBenchmark(start, end) {
    let url = '/api/benchmark';
    const params = [];
    if (start) params.push(`start=${start}`);
    if (end) params.push(`end=${end}`);
    if (params.length) url += '?' + params.join('&');
    return this.get(url);
  },

  async getStrategies() { return this.get('/api/strategies/list'); },

  async getStrategyLikes(opts = {}) {
    return this.get('/api/strategies/likes', opts);
  },

  async toggleStrategyLike(key) {
    const data = await this.post('/api/strategies/likes/toggle', { key });
    if (data?.success) this.clearGetCache('/api/strategies/likes');
    return data;
  },

  async getLeaderboard(sortBy = 'sharpe', limit = 50) {
    return this.get(`/api/strategies/leaderboard?sort_by=${sortBy}&limit=${limit}`);
  },

  async getIndicesCharts(days = 90, scope = 'dashboard') {
    return this.get(`/api/indices/charts?days=${days}&scope=${encodeURIComponent(scope)}`);
  },

  async getAssetsCatalog() {
    return this.get('/api/assets/catalog');
  },

  async getPortfolioSummary(currency) {
    let url = '/api/portfolio/summary';
    if (currency) url += `?currency=${encodeURIComponent(currency)}`;
    return this.get(url, { silent: true });
  },

  async getAssetDetail(symbol, days = 180) {
    return this.get(`/api/assets/detail?symbol=${encodeURIComponent(symbol)}&days=${days}`);
  },

  async getMinutesData(code, period = '5m') { return this.get(`/api/data/minutes?code=${code}&period=${period}`); },
  async runRiskParity(body) { return this.post('/api/portfolio/risk-parity', body); },
  async runMVO(body) { return this.post('/api/portfolio/mvo', body); },
  async runVolTarget(body) { return this.post('/api/portfolio/vol-target', body); },
  async runMaxDiversification(body) { return this.post('/api/portfolio/max-diversification', body); },
  async runAntiCorrelation(body) { return this.post('/api/portfolio/anti-correlation', body); },
  async runRegimeSwitch(body) { return this.post('/api/portfolio/regime-switch', body); },
  async runDynamicPortfolio(body) { return this.post('/api/portfolio/dynamic', body); },
  async runKelly(body) { return this.post('/api/portfolio/kelly', body); },
  async runDegradation(body) { return this.post('/api/portfolio/degradation', body); },
  async runArbitrate(body) { return this.post('/api/portfolio/arbitrate', body); },
  async runFrontier(body) { return this.post('/api/portfolio/frontier', body); },

  // 任務管理增強
  async deleteTask(taskId) { return this.delete(`/api/tasks/${taskId}`); },
  async getTaskParams(taskId) {
    return this.get(`/api/tasks/${encodeURIComponent(taskId)}/params`, { silent: true });
  },
  async getTaskFull(taskId) {
    return this.get(`/api/tasks/${encodeURIComponent(taskId)}/full`, { silent: true });
  },
  async retryTask(taskId) { return this.post(`/api/tasks/${taskId}/retry`); },
  async batchCancelTasks(taskIds) { return this.post('/api/tasks/batch/cancel', { task_ids: taskIds }); },
  async batchDeleteTasks(taskIds) { return this.post('/api/tasks/batch/delete', { task_ids: taskIds }); },
  async cancelAllPendingTasks() { return this.post('/api/tasks/cancel-pending'); },
  async clearCompletedTasks(includeFailed = true, includeCancelled = true) {
    const q = `include_failed=${includeFailed}&include_cancelled=${includeCancelled}`;
    return this.post(`/api/tasks/clear-completed?${q}`);
  },
  async getTaskLogs(taskId, tail = 200) {
    return this.get(`/api/tasks/${encodeURIComponent(taskId)}/logs?tail=${tail}`, { silent: true });
  },
  async createTaskPipeline(body) { return this.post('/api/tasks/pipeline', body); },
  async getTaskStats() { return this.get('/api/tasks/stats'); },

  getLlmConfig() {
    try {
      const raw = SecureStore.getItem('stockq:llm_config_v1');
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  },

  setLlmConfig(partial = {}) {
    const cur = this.getLlmConfig();
    const next = { ...cur, ...partial };
    if (!next.api_key) delete next.api_key;
    SecureStore.setItem('stockq:llm_config_v1', JSON.stringify(next));
    return next;
  },

  async getLlmStatus() { return this.get('/api/llm/status'); },

  async getLlmSettings() {
    return this.get('/api/llm/settings');
  },

  async saveLlmSettings(llm) {
    return this.put('/api/llm/settings', { llm });
  },

  async llmChat(message, history = [], llmConfig = null) {
    const cfg = llmConfig || this.getLlmConfig();
    const body = { message, history };
    if (cfg && (cfg.api_key || cfg.api_base || cfg.model)) {
      body.llm_config = cfg;
    }
    return this.post('/api/llm/chat', body);
  },

  async llmChatStream(message, history = [], onEvent, llmConfig = null) {
    const cfg = llmConfig || this.getLlmConfig();
    const headers = { 'Content-Type': 'application/json' };
    if (this._token) headers.Authorization = `Bearer ${this._token}`;

    const body = { message, history };
    if (cfg && (cfg.api_key || cfg.api_base || cfg.model)) {
      body.llm_config = cfg;
    }

    const resp = await fetch(`${API_BASE}/api/llm/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const j = await resp.json();
        detail = j.detail || j.error || detail;
      } catch (_) { /* ignore */ }
      throw new Error(detail || `流式請求失敗 (${resp.status})`);
    }

    const reader = resp.body?.getReader();
    if (!reader) throw new Error('瀏覽器不支援流式讀取');

    const decoder = new TextDecoder();
    let buffer = '';

    const parseSseBlock = (block) => {
      const lines = String(block || '').split('\n');
      for (const raw of lines) {
        const line = raw.trim();
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === '[DONE]') continue;
        try {
          const ev = JSON.parse(payload);
          if (onEvent) onEvent(ev);
        } catch (_) { /* ignore partial */ }
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() || '';
      chunks.forEach(parseSseBlock);
    }
    if (buffer.trim()) parseSseBlock(buffer);
  },

  /** 公開：方案列表（定價頁） */
  async getBillingPlans() {
    return this.get('/api/billing/plans', { silent: true, timeout: 15000 });
  },

  /** 當前方案、配額與今日用量（需登錄） */
  async getBillingMe() {
    return this.get('/api/billing/me');
  },

  /** 開發/演示：試用升級 Pro；生產環境預留 Stripe */
  async billingCheckout(planId = 'pro', trialDays = 14) {
    return this.post('/api/billing/checkout', { plan_id: planId, trial_days: trialDays });
  },
};

window.Api = Api;
