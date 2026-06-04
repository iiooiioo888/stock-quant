/**
 * utils.js — 工具函數
 */

const Utils = {
  /**
   * 顯示 Toast 通知
   * @param {string} msg - 訊息
   * @param {number} duration - 持續時間 (ms)
   * @param {'info'|'success'|'error'} variant - 樣式變體
   */
  toast(msg, duration = 3000, variant = 'info') {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.className = variant;  // info=default, success=green, error=red
    el.style.display = 'block';
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { el.style.display = 'none'; }, duration);
  },

  /**
   * 自定義確認對話框 — 替代原生 confirm()
   * @param {string} msg  提示文字
   * @param {object} opts  { okText, cancelText, variant }
   * @returns {Promise<boolean>}
   */
  confirm(msg, opts = {}) {
    const { okText = '確定', cancelText = '取消', variant = 'warning' } = opts;
    return new Promise(resolve => {
      const ov = document.createElement('div');
      ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.55);backdrop-filter:blur(4px);z-index:9999;display:flex;align-items:center;justify-content:center;animation:mi .18s ease';
      const box = document.createElement('div');
      box.style.cssText = 'background:var(--bg1,#1e1e2e);border:1px solid var(--bf,#333);border-radius:12px;padding:24px 28px;max-width:420px;width:90vw;box-shadow:0 12px 48px rgba(0,0,0,.5);color:var(--text,#e0e0e0);font-size:14px;line-height:1.6';
      const icon = variant === 'danger' ? '🗑️' : variant === 'warning' ? '⚠️' : 'ℹ️';
      box.innerHTML = `<div style="margin-bottom:20px;white-space:pre-wrap">${icon} ${Utils.escapeHtml ? Utils.escapeHtml(msg) : msg}</div>` +
        '<div style="display:flex;gap:10px;justify-content:flex-end">' +
        `<button data-c="0" style="padding:8px 20px;border-radius:8px;border:1px solid var(--bf,#444);background:transparent;color:var(--text,#ccc);cursor:pointer;font-size:13px">${cancelText}</button>` +
        `<button data-c="1" style="padding:8px 20px;border-radius:8px;border:none;background:var(--accent,#3b82f6);color:#fff;cursor:pointer;font-size:13px;font-weight:600">${okText}</button>` +
        '</div>';
      ov.appendChild(box);
      document.body.appendChild(ov);
      const done = (val) => { ov.remove(); resolve(val); };
      ov.addEventListener('click', e => { if (e.target === ov) done(false); });
      box.addEventListener('click', e => {
        const btn = e.target.closest('button');
        if (btn) done(btn.dataset.c === '1');
      });
      const onKey = e => { if (e.key === 'Escape') { document.removeEventListener('keydown', onKey); done(false); } };
      document.addEventListener('keydown', onKey);
      box.querySelector('[data-c="1"]').focus();
    });
  },

  /**
   * 格式化百分比
   */
  formatPct(v) {
    if (v == null) return 'N/A';
    return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
  },

  /**
   * 格式化數字
   */
  formatNum(v, d = 2) {
    if (v == null) return 'N/A';
    return v.toFixed(d);
  },

  /**
   * 格式化大數字 (萬/億)
   */
  formatLargeNum(v) {
    if (v == null) return 'N/A';
    if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + '億';
    if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + '萬';
    return v.toLocaleString();
  },

  /**
   * 創建帶幫助提示的文字
   */
  helpTip(text, tip) {
    return `<span class="tooltip-help" title="${tip}">${text} ⓘ</span>`;
  },

  /**
   * 格式化為友好時間差
   */
  timeAgo(dateStr) {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return '剛剛';
    if (mins < 60) return mins + ' 分鐘前';
    const hours = Math.floor(mins / 60);
    if (hours < 24) return hours + ' 小時前';
    const days = Math.floor(hours / 24);
    return days + ' 天前';
  },

  /**
   * 獲取漲跌 CSS class
   */
  badgeClass(v) {
    if (v > 0.01) return 'u';
    if (v < -0.01) return 'd';
    return 'f';
  },

  /**
   * 設置按鈕載入狀態
   */
  btnLoading(btn, loading, text = '') {
    if (!btn) return;
    if (loading) {
      btn.disabled = true;
      btn._originalText = btn.textContent;
      btn.innerHTML = '<span class="ld"></span> ' + (text || '載入中...');
    } else {
      btn.disabled = false;
      btn.textContent = text || btn._originalText || '確定';
    }
  },

  /**
   * 統一 Tabs / 子Tabs 操作邏輯
   *
   * - tabsEl：tab 按鈕容器
   * - btnSelector：按鈕 selector（需帶 data-* key）
   * - keyAttr：data attribute key（例如 'dtab' / 'stab'）
   * - panelPrefix：面板 id 前綴（例如 'dtab-' / 'stab-'）
   * - activeClass：啟用樣式 class（預設 'a'）
   * - hiddenClass：隱藏樣式 class（預設 'h'）
   * - onTab：tab 切換後回呼 (key, { initial })
   *
   * 回傳 controller：{ getKey, setKey, refresh }
   */
  bindTabs({
    tabsEl,
    btnSelector = 'button',
    keyAttr,
    panelPrefix = '',
    activeClass = 'a',
    hiddenClass = 'h',
    defaultKey = '',
    onTab = null,
  }) {
    if (!tabsEl || !keyAttr) return null;
    if (tabsEl.dataset.tabBound === '1') return tabsEl._tabController || null;
    tabsEl.dataset.tabBound = '1';

    const getButtons = () => [...tabsEl.querySelectorAll(btnSelector)]
      .filter(b => b && b.dataset && b.dataset[keyAttr] != null);

    const setActiveBtn = (key) => {
      getButtons().forEach(b => {
        const on = String(b.dataset[keyAttr]) === String(key);
        b.classList.toggle(activeClass, on);
        if (b.hasAttribute('role')) {
          b.setAttribute('aria-selected', on ? 'true' : 'false');
        }
      });
    };

    const applyPanels = (key) => {
      if (!panelPrefix) return;
      const panels = document.querySelectorAll(`[id^="${panelPrefix}"]`);
      panels.forEach(p => {
        const pKey = String(p.id || '').replace(panelPrefix, '');
        p.classList.toggle(hiddenClass, pKey !== String(key));
      });
    };

    const controller = {
      _key: defaultKey,
      getKey() { return this._key; },
      setKey(key, { initial = false } = {}) {
        const k = String(key || '').trim() || defaultKey;
        if (!k) return;
        this._key = k;
        setActiveBtn(k);
        applyPanels(k);
        if (typeof onTab === 'function') onTab(k, { initial });
      },
      refresh() {
        this.setKey(this._key || defaultKey, { initial: true });
      },
    };

    // initial key: 優先取目前已標記 activeClass 的按鈕，否則 defaultKey，否則第一個
    const btns = getButtons();
    const activeBtn = btns.find(b => b.classList.contains(activeClass));
    const initKey = activeBtn?.dataset?.[keyAttr] || defaultKey || btns[0]?.dataset?.[keyAttr] || '';
    controller._key = String(initKey || '').trim();

    tabsEl.addEventListener('click', (e) => {
      const btn = e.target.closest(btnSelector);
      if (!btn || btn.dataset[keyAttr] == null) return;
      controller.setKey(btn.dataset[keyAttr], { initial: false });
    });

    tabsEl._tabController = controller;
    controller.refresh();
    return controller;
  },

  /**
   * 統一容器狀態輸出：loading / empty / error
   */
  setState(container, { kind, title, detail } = {}) {
    if (!container) return;
    const t = title ? String(title) : '';
    const d = detail ? String(detail) : '';
    if (kind === 'loading') {
      container.innerHTML = `<div class="state-loading"><span class="ld"></span> ${t || '載入中…'}</div>`;
      return;
    }
    if (kind === 'empty') {
      container.innerHTML = `<div class="state-empty"><span class="state-icon">📭</span><span class="state-text">${t || '暫無資料'}</span>${d ? `<div class="state-sub">${d}</div>` : ''}</div>`;
      return;
    }
    if (kind === 'error') {
      container.innerHTML = `<div class="state-empty"><span class="state-icon">❌</span><span class="state-text">${t || '載入失敗'}</span>${d ? `<div class="state-sub">${d}</div>` : ''}</div>`;
      return;
    }
  },

  /**
   * 關閉 Modal
   */
  closeModal() {
    const el = document.getElementById('modalRoot');
    if (el) el.innerHTML = '';
  },

  /**
   * 顯示 Modal
   */
  showModal(html) {
    const el = document.getElementById('modalRoot');
    if (el) {
      el.innerHTML = `<div class="modal" onclick="if(event.target===this)Utils.closeModal()">
        <div class="modal-c">${html}</div>
      </div>`;
    }
  },

  /**
   * 複製文字到剪貼板
   */
  async copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      this.toast('已複製');
    } catch {
      this.toast('複製失敗');
    }
  },

  /**
   * 防抖
   */
  debounce(fn, delay = 300) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  },

  /**
   * 按 key 互斥執行異步操作（防雙擊、合併進行中請求）
   */
  async withActionLock(key, fn, { btn, loadingText } = {}) {
    if (!this._actionLocks) this._actionLocks = new Map();
    if (this._actionLocks.has(key)) return this._actionLocks.get(key);
    if (btn) this.btnLoading(btn, true, loadingText || '處理中...');
    const p = Promise.resolve().then(fn).finally(() => {
      this._actionLocks.delete(key);
      if (btn) this.btnLoading(btn, false);
    });
    this._actionLocks.set(key, p);
    return p;
  },

  /**
   * 驗證股票代碼格式
   */
  isValidCode(code) {
    if (!code) return false;
    code = code.trim();
    // A 股: 6 位數字
    if (/^\d{6}$/.test(code)) return true;
    // 加密貨幣: XXXUSDT
    if (/^[A-Z]+USDT$/i.test(code)) return true;
    // 外匯: 6 字母
    if (/^[A-Z]{6}$/i.test(code)) return true;
    // 全球: 字母/帶後綴
    if (/^[A-Z0-9.^=]+$/i.test(code)) return true;
    return false;
  },

  /**
   * 驗證並提示（返回驗證過的代碼列表）
   */
  validateCodes(input, fieldName = '股票代碼') {
    const codes = input.split(',').map(s => s.trim()).filter(Boolean);
    if (!codes.length) {
      this.toast(`請輸入${fieldName}`, 3000, 'error');
      return null;
    }
    const invalid = codes.filter(c => !this.isValidCode(c));
    if (invalid.length) {
      this.toast(`無效代碼: ${invalid.join(', ')}`, 3000, 'error');
      return null;
    }
    return codes;
  },

  /**
   * 格式化日期 YYYY-MM-DD → MM-DD
   */
  shortDate(dateStr) {
    if (!dateStr) return '';
    return dateStr.length > 5 ? dateStr.substring(5) : dateStr;
  },

  /**
   * 當前日期 YYYY-MM-DD
   */
  today() {
    return new Date().toISOString().split('T')[0];
  },

  /** A 股市場前綴（滬 SH / 深 SZ） */
  stockMarketPrefix(code) {
    const c = String(code || '').trim().padStart(6, '0').slice(-6);
    if (/^(5|6|9)/.test(c)) return 'SH';
    return 'SZ';
  },

  /** 推斷市場（5 位數為港股，6 位為 A 股，字母為美股） */
  inferStockMarket(code, market = '') {
    const m = String(market || '').trim().toLowerCase();
    if (m.includes('hk')) return 'hk_stock';
    if (m.includes('us')) return 'us_stock';
    if (m === 'sh' || m === 'sz' || m === 'a_share' || m === 'a') return 'a_share';
    if (m) return m;

    const raw = String(code || '').trim().toUpperCase();
    if (/^\d{5}$/.test(raw)) return 'hk_stock';
    const digits = raw.replace(/\D/g, '');
    if (digits.length === 6 || /^\d{6}$/.test(raw)) return 'a_share';
    if (/^[A-Z][A-Z0-9.-]{0,9}$/.test(raw) && !/^\d+$/.test(raw)) return 'us_stock';
    return 'a_share';
  },

  _stockLogoConfigEnabled: undefined,

  /** 是否請求 /api/stock-logo（預設關閉，僅顯示本地 SVG；設 sq_remote_stock_icons=1 強制開啟） */
  stockLogoRemoteEnabled() {
    const ls = localStorage.getItem('sq_remote_stock_icons');
    if (ls === '1') return true;
    if (ls === '0') return false;
    if (this._stockLogoConfigEnabled === false) return false;
    if (this._stockLogoConfigEnabled === true) return true;
    return false;
  },

  /** 由 GET /api/config 同步（App 啟動時可呼叫） */
  applyStockLogoConfig(enabled) {
    this._stockLogoConfigEnabled = enabled === true;
  },

  _iconfontConfig: undefined,
  _iconfontScriptLoaded: false,
  _logoQueue: [],
  _logoActive: 0,
  /** 與 stream-loader 一致：避免列表滾動時打滿 /api/stock-logo */
  _logoMaxConcurrent: 2,
  _logoPendingKeys: new Set(),
  /** key -> objectUrl（虛擬列表重繪時重用，不再重複 fetch） */
  _logoHitUrls: new Map(),
  /** key -> 毫秒時間戳，在此之前視為 miss 不再請求 */
  _logoMissUntil: new Map(),
  _logoRetryTimers: new Map(),
  _LOGO_HIT_CAP: 400,
  _LOGO_MISS_TTL_MS: 6 * 60 * 60 * 1000,

  /** 載入 [iconfont.cn](https://www.iconfont.cn/) 專案設定與 Symbol JS */
  async loadIconfontConfig() {
    if (this._iconfontConfig !== undefined) return this._iconfontConfig;
    try {
      const r = await fetch('/api/iconfont/config', { credentials: 'same-origin' });
      this._iconfontConfig = r.ok ? await r.json() : { enabled: false };
    } catch {
      this._iconfontConfig = { enabled: false };
    }
    if (this._iconfontConfig?.enabled && this._iconfontConfig.symbol_js_url) {
      this._injectIconfontSymbolJs(this._iconfontConfig.symbol_js_url);
    }
    return this._iconfontConfig;
  },

  _injectIconfontSymbolJs(url) {
    if (this._iconfontScriptLoaded || !url) return;
    let src = String(url).trim();
    if (src.startsWith('//')) src = `https:${src}`;
    const existing = document.querySelector(`script[data-sq-iconfont="${src}"]`);
    if (existing) {
      this._iconfontScriptLoaded = true;
      return;
    }
    const s = document.createElement('script');
    s.src = src;
    s.async = true;
    s.dataset.sqIconfont = src;
    s.onload = () => document.dispatchEvent(new Event('sq-iconfont-ready'));
    s.onerror = () => document.dispatchEvent(new Event('sq-iconfont-ready'));
    document.head.appendChild(s);
    this._iconfontScriptLoaded = true;
  },

  stockIconfontSymbolId(code, name = '') {
    const cfg = this._iconfontConfig;
    if (!cfg?.enabled || !cfg.stock_icons) return '';
    const c = String(code || '').trim().toUpperCase();
    const map = cfg.stock_icons;
    if (c && map[c]) return map[c];
    const c6 = c.replace(/\D/g, '').padStart(6, '0').slice(-6);
    if (/^\d{6}$/.test(c6) && map[c6]) return map[c6];
    const n = String(name || '').trim();
    if (n && map[n]) return map[n];
    return '';
  },

  stockIconfontUseHtml(code, name = '', size = 28) {
    const sym = this.stockIconfontSymbolId(code, name);
    if (!sym) return '';
    const px = Math.max(20, Number(size) || 28);
    return `<svg class="stock-iconfont-use" width="${px}" height="${px}" aria-hidden="true">
      <use href="#${this._escAttr(sym)}" xlink:href="#${this._escAttr(sym)}"></use>
    </svg>`;
  },

  /** TradingView symbol slug，用於 s3-symbol-logo CDN */
  stockTradingViewLogoId(code, market = '') {
    const raw = String(code || '').trim().toUpperCase();
    if (!raw) return '';
    const mkt = this.inferStockMarket(code, market);

    const crypto = raw.replace(/USDT$|USD$|-/g, '');
    if (/^(BTC|ETH|BNB|SOL|XRP|DOGE|ADA|AVAX|DOT|MATIC|LINK|UNI|LTC|BCH|ATOM|FIL|APT|ARB|OP|PEPE|SHIB)$/.test(crypto)) {
      return `crypto-${crypto.toLowerCase()}`;
    }

    if (mkt === 'hk_stock') {
      const hk = raw.replace(/^0+/, '') || raw;
      return `hkex-${hk}`;
    }
    if (mkt === 'us_stock') {
      return `nasdaq-${raw.toLowerCase()}`;
    }
    if (mkt === 'a_share') {
      const c6 = raw.replace(/\D/g, '').padStart(6, '0').slice(-6);
      if (/^\d{6}$/.test(c6)) {
        const ex = /^(5|6|9)/.test(c6) ? 'sse' : 'szse';
        return `${ex}-${c6}`;
      }
    }
    return '';
  },

  /** 將股票代碼轉成常見 Logo 服務可識別的 symbol */
  stockLogoSymbol(code, market = '') {
    const c = String(code || '').trim().toUpperCase();
    if (!c) return '';
    const mkt = this.inferStockMarket(code, market);
    if (mkt === 'hk_stock') {
      const hk = c.replace(/^0+/, '') || c;
      return `${hk}.HK`;
    }
    if (mkt === 'us_stock') return c;
    if (mkt === 'a_share') {
      const c6 = c.replace(/\D/g, '').padStart(6, '0').slice(-6);
      return `${c6}.${this.stockMarketPrefix(c6) === 'SH' ? 'SS' : 'SZ'}`;
    }
    return c;
  },

  /** 常見股票代碼到公司網域，用 favicon 服務補足 FMP 沒收錄的標的 */
  stockLogoDomain(code) {
    const c = String(code || '').trim().toUpperCase();
    const map = {
      AAPL: 'apple.com',
      MSFT: 'microsoft.com',
      GOOGL: 'google.com',
      GOOG: 'google.com',
      AMZN: 'amazon.com',
      META: 'meta.com',
      TSLA: 'tesla.com',
      NVDA: 'nvidia.com',
      NFLX: 'netflix.com',
      AMD: 'amd.com',
      INTC: 'intel.com',
      BABA: 'alibabagroup.com',
      TSM: 'tsmc.com',
      JPM: 'jpmorganchase.com',
      V: 'visa.com',
      MA: 'mastercard.com',
      DIS: 'disney.com',
      '00700': 'tencent.com',
      '09988': 'alibabagroup.com',
      '03690': 'meituan.com',
      '09618': 'jd.com',
      '01810': 'mi.com',
      '02318': 'pingan.cn',
      '00941': 'chinamobileltd.com',
      '00005': 'hsbc.com',
      '01299': 'aia.com',
      '00388': 'hkexgroup.com',
      '00992': 'lenovo.com',
      '600519': 'moutaichina.com',
      '000001': 'bank.pingan.com',
      '000858': 'wuliangye.com.cn',
      '601318': 'pingan.cn',
      '600036': 'cmbchina.com',
      '601398': 'icbc.com.cn',
    };
    return map[c] || '';
  },

  _logoCacheKey(code, market = '') {
    return `${String(code || '').trim().toUpperCase()}|${this.inferStockMarket(code, market)}`;
  },

  /** 伺服器 Logo API（僅讀 data/stock_logos/ 快取） */
  stockLogoUrl(code, name = '', market = '') {
    const mkt = this.inferStockMarket(code, market);
    const c = String(code || '').trim();
    if (!c) return '';
    const qParts = [];
    if (mkt) qParts.push(`market=${encodeURIComponent(mkt)}`);
    if (name) qParts.push(`name=${encodeURIComponent(name)}`);
    const q = qParts.length ? `?${qParts.join('&')}` : '';
    return `/api/stock-logo/${encodeURIComponent(c)}${q}`;
  },

  _drainLogoQueue() {
    while (this._logoActive < this._logoMaxConcurrent && this._logoQueue.length) {
      const job = this._logoQueue.shift();
      this._logoActive += 1;
      Promise.resolve(this._loadServerLogo(job))
        .finally(() => {
          this._logoActive -= 1;
          this._drainLogoQueue();
        });
    }
  },

  _logoCacheState(key) {
    const hit = this._logoHitUrls.get(key);
    if (hit) return { kind: 'hit', url: hit };
    const until = this._logoMissUntil.get(key);
    if (until && Date.now() < until) return { kind: 'miss' };
    if (until) this._logoMissUntil.delete(key);
    return { kind: 'fresh' };
  },

  _trimLogoHitCache() {
    while (this._logoHitUrls.size > this._LOGO_HIT_CAP) {
      const oldest = this._logoHitUrls.keys().next().value;
      const url = this._logoHitUrls.get(oldest);
      this._logoHitUrls.delete(oldest);
      if (url) URL.revokeObjectURL(url);
    }
  },

  _rememberLogoHit(key, objUrl) {
    const prev = this._logoHitUrls.get(key);
    if (prev && prev !== objUrl) URL.revokeObjectURL(prev);
    this._logoHitUrls.set(key, objUrl);
    this._logoMissUntil.delete(key);
    this._trimLogoHitCache();
  },

  _applyLogoHit(img, objUrl) {
    if (!img || !objUrl) return;
    const letter = img.closest('.stock-code-icon')?.querySelector('.stock-code-letter');
    const prev = img.dataset.objectUrl;
    if (prev && prev !== objUrl) URL.revokeObjectURL(prev);
    img.dataset.objectUrl = objUrl;
    img.src = objUrl;
    img.style.display = '';
    img.style.objectFit = 'contain';
    if (letter) letter.style.display = 'none';
  },

  _enqueueServerLogo(img, code, name, market) {
    const key = this._logoCacheKey(code, market);
    const st = this._logoCacheState(key);
    if (st.kind === 'hit') {
      this._applyLogoHit(img, st.url);
      return;
    }
    if (st.kind === 'miss') return;
    if (this._logoPendingKeys.has(key)) return;
    this._logoQueue.push({ img, code, name, market });
    this._drainLogoQueue();
  },

  async _loadServerLogo({ img, code, name, market }) {
    const key = this._logoCacheKey(code, market);
    const st = this._logoCacheState(key);
    if (st.kind === 'hit') {
      this._applyLogoHit(img, st.url);
      return;
    }
    if (st.kind === 'miss' || this._logoPendingKeys.has(key)) return;
    const url = this.stockLogoUrl(code, name, market);
    if (!url) return;

    this._logoPendingKeys.add(key);
    try {
      const letter = img.closest('.stock-code-icon')?.querySelector('.stock-code-letter');
      let ok = false;
      try {
        const res = await fetch(url, { credentials: 'same-origin' });
        if (res.ok) {
          const blob = await res.blob();
          if (blob.size >= 80) {
            const objUrl = URL.createObjectURL(blob);
            this._rememberLogoHit(key, objUrl);
            this._applyLogoHit(img, objUrl);
            ok = true;
          }
        } else if (res.status === 404) {
          const logoStatus = (res.headers.get('X-Logo-Status') || '').toLowerCase();
          if (logoStatus === 'pending') {
            const raSec = Math.min(60, Math.max(15, parseInt(res.headers.get('Retry-After') || '30', 10) || 30));
            this._logoMissUntil.set(key, Date.now() + raSec * 1000);
            this._scheduleOneLogoRetry(img, code, name, market, key, raSec * 1000);
          } else {
            this._logoMissUntil.set(key, Date.now() + this._LOGO_MISS_TTL_MS);
          }
        } else {
          this._logoMissUntil.set(key, Date.now() + this._LOGO_MISS_TTL_MS);
        }
      } catch {
        ok = false;
        this._logoMissUntil.set(key, Date.now() + 5 * 60 * 1000);
      }

      if (!ok && letter) letter.style.display = '';
    } finally {
      this._logoPendingKeys.delete(key);
    }
  },

  /** 伺服器背景下載中：單次延遲重試（避免 6s/15s/30s 三重風暴） */
  _scheduleOneLogoRetry(img, code, name, market, key, delayMs) {
    if (this._logoRetryTimers.has(key)) return;
    const wait = Math.min(Math.max(delayMs, 15000), 60000);
    const timer = setTimeout(() => {
      this._logoRetryTimers.delete(key);
      this._logoMissUntil.delete(key);
      if (!img?.isConnected) return;
      this._enqueueServerLogo(img, code, name, market);
    }, wait);
    this._logoRetryTimers.set(key, timer);
  },

  _escAttr(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  },

  _CRYPTO_SLUGS: {
    BTC: 'btc', ETH: 'eth', BNB: 'bnb', SOL: 'sol', XRP: 'xrp',
    DOGE: 'doge', ADA: 'ada', AVAX: 'avax', DOT: 'dot', MATIC: 'matic',
    LINK: 'link', LTC: 'ltc', BCH: 'bch', ATOM: 'atom', TRX: 'trx',
    USDT: 'usdt', USDC: 'usdc',
  },

  /** 是否為加密貨幣代碼（勿走股票 Logo API） */
  isCryptoSymbol(symbol) {
    const base = String(symbol || '').trim().toUpperCase().replace(/USDT$|USD$|PERP$/i, '');
    return Boolean(base && this._CRYPTO_SLUGS[base]);
  },

  /** 加密貨幣專用圖標（不依賴股票 Logo 管線） */
  cryptoIconHtml(symbol, size = 32) {
    const raw = String(symbol || '').trim().toUpperCase();
    const base = raw.replace(/USDT$|USD$|PERP$/i, '') || raw;
    const slug = this._CRYPTO_SLUGS[base] || base.toLowerCase();
    const px = Math.max(24, Number(size) || 32);
    const url = `https://cdn.jsdelivr.net/npm/cryptocurrency-icons@0.18.1/svg/color/${slug}.svg`;
    const letter = base.slice(0, 1) || '?';
    return `<span class="crypto-coin-icon" style="width:${px}px;height:${px}px" data-crypto-icon="1">
      <img src="${url}" width="${px}" height="${px}" alt="${this._escAttr(base)}"
        loading="lazy" decoding="async" referrerpolicy="no-referrer"
        onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
      <span class="crypto-coin-letter">${letter}</span>
    </span>`;
  },

  /** 產生帶 Logo 容器的 HTML（渲染後請呼叫 hydrateStockIcons） */
  stockIconHtml(code, name = '', size = 28, market = '') {
    if (this.isCryptoSymbol(code)) return this.cryptoIconHtml(code, size);
    const px = Math.max(20, Number(size) || 28);
    const letter = (String(name || code || '?').trim() || '?').slice(0, 1);
    const symHtml = this.stockIconfontUseHtml(code, name, px);
    const symLayer = symHtml
      ? `<span class="stock-iconfont-layer" hidden>${symHtml}</span>`
      : '';
    return `<span class="stock-code-icon stock-icon-square stock-code-row-icon" style="width:${px}px;height:${px}px">
      ${symLayer}
      <img width="${px}" height="${px}" alt=""
        data-stock-code="${this._escAttr(code)}"
        data-stock-name="${this._escAttr(name)}"
        data-stock-market="${this._escAttr(market)}">
      <span class="stock-code-letter">${letter}</span>
    </span>`;
  },

  /** 批次綁定容器內股票 Logo（僅可見區，避免全市場列表同時打 API） */
  hydrateStockIcons(root) {
    this.observeStockIcons(root);
  },

  /** 列表懶加載 Logo（索引頁大量卡片時避免同時請求過多） */
  observeStockIcons(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const imgs = [...scope.querySelectorAll('.stock-code-icon img[data-stock-code]')]
      .filter(img => !img.closest('[data-crypto-icon]'));
    if (!imgs.length) return;

    const bindOne = (img) => {
      if (img.dataset.logoBound === '1') return;
      img.dataset.logoBound = '1';
      const code = img.dataset.stockCode || '';
      if (!code) return;
      const mkt = img.dataset.stockMarket || this.inferStockMarket(code, '');
      this.bindStockIcon(img, code, img.dataset.stockName || '', mkt);
    };

    if (!('IntersectionObserver' in window)) {
      imgs.forEach(bindOne);
      return;
    }

    const io = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        io.unobserve(entry.target);
        bindOne(entry.target);
      });
    }, { rootMargin: '100px', threshold: 0.01 });

    imgs.forEach(img => {
      if (img.dataset.logoBound === '1') return;
      io.observe(img);
    });
  },

  /** 本地 SVG 圖標：不依賴任何外部 CDN，確保股票永遠有對應圖標 */
  stockIconLocalUrl(code, name, size = 56) {
    const c = String(code || '').trim();
    const n = String(name || c || '?').trim();
    const label = (n.replace(/\s/g, '') || c || '?').slice(0, 2);
    let hash = 0;
    for (const ch of `${c}${n}`) {
      hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
    }
    const hue = Math.abs(hash) % 360;
    const hue2 = (hue + 42) % 360;
    const fg = '#e0f2fe';
    const codeText = c ? c.slice(-3) : '';
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="hsl(${hue},72%,36%)"/>
            <stop offset="100%" stop-color="hsl(${hue2},78%,48%)"/>
          </linearGradient>
        </defs>
        <rect width="${size}" height="${size}" rx="${Math.round(size * 0.28)}" fill="url(#g)"/>
        <circle cx="${Math.round(size * 0.78)}" cy="${Math.round(size * 0.22)}" r="${Math.round(size * 0.22)}" fill="rgba(255,255,255,.13)"/>
        <text x="50%" y="47%" text-anchor="middle" dominant-baseline="middle"
          font-family="Arial,'Microsoft JhengHei','PingFang TC',sans-serif"
          font-size="${Math.round(size * (label.length >= 2 ? 0.32 : 0.42))}"
          font-weight="800" fill="${fg}">${label}</text>
        <text x="50%" y="76%" text-anchor="middle" dominant-baseline="middle"
          font-family="ui-monospace,Menlo,Consolas,monospace"
          font-size="${Math.round(size * 0.16)}"
          font-weight="700" fill="rgba(224,242,254,.78)">${codeText}</text>
      </svg>`;
    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
  },

  /**
   * 綁定股票圖標：先顯示本地 SVG，再向伺服器請求已快取的 Logo。
   * 開啟伺服器 Logo：localStorage.setItem('sq_remote_stock_icons', '1')
   */
  bindStockIcon(img, code, name, market = '') {
    if (!img) return;
    if (img.closest('[data-crypto-icon]') || this.isCryptoSymbol(code)) return;
    const c = String(code || '').trim();
    const n = String(name || c || '?');
    const mkt = this.inferStockMarket(c, market);
    img.alt = `${c} ${n}`;
    img.loading = 'lazy';
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer';

    const wrap = img.closest('.stock-code-icon');
    const letter = wrap?.querySelector('.stock-code-letter');
    const symLayer = wrap?.querySelector('.stock-iconfont-layer');

    const showIconfontSymbol = () => {
      if (!symLayer) return false;
      const use = symLayer.querySelector('use');
      if (!use) return false;
      const href = use.getAttribute('href') || use.getAttribute('xlink:href') || '';
      const id = href.replace(/^#/, '');
      if (!id || !document.getElementById(id)) return false;
      symLayer.hidden = false;
      img.style.display = 'none';
      if (letter) letter.style.display = 'none';
      return true;
    };

    const localUrl = this.stockIconLocalUrl(c, n, Math.max(img.width || 56, img.height || 56, 56));
    img.onerror = null;
    img.src = localUrl;
    img.style.display = '';
    img.style.objectFit = 'contain';
    if (letter) letter.style.display = '';
    if (wrap) wrap.classList.add('stock-icon-square');

    if (showIconfontSymbol()) return;
    if (symLayer && this._iconfontConfig?.symbol_js_url) {
      const trySym = () => { if (showIconfontSymbol()) return; };
      document.addEventListener('sq-iconfont-ready', trySym, { once: true });
      setTimeout(trySym, 600);
      setTimeout(trySym, 2000);
    }

    if (!this.stockLogoRemoteEnabled()) return;

    const key = this._logoCacheKey(c, mkt);
    const st = this._logoCacheState(key);
    if (st.kind === 'hit') {
      this._applyLogoHit(img, st.url);
      return;
    }
    if (st.kind === 'miss') return;

    this._enqueueServerLogo(img, c, n, mkt);
  },

  /** 套用本地 SVG 到任意元素背景，供非 img 場景使用 */
  applyStockIconBackground(el, code, name) {
    if (!el) return;
    el.style.backgroundImage = `url("${this.stockIconLocalUrl(code, name, 56)}")`;
    el.style.backgroundSize = 'cover';
    el.style.backgroundPosition = 'center';
  },
};

/**
 * SecureStore — localStorage 敏感數據加密封裝
 * 使用 XOR + Base64 混淆，密鑰存於 sessionStorage（關頁即失效）
 * 適用於 JWT token、API Key 等不宜明文存儲的數據
 */
const SecureStore = {
  _key: null,

  _getKey() {
    if (this._key) return this._key;
    let raw = sessionStorage.getItem('_sq_sk');
    if (!raw) {
      const arr = new Uint8Array(32);
      (crypto.getRandomValues || function(a) { for (let i = 0; i < a.length; i++) a[i] = Math.floor(Math.random() * 256); })(arr);
      raw = btoa(String.fromCharCode(...arr));
      sessionStorage.setItem('_sq_sk', raw);
    }
    this._key = raw;
    return raw;
  },

  _xor(str, key) {
    let out = '';
    for (let i = 0; i < str.length; i++) {
      out += String.fromCharCode(str.charCodeAt(i) ^ key.charCodeAt(i % key.length));
    }
    return out;
  },

  setItem(k, v) {
    const key = this._getKey();
    const encrypted = btoa(this._xor(String(v), key));
    localStorage.setItem(k, encrypted);
  },

  getItem(k) {
    const raw = localStorage.getItem(k);
    if (raw == null) return null;
    try {
      const key = this._getKey();
      return this._xor(atob(raw), key);
    } catch {
      return raw;
    }
  },

  removeItem(k) { localStorage.removeItem(k); },
};

window.SecureStore = SecureStore;

// Make globally available
window.Utils = Utils;
