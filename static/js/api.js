/**
 * api.js — API 客戶端封裝（含 Token 管理）
 */

const API_BASE = '';

const Api = {
  _token: null,
  _loggingIn: false,

  /**
   * 初始化：從 localStorage 載入 token
   */
  init() {
    this._token = localStorage.getItem('sq_token');
    this._updateAuthUI();
  },

  /**
   * 保存 token
   */
  setToken(token) {
    this._token = token;
    if (token) {
      localStorage.setItem('sq_token', token);
    } else {
      localStorage.removeItem('sq_token');
    }
    this._updateAuthUI();
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
  _updateAuthUI() {
    const el = document.getElementById('authStatus');
    if (!el) return;
    if (this._token) {
      el.innerHTML = '<span style="color:var(--green)">●</span> 已登錄';
      el.title = '點擊登出';
      el.style.cursor = 'pointer';
    } else {
      el.innerHTML = '<span style="color:var(--red)">●</span> 未登錄';
      el.title = '點擊登錄';
      el.style.cursor = 'pointer';
    }
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
        <button class="btn" onclick="Api.doLogin(${isRegister})">${btnText}</button>
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
    const username = document.getElementById('loginUsername')?.value?.trim();
    const password = document.getElementById('loginPassword')?.value;
    const errorEl = document.getElementById('loginError');

    if (!username || !password) {
      if (errorEl) { errorEl.textContent = '請填寫用戶名和密碼'; errorEl.style.display = 'block'; }
      return;
    }

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

      // 重新連接 WebSocket（攜帶新 token）
      if (typeof App !== 'undefined') {
        if (App._ws) { App._ws.close(); }
        App._connectWS();
        App._initQuickStats();
      }

      // 刷新當前頁面數據
      if (typeof Dashboard !== 'undefined') Dashboard.load();
    } catch (e) {
      if (errorEl) { errorEl.textContent = '網絡錯誤: ' + e.message; errorEl.style.display = 'block'; }
    }
  },

  /**
   * 登出
   */
  logout() {
    this.setToken(null);
    Utils.toast('已登出', 3000, 'success');
    // 斷開 WebSocket（無 token 將被拒絕）
    if (typeof App !== 'undefined') {
      if (App._ws) { App._ws.close(); }
      App._connectWS();
    }
    if (typeof Dashboard !== 'undefined') Dashboard.load();
  },

  /**
   * 通用 GET/POST 請求
   */
  async request(path, options = null) {
    try {
      // 自動附加 Authorization header
      const headers = {};
      if (this._token) {
        headers['Authorization'] = 'Bearer ' + this._token;
      }
      if (options?.headers) {
        Object.assign(headers, options.headers);
      }

      const resp = await fetch(API_BASE + path, { ...options, headers });

      // 401 → 自動彈出登錄
      if (resp.status === 401) {
        this.setToken(null);
        this.showLoginModal();
        return null;
      }

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      return await resp.json();
    } catch (e) {
      Utils.toast('請求失敗: ' + e.message, 3000, 'error');
      return null;
    }
  },

  /**
   * GET 請求
   */
  async get(path) {
    return this.request(path);
  },

  /**
   * POST JSON
   */
  async post(path, body = {}) {
    return this.request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
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
  async getStatus() { return this.get('/api/status'); },
  async getStocks() { return this.get('/api/stocks'); },

  async getKline(code, start, end, limit = 500) {
    let url = `/api/stocks/${code}/kline?limit=${limit}`;
    if (start) url += `&start=${start}`;
    if (end) url += `&end=${end}`;
    return this.get(url);
  },

  async compareStocks(codes, days = 250) {
    return this.post('/api/stocks/compare', { codes, days });
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
    let url = `/api/optimize?code=${params.code}&strategy=${params.strategy}&method=${params.method}&objective=${params.objective}&n_trials=${params.n_trials || 50}`;
    return this.request(url, { method: 'POST' });
  },

  async runAutoOptimize(body = {}) { return this.post('/api/auto-optimize', body); },
  async runPortfolio(body) { return this.post('/api/portfolio', body); },

  async runPresetPortfolio(name, cash) {
    let url = `/api/portfolio/preset/${name}`;
    if (cash) url += `?cash=${cash}`;
    return this.request(url, { method: 'POST' });
  },

  async getConfig() { return this.get('/api/config'); },
  async getPortfolioPresets() { return this.get('/api/portfolio/presets'); },

  async getAlerts(limit = 50, code = null) {
    let url = `/api/alerts?limit=${limit}`;
    if (code) url += `&code=${code}`;
    return this.get(url);
  },

  async getAlertRules() { return this.get('/api/alerts/rules'); },
  async updateAlertRules(rules) { return this.put('/api/alerts/rules', rules); },
  async deleteAlertRule(code) { return this.delete(`/api/alerts/rules/${code}`); },

  async addToWatchlist(code, name = '') {
    return this.post(`/api/watchlist/add?code=${code}&name=${encodeURIComponent(name)}`);
  },

  async getBacktestHistory(code, strategy, limit = 50) {
    let url = `/api/backtest/history?limit=${limit}`;
    if (code) url += `&code=${encodeURIComponent(code)}`;
    if (strategy) url += `&strategy=${encodeURIComponent(strategy)}`;
    return this.get(url);
  },

  async runWalkForward(params) {
    let url = `/api/walkforward?code=${params.code}&strategy=${params.strategy}&train_days=${params.train}&test_days=${params.test}&n_trials=${params.trials}`;
    return this.request(url, { method: 'POST' });
  },

  async runHeatmap(params) {
    let url = `/api/heatmap?code=${params.code}&strategy=${params.strategy}&param_x=${params.paramX}&param_y=${params.paramY}&grid_size=${params.grid}`;
    return this.request(url, { method: 'POST' });
  },

  async getHeatmapParams(strategy) { return this.get(`/api/heatmap/params/${strategy}`); },

  async screenStocks(filters) { return this.post('/api/screener/screen', { filters }); },
  async getStockList(market = 'all') { return this.get(`/api/screener/stocks?market=${market}`); },
  async getNotifyChannels() { return this.get('/api/notify/channels'); },
  async testNotify() { return this.post('/api/notify/test'); },
  async getSchedulerJobs() { return this.get('/api/scheduler/jobs'); },

  // 任務管理
  async getTasks(taskType, status, limit) {
    let url = '/api/tasks?limit=' + (limit || 50);
    if (taskType) url += '&task_type=' + taskType;
    if (status) url += '&status=' + status;
    return this.get(url);
  },
  async getTask(taskId) { return this.get('/api/tasks/' + taskId); },
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
  async getSectors(type = 'industry', topN = 30) { return this.get(`/api/data/sectors?sector_type=${type}&top_n=${topN}`); },
  async getSectorStocks(name, type = 'industry') { return this.get(`/api/data/sector/${encodeURIComponent(name)}/stocks?sector_type=${type}`); },
  async getSectorRotation(days = 10) { return this.get(`/api/data/sectors/rotation?days=${days}`); },
  async getSectorTrend(name, days = 20) { return this.get(`/api/data/sector/${encodeURIComponent(name)}/trend?days=${days}`); },
  async getSectorHeatmap(type = 'industry') { return this.get(`/api/data/sectors/heatmap?sector_type=${type}`); },
  async saveSectorSnapshot(type = 'industry') { return this.post(`/api/data/sectors/snapshot?sector_type=${type}`); },
  async getSectorCapitalFlow(name) { return this.get(`/api/data/sector/${encodeURIComponent(name)}/capital-flow`); },
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
  async getStrategiesList() { return this.getStrategies(); },

  async getLeaderboard(sortBy = 'sharpe', limit = 50) {
    return this.get(`/api/strategies/leaderboard?sort_by=${sortBy}&limit=${limit}`);
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
  async getTaskFull(taskId) { return this.get(`/api/tasks/${taskId}/full`); },
};

window.Api = Api;
