/* global Api, Utils, echarts */

(() => {
  const $id = (id) => document.getElementById(id);

  const App = {
    current: '',
    _navGen: 0,
    _ws: null,
    _wsGen: 0,
    _wsRetry: 0,
    _wsMaxRetry: 8,
    _wsPingTimer: null,

    init() {
      // keep existing API init (token, auth UI) if present
      try { if (typeof Api !== 'undefined' && Api.init) Api.init(); } catch (_) {}
      try { window.StockQPro?.Allocation?.init?.(); } catch (_) {}

      this._bindAuth();
      this._bindNav();
      this._bindModals();
      this._bindCmdPalette();
      this._bindKeyboard();
      this._bindLogo();
      this._connectWS();
      try { window.StockQPro?.Terms?.applyTerms?.(); } catch (_) {}

      // initial render（工作台預設總覽；產品介紹頁在 /）
      this.navFromHash() || this.nav('dashboard', { syncHash: true });

      const schedule = window.requestIdleCallback || ((fn) => setTimeout(fn, 300));
      schedule(() => {
        const h = String(location.hash || '');
        const m = h.match(/^#\/([^/?#]+)/);
        const warm = m ? m[1] : 'dashboard';
        window.StockQPro?.modules?.prefetch?.(warm);
        window.StockQPro?.LegacyBridge?.ensureScripts?.().catch(() => {});
      });
    },

    _yieldPaint() {
      return new Promise((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(resolve));
      });
    },

    _setPageLoading(pageId, on) {
      const pg = $id(`pg-${pageId}`);
      if (!pg) return;
      pg.classList.toggle('is-page-loading', !!on);
      const mount = pg.querySelector('.legacy-mount');
      if (mount && on && !mount.querySelector('.legacy-mount__busy')) {
        const el = document.createElement('div');
        el.className = 'legacy-mount__busy';
        el.setAttribute('role', 'status');
        el.textContent = '載入模組中…';
        mount.appendChild(el);
      } else if (mount && !on) {
        mount.querySelector('.legacy-mount__busy')?.remove();
      }
    },

    reconnectWs() {
      this._wsRetry = 0;
      this._connectWS();
    },

    _disposeWs(sock) {
      if (!sock) return;
      sock.onopen = sock.onclose = sock.onmessage = sock.onerror = null;
      try { sock.close(); } catch (_) {}
    },

    _connectWS() {
      this._disposeWs(this._ws);
      this._ws = null;

      const token = (typeof Api !== 'undefined' && Api._token) || localStorage.getItem('sq_token') || '';
      const conn = document.getElementById('conn-status');
      if (!token) {
        if (conn) conn.textContent = '未登錄';
        return;
      }
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${proto}//${location.host}/ws?token=${encodeURIComponent(token)}`;
      let ws;
      try {
        ws = new WebSocket(wsUrl);
      } catch (_) {
        return;
      }
      const gen = ++this._wsGen;
      this._ws = ws;

      ws.onopen = () => {
        if (this._ws !== ws || this._wsGen !== gen) return;
        this._wsRetry = 0;
        if (conn) conn.textContent = '已連線';
        try {
          window.StockQPro?.pages?.tasks?.updateBadges?.();
        } catch (_) {}
        try {
          Object.values(window.StockQPro?.pages || {}).forEach((m) => {
            if (m && typeof m.rebindWs === 'function') m.rebindWs();
          });
        } catch (_) {}
        try {
          const mods = window.__StockQProESM__?.registry?.listPages?.()
            ?.map((pid) => window.__StockQProESM__?.getPage?.(pid))
            ?.filter(Boolean);
          (mods || []).forEach((m) => {
            if (m && typeof m.rebindWs === 'function') m.rebindWs();
          });
        } catch (_) {}
      };

      ws.onclose = () => {
        if (this._ws !== ws || this._wsGen !== gen) return;
        this._ws = null;
        const still = (typeof Api !== 'undefined' && Api._token) || localStorage.getItem('sq_token') || '';
        if (!still) {
          if (conn) conn.textContent = '未登錄';
          return;
        }
        this._wsRetry += 1;
        if (this._wsRetry > this._wsMaxRetry) return;
        const delay = Math.min(1000 * Math.pow(2, this._wsRetry), 30000);
        setTimeout(() => {
          if (this._wsGen === gen && !this._ws) this._connectWS();
        }, delay);
      };

      ws.onmessage = (e) => {
        if (this._ws !== ws) return;
        try {
          const data = JSON.parse(e.data);
          if (data?.type?.startsWith('task_')) {
            window.StockQPro?.pages?.tasks?.onWsMessage?.(e);
          }
        } catch (_) {}
      };

      if (this._wsPingTimer) clearInterval(this._wsPingTimer);
      this._wsPingTimer = setInterval(() => {
        if (this._ws === ws && ws.readyState === 1) {
          try { ws.send('ping'); } catch (_) {}
        }
      }, 25000);
    },

    _bindAuth() {
      const pill = document.getElementById('auth-pill');
      if (!pill) return;
      pill.addEventListener('click', () => {
        if (typeof Api === 'undefined') return;
        if (Api.isLoggedIn && Api.isLoggedIn()) {
          Api.logout?.();
          this.toast('已登出', 'ok');
          return;
        }
        Api.showLoginModal?.(false);
      });
    },

    _bindLogo() {
      document.querySelectorAll('[data-nav]').forEach((el) => {
        el.addEventListener('click', () => this.nav(el.getAttribute('data-nav'), { syncHash: true }));
      });
    },

    _bindNav() {
      document.querySelectorAll('.sb').forEach((btn) => {
        btn.addEventListener('click', () => {
          const p = btn.getAttribute('data-p');
          if (p) this.nav(p, { syncHash: true });
        });
      });
    },

    _syncNavGroup(pid) {
      document.querySelectorAll('.sidebar .nav-group').forEach((grp) => {
        const hit = grp.querySelector(`.sb[data-p="${pid}"]`);
        grp.open = !!hit;
      });
    },

    async nav(id, opts = {}) {
      const pid = String(id || '').trim();
      if (!pid) return;

      const prev = this.current;
      const gen = ++this._navGen;

      // INP：先切換可見分頁，再背景載入腳本
      document.querySelectorAll('.pg').forEach((p) => p.classList.remove('on'));
      document.querySelectorAll('.sb').forEach((b) => b.classList.remove('on'));
      const pg = $id(`pg-${pid}`);
      if (pg) pg.classList.add('on');
      const sb = document.querySelector(`.sb[data-p="${pid}"]`);
      if (sb) sb.classList.add('on');
      this._syncNavGroup(pid);
      this.current = pid;
      if (opts.syncHash) {
        const want = `#/${pid}`;
        if (location.hash !== want) location.hash = want;
      }
      this._setPageLoading(pid, true);
      await this._yieldPaint();

      if (gen !== this._navGen) return;

      try {
        await window.StockQPro?.modules?.ensurePage?.(pid);
      } catch (e) {
        if (gen === this._navGen) {
          this._setPageLoading(pid, false);
          this.toast(e?.message || '頁面模組載入失敗', 'er');
        }
        return;
      }

      if (gen !== this._navGen) return;

      if (prev && prev !== pid) {
        try {
          const prevMod = window.__StockQProESM__?.getPage?.(prev) || window.StockQPro?.pages?.[prev];
          if (prevMod && typeof prevMod.unload === 'function') prevMod.unload();
        } catch (_) {}
      }

      try {
        window.StockQPro?.Store?.set?.({ page: pid });
      } catch (_) {}

      try {
        const mod = window.__StockQProESM__?.getPage?.(pid) || window.StockQPro?.pages?.[pid];
        if (mod) {
          if (prev !== pid && typeof mod.init === 'function') {
            await Promise.resolve(mod.init());
          }
          if (typeof mod.onShow === 'function') {
            await Promise.resolve(mod.onShow());
          }
        }
      } catch (_) {}
      finally {
        if (gen === this._navGen) this._setPageLoading(pid, false);
      }
    },

    navFromHash() {
      const h = String(location.hash || '');
      const assetM = h.match(/^#\/asset\/([^/?#]+)/);
      if (assetM) {
        const sym = decodeURIComponent(assetM[1]);
        this.nav('assets', { syncHash: false });
        try {
          window.StockQPro?.pages?.assets?.openDetail?.(sym);
        } catch (_) {}
        return true;
      }
      const m = h.match(/^#\/([^/?#]+)/);
      if (!m) return false;
      const tab = m[1];
      this.nav(tab, { syncHash: false });
      if (tab === 'assets') {
        try { window.StockQPro?.pages?.assets?.showList?.(); } catch (_) {}
      }
      return true;
    },

    toast(msg, type = 'ok') {
      // prefer shared UI library if present
      if (window.StockQPro?.UI?.toast) {
        window.StockQPro.UI.toast(msg, type);
        return;
      }
      const c = $id('toasts');
      if (!c) return;
      const el = document.createElement('div');
      el.className = `toast ${type}`;
      const icon = type === 'ok' ? '✓' : type === 'er' ? '✕' : 'ℹ';
      el.innerHTML = `<span>${icon}</span><span>${String(msg || '')}</span>`;
      c.appendChild(el);
      setTimeout(() => { el.style.opacity = '0'; el.style.transition = '.3s'; }, 3000);
      setTimeout(() => el.remove(), 3500);
    },

    openModal(id) {
      if (window.StockQPro?.UI?.modalOpen) return window.StockQPro.UI.modalOpen(id);
      const el = $id(id);
      if (!el) return;
      el.classList.add('show');
      el.setAttribute('aria-hidden', 'false');
    },

    closeModal(id) {
      if (window.StockQPro?.UI?.modalClose) return window.StockQPro.UI.modalClose(id);
      const el = $id(id);
      if (!el) return;
      el.classList.remove('show');
      el.setAttribute('aria-hidden', 'true');
    },

    _bindModals() {
      document.querySelectorAll('.modal-ov').forEach((ov) => {
        ov.addEventListener('click', (e) => {
          if (e.target === ov) this.closeModal(ov.id);
        });
      });
      document.querySelectorAll('[data-close]').forEach((btn) => {
        btn.addEventListener('click', () => this.closeModal(btn.getAttribute('data-close')));
      });
    },

    _bindCmdPalette() {
      const openBtn = $id('cmd-open-btn');
      const ov = $id('cmd-ov');
      const input = $id('cmd-in');
      const list = $id('cmd-list');
      if (!ov || !input || !list) return;

      const pages = [
        { n: '產品介紹頁', d: '功能概覽與系統入口', href: '/', k: 'H' },
        { n: '總覽', d: 'KPI、行情與快捷入口', p: 'dashboard', k: '1' },
        { n: '資金流', d: '板塊資金與市場圖表', p: 'capitalflow' },
        { n: '策略庫', d: '130+ 策略', p: 'strategies', k: 'S' },
        { n: '回測', d: '策略回測', p: 'backtest', k: '2' },
        { n: '任務中心', d: '回測與數據任務佇列', p: 'tasks', k: 'T' },
        { n: '對比', d: '策略對比', p: 'compare', k: '3' },
        { n: '組合回測', d: '多標的組合與權重', p: 'portfolio', k: '4' },
        { n: '我的配置', d: '右側持倉欄 · 回測/對比/結算', act: 'allocation', k: 'P' },
        { n: '自選股', d: '自選列表', p: 'watchlist', k: '5' },
        { n: '選股器', d: '全市場掃描', p: 'scanner', k: '6' },
        { n: '預警', d: '條件預警', p: 'alerts', k: '7' },
        { n: '風控', d: '風控規則', p: 'risk', k: '8' },
        { n: '日誌', d: '交易紀錄', p: 'journal', k: '9' },
        { n: '歷史', d: '回測歷史', p: 'backhistory' },
        { n: 'AI 問答', d: '查詢數據、整合北向/板塊/個股', p: 'ai', k: 'A' },

        { n: '參數優化', d: 'Grid / Optuna', p: 'optimize' },
        { n: 'Walk-Forward', d: '滾動窗口驗證', p: 'walkforward' },
        { n: '參數熱力圖', d: '敏感性分析', p: 'heatmap' },
        { n: '實時信號', d: '當前 / 歷史 / 強度', p: 'signals' },
        { n: '數據中心', d: '下載 / 板塊 / 資金流', p: 'data' },
        { n: '深度分析', d: '技術 + 基本面', p: 'analysis' },
        { n: '策略報告', d: '日報生成', p: 'reports' },
        { n: '定時任務', d: 'APScheduler', p: 'scheduler' },
        { n: '多市場', d: 'A股 / 美股 / 港股', p: 'markets' },
        { n: '加密行情', d: 'Binance 等', p: 'crypto' },
        { n: '連線檢查', d: '數據源可用性探測', p: 'connectivity' },
        { n: '定價', d: '方案', p: 'pricing' },
        { n: '設定', d: '全局設定', p: 'settings' },
      ];

      const getExtraItems = (q) => {
        const qq = String(q || '').trim().toLowerCase();
        const extra = [];

        // strategies (local catalog)
        const catalog = window.StockQPro?.catalog;
        if (catalog?.strats?.length && qq) {
          const hits = catalog.strats
            .filter((s) => String(s.name || '').toLowerCase().includes(qq) || String(s.desc || '').toLowerCase().includes(qq))
            .slice(0, 6);
          hits.forEach((s) => extra.push({
            n: `策略：${s.name}`,
            d: (s.status === 'implemented' || s.status === 'user') ? '可回測' : '即將推出',
            action: () => {
              window.StockQPro?.App?.nav?.('strategies', { syncHash: true });
              setTimeout(() => window.StockQPro?.showStratDetail?.(s.id), 50);
            },
          }));
        }

        // quick code to backtest
        if (/^\d{3,6}$/.test(qq)) {
          extra.unshift({
            n: `回測：${qq}`,
            d: '打開回測並填入代碼',
            action: () => {
              this.nav('backtest', { syncHash: true });
              if (window.StockQPro?.backtestSymbol?.setSymbol) {
                window.StockQPro.backtestSymbol.setSymbol(qq);
              } else {
                const el = document.getElementById('bt-code');
                if (el) el.value = qq;
              }
            },
          });
        }

        return extra;
      };

      const open = () => {
        ov.classList.add('show');
        ov.setAttribute('aria-hidden', 'false');
        input.value = '';
        input.focus();
        render('');
      };

      const close = () => {
        ov.classList.remove('show');
        ov.setAttribute('aria-hidden', 'true');
      };

      const render = (q) => {
        const qq = String(q || '').toLowerCase();
        const filtered = pages.filter((p) => p.n.toLowerCase().includes(qq) || p.d.toLowerCase().includes(qq));
        const extras = getExtraItems(q);
        list.innerHTML =
          extras.map((p, idx) => (
            `<div class="cmd-item" data-cmd-extra="${idx}">` +
              `<div class="cmd-item-info"><div class="cmd-item-name">${p.n}</div><div class="cmd-item-desc">${p.d}</div></div>` +
            `</div>`
          )).join('')
          + filtered.map((p) => (
            `<div class="cmd-item" data-cmd="${p.p || ''}" data-href="${p.href || ''}" data-act="${p.act || ''}">` +
              `<div class="cmd-item-info"><div class="cmd-item-name">${p.n}</div><div class="cmd-item-desc">${p.d}</div></div>` +
              (p.k ? `<div class="cmd-item-kb"><kbd>${p.k}</kbd></div>` : '') +
            `</div>`
          )).join('');

        // attach extras to element for click dispatch
        list._extras = extras;
      };

      if (openBtn) openBtn.addEventListener('click', open);
      ov.addEventListener('click', (e) => { if (e.target === ov) close(); });
      input.addEventListener('input', () => render(input.value));
      list.addEventListener('click', (e) => {
        const item = e.target.closest('.cmd-item');
        if (!item) return;
        const extraIdx = item.getAttribute('data-cmd-extra');
        if (extraIdx != null) {
          const fn = list._extras?.[Number(extraIdx)]?.action;
          close();
          try { fn && fn(); } catch (_) {}
          return;
        }
        const href = item.getAttribute('data-href');
        if (href) {
          close();
          window.location.href = href;
          return;
        }
        const act = item.getAttribute('data-act');
        if (act === 'allocation') {
          close();
          window.StockQPro?.Allocation?.setOpen?.(true);
          return;
        }
        const p = item.getAttribute('data-cmd');
        if (!p) return;
        close();
        this.nav(p, { syncHash: true });
      });

      this._cmd = { open, close };
    },

    _bindKeyboard() {
      window.addEventListener('hashchange', () => this.navFromHash());
      document.addEventListener('keydown', (e) => {
        const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
          e.preventDefault();
          this._cmd?.open?.();
          return;
        }
        if (e.key === 'Escape') {
          document.querySelectorAll('.modal-ov.show').forEach((m) => m.classList.remove('show'));
          this._cmd?.close?.();
          return;
        }

        const map = { '1':'dashboard','2':'backtest','3':'compare','4':'portfolio','5':'watchlist','6':'scanner','7':'alerts','8':'risk','9':'journal','0':'pricing' };
        if (map[e.key]) this.nav(map[e.key], { syncHash: true });
        if (e.key === 't' || e.key === 'T') this.nav('tasks', { syncHash: true });
        if (e.key === 'h' || e.key === 'H') { window.location.href = '/'; return; }
        if (e.key === 's' || e.key === 'S') this.nav('strategies', { syncHash: true });
        if (e.key === 'r' || e.key === 'R') {
          if (this.current === 'tasks') window.StockQPro?.Tasks?.refresh?.();
        }
      });
    },
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.App = App;
  window.StockQApp = App;
  window.StockQPro.pages = window.StockQPro.pages || {};

  window.addEventListener('DOMContentLoaded', () => App.init());
})();

