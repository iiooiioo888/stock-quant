/**
 * app.js — 主應用邏輯、Tab 路由、初始化
 */

const App = {
  _ws: null,
  _wsRetry: 0,
  _wsMaxRetry: 15,
  _currentTab: 'dashboard',

  /**
   * 初始化應用
   */
  init() {
    // 初始化 API（載入 token、設置 auth UI）
    Api.init();

    this.initTheme();
    this.initTabs();
    this.initWebSocket();
    this.initHeatmapStrategy();
    this._initGreeting();
    this._initMarketStatus();
    this._initTips();
    this._initStrategies();
    this._initSidebarToggle();
    this._initGlobalSearch();
    this._initQuickStats();
    this._initTaskPanel();

    // 載入默認 Tab
    this.loadTab('dashboard');

    // 初始化子模塊
    if (typeof Signals !== 'undefined') Signals.init();
    if (typeof Data !== 'undefined') Data.init();
    if (typeof Portfolio !== 'undefined') Portfolio.init();
    if (typeof Analysis !== 'undefined') Analysis.init();
  },

  quickAction(tab) {
    this.loadTab(tab);
  },

  dismissTip() {
    const el = document.getElementById('tipCard');
    if (el) el.style.display = 'none';
    localStorage.setItem('tipDismissed', 'true');
  },

  _initGreeting() {
    const hour = new Date().getHours();
    const el = document.getElementById('greetingText');
    const sub = document.getElementById('greetingSubtext');
    if (!el) return;

    if (hour < 9) {
      el.textContent = '早安 ☀️';
      sub.textContent = '新的一天開始了，準備好分析市場了嗎？';
    } else if (hour < 12) {
      el.textContent = '上午好 📈';
      sub.textContent = '上午是覆盤和策略調整的好時機！';
    } else if (hour < 14) {
      el.textContent = '午安 🍵';
      sub.textContent = '午後繼續加油，市場機會稍縱即逝。';
    } else if (hour < 17) {
      el.textContent = '下午好 🌤️';
      sub.textContent = '接近收盤了，記得檢視今日表現。';
    } else {
      el.textContent = '晚上好 🌙';
      sub.textContent = '晚上適合覆盤和優化策略。';
    }
  },

  _initMarketStatus() {
    const now = new Date();
    const day = now.getDay();
    const hm = now.getHours() * 100 + now.getMinutes();
    const dot = document.getElementById('marketDot');
    const text = document.getElementById('marketStatusText');
    if (!dot || !text) return;

    const isWeekday = day >= 1 && day <= 5;
    const isTradingHours = (hm >= 915 && hm <= 1130) || (hm >= 1300 && hm <= 1500);
    const isOpen = isWeekday && isTradingHours;

    dot.className = 'market-dot ' + (isOpen ? 'open' : 'closed');
    text.textContent = isOpen ? '交易中' : (isWeekday ? '已休市' : '週末休市');
  },

  _initTips() {
    if (localStorage.getItem('tipDismissed') === 'true') {
      const el = document.getElementById('tipCard');
      if (el) el.style.display = 'none';
      return;
    }

    const tips = [
      '夏普比率 (Sharpe Ratio) 表示每承受一單位風險能獲得多少超額收益，大於 1 算不錯，大於 2 算優秀。',
      '最大回撤 (Max Drawdown) 是從最高點到最低點的跌幅，越小越好，代表策略的穩定性。',
      'Sortino 比率只考慮下行風險，比夏普比率更關注「虧損」而非「波動」。',
      'Calmar 比率 = 年化收益 / 最大回撤，數值越大表示風險調整後的收益越好。',
      'Win Rate (勝率) 不是越高越好，關鍵是盈虧比 — 即使勝率只有 40%，盈虧比夠高也能盈利。',
      'Walk-Forward 分析能幫你檢測策略是否過擬合 — 如果樣本外表現遠差於樣本內，就要小心了。',
      '蒙特卡羅模擬通過隨機重組交易順序，幫你評估策略在不同市場環境下的表現範圍。',
    ];

    const idx = Math.floor(Math.random() * tips.length);
    const el = document.getElementById('tipText');
    if (el) el.textContent = tips[idx];
  },

  async _initStrategies() {
    try {
      const d = await Api.getStrategiesList();
      if (!d) return;

      const all = [...(d.builtin || []), ...(d.user || [])];
      if (all.length === 0) return;

      const options = all.map(s =>
        `<option value="${s.name}">${s.display_name || s.name}</option>`
      ).join('');

      // 填充一般策略下拉框
      ['btStrategy', 'hmStrategy', 'wfStrategy', 'anStrategy'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          const current = el.value;
          el.innerHTML = options;
          if (current && el.querySelector(`option[value="${current}"]`)) {
            el.value = current;
          }
        }
      });

      // 優化策略下拉框（保留「全部」選項）
      const optEl = document.getElementById('optStrategy');
      if (optEl) {
        const current = optEl.value;
        optEl.innerHTML = '<option value="all">全部</option>' + options;
        if (current && optEl.querySelector(`option[value="${current}"]`)) {
          optEl.value = current;
        }
      }
    } catch (e) {
      console.warn('載入策略列表失敗:', e);
    }
  },

  // ============================================================
  // Sidebar Toggle
  // ============================================================

  _initSidebarToggle() {
    const btn = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    if (!btn || !sidebar) return;

    // Restore collapsed state
    if (localStorage.getItem('sidebarCollapsed') === 'true') {
      sidebar.classList.add('collapsed');
    }

    btn.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    });
  },

  // ============================================================
  // Global Search
  // ============================================================

  _initGlobalSearch() {
    const input = document.getElementById('globalSearch');
    const results = document.getElementById('searchResults');
    if (!input || !results) return;

    // Keyboard shortcut: "/" to focus search
    document.addEventListener('keydown', e => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
        e.preventDefault();
        input.focus();
      }
      if (e.key === 'Escape') {
        input.blur();
        results.classList.remove('show');
      }
    });

    // Search data
    const searchData = [
      { icon: '📊', code: '000001', name: '平安銀行', type: 'A股', action: () => { this.loadTab('backtest'); document.getElementById('btCode').value = '000001'; } },
      { icon: '📊', code: '600519', name: '貴州茅台', type: 'A股', action: () => { this.loadTab('backtest'); document.getElementById('btCode').value = '600519'; } },
      { icon: '📊', code: '000858', name: '五糧液', type: 'A股', action: () => { this.loadTab('backtest'); document.getElementById('btCode').value = '000858'; } },
      { icon: '📊', code: '601318', name: '中國平安', type: 'A股', action: () => { this.loadTab('backtest'); document.getElementById('btCode').value = '601318'; } },
      { icon: '📊', code: '000333', name: '美的集團', type: 'A股', action: () => { this.loadTab('backtest'); document.getElementById('btCode').value = '000333'; } },
      { icon: '🧪', code: '', name: '策略回測', type: '功能', action: () => this.loadTab('backtest') },
      { icon: '⚡', code: '', name: '參數優化', type: '功能', action: () => this.loadTab('optimize') },
      { icon: '🔄', code: '', name: 'Walk-Forward', type: '功能', action: () => this.loadTab('walkforward') },
      { icon: '🌡️', code: '', name: '熱力圖', type: '功能', action: () => this.loadTab('heatmap') },
      { icon: '💼', code: '', name: '組合回測', type: '功能', action: () => this.loadTab('portfolio') },
      { icon: '⚖️', code: '', name: '多股對比', type: '功能', action: () => this.loadTab('compare') },
      { icon: '🔍', code: '', name: '股票篩選', type: '功能', action: () => this.loadTab('screener') },
      { icon: '📡', code: '', name: '實時信號', type: '功能', action: () => this.loadTab('signals') },
      { icon: '🗄️', code: '', name: '數據中心', type: '功能', action: () => this.loadTab('data') },
      { icon: '🔬', code: '', name: '深度分析', type: '功能', action: () => this.loadTab('analysis') },
      { icon: '📋', code: '', name: '策略報告', type: '功能', action: () => this.loadTab('reports') },
      { icon: '🔔', code: '', name: '預警通知', type: '功能', action: () => this.loadTab('alerts') },
      { icon: '🌐', code: '', name: '多市場', type: '功能', action: () => this.loadTab('markets') },
      { icon: '📋', code: '', name: '任務面板', type: '功能', action: () => this.loadTab('tasks') },
      { icon: '📥', code: '', name: '下載全市場數據', type: '操作', action: () => this.downloadAllFromDashboard() },
    ];

    let debounceTimer;
    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        const q = input.value.trim().toLowerCase();
        if (!q) { results.classList.remove('show'); return; }

        const matched = searchData.filter(item =>
          item.code.includes(q) || item.name.toLowerCase().includes(q) || item.name.includes(q)
        ).slice(0, 8);

        if (matched.length === 0) {
          results.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-dim);font-size:12px">找不到相關結果</div>';
        } else {
          results.innerHTML = matched.map((item, i) =>
            `<div class="search-result-item" data-idx="${i}">
              <span class="sr-icon">${item.icon}</span>
              <span class="sr-code">${item.code}</span>
              <span class="sr-name">${item.name}</span>
              <span class="sr-type">${item.type}</span>
            </div>`
          ).join('');

          results.querySelectorAll('.search-result-item').forEach((el, i) => {
            el.addEventListener('click', () => {
              matched[i].action();
              input.value = '';
              results.classList.remove('show');
            });
          });
        }
        results.classList.add('show');
      }, 150);
    });

    input.addEventListener('focus', () => {
      if (input.value.trim()) results.classList.add('show');
    });

    document.addEventListener('click', e => {
      if (!e.target.closest('.global-search')) results.classList.remove('show');
    });
  },

  // ============================================================
  // Quick Stats (header)
  // ============================================================

  async _initQuickStats() {
    try {
      const d = await Api.getHealth();
      if (!d) return;
      const stocksEl = document.getElementById('hqStocks');
      const alertsEl = document.getElementById('hqAlerts');
      if (stocksEl) stocksEl.textContent = d.total_stocks || 0;
      if (alertsEl) alertsEl.textContent = d.total_alerts || 0;
      // 動態設置版本號
      if (d.version) {
        const verEl = document.getElementById('sidebarVersion');
        if (verEl) verEl.textContent = 'v' + d.version;
      }
    } catch (e) { /* ignore */ }
  },

  // ============================================================
  // Theme Toggle
  // ============================================================

  initTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    if (saved === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    }

    const btn = document.getElementById('themeToggle');
    if (btn) {
      btn.addEventListener('click', () => this.toggleTheme());
      this._updateThemeIcon();
    }
  },

  toggleTheme() {
    const isDark = !document.documentElement.hasAttribute('data-theme') ||
                   document.documentElement.getAttribute('data-theme') === 'dark';

    if (isDark) {
      document.documentElement.setAttribute('data-theme', 'light');
      localStorage.setItem('theme', 'light');
    } else {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('theme', 'dark');
    }

    this._updateThemeIcon();

    // 刷新圖表配色
    if (typeof Charts !== 'undefined') {
      Charts.refreshAll();
    }
  },

  _updateThemeIcon() {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;
    const isDark = !document.documentElement.hasAttribute('data-theme') ||
                   document.documentElement.getAttribute('data-theme') === 'dark';
    btn.textContent = isDark ? '☀️' : '🌙';
    btn.title = isDark ? '切換亮色主題' : '切換暗色主題';
  },

  // ============================================================
  // Tab Routing
  // ============================================================

  initTabs() {
    document.getElementById('sidebar').addEventListener('click', e => {
      const btn = e.target.closest('button[data-tab]');
      if (!btn) return;
      const tab = btn.dataset.tab;
      this.loadTab(tab);
    });
  },

  loadTab(tab) {
    // 隱藏所有 tab 內容
    document.querySelectorAll('[id^="tab-"]').forEach(el => el.classList.add('h'));

    // 顯示目標 tab
    const target = document.getElementById('tab-' + tab);
    if (target) target.classList.remove('h');

    // 更新導航高亮
    document.querySelectorAll('.sidebar button').forEach(b => b.classList.remove('a'));
    const navBtn = document.querySelector(`.sidebar button[data-tab="${tab}"]`);
    if (navBtn) navBtn.classList.add('a');

    this._currentTab = tab;

    // 切換 tab 時停止非活躍模塊的輪詢
    if (tab !== 'dashboard' && typeof Dashboard !== 'undefined') {
      Dashboard.stopPolling();
    }
    if (tab !== 'tasks' && typeof Tasks !== 'undefined') {
      Tasks.unload();
    }

    // Tab 切換時載入數據
    switch (tab) {
      case 'dashboard':
        if (typeof Dashboard !== 'undefined') Dashboard.load();
        break;
      case 'portfolio':
        if (typeof Portfolio !== 'undefined') Portfolio.loadPresets();
        break;
      case 'alerts':
        this.loadAlerts();
        this.loadNotifyChannels();
        break;
      case 'markets':
        this.loadMarkets();
        break;
      case 'signals':
        if (typeof Signals !== 'undefined') Signals.load();
        break;
      case 'data':
        if (typeof Data !== 'undefined') Data.load();
        break;
      case 'analysis':
        // Analysis tab loads on demand via buttons
        break;
      case 'tasks':
        if (typeof Tasks !== 'undefined') Tasks.load();
        break;
    }
  },

  // ============================================================
  // WebSocket
  // ============================================================

  initWebSocket() {
    this._connectWS();

    // 心跳
    setInterval(() => {
      if (this._ws && this._ws.readyState === 1) {
        this._ws.send('ping');
      }
    }, 25000);
  },

  _connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    // 攜帶 token 進行 WebSocket 認證
    const token = localStorage.getItem('sq_token');
    const wsUrl = token
      ? `${proto}//${location.host}/ws?token=${token}`
      : `${proto}//${location.host}/ws`;
    this._ws = new WebSocket(wsUrl);

    this._ws.onopen = () => {
      document.getElementById('wsDot').className = 'ws-dot on';
      const sidebarDot = document.getElementById('wsDotSidebar');
      if (sidebarDot) sidebarDot.className = 'ws-dot on';
      const sidebarText = document.getElementById('sidebarStatusText');
      if (sidebarText) sidebarText.textContent = '已連接';
      this._wsRetry = 0;
    };

    this._ws.onclose = () => {
      document.getElementById('wsDot').className = 'ws-dot off';
      const sidebarDot = document.getElementById('wsDotSidebar');
      if (sidebarDot) sidebarDot.className = 'ws-dot off';
      const sidebarText = document.getElementById('sidebarStatusText');

      this._wsRetry++;
      if (this._wsRetry > this._wsMaxRetry) {
        if (sidebarText) sidebarText.textContent = '連接失敗';
        return; // 停止重連
      }

      if (sidebarText) sidebarText.textContent = '重連中...';
      const delay = Math.min(1000 * Math.pow(2, this._wsRetry), 30000);
      setTimeout(() => this._connectWS(), delay);
      this._wsRetry++;
    };

    this._ws.onmessage = e => {
      try {
        const d = JSON.parse(e.data);
        if (d.type === 'quotes') this._updateRealtimeQuotes(d.data);
        if (d.type === 'signals') this._updateRealtimeSignals(d.data);
      } catch {}
    };
  },

  _updateRealtimeQuotes(data) {
    // 更新儀表盤監控列表的實時價格（如果在 dashboard tab）
    if (this._currentTab === 'dashboard') {
      data.forEach(r => {
        const row = document.querySelector(`#watchlistTable tr td:first-child`);
        // 嘗試更新已存在的行
        const rows = document.querySelectorAll('#watchlistTable tr');
        rows.forEach(tr => {
          const codeCell = tr.querySelector('td:first-child');
          if (codeCell && codeCell.textContent === r.code) {
            const pctCell = tr.querySelector('td:nth-child(5) span');
            if (pctCell && r.change_pct != null) {
              pctCell.textContent = Utils.formatPct(r.change_pct);
              pctCell.className = 'b ' + Utils.badgeClass(r.change_pct);
            }
          }
        });
      });
    }

    // 如果在 markets tab 的實時行情區，更新數據
    if (this._currentTab === 'markets') {
      const el = document.getElementById('rtQuotes');
      if (el) {
        const rows = data.map(r =>
          `<tr>
            <td>${r.code}</td>
            <td>${r.price?.toFixed(2) || '-'}</td>
            <td class="r"><span class="b ${Utils.badgeClass(r.change_pct)}">${Utils.formatPct(r.change_pct)}</span></td>
            <td class="r">${r.volume?.toLocaleString() || '-'}</td>
          </tr>`
        ).join('');
        el.innerHTML = rows;
      }
    }
  },

  _updateRealtimeSignals(data) {
    // 如果在 signals tab 且是 current 子 tab，自動刷新
    if (this._currentTab === 'signals' && typeof Signals !== 'undefined') {
      if (Signals._currentTab === 'current') {
        Signals.loadCurrent();
      }
    }
  },

  // ============================================================
  // Alert & Notify (shared)
  // ============================================================

  async loadAlerts() {
    const d = await Api.getAlerts(50);
    const el = document.getElementById('alertList');
    if (!el) return;

    if (d && d.alerts && d.alerts.length > 0) {
      el.innerHTML = d.alerts.map(a =>
        `<div style="padding:8px;border-bottom:1px solid var(--border-color)">
          <div style="font-size:12px">${a.message || '-'}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:2px">${a.triggered_at || ''}</div>
        </div>`
      ).join('');
    } else {
      el.innerHTML = '<div class="state-empty"><span class="state-icon">🔔</span><span class="state-text">暫無預警記錄</span></div>';
    }
  },

  async loadNotifyChannels() {
    const d = await Api.getNotifyChannels();
    if (!d) return;

    const chs = d.channels || [];
    const el = document.getElementById('notifyChannels');
    if (!el) return;

    el.innerHTML = chs.map(ch => {
      const statusChip = ch.enabled ? '<span class="chip on">啟用</span>' : '<span class="chip off">禁用</span>';
      const cfgChip = ch.configured ? '<span class="chip cfg">已配置</span>' : '<span class="chip off">未配置</span>';
      return `<div class="channel-item">
        <span>${ch.name}</span>${statusChip}${cfgChip}
      </div>`;
    }).join('');
  },

  // ============================================================
  // Multi-Market
  // ============================================================

  async loadMarkets() {
    try {
      const d = await Api.get('/api/markets');
      if (!d || !d.markets) return;
      const el = document.getElementById('marketCards');
      if (!el) return;
      const colors = { a_share: '#ef4444', crypto: '#f59e0b', forex: '#22c55e' };
      el.innerHTML = d.markets.map(m =>
        `<div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:10px;padding:16px">
          <div style="font-size:28px;margin-bottom:8px">${m.icon || '📊'}</div>
          <div style="font-size:16px;font-weight:600">${m.name}</div>
          <div style="font-size:12px;color:var(--text-dim);margin:4px 0">${m.description}</div>
          <div style="font-size:20px;font-weight:700;color:${colors[m.market] || '#38bdf8'}">${m.data_count} <span style="font-size:12px;font-weight:400;color:var(--text-dim)">條記錄</span></div>
        </div>`
      ).join('');
    } catch (e) { console.warn('載入市場失敗:', e); }
  },

  async downloadMarket() {
    const market = document.getElementById('dlMarket')?.value;
    const symInput = document.getElementById('dlSymbols')?.value?.trim();
    const btn = document.getElementById('dlMarketBtn');
    const body = symInput ? symInput.split(',').map(s => s.trim()) : null;
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="ld"></span> 下載中...'; }
    const d = await Api.post(`/api/markets/${market}/download`, body);
    if (btn) { btn.disabled = false; btn.textContent = '下載'; }
    const el = document.getElementById('dlMarketResult');
    if (d && d.success && el) {
      el.innerHTML = `<div class="chip on">✅ ${market} 下載完成: ${d.total_records} 條記錄</div>`;
      this.loadMarkets();
    } else if (el) {
      el.innerHTML = `<div class="chip off">❌ 下載失敗</div>`;
    }
  },

  async downloadAllMarkets() {
    const btn = document.getElementById('dlAllBtn');
    const progress = document.getElementById('dlAllProgress');
    const statusEl = document.getElementById('dlAllStatus');
    const bar = document.getElementById('dlAllBar');
    const resultEl = document.getElementById('dlMarketResult');

    if (!confirm('將下載所有市場的股票數據（A股、美股、港股、指數、ETF、商品、加密貨幣、外匯），耗時較長，確定？')) return;

    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="ld"></span> 下載中...'; }
    if (progress) progress.style.display = 'block';
    if (statusEl) statusEl.textContent = '正在下載所有市場數據，請稍候...';
    if (bar) bar.style.width = '10%';

    try {
      const d = await Api.post('/api/download-all');
      if (bar) bar.style.width = '100%';

      if (d && d.success) {
        if (statusEl) statusEl.textContent = '下載完成！';
        if (resultEl) {
          const details = d.details || [];
          const successList = details.filter(r => r.records > 0);
          const failList = details.filter(r => r.records === 0);
          let html = `<div class="chip on">✅ 全部下載完成: ${d.total_records} 條記錄, ${d.success_symbols}/${d.total_symbols} 個標的成功</div>`;
          if (failList.length > 0) {
            html += `<div style="margin-top:6px;font-size:11px;color:var(--text-dim)">失敗: ${failList.map(r => r.code).join(', ')}</div>`;
          }
          resultEl.innerHTML = html;
        }
        this.loadMarkets();
      } else {
        if (resultEl) resultEl.innerHTML = '<div class="chip off">❌ 下載失敗</div>';
      }
    } catch (e) {
      if (resultEl) resultEl.innerHTML = `<div class="chip off">❌ 下載出錯: ${e.message}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🚀 一鍵下載全部市場'; }
      setTimeout(() => { if (progress) progress.style.display = 'none'; }, 3000);
    }
  },

  async downloadAllFromDashboard() {
    const section = document.getElementById('downloadSection');
    const statusEl = document.getElementById('dlStatus');
    const bar = document.getElementById('dlBar');
    const detail = document.getElementById('dlDetail');
    const qaBtn = document.getElementById('qaDownload');

    if (!confirm('將下載全市場股票數據（A股、美股、港股、指數、ETF、商品、加密貨幣、外匯），耗時較長，確定？')) return;

    if (section) section.style.display = 'block';
    if (qaBtn) qaBtn.style.opacity = '0.5';
    if (statusEl) statusEl.textContent = '正在下載全市場數據，請稍候...';
    if (bar) bar.style.width = '5%';
    if (detail) detail.textContent = '連接中...';

    try {
      const d = await Api.post('/api/download-all');
      if (bar) bar.style.width = '100%';

      if (d && d.success) {
        const details = d.details || [];
        const successList = details.filter(r => r.records > 0);
        const failList = details.filter(r => r.records === 0);

        if (statusEl) statusEl.textContent = `✅ 下載完成！共 ${d.total_records.toLocaleString()} 條記錄`;
        if (detail) {
          let txt = `${d.success_symbols}/${d.total_symbols} 個標的成功`;
          if (failList.length > 0) txt += ` | 失敗: ${failList.map(r => r.code).join(', ')}`;
          detail.textContent = txt;
        }

        // 刷新儀表盤數據
        if (typeof Dashboard !== 'undefined') Dashboard.load();
        Utils.toast(`下載完成: ${d.total_records.toLocaleString()} 條記錄`);
      } else {
        if (statusEl) statusEl.textContent = '❌ 下載失敗';
      }
    } catch (e) {
      if (statusEl) statusEl.textContent = '❌ 下載出錯: ' + e.message;
    } finally {
      if (qaBtn) qaBtn.style.opacity = '1';
      setTimeout(() => { if (section) section.style.display = 'none'; }, 8000);
    }
  },

  async loadMarketRealtime() {
    const market = document.getElementById('rtMarket')?.value;
    const el = document.getElementById('rtMarketData');
    if (!el) return;
    el.innerHTML = '<p style="color:var(--text-dim)">載入中...</p>';
    const d = await Api.get(`/api/markets/${market}/realtime`);
    if (!d || !d.data || d.data.length === 0) { el.innerHTML = '<p style="color:var(--text-dim)">無數據</p>'; return; }
    let html = '<table><thead><tr><th>標的</th><th>名稱</th><th>價格</th><th>漲跌幅</th><th>24h最高</th><th>24h最低</th></tr></thead><tbody>';
    d.data.forEach(r => {
      const pct = parseFloat(r.change_pct || 0);
      const cls = pct >= 0 ? 'color:#22c55e' : 'color:#ef4444';
      html += `<tr><td>${r.symbol}</td><td>${r.name || ''}</td><td>${r.price}</td><td style="${cls}">${pct.toFixed(2)}%</td><td>${r.high || '-'}</td><td>${r.low || '-'}</td></tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  },

  async testNotify() {
    const btn = document.getElementById('testNotifyBtn');
    Utils.btnLoading(btn, true, '發送中...');

    const d = await Api.testNotify();
    Utils.btnLoading(btn, false, '🔔 測試所有渠道');

    if (!d) return Utils.toast('失敗', 3000, 'error');
    const r = d.results || {};
    const summary = Object.entries(r).map(([k, v]) => `${k}: ${v}`).join(', ');
    Utils.toast('測試結果: ' + summary);
  },

  // ============================================================
  // Heatmap Strategy Listener
  // ============================================================

  initHeatmapStrategy() {
    const sel = document.getElementById('hmStrategy');
    if (sel) {
      sel.addEventListener('change', () => {
        if (typeof Heatmap !== 'undefined') Heatmap.updateParams();
      });
      // 初始化時也更新參數
      if (typeof Heatmap !== 'undefined') Heatmap.updateParams();
    }
  },
};

