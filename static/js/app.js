/**
 * app.js — 主應用邏輯、Tab 路由、初始化
 */

const App = {
  _ws: null,
  _wsRetry: 0,
  _wsMaxRetry: 15,
  _wsAuthRequired: false,
  _currentTab: 'dashboard',
  _routerReady: false,
  _tabIds: null,

  /**
   * 初始化應用
   */
  init() {
    // 初始化 API（載入 token、設置 auth UI）
    Api.init();

    this.initTheme();
    this.initTabs();
    this.initWebSocket();
    this._initGreeting();
    this._initMarketStatus();
    this._initTips();
    this._initSidebarToggle();
    this._initGlobalSearch();
    this._initTaskPanel();

    // 並行預載（不阻塞首屏 Tab）
    Promise.all([
      this._initStrategies(),
      this._initQuickStats(),
    ]).catch(() => {});

    // 路由：#/stock/代碼、#/stocks、#/dashboard 等各 Tab 深連結
    this.initRouter();
    if (typeof StockDetail !== 'undefined') StockDetail.initRouter();
    if (!this.routeFromHash(true)) {
      const lastTab = (typeof LocalStore !== 'undefined' && LocalStore.get('lastTab')) || 'dashboard';
      const valid = document.getElementById('tab-' + lastTab);
      this.loadTab(valid ? lastTab : 'dashboard', { syncHash: true });
    }

    // 初始化子模塊
    if (typeof Signals !== 'undefined') Signals.init();
    if (typeof Data !== 'undefined') Data.init();
    if (typeof Portfolio !== 'undefined') Portfolio.init();
    if (typeof StockPicker !== 'undefined') StockPicker.initAll();
    if (typeof Analysis !== 'undefined') Analysis.init();
    if (typeof Backtest !== 'undefined') Backtest.init();

    // 全局快捷鍵
    this._initKeyboardShortcuts();
    // 快捷卡片滑鼠追蹤光效
    this._initQuickCardHover();
  },

  quickAction(tab) {
    this.loadTab(tab);
  },

  /** 舊版回測 Tab → 個股詳情子功能（#/stock/代碼/子Tab） */
  _STOCK_TOOL_TABS: ['backtest', 'optimize', 'walkforward', 'heatmap', 'history'],

  openStockTool(subTab, code) {
    const sub = this._STOCK_TOOL_TABS.includes(subTab) ? subTab : 'backtest';
    const c = String(code || '').trim();
    if (typeof StockDetail === 'undefined') {
      this.loadTab('stock-detail');
      return;
    }
    StockDetail.initRouter();
    if (c) {
      StockDetail._pendingSubTab = sub;
      StockDetail.open(c);
      return;
    }
    this.loadTab('stock-detail');
    StockDetail._pendingSubTab = sub;
    StockDetail.showIndex();
    if (typeof Utils !== 'undefined') {
      Utils.toast('請先從股票詳情選擇標的', 2800, 'info');
    }
  },

  /** 打開該股獨立詳情頁（#/stock/代碼，可收藏分享） */
  openStockDetail(code, meta = {}) {
    const c = String(code || '').trim();
    if (c && typeof LocalStore !== 'undefined') {
      LocalStore.pushRecentStock({
        code: c,
        name: meta.name || '',
        market: meta.market || '',
      });
    }
    if (!c) {
      if (typeof StockDetail !== 'undefined') {
        StockDetail.initRouter();
        this.loadTab('stock-detail');
        StockDetail.showIndex();
      } else {
        this.loadTab('stock-detail');
      }
      return;
    }
    if (typeof StockDetail !== 'undefined') StockDetail.open(c);
    else this.loadTab('stock-detail');
  },

  dismissTip() {
    const el = document.getElementById('tipCard');
    if (el) el.style.display = 'none';
    if (typeof LocalStore !== 'undefined') LocalStore.set('tipDismissed', true);
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
    const dismissed = (typeof LocalStore !== 'undefined' && LocalStore.get('tipDismissed'))
      || localStorage.getItem('tipDismissed') === 'true';
    if (dismissed) {
      const el = document.getElementById('tipCard');
      if (el) el.style.display = 'none';
      return;
    }

    const tips = [
      '夏普比率 (Sharpe Ratio) 表示每承受一單位風險能獲得多少超額收益，大於 1 算不錯，大於 2 算優秀。',
      '最大回撤 (Max Drawdown) 是從最高點到最低點的跌幅，越小越好，代表策略的穩定性。',
      '索提諾比率只考慮下行風險，比夏普比率更關注「虧損」而非「波動」。',
      '卡瑪比率 = 年化收益 / 最大回撤，數值越大表示風險調整後的收益越好。',
      'Win Rate (勝率) 不是越高越好，關鍵是盈虧比 — 即使勝率只有 40%，盈虧比夠高也能盈利。',
      '滾動窗口驗證能幫你檢測策略是否過擬合 — 如果樣本外表現遠差於樣本內，就要小心了。',
      '蒙特卡羅模擬通過隨機重組交易順序，幫你評估策略在不同市場環境下的表現範圍。',
    ];

    const idx = Math.floor(Math.random() * tips.length);
    const el = document.getElementById('tipText');
    if (el) el.textContent = tips[idx];
  },

  async _initStrategies() {
    try {
      const d = await Api.getStrategies();
      if (!d) return;

      const all = [...(d.builtin || []), ...(d.user || [])];
      if (all.length === 0) return;

      const builtinNames = new Set((d.builtin || []).map(s => s.name));

      const options = all.map(s =>
        `<option value="${s.name}">${s.display_name || s.name}</option>`
      ).join('');

      // 填充一般策略下拉框
      ['btStrategy', 'hmStrategy', 'wfStrategy', 'anStrategy'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          const current = el.value || el.options[0]?.value;
          el.innerHTML = options;
          if (current && el.querySelector(`option[value="${current}"]`)) {
            el.value = current;
          } else if (id === 'btStrategy' && builtinNames.has('dual_ma')) {
            el.value = 'dual_ma';
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
      if (typeof Heatmap !== 'undefined') {
        Heatmap.bindStrategyChange();
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

    const collapsed = (typeof LocalStore !== 'undefined' && LocalStore.get('sidebarCollapsed'))
      || localStorage.getItem('sidebarCollapsed') === 'true';
    if (collapsed) sidebar.classList.add('collapsed');

    btn.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      const isCollapsed = sidebar.classList.contains('collapsed');
      localStorage.setItem('sidebarCollapsed', isCollapsed);
      if (typeof LocalStore !== 'undefined') LocalStore.set('sidebarCollapsed', isCollapsed);
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
      { ti: 'ti-chart-candle', code: '000001', name: '平安銀行', type: 'A股', action: () => this.openStockDetail('000001') },
      { ti: 'ti-chart-candle', code: '600519', name: '貴州茅台', type: 'A股', action: () => this.openStockDetail('600519') },
      { ti: 'ti-chart-candle', code: '000858', name: '五糧液', type: 'A股', action: () => this.openStockDetail('000858') },
      { ti: 'ti-chart-candle', code: '601318', name: '中國平安', type: 'A股', action: () => this.openStockDetail('601318') },
      { ti: 'ti-chart-candle', code: '000333', name: '美的集團', type: 'A股', action: () => this.openStockDetail('000333') },
      { ti: 'ti-crystal-ball', code: '', name: '預測市場', type: '功能', action: () => this.loadTab('polymarket') },
      { ti: 'ti-chart-line', code: '', name: '股票詳情索引', type: '功能', action: () => this.openStockDetail('') },
      { ti: 'ti-flask', code: '', name: '策略回測', type: '功能', action: () => this.openStockTool('backtest') },
      { ti: 'ti-bolt', code: '', name: '參數優化', type: '功能', action: () => this.openStockTool('optimize') },
      { ti: 'ti-refresh', code: '', name: 'Walk-Forward', type: '功能', action: () => this.openStockTool('walkforward') },
      { ti: 'ti-temperature', code: '', name: '熱力圖', type: '功能', action: () => this.openStockTool('heatmap') },
      { ti: 'ti-briefcase', code: '', name: '組合回測', type: '功能', action: () => this.loadTab('portfolio') },
      { ti: 'ti-scale', code: '', name: '多股對比', type: '功能', action: () => this.loadTab('compare') },
      { ti: 'ti-filter', code: '', name: '股票篩選', type: '功能', action: () => this.loadTab('screener') },
      { ti: 'ti-antenna-bars-5', code: '', name: '實時信號', type: '功能', action: () => this.loadTab('signals') },
      { ti: 'ti-database', code: '', name: '數據中心', type: '功能', action: () => this.loadTab('data') },
      { ti: 'ti-microscope', code: '', name: '深度分析', type: '功能', action: () => this.loadTab('analysis') },
      { ti: 'ti-file-analytics', code: '', name: '策略報告', type: '功能', action: () => this.loadTab('reports') },
      { ti: 'ti-clock', code: '', name: '定時任務', type: '功能', action: () => this.loadTab('scheduler') },
      { ti: 'ti-bell-ringing', code: '', name: '預警通知', type: '功能', action: () => this.loadTab('alerts') },
      { ti: 'ti-world', code: '', name: '多市場', type: '功能', action: () => this.loadTab('markets') },
      { ti: 'ti-plug', code: '', name: '接口檢查', type: '功能', action: () => this.loadTab('connectivity') },
      { ti: 'ti-list-check', code: '', name: '任務面板', type: '功能', action: () => this.loadTab('tasks') },
      { ti: 'ti-download', code: '', name: '下載全市場數據', type: '操作', action: () => this.downloadAllFromDashboard() },
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
          results.innerHTML = matched.map((item, i) => {
            const logo = item.code && typeof Utils !== 'undefined' && Utils.stockIconHtml
              ? `<span class="sr-logo">${Utils.stockIconHtml(item.code, item.name, 28)}</span>`
              : `<span class="sr-icon-func"><i class="ti ${item.ti || 'ti-apps'}" aria-hidden="true"></i></span>`;
            return `<div class="search-result-item" data-idx="${i}">
              ${logo}
              <span class="sr-code">${item.code || '—'}</span>
              <span class="sr-name">${item.name}</span>
              <span class="sr-type">${item.type}</span>
            </div>`;
          }).join('');

          if (typeof Utils !== 'undefined' && Utils.hydrateStockIcons) {
            Utils.hydrateStockIcons(results);
          }

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
    const saved = (typeof LocalStore !== 'undefined' && LocalStore.get('theme'))
      || localStorage.getItem('theme')
      || 'dark';
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
      if (typeof LocalStore !== 'undefined') LocalStore.set('theme', 'light');
    } else {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('theme', 'dark');
      if (typeof LocalStore !== 'undefined') LocalStore.set('theme', 'dark');
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
    btn.innerHTML = isDark
      ? '<i class="ti ti-sun" aria-hidden="true"></i>'
      : '<i class="ti ti-moon" aria-hidden="true"></i>';
    btn.title = isDark ? '切換亮色主題' : '切換暗色主題';
  },

  // ============================================================
  // Keyboard Shortcuts
  // ============================================================

  _initKeyboardShortcuts() {
    document.addEventListener('keydown', e => {
      // 忽略輸入框、PDF 查看器、彈窗中的按鍵
      const active = document.activeElement;
      const tag = active?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (active?.isContentEditable) return;
      if (active?.closest('.bpdf, .modal, #modalRoot, .shortcuts-modal, [role="dialog"]')) return;

      // Ctrl/Cmd + K → 聚焦搜索
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        document.getElementById('globalSearch')?.focus();
        return;
      }

      // ? → 顯示快捷鍵幫助
      if (e.key === '?') {
        e.preventDefault();
        this._showShortcutsModal();
        return;
      }

      // Escape → 關閉彈窗
      if (e.key === 'Escape') {
        const modal = document.querySelector('.shortcuts-modal');
        if (modal) { modal.remove(); return; }
      }

      // 數字鍵快速切換 Tab
      const tabMap = {
        '1': 'dashboard',
        '2': 'portfolio',
        '3': 'signals',
        '4': 'data',
        '5': 'stock-detail',
        '6': 'tasks',
      };
      if (tabMap[e.key] && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        this.loadTab(tabMap[e.key]);
        return;
      }

      // 字母快捷鍵
      const letterMap = {
        'b': 'backtest',
        's': 'screener',
        'c': 'compare',
        'r': 'reports',
        'a': 'alerts',
        'm': 'markets',
        'p': 'polymarket',
        'x': 'crypto',
        't': 'tasks',
      };
      if (letterMap[e.key] && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        if (['backtest', 'optimize'].includes(letterMap[e.key])) {
          this.openStockTool(letterMap[e.key]);
        } else {
          this.loadTab(letterMap[e.key]);
        }
      }
    });
  },

  _showShortcutsModal() {
    // 避免重複
    if (document.querySelector('.shortcuts-modal')) return;

    const shortcuts = [
      ['/', '聚焦搜索'],
      ['Ctrl+K', '聚焦搜索'],
      ['?', '顯示快捷鍵'],
      ['1-6', '切換常用 Tab'],
      ['B', '策略回測'],
      ['S', '股票篩選'],
      ['C', '多股對比'],
      ['T', '任務面板'],
      ['M', '多市場'],
      ['P', '預測市場'],
      ['X', '加密行情'],
      ['Esc', '關閉彈窗'],
    ];

    const rows = shortcuts.map(([key, desc]) =>
      `<div class="shortcut-row"><span>${desc}</span><span class="kbd-hint">${key}</span></div>`
    ).join('');

    const el = document.createElement('div');
    el.className = 'shortcuts-modal';
    el.innerHTML = `<div class="shortcuts-modal-content">
      <h3><i class="ti ti-keyboard"></i> 鍵盤快捷鍵</h3>
      <div class="shortcuts-grid">${rows}</div>
    </div>`;
    el.addEventListener('click', e => { if (e.target === el) el.remove(); });
    document.body.appendChild(el);
  },

  // ============================================================
  // KPI Counter Animation
  // ============================================================

  /**
   * 將數字以動態計數方式顯示
   * @param {HTMLElement} el - 目標元素
   * @param {number} endVal - 目標數值
   * @param {object} opts - { duration, decimals, prefix, suffix }
   */
  animateCounter(el, endVal, opts = {}) {
    if (!el) return;
    const duration = opts.duration || 800;
    const decimals = opts.decimals ?? 0;
    const prefix = opts.prefix || '';
    const suffix = opts.suffix || '';
    const startVal = parseFloat(el.textContent.replace(/[^0-9.\-]/g, '')) || 0;
    const startTime = performance.now();

    const easeOut = t => 1 - Math.pow(1 - t, 3);

    const tick = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easeOut(progress);
      const current = startVal + (endVal - startVal) * eased;
      el.textContent = prefix + current.toFixed(decimals) + suffix;
      if (progress < 1) requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
  },

  // ============================================================
  // Quick Card Hover Effect
  // ============================================================

  _initQuickCardHover() {
    document.querySelectorAll('.qa-card').forEach(card => {
      card.addEventListener('mousemove', e => {
        const rect = card.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / rect.width * 100).toFixed(0);
        const y = ((e.clientY - rect.top) / rect.height * 100).toFixed(0);
        card.style.setProperty('--mouse-x', x + '%');
        card.style.setProperty('--mouse-y', y + '%');
      });
    });
  },

  // ============================================================
  // Tab Routing（#/tabId；股票詳情保留 #/stock/代碼、#/stocks）
  // ============================================================

  initRouter() {
    if (this._routerReady) return;
    this._routerReady = true;
    const tabs = new Set(['dashboard']);
    document.querySelectorAll('.sidebar button[data-tab]').forEach(b => {
      if (b.dataset.tab) tabs.add(b.dataset.tab);
    });
    this._tabIds = tabs;
    const onRoute = () => this.routeFromHash(false);
    window.addEventListener('hashchange', onRoute);
    window.addEventListener('popstate', onRoute);
  },

  /** 是否為股票詳情專用 hash（不由 Tab hash 處理） */
  isStockHash(raw) {
    const r = String(
      raw != null ? raw : (location.hash || '').replace(/^#/, '')
    ).trim();
    const parts = r.split('/').filter(Boolean);
    if (parts[0] === 'stock' && parts[1]) return true;
    if (parts[0] === 'stocks' || r === 'stock-detail' || r === 'stock') return true;
    return false;
  },

  /** 從 hash 解析主 Tab id；股票路由返回 null */
  tabFromHash() {
    const raw = (location.hash || '').replace(/^#/, '').trim();
    if (!raw) return 'dashboard';
    if (this.isStockHash(raw)) return null;
    const seg = raw.split('/').filter(Boolean)[0] || '';
    if (this._tabIds && this._tabIds.has(seg)) return seg;
    return null;
  },

  /**
   * 依網址載入對應畫面。先處理股票詳情，再處理各 Tab。
   * @returns {boolean} 是否已識別並處理 hash
   */
  routeFromHash(pushTab = true) {
    const raw = (location.hash || '').replace(/^#/, '').trim();
    const seg = raw.split('/').filter(Boolean)[0] || '';
    if (this._STOCK_TOOL_TABS?.includes(seg)) {
      const code =
        (typeof StockDetail !== 'undefined' && StockDetail._code) ||
        (typeof Backtest !== 'undefined' && Backtest.getCode?.()) ||
        document.getElementById('btCode')?.value ||
        '';
      this.openStockTool(seg, code);
      return true;
    }
    if (typeof StockDetail !== 'undefined' && StockDetail.routeFromHash(pushTab)) {
      return true;
    }
    const tab = this.tabFromHash();
    if (tab) {
      this.loadTab(tab, { syncHash: false });
      return true;
    }
    if (!raw) {
      if (pushTab) this.loadTab('dashboard', { syncHash: true });
      return true;
    }
    return false;
  },

  _setTabHash(tab) {
    const hash = '#/' + tab;
    if (location.hash === hash) return;
    if (history.replaceState) {
      history.replaceState({ appTab: tab }, '', hash);
    } else {
      location.hash = hash;
    }
  },

  /** 切換 Tab 時同步網址（側欄用 replaceState，不堆疊 history） */
  _syncHashForTab(tab) {
    if (tab === 'stock-detail') {
      if (typeof StockDetail === 'undefined') return;
      const raw = (location.hash || '').replace(/^#/, '').trim();
      if (this.isStockHash(raw)) return;
      StockDetail._setHash('/stocks', false);
      return;
    }
    this._setTabHash(tab);
  },

  initTabs() {
    document.getElementById('sidebar').addEventListener('click', e => {
      const btn = e.target.closest('button[data-tab]');
      if (!btn) return;
      const tab = btn.dataset.tab;
      this.loadTab(tab);
    });
  },

  loadTab(tab, options = {}) {
    const syncHash = options.syncHash !== false;

    // 回測相關功能已併入個股詳情子 Tab
    if (this._STOCK_TOOL_TABS?.includes(tab)) {
      const code =
        (typeof Backtest !== 'undefined' && Backtest.getCode?.()) ||
        document.getElementById('btCode')?.value ||
        (typeof StockDetail !== 'undefined' ? StockDetail._code : '') ||
        '';
      this.openStockTool(tab, code);
      return;
    }

    // 同一 Tab：仍同步網址（修復停留在 #/stock/xxx 卻顯示其他 Tab）
    if (this._currentTab === tab) {
      if (syncHash) this._syncHashForTab(tab);
      return;
    }

    // 隱藏當前 tab（帶淡出動畫）
    const currentTarget = document.getElementById('tab-' + this._currentTab);
    if (currentTarget && !currentTarget.classList.contains('h')) {
      currentTarget.style.opacity = '0';
      currentTarget.style.transform = 'translateY(-4px)';
      currentTarget.style.transition = 'opacity 0.12s ease-in, transform 0.12s ease-in';
      setTimeout(() => {
        currentTarget.style.transition = '';
      }, 130);
    }

    // 隱藏所有 tab 內容（已掛載到個股頁的面板除外）
    document.querySelectorAll('[id^="tab-"]').forEach(el => {
      if (el.dataset.sdMounted === '1' || el.classList.contains('sd-embedded-tab')) return;
      el.classList.add('h');
    });

    // 顯示目標 tab
    const target = document.getElementById('tab-' + tab);
    if (target) {
      target.classList.remove('h');
      target.style.opacity = '';
      target.style.transform = '';
    }

    // 更新導航高亮
    document.querySelectorAll('.sidebar button').forEach(b => b.classList.remove('a'));
    const navBtn = document.querySelector(`.sidebar button[data-tab="${tab}"]`);
    if (navBtn) navBtn.classList.add('a');

    this._currentTab = tab;
    if (typeof LocalStore !== 'undefined') LocalStore.set('lastTab', tab);

    if (syncHash) this._syncHashForTab(tab);

    // Tab 顯示後重算圖表尺寸（避免在隱藏狀態下渲染為空白）
    if (typeof Charts !== 'undefined') {
      requestAnimationFrame(() => {
        Charts.resizeTab('tab-' + tab);
        if (typeof ProCharts !== 'undefined') ProCharts.initTab(tab);
        if (tab === 'dashboard' && typeof Dashboard !== 'undefined') {
          Dashboard.ensureCharts();
        }
      });
    }

    // 切換 tab 時停止非活躍模塊的輪詢
    if (tab !== 'dashboard' && typeof Dashboard !== 'undefined') {
      Dashboard.stopPolling();
    }
    if (tab !== 'tasks' && typeof Tasks !== 'undefined') {
      Tasks.unload();
    }
    if (tab !== 'scheduler' && typeof SchedulerTab !== 'undefined' && typeof SchedulerTab.unload === 'function') {
      SchedulerTab.unload();
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
      case 'crypto':
        if (typeof CryptoUI !== 'undefined') CryptoUI.load();
        break;
      case 'markets':
        Promise.all([this.loadMarkets(), this.loadMarketRealtime()]);
        break;
      case 'polymarket':
        if (typeof PolymarketUI !== 'undefined') PolymarketUI.load();
        break;
      case 'stock-detail':
        if (typeof StockDetail !== 'undefined') StockDetail.onTabActivated();
        break;
      case 'connectivity':
        if (typeof ConnectivityPage !== 'undefined') ConnectivityPage.load();
        break;
      case 'signals':
        if (typeof Signals !== 'undefined') Signals.load();
        break;
      case 'data':
        if (typeof Data !== 'undefined') Data.load();
        break;
      case 'heatmap':
        if (typeof Heatmap !== 'undefined') Heatmap.initTab();
        break;
      case 'compare':
        this._onCompareTab();
        break;
      case 'history':
        this._onHistoryTab();
        break;
      case 'walkforward':
        this._onWalkforwardTab();
        break;
      case 'optimize':
        this._onOptimizeTab();
        break;
      case 'analysis':
        if (typeof Analysis !== 'undefined' && typeof Analysis.onTabShow === 'function') {
          Analysis.onTabShow();
        }
        break;
      case 'screener':
        this._onScreenerTab();
        break;
      case 'reports':
        this._onReportsTab();
        break;
      case 'tasks':
        if (typeof Tasks !== 'undefined') Tasks.load();
        break;
      case 'scheduler':
        if (typeof SchedulerTab !== 'undefined' && typeof SchedulerTab.load === 'function') {
          SchedulerTab.load();
        }
        break;
      case 'backtest':
        if (typeof Backtest !== 'undefined') {
          Backtest.populateStockSelectSync?.();
          Backtest.ensureStockOptions();
        }
        break;
    }
  },

  // ============================================================
  // WebSocket
  // ============================================================

  async initWebSocket() {
    try {
      const h = await Api.getHealth();
      if (h && typeof h.ws_auth_required === 'boolean') {
        this._wsAuthRequired = h.ws_auth_required;
      }
    } catch (e) { /* ignore */ }
    this._connectWS();

    if (this._wsPingTimer) clearInterval(this._wsPingTimer);
    this._wsPingTimer = setInterval(() => {
      if (this._ws && this._ws.readyState === 1) {
        this._ws.send('ping');
      }
    }, 25000);
  },

  _setWsStatus(on, text) {
    const dot = document.getElementById('wsDot');
    if (dot) dot.className = 'ws-dot ' + (on ? 'on' : 'off');
    const sidebarDot = document.getElementById('wsDotSidebar');
    if (sidebarDot) sidebarDot.className = 'ws-dot ' + (on ? 'on' : 'off');
    const sidebarText = document.getElementById('sidebarStatusText');
    if (sidebarText && text) sidebarText.textContent = text;
  },

  _connectWS() {
    let token = localStorage.getItem('sq_token') || Api._token;
    if (token && typeof Api.isTokenExpired === 'function' && Api.isTokenExpired(token)) {
      Api.setToken(null);
      token = null;
      if (typeof Utils !== 'undefined') {
        Utils.toast('登錄已過期，請重新登錄', 3500, 'warning');
      }
      if (typeof Api.showLoginModal === 'function') Api.showLoginModal(false);
    }
    if (this._wsAuthRequired && !token) {
      this._setWsStatus(false, '需登錄');
      this._wsRetry = this._wsMaxRetry + 1;
      return;
    }

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = token
      ? `${proto}//${location.host}/ws?token=${encodeURIComponent(token)}`
      : `${proto}//${location.host}/ws`;
    if (this._ws && (this._ws.readyState === WebSocket.CONNECTING || this._ws.readyState === WebSocket.OPEN)) {
      try { this._ws.close(); } catch (_) {}
    }
    this._ws = new WebSocket(wsUrl);

    this._ws.onopen = () => {
      this._setWsStatus(true, '已連接');
      this._wsRetry = 0;
      if (typeof Tasks !== 'undefined' && typeof Tasks.rebindWs === 'function') {
        Tasks.rebindWs();
      }
    };

    this._ws.onclose = () => {
      this._setWsStatus(false);

      const cur = localStorage.getItem('sq_token') || Api._token;
      if (cur && typeof Api.isTokenExpired === 'function' && Api.isTokenExpired(cur)) {
        Api.setToken(null);
        this._setWsStatus(false, '登錄已過期');
        this._wsRetry = this._wsMaxRetry + 1;
        if (typeof Utils !== 'undefined') {
          Utils.toast('登錄已過期，請重新登錄', 3500, 'warning');
        }
        if (typeof Api.showLoginModal === 'function') Api.showLoginModal(false);
        return;
      }

      if (this._wsAuthRequired && !cur) {
        this._setWsStatus(false, '需登錄');
        return;
      }

      this._wsRetry++;
      if (this._wsRetry > this._wsMaxRetry) {
        this._setWsStatus(false, '連接失敗');
        return;
      }

      this._setWsStatus(false, '重連中...');
      const delay = Math.min(1000 * Math.pow(2, this._wsRetry), 30000);
      setTimeout(() => this._connectWS(), delay);
    };

    this._ws.onmessage = e => {
      try {
        const d = JSON.parse(e.data);
        if (d.type === 'quotes') this._updateRealtimeQuotes(d.data);
        if (d.type === 'signals') this._updateRealtimeSignals(d.data);
        // 任務面板 WS 實時更新
        if (App._taskWsHandler) App._taskWsHandler(e);
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

  _updateRealtimeSignals(_data) {
    if (this._currentTab !== 'signals' || typeof Signals === 'undefined') return;
    if (Signals._currentTab !== 'current') return;
    if (!this._signalsWsDebounce) {
      this._signalsWsDebounce = Utils.debounce(() => {
        if (typeof Signals.loadCurrent === 'function') Signals.loadCurrent();
      }, 1800);
    }
    this._signalsWsDebounce();
  },

  // ============================================================
  // Alert & Notify (shared)
  // ============================================================

  async loadAlerts() {
    const d = await Api.getAlerts(50);
    const el = document.getElementById('alertList');
    if (!el) return;

    if (d && d.alerts && d.alerts.length > 0) {
      if (typeof ProCharts !== 'undefined') ProCharts.renderAlertTrend(d.alerts);
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

  _downloadPollOptions(onProgress) {
    return { timeout: 7200000, interval: 2000, onProgress };
  },

  async downloadMarket() {
    const market = document.getElementById('dlMarket')?.value;
    const symInput = document.getElementById('dlSymbols')?.value?.trim();
    const btn = document.getElementById('dlMarketBtn');
    const body = symInput ? symInput.split(',').map(s => s.trim()) : null;
    const el = document.getElementById('dlMarketResult');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="ld"></span> 下載中...'; }
    if (el) el.innerHTML = '<div class="chip cfg">⏳ 任務已提交，下載中…</div>';
    try {
      const d = await Api.post(`/api/markets/${market}/download`, body);
      const resolved = await Api.resolveTaskResponse(d, App._downloadPollOptions((task) => {
        if (!el || typeof TaskCommon === 'undefined') return;
        const sub = TaskCommon.formatTaskSubtitle(task);
        if (sub) el.innerHTML = `<div class="chip cfg">⏳ ${sub}</div>`;
      }));
      const result = Api.extractResult(resolved);
      if (resolved?.success && result && el) {
        const line = (typeof TaskCommon !== 'undefined' && TaskCommon.downloadResultLine(result))
          || `${result.total_records || 0} 條記錄`;
        el.innerHTML = `<div class="chip on">✅ ${market} 下載完成: ${line}</div>`;
        this.loadMarkets();
        if (typeof Utils !== 'undefined') Utils.toast('下載完成，可在任務面板查看詳情', 3000, 'success');
      } else if (el) {
        const err = resolved?.task?.error || '';
        el.innerHTML = `<div class="chip off">❌ 下載失敗${err ? ': ' + err : ''}</div>`;
      }
    } catch (e) {
      if (el) el.innerHTML = `<div class="chip off">❌ 下載出錯: ${e.message}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '下載'; }
    }
  },

  async downloadAllMarkets() {
    if (Api._exclusive.has('download-all')) {
      Utils.toast('全市場下載進行中，請稍候', 2500, 'warning');
      return;
    }
    const btn = document.getElementById('dlAllBtn');
    const progress = document.getElementById('dlAllProgress');
    const statusEl = document.getElementById('dlAllStatus');
    const bar = document.getElementById('dlAllBar');
    const resultEl = document.getElementById('dlMarketResult');

    if (!confirm('將下載所有市場的股票數據（A股、美股、港股、指數、ETF、商品、加密貨幣、外匯），耗時較長，確定？')) return;

    return Api.runExclusive('download-all', async () => {
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="ld"></span> 下載中...'; }
    if (progress) progress.style.display = 'block';
    if (statusEl) statusEl.textContent = '正在下載所有市場數據，請稍候...';
    if (bar) bar.style.width = '10%';

    try {
      const d = await Api.post('/api/download-all');
      const resolved = await Api.resolveTaskResponse(d, App._downloadPollOptions((task) => {
        if (statusEl && typeof TaskCommon !== 'undefined') {
          const sub = TaskCommon.formatTaskSubtitle(task);
          if (sub) statusEl.textContent = sub;
        }
        if (bar && task?.progress) bar.style.width = Math.max(10, task.progress) + '%';
      }));
      if (bar) bar.style.width = '100%';
      const result = Api.extractResult(resolved);
      if (resolved?.success && result) {
        if (statusEl) statusEl.textContent = '下載完成！';
        if (resultEl) {
          const details = result.details || [];
          const failList = details.filter(r => r.records === 0);
          let html = `<div class="chip on">✅ 全部下載完成: ${result.total_records} 條記錄, ${result.success_symbols}/${result.total_symbols} 個標的成功</div>`;
          if (failList.length > 0) {
            html += `<div style="margin-top:6px;font-size:11px;color:var(--text-dim)">失敗: ${failList.map(r => r.code).join(', ')}</div>`;
          }
          resultEl.innerHTML = html;
        }
        this.loadMarkets();
        if (typeof Data !== 'undefined') {
          if (Data.loadUniverseStats) Data.loadUniverseStats();
          if (Data._currentTab === 'universe' && Data.searchUniverse) {
            Data.searchUniverse(Data._universeOffset || 0);
          }
        }
        if (typeof Utils !== 'undefined') {
          const ur = result.universe_refresh;
          const uniHint = ur && !ur.error
            ? `，股票庫已更新（+${ur.inserted || 0}/↻${ur.updated || 0}）`
            : '';
          Utils.toast(`全市場下載完成${uniHint}`, 3500, 'success');
        }
      } else {
        if (resultEl) resultEl.innerHTML = '<div class="chip off">❌ 下載失敗</div>';
      }
    } catch (e) {
      if (resultEl) resultEl.innerHTML = `<div class="chip off">❌ 下載出錯: ${e.message}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🚀 一鍵下載全部市場'; }
      setTimeout(() => { if (progress) progress.style.display = 'none'; }, 3000);
    }
    });
  },

  async downloadAllFromDashboard() {
    if (Api._exclusive.has('download-all')) {
      Utils.toast('全市場下載進行中，請稍候', 2500, 'warning');
      return;
    }
    const section = document.getElementById('downloadSection');
    const statusEl = document.getElementById('dlStatus');
    const bar = document.getElementById('dlBar');
    const detail = document.getElementById('dlDetail');
    const qaBtn = document.getElementById('qaDownload');

    if (!confirm('將下載全市場股票數據（A股、美股、港股、指數、ETF、商品、加密貨幣、外匯），耗時較長，確定？')) return;

    if (section) section.style.display = 'block';
    if (qaBtn) { qaBtn.disabled = true; qaBtn.style.opacity = '0.6'; }
    if (statusEl) statusEl.textContent = '正在下載全市場數據，請稍候...';
    if (bar) bar.style.width = '5%';
    if (detail) detail.textContent = '連接中...';

    return Api.runExclusive('download-all', async () => {
    try {
      const d = await Api.post('/api/download-all');
      const resolved = await Api.resolveTaskResponse(d, App._downloadPollOptions((task) => {
        if (typeof TaskCommon !== 'undefined') {
          const sub = TaskCommon.formatTaskSubtitle(task);
          if (sub && statusEl) statusEl.textContent = sub;
        }
        if (bar && task?.progress) bar.style.width = Math.max(5, task.progress) + '%';
        if (detail && typeof TaskCommon !== 'undefined') {
          const sub = TaskCommon.formatTaskSubtitle(task);
          if (sub) detail.textContent = sub;
        }
      }));
      if (bar) bar.style.width = '100%';
      const result = Api.extractResult(resolved);
      if (resolved?.success && result) {
        const details = result.details || [];
        const failList = details.filter(r => r.records === 0);
        if (statusEl) statusEl.textContent = `✅ 下載完成！共 ${(result.total_records || 0).toLocaleString()} 條記錄`;
        if (detail) {
          let txt = `${result.success_symbols}/${result.total_symbols} 個標的成功`;
          if (failList.length > 0) txt += ` | 失敗: ${failList.map(r => r.code).join(', ')}`;
          detail.textContent = txt;
        }
        if (typeof Dashboard !== 'undefined') Dashboard.load();
        if (typeof Data !== 'undefined' && Data.loadUniverseStats) {
          Data.loadUniverseStats();
          if (Data._currentTab === 'universe' && Data.searchUniverse) {
            Data.searchUniverse(Data._universeOffset || 0);
          }
        }
        const ur = result.universe_refresh;
        const uniHint = ur && !ur.error
          ? ` | 股票庫 +${ur.inserted || 0}/↻${ur.updated || 0}`
          : '';
        Utils.toast(`下載完成: ${(result.total_records || 0).toLocaleString()} 條記錄${uniHint}`);
      } else {
        if (statusEl) statusEl.textContent = '❌ 下載失敗';
      }
    } catch (e) {
      if (statusEl) statusEl.textContent = '❌ 下載出錯: ' + e.message;
    } finally {
      if (qaBtn) { qaBtn.disabled = false; qaBtn.style.opacity = '1'; }
      setTimeout(() => { if (section) section.style.display = 'none'; }, 8000);
    }
    });
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
    if (typeof ProCharts !== 'undefined') ProCharts.renderMarketRealtime(d.data);
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
    if (typeof Heatmap !== 'undefined') {
      Heatmap.bindStrategyChange();
      Heatmap.updateParams();
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
function setupScheduler() {
  if (typeof SchedulerTab !== 'undefined' && typeof SchedulerTab.setupAll === 'function') {
    SchedulerTab.setupAll();
  } else App._setupScheduler();
}
function enableScheduler() { setupScheduler(); }
function disableScheduler() {
  if (typeof SchedulerTab !== 'undefined' && typeof SchedulerTab.disableAll === 'function') {
    SchedulerTab.disableAll();
  } else App._disableScheduler();
}
function listSchedulerJobs() {
  App.loadTab('scheduler');
}
function testNotify() { App.testNotify(); }
function showAddRule() { Dashboard.showAddRule(); }
function addToWatchlist(code) { Screener.addToWatchlist(code); }
function downloadMarket() { App.downloadMarket(); }
function downloadAllMarkets() { App.downloadAllMarkets(); }
function loadMarketRealtime() { App.loadMarketRealtime(); }

// ============================================================
// Tab 進入即載入（無需手動點刷新）
// ============================================================

App._onCompareTab = function() {
  const result = document.getElementById('cmpResult');
  if (result && !result.dataset.cmpHasResult) {
    result.classList.add('h');
  }
};

App._onHistoryTab = function() {
  const tbody = document.getElementById('histTable');
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;color:var(--text-dim)"><span class="ld"></span> 載入中…</td></tr>';
  }
  this._loadHistory();
};

App._onWalkforwardTab = function() {
  const tbody = document.getElementById('wfTable');
  if (tbody && !tbody.querySelector('tr')) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-dim)">填寫參數後點「滾動窗口驗證」；結果將顯示於此</td></tr>';
  }
  const stats = document.getElementById('wfStats');
  if (stats && !stats.innerHTML.trim()) {
    stats.innerHTML = '<div class="c"><h3>提示</h3><div class="v" style="font-size:12px;color:var(--text-dim)">選擇股票與策略後執行滾動窗口分析</div></div>';
  }
};

App._onOptimizeTab = function() {
  if (!document.getElementById('optStrategy')?.options?.length || document.getElementById('optStrategy').options.length <= 1) {
    this._initStrategies();
  }
};

App._onScreenerTab = function() {
  const box = document.getElementById('scrResult');
  if (box) box.classList.remove('h');
  const tbody = document.getElementById('scrTable');
  if (tbody && !tbody.querySelector('tr')) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-dim)">勾選條件後點「開始篩選」</td></tr>';
  }
};

App._onReportsTab = async function() {
  const pre = document.getElementById('rptContent');
  const box = document.getElementById('rptResult');
  if (!pre || !box) return;
  if (!pre.textContent.trim()) {
    pre.textContent = '載入系統概覽…';
    box.classList.remove('h');
    const h = await Api.getHealth();
    if (h) {
      pre.textContent = [
        `系統概覽 · ${new Date().toLocaleString()}`,
        `版本: ${h.version || '-'}`,
        `本地標的: ${h.total_stocks ?? 0}`,
        `K 線: ${(h.total_klines ?? 0).toLocaleString()} 條`,
        `預警記錄: ${h.total_alerts ?? 0}`,
        `庫大小: ${h.db_size_mb ?? 0} MB`,
        '',
        '點「生成報告」可產出完整策略日報。',
      ].join('\n');
    } else {
      pre.textContent = '無法取得系統狀態。點「生成報告」重試。';
    }
  }
};

// ============================================================
// Compare, History, WalkForward, Reports (shared)
// ============================================================

App._runCompare = async function() {
  const codes = document.getElementById('cmpCodes').value.split(',').map(s => s.trim()).filter(Boolean);
  const days = parseInt(document.getElementById('cmpDays').value) || 250;
  const btn = document.getElementById('cmpBtn');

  if (!codes.length) {
    return Utils.toast('請輸入至少一個股票代碼', 3000, 'warning');
  }

  Utils.btnLoading(btn, true, '對比中...');
  const d = await Api.compareStocks(codes, days);
  Utils.btnLoading(btn, false, '對比');

  if (!d) return;

  const comp = d.comparison || {};
  const series = [];
  for (const [code, v] of Object.entries(comp)) {
    if (v?.relative_return?.length) {
      const relLabel = (typeof SignalLabels !== 'undefined')
        ? `${code} ${SignalLabels.strategyName(code, 'short')}`
        : code;
      series.push({ label: relLabel, data: v.relative_return, dates: v.dates });
    }
  }

  if (series.length) {
    if (typeof ProCharts !== 'undefined') ProCharts.renderCompare(series);
    else Charts.drawLineChart('cmpChart', series);
    const cmpResult = document.getElementById('cmpResult');
    if (cmpResult) {
      cmpResult.classList.remove('h');
      cmpResult.dataset.cmpHasResult = '1';
    }
    if (d.missing?.length) {
      Utils.toast(`已載入 ${series.length} 只；無本地數據: ${d.missing.join(', ')}`, 5000, 'warning');
    }
  } else {
    const hint = d.missing?.length
      ? `無本地 K 線: ${d.missing.join(', ')}。請先在「數據」頁下載對應股票。`
      : '無可比對數據，請先在「數據」頁下載股票歷史數據。';
    Utils.toast(hint, 6000, 'warning');
  }
};

App._loadHistory = async function() {
  const code = document.getElementById('histCode')?.value?.trim() || '';
  const strategy = document.getElementById('histStrategy')?.value?.trim() || '';

  const d = await Api.getBacktestHistory(code, strategy, 100);
  if (!d) return;

  const rows = d.results || [];
  const stratLabel = (s) => (typeof SignalLabels !== 'undefined')
    ? SignalLabels.strategyName(s, 'short') : s;
  document.getElementById('histTable').innerHTML = rows.map(r =>
    `<tr class="hist-row" data-id="${r.id}">
      <td>${r.id}</td>
      <td>${r.code}</td>
      <td>${stratLabel(r.strategy)}</td>
      <td class="r"><span class="b ${Utils.badgeClass(r.total_return_pct)}">${Utils.formatPct(r.total_return_pct)}</span></td>
      <td class="r">${Utils.formatNum(r.sharpe_ratio, 2)}</td>
      <td class="r">${Utils.formatNum(r.sortino_ratio, 2)}</td>
      <td class="r">${Utils.formatNum(r.calmar_ratio, 2)}</td>
      <td class="r">${Utils.formatPct(-r.max_drawdown_pct)}</td>
      <td class="r">${Utils.formatNum(r.var_95, 4)}</td>
      <td class="r">${Utils.formatNum(r.win_rate_pct, 1)}%</td>
      <td class="r">${r.total_trades || 0}</td>
      <td style="font-size:10px;color:var(--text-dim)">${r.created_at || ''}</td>
      <td><button type="button" class="btn s hist-view-btn" data-id="${r.id}">查看</button></td>
    </tr>`
  ).join('') || '<tr><td colspan="13" style="color:var(--text-muted);text-align:center">暫無回測歷史</td></tr>';

  document.getElementById('histTable')?.querySelectorAll('.hist-view-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const id = btn.dataset.id;
      if (typeof Backtest !== 'undefined' && Backtest.showFromHistoryId) {
        Backtest.showFromHistoryId(id);
      }
    });
  });
  document.getElementById('histTable')?.querySelectorAll('.hist-row').forEach(row => {
    row.addEventListener('dblclick', () => {
      const id = row.dataset.id;
      if (id && typeof Backtest !== 'undefined') Backtest.showFromHistoryId(id);
    });
  });

  if (typeof ProCharts !== 'undefined') ProCharts.renderHistoryAnalytics(rows);
};

App.renderWalkForwardResult = function(r) {
  if (!r) return;
  document.getElementById('wfStats').innerHTML = `
    <div class="c"><h3>窗口數</h3><div class="v bl">${r.n_windows}</div></div>
    <div class="c"><h3>平均樣本外收益</h3><div class="v ${Utils.badgeClass(r.avg_oos_return_pct)}">${Utils.formatPct(r.avg_oos_return_pct)}</div></div>
    <div class="c"><h3>平均樣本外夏普</h3><div class="v">${Utils.formatNum(r.avg_oos_sharpe, 4)}</div></div>
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

  if (typeof ProCharts !== 'undefined') ProCharts.renderWalkForward(wins);
  else {
    const oosReturns = wins.map(w => w.test_return_pct);
    const oosLabels = wins.map(w => '窗口 ' + w.window);
    Charts.drawBarChart('wfChart', oosReturns, oosLabels, '樣本外收益率 (%)');
  }

  document.getElementById('wfResult').classList.remove('h');
  Utils.toast('滾動窗口驗證完成', 3000, 'success');
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

  try {
    if (d.is_duplicate) {
      Utils.toast('⏳ ' + (d.message || '相同分析執行中，等待完成...'), 3000, 'warning');
    } else if (d.async && d.task_id) {
      Utils.toast('📋 滾動窗口驗證已提交', 2000, 'info');
    }
    const resolved = await Api.resolveTaskResponse(d);
    const r = resolved?.result || resolved?.task?.result;
    if (!r) {
      Utils.toast('未取得分析結果', 3000, 'error');
      return;
    }
    App.renderWalkForwardResult(r);
  } catch (e) {
    Utils.toast('滾動窗口驗證失敗: ' + (e.message || e), 3000, 'error');
  }
};

App._generateReport = async function() {
  const btn = document.getElementById('rptBtn');
  Utils.btnLoading(btn, true, '生成中...');

  try {
    const codes = ['000001', '600519', '000858'];
    let report = '📊 每日策略報告\n' + new Date().toLocaleString('zh-CN') + '\n' + '='.repeat(40) + '\n\n';
    const perfItems = [];

    for (const code of codes) {
      try {
        const d = await Api.runBacktest({ code, strategy: 'dual_ma' });
        if (d && d.success) {
          const resolved = await Api.resolveTaskResponse(d);
          const r = Api.extractResult(resolved);
          if (!r) continue;
          perfItems.push({
            code,
            sharpe: r.sharpe_ratio,
            return_pct: r.total_return_pct,
          });
          report += `🏆 ${code}: dual_ma | 夏普 ${r.sharpe_ratio?.toFixed(2)} | 收益 ${r.total_return_pct?.toFixed(2)}% | 回撤 ${r.max_drawdown_pct?.toFixed(1)}%\n`;
        }
      } catch {}
    }

    report += '\n' + '='.repeat(40);
    document.getElementById('rptContent').textContent = report;
    document.getElementById('rptResult').classList.remove('h');
    if (perfItems.length && typeof ProCharts !== 'undefined') {
      ProCharts.renderReportPerf(perfItems);
    }
  } catch {}

  Utils.btnLoading(btn, false, '生成報告');
};

App._setupScheduler = async function() {
  if (typeof SchedulerTab !== 'undefined' && typeof SchedulerTab.setupAll === 'function') {
    await SchedulerTab.setupAll();
    return;
  }
  const d = await Api.setupScheduler();
  if (d) Utils.toast(d.message || '定時任務已註冊', 3000, 'success');
};

App._enableScheduler = App._setupScheduler;

App._disableScheduler = async function() {
  const d = await Api.disableScheduler();
  if (d) Utils.toast(d.message || '已禁用');
};

App._listSchedulerJobs = async function() {
  if (!document.getElementById('jobsList')) {
    if (typeof SchedulerTab !== 'undefined') {
      App.loadTab('scheduler');
      return;
    }
    return;
  }
  const d = await Api.getSchedulerCatalog();
  if (!d) return;

  const catalog = d.catalog || [];
  const jobs = d.jobs || [];
  const jobMap = Object.fromEntries(jobs.map(j => [j.id, j]));
  const el = document.getElementById('jobsList');
  if (!el) return;

  if (catalog.length) {
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>任務</th><th>計劃</th><th>狀態</th><th>下次執行</th><th>操作</th></tr></thead>
      <tbody>${catalog.map(c => {
        const j = jobMap[c.id];
        const status = c.enabled ? '<span style="color:#22c55e">已啟用</span>' : '<span style="color:var(--text-dim)">未啟用</span>';
        return `<tr>
          <td><strong>${c.name}</strong><br><span style="font-size:10px;color:var(--text-dim)">${c.id}</span></td>
          <td style="font-size:11px">${c.schedule}</td>
          <td>${status}</td>
          <td style="font-size:11px">${j?.next_run || '-'}</td>
          <td style="white-space:nowrap">
            <button class="btn s" style="padding:2px 6px;font-size:10px" onclick="App._runSchedulerJob('${c.id}')">執行</button>
            ${c.enabled
              ? `<button class="btn s" style="padding:2px 6px;font-size:10px" onclick="App._disableSchedulerJob('${c.id}')">禁用</button>`
              : `<button class="btn s" style="padding:2px 6px;font-size:10px" onclick="App._enableSchedulerJob('${c.id}')">啟用</button>`}
          </td>
        </tr>`;
      }).join('')}</tbody>
    </table></div>
    <p style="font-size:11px;color:var(--text-dim);margin-top:8px">啟動服務時 SQ_SCHEDULER_AUTO_REGISTER=true 會自動註冊</p>`;
  } else {
    el.innerHTML = '<p style="color:var(--text-muted)">無任務目錄</p>';
  }

  document.getElementById('schedulerJobs').classList.remove('h');
};

App._runSchedulerJob = async function(jobId) {
  const d = await Api.runSchedulerJob(jobId);
  if (d) Utils.toast(d.message || '已觸發', 2000, 'success');
};

App._enableSchedulerJob = async function(jobId) {
  const d = await Api.enableSchedulerJob(jobId);
  if (d) { Utils.toast(d.message || '已啟用', 2000, 'success'); App._listSchedulerJobs(); }
};

App._disableSchedulerJob = async function(jobId) {
  const d = await Api.disableSchedulerJob(jobId);
  if (d) { Utils.toast(d.message || '已禁用', 2000, 'success'); App._listSchedulerJobs(); }
};

// ============================================================
// Task Panel — 任務面板（防止重複執行）
// ============================================================

App._pauseTaskPoll = false;
App._lastPolledCompletedId = sessionStorage.getItem('lastSeenCompletedId') || '';

/** 任務完成通知去重（Tasks Tab 與浮動面板共用） */
App.markTaskCompletedSeen = function(recent) {
  if (!recent?.task_id) return false;
  const id = recent.task_id;
  const prev = App._lastPolledCompletedId || sessionStorage.getItem('lastSeenCompletedId') || '';
  if (prev === id) return false;
  App._lastPolledCompletedId = id;
  sessionStorage.setItem('lastSeenCompletedId', id);
  return true;
};

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
        <button onclick="App.loadTab('tasks')" style="background:none;border:1px solid var(--border-color);color:var(--accent,#38bdf8);cursor:pointer;font-size:10px;padding:2px 8px;border-radius:4px;margin-right:4px">查看全部</button>
        <button onclick="App._refreshTasks()" style="background:none;border:none;color:var(--text-dim,#94a3b8);cursor:pointer;font-size:14px;padding:2px 6px" title="刷新">🔄</button>
        <button onclick="App.toggleTaskPanel()" style="background:none;border:none;color:var(--text-dim,#94a3b8);cursor:pointer;font-size:14px;padding:2px 6px">✕</button>
      </div>
    </div>
    <div id="taskPanelQueue" style="padding:8px;border-bottom:1px solid var(--border-color,#334155)"></div>
    <div id="taskPanelList" style="max-height:220px;overflow-y:auto;padding:8px"></div>`;
  document.body.appendChild(panel);
  // Header 任務指示器
  const indicator = document.createElement('div');
  indicator.id = 'taskIndicator';
  indicator.style.cssText = 'display:none;cursor:pointer;font-size:11px;padding:4px 8px;border-radius:4px;background:var(--bg-primary);border:1px solid var(--border-color);margin-left:8px';
  indicator.onclick = () => App.toggleTaskPanel();
  indicator.innerHTML = '⏳ <span id="taskIndicatorCount">0</span>';
  const hdrRight = document.querySelector('.hdr-right');
  if (hdrRight) hdrRight.insertBefore(indicator, hdrRight.firstChild);

  // WS 實時更新浮動面板（帶去抖，避免與輪詢重複觸發）
  App._taskWsHandler = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (!data || !data.type || !data.type.startsWith('task_')) return;
      // 去抖：如果 2 秒內已觸發過輪詢，跳過
      const now = Date.now();
      if (App._lastTaskPollAt && (now - App._lastTaskPollAt) < 2000) return;
      App._lastTaskPollAt = now;
      App._pollTasks();
    } catch (_) {}
  };

  App._taskPollTimer = setInterval(() => App._pollTasks(), 8000);
};

App.toggleTaskPanel = function() {
  const panel = document.getElementById('taskPanel');
  if (!panel) return;
  const isVisible = panel.style.display !== 'none';
  panel.style.display = isVisible ? 'none' : 'block';
  if (!isVisible) App._refreshTasks();
};

App._pollTasks = async function() {
  if (App._pauseTaskPoll) return;
  const panel = document.getElementById('taskPanel');
  const panelOpen = panel && panel.style.display !== 'none';
  const onTasksTab = App._currentTab === 'tasks';
  if (!panelOpen && !onTasksTab) return;
  App._lastTaskPollAt = Date.now();
  try {
    const q = await Api.getTaskQueue({ silent: true });
    if (!q || q._rateLimited) return;
    const stats = q.stats || {};
    const active = (stats.running || 0) + (stats.pending || 0);
    const indicator = document.getElementById('taskIndicator');
    const countEl = document.getElementById('taskIndicatorCount');
    if (indicator) {
      indicator.style.display = active > 0 ? 'inline-block' : 'none';
      if (countEl) countEl.textContent = active;
    }
    if (typeof Tasks !== 'undefined' && Tasks._updateNavBadge) {
      Tasks._updateNavBadge(stats);
    }
    const recent = q.recent_completed;
    if (recent?.task_id && App.markTaskCompletedSeen(recent)) {
      Utils.toast('✅ 任務完成: ' + (recent.title || ''), 3500, 'success');
      const panel = document.getElementById('taskPanel');
      if (panel && panel.style.display === 'none') {
        panel.style.display = 'block';
      }
    }
    const queueEl = document.getElementById('taskPanelQueue');
    if (queueEl && typeof TaskCommon !== 'undefined') {
      queueEl.innerHTML = TaskCommon.renderQueueSection(q, true);
    }
  } catch {}
};

App._refreshTasks = async function() {
  const container = document.getElementById('taskPanelList');
  const queueEl = document.getElementById('taskPanelQueue');
  if (!container) return;
  container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-dim)"><span class="ld"></span> 載入中...</div>';

  const d = await Api.getTasks(null, null, 30, { silent: true });
  const q = d?.queue || await Api.getTaskQueue({ silent: true });
  if (queueEl && q && !q._rateLimited && typeof TaskCommon !== 'undefined') {
    queueEl.innerHTML = TaskCommon.renderQueueSection(q, true);
  }

  if (!d || d._rateLimited) {
    container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-dim)">任務載入中或請稍後重試…</div>';
    return;
  }
  if (!d.tasks || !d.tasks.length) {
    container.innerHTML = `
      <div style="padding:20px;text-align:center;color:var(--text-dim)">
        <div style="font-size:24px;margin-bottom:8px">📋</div>
        <div>暫無任務</div>
        <button class="btn s" style="margin-top:8px;font-size:11px" onclick="App.loadTab('tasks');App.toggleTaskPanel()">前往任務面板</button>
      </div>`;
    return;
  }

  if (typeof TaskCommon === 'undefined') {
    container.innerHTML = '<div style="padding:12px;color:var(--text-dim)">任務模塊載入中…</div>';
    return;
  }
  const TC = TaskCommon;

  // 統計摘要
  const stats = d.stats || {};
  const statsHtml = `
    <div style="display:flex;gap:12px;padding:8px 4px;margin-bottom:8px;border-bottom:1px solid var(--border-color,#334155);font-size:11px;color:var(--text-dim,#64748b)">
      <span>📋 總計 ${stats.total || 0}</span>
      <span style="color:#f59e0b">⏸️ 等待 ${stats.pending || 0}</span>
      <span style="color:#38bdf8">⏳ 運行 ${stats.running || 0}</span>
      <span style="color:#22c55e">✅ 完成 ${stats.completed || 0}</span>
      <span style="color:#ef4444">❌ 失敗 ${stats.failed || 0}</span>
    </div>`;

  const statusIcons = TC.STATUS_ICONS;
  const statusColors = TC.STATUS_COLORS;
  const typeNameMap = TC.TYPE_NAMES;

  container.innerHTML = statsHtml + d.tasks.map(t => {
    const typeName = typeNameMap[t.task_type] || t.task_type;
    const canViewResult = t.status === 'completed' && t.has_result;
    const elapsed = TC.elapsed(t.started_at || t.created_at, t.completed_at);
    const elapsedStr = TC.formatElapsed(elapsed);
    return `
    <div style="display:flex;align-items:center;gap:8px;padding:8px;margin-bottom:4px;background:var(--bg-primary,#0f172a);border-radius:8px;border:1px solid var(--border-color,#334155);${canViewResult ? 'cursor:pointer' : ''}" ${canViewResult ? `onclick="App._viewTaskResult('${t.task_id}')"` : ''}>
      <span style="font-size:16px">${statusIcons[t.status] || '❓'}</span>
      <div style="flex:1;min-width:0">
        <div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${t.title || t.task_type}</div>
        <div style="font-size:10px;color:var(--text-dim,#64748b);margin-top:2px">${typeName} · ${elapsedStr ? '⏱' + elapsedStr + ' · ' : ''}${Utils.timeAgo(t.created_at)}</div>
        ${t.error ? `<div style="font-size:10px;color:#ef4444;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">⚠ ${String(t.error).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>` : ''}
      </div>
      <div style="display:flex;align-items:center;gap:4px">
        <span style="color:${statusColors[t.status] || '#94a3b8'};font-size:11px;font-weight:600">${
          t.status === 'running' ? t.progress + '%' : (t.status === 'completed' && t.has_result ? '查看' : t.status)
        }</span>
        ${(t.status === 'running' || t.status === 'pending') ? `<button onclick="event.stopPropagation();App._cancelTask('${t.task_id}')" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:12px;padding:2px 4px" title="取消">✕</button>` : ''}
        ${canViewResult ? `<button onclick="event.stopPropagation();TaskCommon.navigateToResult('${t.task_id}')" style="background:none;border:1px solid var(--accent);color:var(--accent);cursor:pointer;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:4px">前往</button>` : ''}
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
  const typeName = TaskCommon.typeName(task.task_type);

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
        <div class="c"><h3>索提諾比率</h3><div class="v">${Utils.formatNum(r.sortino_ratio, 4)}</div></div>
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
    const pm = (r && (r.portfolio || r.pm)) || r;
    const tr = pm.total_return_pct ?? r.total_return_pct ?? 0;
    const sh = pm.sharpe_ratio ?? r.sharpe_ratio ?? 0;
    const dd = pm.max_drawdown_pct ?? r.max_drawdown_pct ?? 0;
    content = `
      <h3>${typeName}結果 — ${task.title}</h3>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0">
        <div class="c"><h3>收益率</h3><div class="v ${(tr || 0) >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(tr)}</div></div>
        <div class="c"><h3>夏普比率</h3><div class="v">${Utils.formatNum(sh, 4)}</div></div>
        <div class="c"><h3>最大回撤</h3><div class="v rd">${Utils.formatPct(-dd)}</div></div>
      </div>
      <div style="margin-top:8px">
        <button class="btn s" onclick="Utils.closeModal();App.loadTab('portfolio')">📈 前往組合頁</button>
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
  if (typeof App !== 'undefined' && App.openStockTool) {
    App.openStockTool('backtest', r.code || '');
  }

  // 將結果填充到 Backtest 對象
  if (typeof Backtest !== 'undefined') {
    Backtest._lastResult = r;
    // 設置股票代碼
    if (Backtest.setCode) Backtest.setCode(r.code || '');
    // 顯示結果
    if (Backtest.showResult) {
      Backtest.showResult(r);
    } else if (Backtest._displayResult) {
      Backtest._displayResult(r);
      Backtest._finishDisplay?.();
    }
  }
};

// ============================================================
// Boot
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
  if (typeof Utils !== 'undefined' && Utils.loadIconfontConfig) {
    Utils.loadIconfontConfig();
  }
  // Pro 工作站（/app）由 StockQPro.App 接管導航；legacy 模組僅掛載片段
  if (window.StockQPro?.App && document.getElementById('pg-dashboard')) {
    return;
  }
  App.init();
});

window.addEventListener('load', () => {
  if (typeof Charts === 'undefined') return;
  const tab = App._currentTab || 'dashboard';
  Charts.resizeTab('tab-' + tab);
  if (tab === 'dashboard' && typeof Dashboard !== 'undefined') {
    Dashboard.ensureCharts();
  }
});
