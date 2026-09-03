/* global Api, Utils, echarts */

(() => {
  const $id = (id) => document.getElementById(id);
  const PLANNED = new Set(['factor', 'seasonal', 'regime', 'risk', 'journal']);
  const PAGE_TITLE = {
    dashboard: '總覽', tasks: '任務中心', watchlist: '自選股', scanner: '選股器',
    alerts: '預警', strategies: '策略庫', backtest: '策略回測', compare: '對比',
    portfolio: '持倉與淨值', backhistory: '回測歷史', optimize: '參數優化',
    walkforward: '滾動驗證', heatmap: '熱力圖', reports: '策略報告',
    assets: '資產庫', capitalflow: '資金流', data: '數據中心', analysis: '深度分析',
    signals: '信號', markets: '市場', crypto: '加密', scheduler: '定時',
    connectivity: '數據源', ai: 'AI', pricing: '定價', settings: '設定',
  };

  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function rememberPage(pid) {
    if (!pid || PLANNED.has(pid)) return;
    const prefs = window.StockQPro?.Prefs;
    if (!prefs?.save) return;
    const cur = prefs.get('recentPages') || [];
    if (cur[0] === pid) return;
    const list = cur.filter((x) => x !== pid);
    list.unshift(pid);
    prefs.save({ recentPages: list.slice(0, 8) });
  }

  const App = {
    current: '',
    _navGen: 0,
    _pendingAssetSymbol: null,
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
      this._restoreNavGroups();
      this._bindMobileNav();
      this._bindTickerJump();
      this._bindModals();
      this._bindCmdPalette();
      this._bindShortcutsHelp();
      this._bindKeyboard();
      this._bindLogo();
      this._connectWS();
      try { window.StockQPro?.services?.opsMonitor?.init?.(); } catch (_) {}
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

      const token = (typeof Api !== 'undefined' && Api._token) || SecureStore.getItem('sq_token') || '';
      const conn = document.getElementById('conn-status');
      const connFooter = document.getElementById('conn-status-footer');
      const _setConn = (txt) => { if (conn) conn.textContent = txt; if (connFooter) connFooter.textContent = txt; };
      if (!token) {
        _setConn('未登錄');
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
        _setConn('已連線');
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
        const still = (typeof Api !== 'undefined' && Api._token) || SecureStore.getItem('sq_token') || '';
        if (!still) {
          _setConn('未登錄');
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
      const planBadge = document.getElementById('plan-badge');
      planBadge?.addEventListener('click', () => this.nav('pricing', { syncHash: true }));
      if (!pill) return;
      pill.addEventListener('click', () => {
        if (typeof Api === 'undefined') return;
        if (Api.isLoggedIn && Api.isLoggedIn()) {
          const now = Date.now();
          if (this._authClickAt && now - this._authClickAt < 450) {
            this._authClickAt = 0;
            Api.logout?.();
            this.toast('已登出', 'ok');
            return;
          }
          this._authClickAt = now;
          this.nav('settings', { syncHash: true });
          return;
        }
        Api.showLoginModal?.(false);
      });
      pill.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          pill.click();
        }
      });
    },

    _bindLogo() {
      document.querySelectorAll('[data-nav]').forEach((el) => {
        el.addEventListener('click', (e) => {
          e.preventDefault();
          this.nav(el.getAttribute('data-nav'), { syncHash: true });
        });
      });
    },

    _bindNav() {
      document.querySelectorAll('.sb').forEach((btn) => {
        btn.addEventListener('click', () => {
          const p = btn.getAttribute('data-p');
          if (p) this.nav(p, { syncHash: true });
          document.body.classList.remove('nav-open');
        });
      });
      document.querySelectorAll('.sidebar .nav-group').forEach((grp) => {
        grp.addEventListener('toggle', () => this._persistNavGroups());
      });
    },

    _restoreNavGroups() {
      const saved = window.StockQPro?.Prefs?.get?.('navGroupsOpen');
      if (!saved || typeof saved !== 'object') return;
      document.querySelectorAll('.sidebar .nav-group[data-nav-group]').forEach((grp) => {
        const key = grp.getAttribute('data-nav-group');
        if (key && Object.prototype.hasOwnProperty.call(saved, key)) {
          grp.open = !!saved[key];
        }
      });
    },

    _persistNavGroups() {
      const navGroupsOpen = {};
      document.querySelectorAll('.sidebar .nav-group[data-nav-group]').forEach((grp) => {
        navGroupsOpen[grp.getAttribute('data-nav-group')] = !!grp.open;
      });
      window.StockQPro?.Prefs?.save?.({ navGroupsOpen });
    },

    _syncNavGroup(pid) {
      document.querySelectorAll('.sidebar .nav-group').forEach((grp) => {
        const hit = grp.querySelector(`.sb[data-p="${pid}"]`);
        if (hit) grp.open = true;
      });
      this._persistNavGroups();
    },

    _bindMobileNav() {
      const btn = document.getElementById('nav-toggle');
      const backdrop = document.getElementById('nav-backdrop');
      const close = () => document.body.classList.remove('nav-open');
      btn?.addEventListener('click', () => document.body.classList.toggle('nav-open'));
      backdrop?.addEventListener('click', close);
    },

    _bindTickerJump() {
      document.addEventListener('click', (e) => {
        const card = e.target.closest('.ticker-card[data-symbol]');
        if (!card?.dataset?.symbol) return;
        if (e.target.closest('a, button, input, select')) return;
        this.openAsset(card.dataset.symbol);
      });
    },

    openAsset(symbol) {
      const raw = String(symbol || '').trim();
      const sym = window.StockQPro?.SymbolUtils?.normalizeAssetSymbol?.(raw) || raw.toUpperCase();
      if (!sym) return;
      this._pendingAssetSymbol = sym;
      try { window.StockQPro?.WorkContext?.set?.(sym); } catch (_) {}
      const want = `#/asset/${encodeURIComponent(sym)}`;
      if (location.hash !== want) location.hash = want;
      else this.navFromHash();
    },

    async nav(id, opts = {}) {
      const pid = String(id || '').trim();
      if (!pid) return;
      if (PLANNED.has(pid)) {
        this.toast('此模組即將推出', 'inf');
        return;
      }

      const hash = String(location.hash || '');
      if (pid !== 'assets' || !/^#\/asset\//.test(hash)) {
        this._pendingAssetSymbol = null;
      }

      const prev = this.current;
      const gen = ++this._navGen;

      // INP：先切換可見分頁，再背景載入腳本
      document.querySelectorAll('.pg').forEach((p) => p.classList.remove('on'));
      document.querySelectorAll('.sb').forEach((b) => b.classList.remove('on'));
      const pg = $id(`pg-${pid}`);
      if (pg) {
        pg.classList.add('on');
      }
      const sb = document.querySelector(`.sb[data-p="${pid}"]`);
      if (sb) sb.classList.add('on');
      this._syncNavGroup(pid);
      this.current = pid;
      rememberPage(pid);
      try { window.StockQPro?.WorkContext?.render?.(); } catch (_) {}
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
          try { window.StockQPro?.WorkContext?.applyToPage?.(pid); } catch (_) {}
        }
      } catch (_) {}
      finally {
        if (gen === this._navGen) {
          this._setPageLoading(pid, false);
          if (pid === 'assets') this._flushPendingAssetDetail();
        }
      }
    },

    _flushPendingAssetDetail() {
      const sym = this._pendingAssetSymbol;
      if (!sym || this.current !== 'assets') return;
      this._pendingAssetSymbol = null;
      try {
        window.StockQPro?.pages?.assets?.openDetail?.(sym);
      } catch (_) {}
    },

    navFromHash() {
      const h = String(location.hash || '');
      const assetM = h.match(/^#\/asset\/([^/?#]+)/);
      if (assetM) {
        const sym = decodeURIComponent(assetM[1]);
        this._pendingAssetSymbol = sym;
        this.nav('assets', { syncHash: false });
        return true;
      }
      this._pendingAssetSymbol = null;
      const m = h.match(/^#\/([^/?#]+)/);
      if (!m) return false;
      const tab = m[1];
      this.nav(tab, { syncHash: false });
      if (tab === 'assets') {
        try { window.StockQPro?.pages?.assets?.showList?.(); } catch (_) {}
      }
      return true;
    },

    _setWork(symbol, name = '') {
      try { window.StockQPro?.WorkContext?.set?.(symbol, name); } catch (_) {}
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
      const safeMsg = (typeof UI !== 'undefined' && UI.escapeHtml) ? UI.escapeHtml(msg || '') : String(msg || '');
      el.innerHTML = `<span>${icon}</span><span>${safeMsg}</span><button type="button" style="border:none;background:none;color:var(--t3);cursor:pointer;font-size:.9rem;padding:0 0 0 6px;line-height:1" aria-label="關閉">×</button>`;
      el.querySelector('button').addEventListener('click', () => el.remove());
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

      let sel = 0;

      const pages = [
        { n: '總覽', d: 'KPI、行情與快捷入口', p: 'dashboard', k: '1' },
        { n: '任務中心', d: '回測與數據任務佇列', p: 'tasks', k: 'T' },
        { n: '自選股', d: '關注清單與提醒', p: 'watchlist', k: '5' },
        { n: '選股器', d: '條件篩選與池管理', p: 'scanner', k: '6' },
        { n: '預警', d: '條件預警', p: 'alerts', k: '7' },
        { n: '策略庫', d: '130+ 策略', p: 'strategies', k: 'S' },
        { n: '回測', d: '策略回測', p: 'backtest', k: '2' },
        { n: '對比', d: '策略對比', p: 'compare', k: '3' },
        { n: '組合回測', d: '多標的組合與權重', p: 'portfolio', k: '4' },
        { n: '資產庫', d: '標的歸檔與詳情', p: 'assets', k: '9' },
        { n: '我的配置', d: '右側持倉欄 · 回測/對比/結算', act: 'allocation', k: 'P' },
        { n: '回測歷史', d: '已完成回測', p: 'backhistory' },
        { n: '資金流', d: '板塊資金與市場圖表', p: 'capitalflow' },
        { n: 'AI 問答', d: '查詢數據、整合北向/板塊/個股', p: 'ai' },
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
        { n: '運維健檢', d: 'SOP 狀態 · 數據源 · 管線', act: 'ops', k: 'O' },
        { n: '定價', d: '方案', p: 'pricing', k: '0' },
        { n: '設定', d: '偏好、帳戶與登出', p: 'settings', k: '8' },
        { n: '產品介紹頁', d: '功能概覽與系統入口', href: '/', k: 'Shift+H' },
        { n: '登出', d: '結束目前工作階段', act: 'logout' },
      ];

      const goBacktest = (code) => {
        this.nav('backtest', { syncHash: true });
        const setSym = window.StockQPro?.backtestSymbol?.setSymbol;
        if (setSym) setSym(code);
        else {
          const el = document.getElementById('bt-code');
          if (el) el.value = code;
        }
      };

      const getExtraItems = (q) => {
        const raw = String(q || '').trim();
        const qq = raw.toLowerCase();
        const extra = [];

        if (!qq) {
          const ctx = window.StockQPro?.WorkContext?.get?.();
          if (ctx?.symbol) {
            extra.push({
              n: `繼續：${ctx.symbol} ${ctx.name || ''}`.trim(),
              d: '用目前工作標的打開回測',
              action: () => {
                this.nav('backtest', { syncHash: true });
                setTimeout(() => window.StockQPro?.WorkContext?.applyToPage?.('backtest'), 40);
              },
            });
            extra.push({
              n: `資產詳情：${ctx.symbol}`,
              d: '打開資產庫',
              action: () => this.openAsset(ctx.symbol),
            });
          }
          (window.StockQPro?.Prefs?.get?.('recentPages') || []).slice(0, 6).forEach((pid) => {
            extra.push({
              n: PAGE_TITLE[pid] || pid,
              d: '最近造訪',
              action: () => this.nav(pid, { syncHash: true }),
            });
          });
        }

        const catalog = window.StockQPro?.catalog;
        if (catalog?.strats?.length && qq) {
          catalog.strats
            .filter((s) => String(s.name || '').toLowerCase().includes(qq) || String(s.desc || '').toLowerCase().includes(qq))
            .slice(0, 6)
            .forEach((s) => extra.push({
              n: `策略：${s.name}`,
              d: (s.status === 'implemented' || s.status === 'user') ? '可回測' : '即將推出',
              action: () => {
                this.nav('strategies', { syncHash: true });
                setTimeout(() => window.StockQPro?.showStratDetail?.(s.id), 50);
              },
            }));
        }

        if (!qq || /運維|sop|ops|健檢|health|維運/.test(qq)) {
          extra.push({
            n: '運維健檢（立即刷新）',
            d: '重新拉取 SOP 並打開設定',
            action: () => {
              const mon = window.StockQPro?.services?.opsMonitor;
              Promise.resolve(mon?.tick?.())
                .then((d) => {
                  const zh = d?.sop?.verdict_zh || '—';
                  const v = d?.sop?.verdict;
                  const tone = v === 'ok' ? 'ok' : v === 'critical' ? 'er' : 'warn';
                  this.toast(`運維：${zh}`, tone);
                  this.nav('settings', { syncHash: true });
                })
                .catch(() => this.toast('運維健檢失敗', 'er'));
            },
          });
        }

        const code = raw.toUpperCase();
        const looksCode = /^\d{3,6}$/.test(code) || /\.(HK|US)$/i.test(code)
          || (/^[A-Z]{2,5}$/.test(code) && !pages.some((pg) => pg.n.toLowerCase().includes(qq)));
        if (looksCode) {
          extra.unshift({
            n: `分析：${code}`,
            d: '深度分析並帶入代碼',
            action: () => {
              this._setWork(code);
              window.StockQPro?.WorkContext?.go?.('analysis');
            },
          });
          extra.unshift({
            n: `對比：${code}`,
            d: '多股對比並帶入代碼',
            action: () => {
              this._setWork(code);
              window.StockQPro?.WorkContext?.go?.('compare');
            },
          });
          extra.unshift({
            n: `資產詳情：${code}`,
            d: '打開資產庫',
            action: () => this.openAsset(code),
          });
          extra.unshift({
            n: `回測：${code}`,
            d: '打開回測並填入代碼',
            action: () => {
              this._setWork(code);
              goBacktest(code);
            },
          });
        }

        return extra;
      };

      const itemsOf = () => [...list.querySelectorAll('.cmd-item')];

      const paintSel = () => {
        const items = itemsOf();
        items.forEach((el, i) => el.classList.toggle('sel', i === sel));
        items[sel]?.scrollIntoView({ block: 'nearest' });
      };

      const runItem = (item) => {
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
        if (act === 'logout') {
          close();
          if (typeof Api !== 'undefined' && Api.isLoggedIn?.()) {
            Api.logout?.();
            this.toast('已登出', 'ok');
          } else {
            this.toast('尚未登錄', 'inf');
          }
          return;
        }
        if (act === 'ops') {
          close();
          const mon = window.StockQPro?.services?.opsMonitor;
          Promise.resolve(mon?.tick?.())
            .then((d) => {
              const zh = d?.sop?.verdict_zh || '—';
              const v = d?.sop?.verdict;
              const tone = v === 'ok' ? 'ok' : v === 'critical' ? 'er' : 'warn';
              this.toast(`運維：${zh}`, tone);
              window.StockQPro?.services?.opsMonitor?.navigateToOps?.();
            })
            .catch(() => this.toast('運維健檢失敗', 'er'));
          return;
        }
        const pg = item.getAttribute('data-cmd');
        if (!pg) return;
        close();
        this.nav(pg, { syncHash: true });
      };

      const render = (q) => {
        const qq = String(q || '').toLowerCase();
        const filtered = pages.filter((pg) => !qq || pg.n.toLowerCase().includes(qq) || pg.d.toLowerCase().includes(qq));
        const extras = getExtraItems(q);
        list.innerHTML =
          extras.map((item, idx) => (
            `<div class="cmd-item" data-cmd-extra="${idx}">` +
              `<div class="cmd-item-info"><div class="cmd-item-name">${esc(item.n)}</div><div class="cmd-item-desc">${esc(item.d)}</div></div>` +
            `</div>`
          )).join('')
          + filtered.map((pg) => (
            `<div class="cmd-item" data-cmd="${esc(pg.p || '')}" data-href="${esc(pg.href || '')}" data-act="${esc(pg.act || '')}">` +
              `<div class="cmd-item-info"><div class="cmd-item-name">${esc(pg.n)}</div><div class="cmd-item-desc">${esc(pg.d)}</div></div>` +
              (pg.k ? `<div class="cmd-item-kb"><kbd>${esc(pg.k)}</kbd></div>` : '') +
            `</div>`
          )).join('');
        list._extras = extras;
        sel = 0;
        paintSel();
      };

      const open = () => {
        ov.classList.add('show');
        ov.setAttribute('aria-hidden', 'false');
        input.value = '';
        render('');
        input.focus();
      };

      const close = () => {
        ov.classList.remove('show');
        ov.setAttribute('aria-hidden', 'true');
      };

      if (openBtn) openBtn.addEventListener('click', open);
      ov.addEventListener('click', (e) => { if (e.target === ov) close(); });
      input.addEventListener('input', () => render(input.value));
      input.addEventListener('keydown', (e) => {
        const n = itemsOf().length;
        if (!n) return;
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          sel = (sel + 1) % n;
          paintSel();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          sel = (sel - 1 + n) % n;
          paintSel();
        } else if (e.key === 'Enter') {
          e.preventDefault();
          runItem(itemsOf()[sel]);
        }
      });
      list.addEventListener('click', (e) => {
        const item = e.target.closest('.cmd-item');
        if (item) runItem(item);
      });
      list.addEventListener('mousemove', (e) => {
        const item = e.target.closest('.cmd-item');
        if (!item) return;
        const items = itemsOf();
        const i = items.indexOf(item);
        if (i >= 0 && i !== sel) {
          sel = i;
          paintSel();
        }
      });

      this._cmd = { open, close, isOpen: () => ov.classList.contains('show') };
    },

    _bindShortcutsHelp() {
      const rows = [
        ['Ctrl+K', '命令面板（↑↓ Enter）'],
        ['/', '聚焦工作標的輸入'],
        ['?', '快捷鍵說明'],
        ['1–7', '總覽 / 回測 / 對比 / 組合 / 自選 / 選股 / 預警'],
        ['8 / 9 / 0', '設定 / 資產庫 / 定價'],
        ['T', '任務中心'],
        ['S', '策略庫'],
        ['O', '運維 SOP'],
        ['B', '用工作標的打開回測'],
        ['C', '用工作標的打開對比'],
        ['A', '用工作標的打開分析'],
        ['P', '開關配置欄'],
        ['Shift+H', '產品介紹頁'],
        ['R', '任務頁刷新'],
        ['Esc', '關閉彈窗 / 命令面板'],
      ];
      const grid = rows.map(([k, d]) => (
        `<div class="pro-shortcut-row"><span>${d}</span><kbd>${k}</kbd></div>`
      )).join('');

      const open = () => {
        if (document.getElementById('pro-shortcuts-ov')) return;
        const ov = document.createElement('div');
        ov.id = 'pro-shortcuts-ov';
        ov.className = 'modal-ov show';
        ov.setAttribute('role', 'dialog');
        ov.setAttribute('aria-label', '鍵盤快捷鍵');
        ov.innerHTML = (
          '<div class="modal pro-shortcuts-modal">' +
          '<div class="modal-hd"><div class="modal-title">鍵盤快捷鍵</div>' +
          '<button type="button" class="btn s" data-close-pro-shortcuts>關閉</button></div>' +
          `<div class="modal-bd pro-shortcuts-grid">${grid}</div>` +
          '</div>'
        );
        const close = () => ov.remove();
        ov.addEventListener('click', (e) => { if (e.target === ov) close(); });
        ov.querySelector('[data-close-pro-shortcuts]')?.addEventListener('click', close);
        document.body.appendChild(ov);
      };

      this._shortcutsHelp = { open, close: () => document.getElementById('pro-shortcuts-ov')?.remove() };
    },

    _bindKeyboard() {
      window.addEventListener('hashchange', () => this.navFromHash());
      document.addEventListener('keydown', (e) => {
        const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
        const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable;
        const cmdOpen = this._cmd?.isOpen?.();

        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
          e.preventDefault();
          this._cmd?.open?.();
          return;
        }
        if (e.key === 'Escape') {
          if (document.body.classList.contains('nav-open')) {
            document.body.classList.remove('nav-open');
            return;
          }
          if (document.getElementById('pro-shortcuts-ov')) {
            this._shortcutsHelp?.close?.();
            return;
          }
          document.querySelectorAll('.modal-ov.show').forEach((m) => m.classList.remove('show'));
          this._cmd?.close?.();
          return;
        }
        if (typing || cmdOpen) return;

        if (e.key === '?' || (e.shiftKey && e.key === '/')) {
          e.preventDefault();
          this._shortcutsHelp?.open?.();
          return;
        }
        if (e.altKey || e.ctrlKey || e.metaKey) return;

        const map = {
          '1': 'dashboard', '2': 'backtest', '3': 'compare', '4': 'portfolio',
          '5': 'watchlist', '6': 'scanner', '7': 'alerts', '8': 'settings',
          '9': 'assets', '0': 'pricing',
        };
        if (map[e.key]) {
          e.preventDefault();
          this.nav(map[e.key], { syncHash: true });
          return;
        }
        if (e.key === 't' || e.key === 'T') {
          e.preventDefault();
          this.nav('tasks', { syncHash: true });
          return;
        }
        if (e.key === 'b' || e.key === 'B') {
          e.preventDefault();
          window.StockQPro?.WorkContext?.go?.('backtest');
          return;
        }
        if (e.key === 'c' || e.key === 'C') {
          e.preventDefault();
          window.StockQPro?.WorkContext?.go?.('compare');
          return;
        }
        if (e.key === 'a' || e.key === 'A') {
          e.preventDefault();
          window.StockQPro?.WorkContext?.go?.('analysis');
          return;
        }
        if (e.key === '/') {
          e.preventDefault();
          window.StockQPro?.WorkContext?.focusInput?.();
          return;
        }
        if (e.key === 'p' || e.key === 'P') {
          e.preventDefault();
          window.StockQPro?.Allocation?.toggle?.();
          return;
        }
        if (e.key === 'o' || e.key === 'O') {
          e.preventDefault();
          const mon = window.StockQPro?.services?.opsMonitor;
          Promise.resolve(mon?.tick?.())
            .then((d) => {
              const zh = d?.sop?.verdict_zh || '—';
              const v = d?.sop?.verdict;
              const tone = v === 'ok' ? 'ok' : v === 'critical' ? 'er' : 'warn';
              this.toast(`運維：${zh}`, tone);
              this.nav('settings', { syncHash: true });
              requestAnimationFrame(() => {
                window.StockQPro?.services?.opsMonitor?.scrollToOpsPanel?.();
              });
            })
            .catch(() => this.toast('運維健檢失敗', 'er'));
          return;
        }
        if ((e.key === 'h' || e.key === 'H') && e.shiftKey) {
          window.location.href = '/';
          return;
        }
        if (e.key === 's' || e.key === 'S') {
          e.preventDefault();
          this.nav('strategies', { syncHash: true });
          return;
        }
        if (e.key === 'r' || e.key === 'R') {
          if (this.current === 'tasks') window.StockQPro?.Tasks?.refresh?.();
        }
      });
    },

  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.App = App;
  window.StockQPro.openAsset = (sym) => App.openAsset(sym);
  window.StockQApp = App;
  window.StockQPro.pages = window.StockQPro.pages || {};

  window.addEventListener('DOMContentLoaded', () => App.init());
})();