// ============================================================
// Global function bridges (for onclick handlers in HTML)
// ============================================================

function runBacktest() { Backtest.run(); }
function runMultiBacktest() { Backtest.runMulti(); }
function runOptimize() { Optimize.run(); }
function runAutoOptimize() { Optimize.runAuto(); }
function runPortfolio() { Portfolio.run(); }
function runCompare() { App._runCompare(); }
function loadHistory() { App._loadHistory(); }
function runWalkForward() { App._runWalkForward(); }
function runHeatmap() { Heatmap.run(); }
function runScreener() { Screener.run(); }
function generateReport() { App._generateReport(); }
function enableScheduler() { App._enableScheduler(); }
function disableScheduler() { App._disableScheduler(); }
function listSchedulerJobs() { App._listSchedulerJobs(); }
function testNotify() { App.testNotify(); }
function showAddRule() { Dashboard.showAddRule(); }
function addToWatchlist(code) { Screener.addToWatchlist(code); }
function downloadMarket() { App.downloadMarket(); }
function downloadAllMarkets() { App.downloadAllMarkets(); }
function loadMarketRealtime() { App.loadMarketRealtime(); }

// ============================================================
// Compare, History, WalkForward, Reports (shared)
// ============================================================

App._runCompare = async function() {
  const codes = document.getElementById('cmpCodes').value.split(',').map(s => s.trim());
  const days = parseInt(document.getElementById('cmpDays').value) || 250;
  const btn = document.getElementById('cmpBtn');

  Utils.btnLoading(btn, true);
  const d = await Api.compareStocks(codes, days);
  Utils.btnLoading(btn, false, '對比');

  if (!d) return;

  const comp = d.comparison || {};
  const series = [];
  for (const [code, v] of Object.entries(comp)) {
    series.push({ label: code, data: v.relative_return, dates: v.dates });
  }

  if (series.length) {
    Charts.drawLineChart('cmpChart', series);
    document.getElementById('cmpResult').classList.remove('h');
  }
};

