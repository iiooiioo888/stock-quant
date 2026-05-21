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
    const c = String(code || '').trim().padStart(6, '0');
    if (/^(5|6|9)/.test(c)) return 'SH';
    return 'SZ';
  },

  /** 將股票代碼轉成常見 Logo 服務可識別的 symbol */
  stockLogoSymbol(code, market = '') {
    const c = String(code || '').trim().toUpperCase();
    const m = String(market || '').trim();
    if (!c) return '';
    if (/^[A-Z][A-Z0-9.-]{0,9}$/.test(c)) return c;
    if (/^\d{5}$/.test(c)) return `${c.replace(/^0(?=\d{4}$)/, '')}.HK`;
    if (/^\d{6}$/.test(c)) return `${c}.${this.stockMarketPrefix(c) === 'SH' ? 'SS' : 'SZ'}`;
    if (m === 'hk_stock') return `${c.replace(/^0+(?=\d)/, '')}.HK`;
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
      '600519': 'moutaichina.com',
      '000001': 'bank.pingan.com',
      '000858': 'wuliangye.com.cn',
      '601318': 'pingan.cn',
      '600036': 'cmbchina.com',
      '601398': 'icbc.com.cn',
    };
    return map[c] || '';
  },

  /**
   * 外部 Logo 候選來源（不再使用東財）。
   * FMP image-stock 對美股較完整，部分港股/A股使用 .HK/.SS/.SZ symbol。
   * 網域 favicon 作為第二層補強，失敗時仍回落本地 SVG。
   */
  stockLogoUrls(code, name = '', market = '') {
    const symbol = this.stockLogoSymbol(code, market);
    const domain = this.stockLogoDomain(code, name);
    const urls = [];
    if (symbol) {
      urls.push(`https://financialmodelingprep.com/image-stock/${encodeURIComponent(symbol)}.png`);
    }
    if (domain) {
      urls.push(`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`);
      urls.push(`https://icons.duckduckgo.com/ip3/${encodeURIComponent(domain)}.ico`);
    }
    return [...new Set(urls)];
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
   * 綁定股票圖標：先使用本地 SVG，外部 Logo 只作可選增強。
   * 若想嘗試 FMP / favicon 外部 Logo，可在控制台執行：
   * localStorage.setItem('sq_remote_stock_icons', '1')
   */
  bindStockIcon(img, code, name, market = '') {
    if (!img) return;
    const c = String(code || '').trim();
    const n = String(name || c || '?');
    img.alt = `${c} ${n}`;
    img.loading = 'lazy';
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer';

    const localUrl = this.stockIconLocalUrl(c, n, Math.max(img.width || 56, img.height || 56, 56));
    img.onerror = null;
    img.src = localUrl;

    const wrap = img.closest('.stock-code-icon');
    const letter = wrap?.querySelector('.stock-code-letter');
    if (letter) letter.style.display = 'none';

    const allowRemote = localStorage.getItem('sq_remote_stock_icons') === '1';
    if (!allowRemote) return;

    const urls = this.stockLogoUrls(c, n, market);
    if (!urls.length) return;

    let idx = 0;
    const tryNext = () => {
      if (idx >= urls.length) return;
      const remote = new Image();
      let done = false;
      const timer = setTimeout(() => {
        if (done) return;
        done = true;
        tryNext();
      }, 2500);
      remote.referrerPolicy = 'no-referrer';
      remote.decoding = 'async';
      remote.onload = () => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        // 一些服務會回傳極小/透明佔位圖，尺寸太小就不要覆蓋本地 SVG。
        if (remote.naturalWidth >= 16 && remote.naturalHeight >= 16) {
          img.src = remote.src;
        } else {
          tryNext();
        }
      };
      remote.onerror = () => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        tryNext();
      };
      remote.src = urls[idx++];
    };
    tryNext();
  },

  /** 套用本地 SVG 到任意元素背景，供非 img 場景使用 */
  applyStockIconBackground(el, code, name) {
    if (!el) return;
    el.style.backgroundImage = `url("${this.stockIconLocalUrl(code, name, 56)}")`;
    el.style.backgroundSize = 'cover';
    el.style.backgroundPosition = 'center';
  },
};

// Make globally available
window.Utils = Utils;
