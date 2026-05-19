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
  }
};

// Make globally available
window.Utils = Utils;