App._loadHistory = async function() {
  const code = document.getElementById('histCode')?.value?.trim() || '';
  const strategy = document.getElementById('histStrategy')?.value?.trim() || '';

  const d = await Api.getBacktestHistory(code, strategy, 100);
  if (!d) return;

  const rows = d.results || [];
  document.getElementById('histTable').innerHTML = rows.map(r =>
    `<tr>
      <td>${r.id}</td>
      <td>${r.code}</td>
      <td>${r.strategy}</td>
      <td class="r"><span class="b ${Utils.badgeClass(r.total_return_pct)}">${Utils.formatPct(r.total_return_pct)}</span></td>
      <td class="r">${Utils.formatNum(r.sharpe_ratio, 2)}</td>
      <td class="r">${Utils.formatNum(r.sortino_ratio, 2)}</td>
      <td class="r">${Utils.formatNum(r.calmar_ratio, 2)}</td>
      <td class="r">${Utils.formatPct(-r.max_drawdown_pct)}</td>
      <td class="r">${Utils.formatNum(r.var_95, 4)}</td>
      <td class="r">${Utils.formatNum(r.win_rate_pct, 1)}%</td>
      <td class="r">${r.total_trades || 0}</td>
      <td style="font-size:10px;color:var(--text-dim)">${r.created_at || ''}</td>
    </tr>`
  ).join('') || '<tr><td colspan="12" style="color:var(--text-muted);text-align:center">暫無回測歷史</td></tr>';
};

App._runWalkForward = async function() {
  const code = document.getElementById('wfCode').value.trim();
  if (!code) return Utils.toast('請輸入股票代碼', 3000, 'error');

  const params = {
    code,
    strategy: document.getElementById('wfStrategy').value,
    train: parseInt(document.getElementById('wfTrain').value) || 750,
    test: parseInt(document.getElementById('wfTest').value) || 250,
    trials: parseInt(document.getElementById('wfTrials').value) || 30,
  };
  const btn = document.getElementById('wfBtn');

  Utils.btnLoading(btn, true, '分析中...');
  const d = await Api.runWalkForward(params);
  Utils.btnLoading(btn, false, '開始分析');

  if (!d || !d.success) return Utils.toast('失敗: ' + (d?.detail || ''), 3000, 'error');

  const r = d.result;
  document.getElementById('wfStats').innerHTML = `
    <div class="c"><h3>窗口數</h3><div class="v bl">${r.n_windows}</div></div>
    <div class="c"><h3>平均 OOS 收益</h3><div class="v ${Utils.badgeClass(r.avg_oos_return_pct)}">${Utils.formatPct(r.avg_oos_return_pct)}</div></div>
    <div class="c"><h3>平均 OOS 夏普</h3><div class="v">${Utils.formatNum(r.avg_oos_sharpe, 4)}</div></div>
    <div class="c"><h3>穩定性</h3><div class="v">${Utils.formatNum(r.stability_score, 4)}</div></div>
    <div class="c"><h3>過擬合比</h3><div class="v rd">${Utils.formatNum(r.overfit_ratio, 4)}</div></div>
    <div class="c"><h3>正收益窗口</h3><div class="v gn">${r.positive_windows}/${r.total_windows}</div></div>`;

  const wins = r.windows || [];
  document.getElementById('wfTable').innerHTML = wins.map(w =>
    `<tr>
      <td>${w.window}</td>
      <td style="font-size:10px">${w.train_period}</td>
      <td style="font-size:10px">${w.test_period}</td>
      <td class="r"><span class="b ${Utils.badgeClass(w.test_return_pct)}">${Utils.formatPct(w.test_return_pct)}</span></td>
      <td class="r">${Utils.formatNum(w.test_sharpe, 2)}</td>
      <td class="r">${Utils.formatPct(-w.test_max_dd_pct)}</td>
      <td class="r">${w.test_trades}</td>
      <td style="font-size:9px;color:var(--text-dim)">${Object.entries(w.best_params || {}).map(([k, v]) => k + '=' + v).join(', ')}</td>
    </tr>`
  ).join('');

  const oosReturns = wins.map(w => w.test_return_pct);
  const oosLabels = wins.map(w => 'W' + w.window);
  Charts.drawBarChart('wfChart', oosReturns, oosLabels, '樣本外收益率 (%)');

  document.getElementById('wfResult').classList.remove('h');
  Utils.toast('Walk-Forward 分析完成', 3000, 'success');
};

App._generateReport = async function() {
  const btn = document.getElementById('rptBtn');
  Utils.btnLoading(btn, true, '生成中...');

  try {
    const codes = ['000001', '600519', '000858'];
    let report = '📊 每日策略報告\n' + new Date().toLocaleString('zh-CN') + '\n' + '='.repeat(40) + '\n\n';

    for (const code of codes) {
      try {
        const d = await Api.runBacktest({ code, strategy: 'dual_ma' });
        if (d && d.success) {
          const r = d.result;
          report += `🏆 ${code}: dual_ma | 夏普 ${r.sharpe_ratio?.toFixed(2)} | 收益 ${r.total_return_pct?.toFixed(2)}% | 回撤 ${r.max_drawdown_pct?.toFixed(1)}%\n`;
        }
      } catch {}
    }

    report += '\n' + '='.repeat(40);
    document.getElementById('rptContent').textContent = report;
    document.getElementById('rptResult').classList.remove('h');
  } catch {}

  Utils.btnLoading(btn, false, '生成報告');
};

App._enableScheduler = async function() {
  const d = await Api.enableScheduler();
  if (d) Utils.toast(d.message || '已啟用');
};

App._disableScheduler = async function() {
  const d = await Api.disableScheduler();
  if (d) Utils.toast(d.message || '已禁用');
};

App._listSchedulerJobs = async function() {
  const d = await Api.getSchedulerJobs();
  if (!d) return;

  const jobs = d.jobs || [];
  const el = document.getElementById('jobsList');
  if (!el) return;

  if (jobs.length) {
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>ID</th><th>名稱</th><th>下次執行</th><th>觸發器</th></tr></thead>
      <tbody>${jobs.map(j => `<tr>
        <td>${j.id}</td>
        <td>${j.name}</td>
        <td>${j.next_run || '-'}</td>
        <td style="font-size:10px">${j.trigger}</td>
      </tr>`).join('')}</tbody>
    </table></div>`;
  } else {
    el.innerHTML = '<p style="color:var(--text-muted)">無調度任務</p>';
  }

  document.getElementById('schedulerJobs').classList.remove('h');
};

// ============================================================
// Task Panel — 任務面板（防止重複執行）
// ============================================================

App._initTaskPanel = function() {
  // 創建任務面板 DOM
  const panel = document.createElement('div');
  panel.id = 'taskPanel';
  panel.className = 'task-panel';
  panel.style.cssText = 'display:none;position:fixed;bottom:20px;right:20px;width:340px;max-height:400px;background:var(--bg-secondary,#1e293b);border:1px solid var(--border-color,#334155);border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.3);z-index:9999;overflow:hidden;font-size:12px';
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid var(--border-color,#334155);background:var(--bg-primary,#0f172a)">
      <span style="font-weight:600">📋 任務列表</span>
      <div>
        <button onclick="App._refreshTasks()" style="background:none;border:none;color:var(--text-dim,#94a3b8);cursor:pointer;font-size:14px;padding:2px 6px" title="刷新">🔄</button>
        <button onclick="App.toggleTaskPanel()" style="background:none;border:none;color:var(--text-dim,#94a3b8);cursor:pointer;font-size:14px;padding:2px 6px">✕</button>
      </div>
    </div>
    <div id="taskPanelList" style="max-height:300px;overflow-y:auto;padding:8px"></div>`;
  document.body.appendChild(panel);

  // Header 任務指示器
  const indicator = document.createElement('div');
  indicator.id = 'taskIndicator';
  indicator.style.cssText = 'display:none;cursor:pointer;font-size:11px;padding:4px 8px;border-radius:4px;background:var(--bg-primary);border:1px solid var(--border-color);margin-left:8px';
  indicator.onclick = () => App.toggleTaskPanel();
  indicator.innerHTML = '⏳ <span id="taskIndicatorCount">0</span>';
  const hdrRight = document.querySelector('.hdr-right');
  if (hdrRight) hdrRight.insertBefore(indicator, hdrRight.firstChild);

  // 定期刷新任務狀態
  setInterval(() => App._pollTasks(), 5000);
};

App.toggleTaskPanel = function() {
  const panel = document.getElementById('taskPanel');
  if (!panel) return;
  const isVisible = panel.style.display !== 'none';
  panel.style.display = isVisible ? 'none' : 'block';
  if (!isVisible) App._refreshTasks();
};

App._pollTasks = async function() {
  try {
    const d = await Api.getTasks(null, 'running');
    if (!d) return;
    const running = d.stats?.running || 0;
    const indicator = document.getElementById('taskIndicator');
    const countEl = document.getElementById('taskIndicatorCount');
    if (indicator) {
      indicator.style.display = running > 0 ? 'inline-block' : 'none';
      if (countEl) countEl.textContent = running;
    }
  } catch {}
};

App._TASK_TYPE_NAMES = {
  backtest: '📊 回測',
  backtest_advanced: '📊 進階回測',
  backtest_multi: '📊 多策略對比',
  optimize: '⚡ 參數優化',
  portfolio: '📈 組合回測',
  walkforward: '🔄 Walk-Forward',
  auto_optimize: '🤖 自動優化',
  heatmap: '🌡️ 熱力圖',
};

App._refreshTasks = async function() {
  const container = document.getElementById('taskPanelList');
  if (!container) return;
  container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-dim)"><span class="ld"></span> 載入中...</div>';

  const d = await Api.getTasks(null, null, 30);
  if (!d || !d.tasks || !d.tasks.length) {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-dim)">暫無任務</div>';
    return;
  }

  // 統計摘要
  const stats = d.stats || {};
  const statsHtml = `
    <div style="display:flex;gap:12px;padding:8px 4px;margin-bottom:8px;border-bottom:1px solid var(--border-color,#334155);font-size:11px;color:var(--text-dim,#64748b)">
      <span>📋 總計 ${stats.total || 0}</span>
      <span style="color:#38bdf8">⏳ 運行中 ${stats.running || 0}</span>
      <span style="color:#22c55e">✅ 完成 ${stats.completed || 0}</span>
      <span style="color:#ef4444">❌ 失敗 ${stats.failed || 0}</span>
    </div>`;

  const statusIcons = {
    running: '⏳', completed: '✅', failed: '❌', cancelled: '🚫', pending: '⏸️',
  };
  const statusColors = {
    running: '#38bdf8', completed: '#22c55e', failed: '#ef4444', cancelled: '#94a3b8', pending: '#f59e0b',
  };

  container.innerHTML = statsHtml + d.tasks.map(t => {
    const typeName = App._TASK_TYPE_NAMES[t.task_type] || t.task_type;
    const canViewResult = t.status === 'completed' && t.has_result;
    return `
    <div style="display:flex;align-items:center;gap:8px;padding:8px;margin-bottom:4px;background:var(--bg-primary,#0f172a);border-radius:8px;border:1px solid var(--border-color,#334155);${canViewResult ? 'cursor:pointer' : ''}" ${canViewResult ? `onclick="App._viewTaskResult('${t.task_id}')"` : ''}>
      <span style="font-size:16px">${statusIcons[t.status] || '❓'}</span>
      <div style="flex:1;min-width:0">
        <div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${t.title || t.task_type}</div>
        <div style="font-size:10px;color:var(--text-dim,#64748b);margin-top:2px">${typeName} · ${t.created_at || ''}</div>
        ${t.error ? `<div style="font-size:10px;color:#ef4444;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">⚠ ${String(t.error).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>` : ''}
      </div>
      <div style="display:flex;align-items:center;gap:4px">
        <span style="color:${statusColors[t.status] || '#94a3b8'};font-size:11px;font-weight:600">${
          t.status === 'running' ? t.progress + '%' : (t.status === 'completed' && t.has_result ? '查看' : t.status)
        }</span>
        ${t.status === 'running' ? `<button onclick="event.stopPropagation();App._cancelTask('${t.task_id}')" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:12px;padding:2px 4px" title="取消">✕</button>` : ''}
      </div>
    </div>`;
  }).join('');
};

App._cancelTask = async function(taskId) {
  const d = await Api.cancelTask(taskId);
  if (d && d.success) {
    Utils.toast('任務已取消', 2000, 'success');
    App._refreshTasks();
  }
};

App._viewTaskResult = async function(taskId) {
  const d = await Api.getTask(taskId);
  if (!d || !d.task) return;

  const task = d.task;
  if (!task.result) {
    Utils.toast('此任務暫無結果', 2000, 'warning');
    return;
  }

  const r = task.result;
  const typeName = App._TASK_TYPE_NAMES[task.task_type] || task.task_type;

  // 根據任務類型顯示不同結果
  let content = '';

  if (task.task_type === 'backtest' || task.task_type === 'backtest_advanced') {
    // 回測結果：顯示關鍵指標
    content = `
      <h3>${typeName}結果 — ${task.title}</h3>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0">
        <div class="c"><h3>收益率</h3><div class="v ${r.total_return_pct >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(r.total_return_pct)}</div></div>
        <div class="c"><h3>夏普比率</h3><div class="v">${Utils.formatNum(r.sharpe_ratio, 4)}</div></div>
        <div class="c"><h3>最大回撤</h3><div class="v rd">${Utils.formatPct(-r.max_drawdown_pct)}</div></div>
        <div class="c"><h3>勝率</h3><div class="v">${Utils.formatNum(r.win_rate_pct, 1)}%</div></div>
        <div class="c"><h3>交易次數</h3><div class="v">${r.total_trades}</div></div>
        <div class="c"><h3>年化收益</h3><div class="v">${Utils.formatPct(r.annual_return_pct)}</div></div>
        <div class="c"><h3>Sortino</h3><div class="v">${Utils.formatNum(r.sortino_ratio, 4)}</div></div>
        <div class="c"><h3>最終市值</h3><div class="v">¥${(r.final_value || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}</div></div>
      </div>
      <div style="margin-top:8px">
        <button class="btn s" onclick="Utils.closeModal();App._loadBacktestResult('${taskId}')">📊 在回測頁查看完整結果</button>
      </div>`;
  } else if (task.task_type === 'backtest_multi') {
    // 多策略對比結果
    const results = Array.isArray(r) ? r : (r.results || []);
    const rows = results.slice(0, 10).map(item => `
      <tr>
        <td>${item.strategy}</td>
        <td class="r"><span class="b ${item.total_return_pct >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(item.total_return_pct)}</span></td>
        <td class="r">${Utils.formatNum(item.sharpe_ratio, 2)}</td>
        <td class="r">${Utils.formatPct(-item.max_drawdown_pct)}</td>
        <td class="r">${Utils.formatNum(item.win_rate_pct, 1)}%</td>
      </tr>
    `).join('');
    content = `
      <h3>${typeName}結果 — ${task.title}</h3>
      <div class="table-wrap" style="margin-top:8px"><table>
        <tr><th>策略</th><th>收益率</th><th>夏普</th><th>回撤</th><th>勝率</th></tr>
        ${rows}
      </table></div>`;
  } else if (task.task_type === 'optimize') {
    // 優化結果
    let rows = '';
    if (typeof r === 'object' && !Array.isArray(r)) {
      // 多策略優化結果
      for (const [strat, results] of Object.entries(r)) {
        const top3 = Array.isArray(results) ? results.slice(0, 3) : [];
        rows += `<tr><td colspan="5" style="font-weight:600;padding-top:8px">${strat}</td></tr>`;
        top3.forEach((item, i) => {
          rows += `<tr>
            <td>#${i + 1}</td>
            <td>${JSON.stringify(item.params || {})}</td>
            <td class="r">${Utils.formatNum(item.sharpe || item.value || 0, 4)}</td>
            <td class="r">${Utils.formatPct(-(item.max_drawdown_pct || 0))}</td>
            <td class="r">${Utils.formatNum(item.win_rate_pct || 0, 1)}%</td>
          </tr>`;
        });
      }
    }
    content = `
      <h3>${typeName}結果 — ${task.title}</h3>
      <div class="table-wrap" style="margin-top:8px"><table>
        <tr><th>#</th><th>參數</th><th>夏普</th><th>回撤</th><th>勝率</th></tr>
        ${rows || '<tr><td colspan="5" style="text-align:center;color:var(--text-dim)">無數據</td></tr>'}
      </table></div>`;
  } else if (task.task_type === 'portfolio') {
    // 組合回測結果
    content = `
      <h3>${typeName}結果 — ${task.title}</h3>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0">
        <div class="c"><h3>收益率</h3><div class="v ${(r.total_return_pct || 0) >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(r.total_return_pct || 0)}</div></div>
        <div class="c"><h3>夏普比率</h3><div class="v">${Utils.formatNum(r.sharpe_ratio || 0, 4)}</div></div>
        <div class="c"><h3>最大回撤</h3><div class="v rd">${Utils.formatPct(-(r.max_drawdown_pct || 0))}</div></div>
      </div>`;
  } else {
    // 通用結果顯示
    const json = JSON.stringify(r, null, 2);
    content = `
      <h3>${typeName}結果 — ${task.title}</h3>
      <pre style="background:var(--bg-secondary,#1e293b);padding:12px;border-radius:8px;overflow:auto;max-height:400px;font-size:12px">${json.substring(0, 3000)}${json.length > 3000 ? '\n...(截斷)' : ''}</pre>`;
  }

  Utils.showModal(content);
};

App._loadBacktestResult = async function(taskId) {
  // 從任務結果加載回測結果到回測頁面
  const d = await Api.getTask(taskId);
  if (!d || !d.task || !d.task.result) return;

  const r = d.task.result;
  // 切換到回測 tab
  if (typeof App !== 'undefined' && App.loadTab) {
    App.loadTab('backtest');
  }

  // 將結果填充到 Backtest 對象
  if (typeof Backtest !== 'undefined') {
    Backtest._lastResult = r;
    // 設置股票代碼
    const codeInput = document.getElementById('btCode');
    if (codeInput) codeInput.value = r.code || '';
    // 顯示結果
    if (Backtest._displayResult) {
      Backtest._displayResult(r);
    }
  }
};

// 全局任務去重輔助 — 用於按鈕點擊防重複
App._activeTasks = {};
App.checkTaskDedup = function(taskType, params) {
  const key = taskType + ':' + JSON.stringify(params);
  if (App._activeTasks[key]) {
    Utils.toast('⏳ 相同任務正在執行中，請等待完成', 3000, 'warning');
    return false;
  }
  App._activeTasks[key] = true;
  return true;
};
App.releaseTaskDedup = function(taskType, params) {
  const key = taskType + ':' + JSON.stringify(params);
  delete App._activeTasks[key];
};

// ============================================================
// Boot
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
