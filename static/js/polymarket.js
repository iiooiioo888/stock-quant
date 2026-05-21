/**
 * Polymarket 預測市場 UI — 獨立 Tab + 個股分析頁嵌入
 * 依賴：Api、Chart（可選）
 */
const PolymarketUI = {
  _markets: [],
  _selected: null,
  _chart: null,
  _chartCanvasId: null,
  _bound: false,
  _scope: 'main',

  /** main = 預測市場 Tab；stock = 個股分析頁 */
  useScope(scope) {
    this._scope = scope === 'stock' ? 'stock' : 'main';
  },

  _el(key) {
    const ids = this._scope === 'stock' ? {
      table: 'sdPmMarketTable',
      detailPanel: 'sdPmDetailPanel',
      detailTitle: 'sdPmDetailTitle',
      detailMeta: 'sdPmDetailMeta',
      orderbook: 'sdPmOrderbook',
      priceChart: 'sdPmPriceChart',
    } : {
      table: 'pmMarketTable',
      searchQ: 'pmSearchQ',
      tagFilter: 'pmTagFilter',
      searchBtn: 'pmSearchBtn',
      reloadBtn: 'pmReloadBtn',
      detailPanel: 'pmDetailPanel',
      detailTitle: 'pmDetailTitle',
      detailMeta: 'pmDetailMeta',
      orderbook: 'pmOrderbook',
      priceChart: 'pmPriceChart',
      signalsBox: 'pmSignalsBox',
      signalsBtn: 'pmSignalsBtn',
      rulesBox: 'pmRulesBox',
      addRuleBtn: 'pmAddRuleBtn',
      evalBtn: 'pmEvalAlertsBtn',
      ruleYesAbove: 'pmRuleYesAbove',
      ruleYesBelow: 'pmRuleYesBelow',
      ruleChangePct: 'pmRuleChangePct',
    };
    const id = ids[key];
    return id ? document.getElementById(id) : null;
  },

  setMarkets(list) {
    this._markets = list || [];
    this.renderTable();
  },

  /** 僅綁定一次事件（避免每次切 Tab 重複綁定） */
  init() {
    if (this._bound) return;
    this._bound = true;
    const searchBtn = this._el('searchBtn');
    const reloadBtn = this._el('reloadBtn');
    if (searchBtn) searchBtn.onclick = () => this.search();
    if (reloadBtn) reloadBtn.onclick = () => this.loadMarkets();
    const tagSel = this._el('tagFilter');
    if (tagSel) tagSel.onchange = () => this.loadMarkets();
    const sigBtn = this._el('signalsBtn');
    const addRuleBtn = this._el('addRuleBtn');
    const evalBtn = this._el('evalBtn');
    if (sigBtn) sigBtn.onclick = () => this.loadSignals();
    if (addRuleBtn) addRuleBtn.onclick = () => this.addRuleForSelected();
    if (evalBtn) evalBtn.onclick = () => this.evaluateAlerts();
  },

  /** 進入預測市場 Tab 時刷新列表與預警 */
  load() {
    this.useScope('main');
    this.init();
    this.loadTags();
    this.loadMarkets();
    this.loadRules();
    this.loadSignals();
  },

  /** 載入標籤下拉 */
  async loadTags() {
    const sel = this._el('tagFilter');
    if (!sel) return;
    try {
      const d = await Api.get('/api/polymarket/tags');
      const tags = d.tags || [];
      sel.innerHTML = '<option value="">全部標籤</option>' +
        tags.map(t => `<option value="${t.slug || t.tag_id}">${t.label || t.slug}</option>`).join('');
    } catch (e) {
      console.warn('Polymarket tags', e);
    }
  },

  /** 載入市場列表 */
  async loadMarkets() {
    const tbody = this._el('table');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7"><span class="ld"></span> 載入中…</td></tr>';
    const tag = this._el('tagFilter')?.value || '';
    const limit = 30;
    let url = `/api/polymarket/markets?limit=${limit}&order=volume`;
    if (tag) url += `&tag=${encodeURIComponent(tag)}`;
    try {
      const d = await Api.get(url);
      this._markets = d.markets || [];
      this.renderTable();
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" class="err">載入失敗: ${e.message || e}</td></tr>`;
    }
  },

  /** 關鍵字搜尋 */
  async search() {
    if (this._searching) return;
    const q = this._el('searchQ')?.value?.trim();
    const tbody = this._el('table');
    const btn = this._el('searchBtn');
    if (!q) {
      this.loadMarkets();
      return;
    }
    this._searching = true;
    if (btn) btn.disabled = true;
    tbody.innerHTML = '<tr><td colspan="7"><span class="ld"></span> 搜尋中…</td></tr>';
    try {
      const d = await Api.get(`/api/polymarket/search?q=${encodeURIComponent(q)}&limit=25`);
      this._markets = (d.results || []).filter(r => r.result_type !== 'event');
      if (!this._markets.length) {
        this._markets = d.results || [];
      }
      this.renderTable();
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" class="err">搜尋失敗: ${e.message || e}</td></tr>`;
    } finally {
      this._searching = false;
      if (btn) btn.disabled = false;
    }
  },

  /** 渲染市場表格 */
  renderTable() {
    const tbody = this._el('table');
    if (!tbody) return;
    if (!this._markets.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="muted">暫無市場數據</td></tr>';
      return;
    }
    tbody.innerHTML = this._markets.map((m, i) => {
      const yesPct = (m.yes_price * 100).toFixed(1);
      const noPct = (m.no_price * 100).toFixed(1);
      const vol = this._fmtNum(m.volume);
      const liq = this._fmtNum(m.liquidity);
      const end = (m.end_date || '').slice(0, 10);
      const q = (m.question || '').slice(0, 80);
      return `<tr class="pm-row" data-idx="${i}" style="cursor:pointer">
        <td title="${m.slug}">${q}</td>
        <td class="pos">${yesPct}%</td>
        <td class="neg">${noPct}%</td>
        <td>${vol}</td>
        <td>${liq}</td>
        <td>${end}</td>
        <td><button class="btn s" type="button" data-idx="${i}">詳情</button></td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('.pm-row, button[data-idx]').forEach(el => {
      el.onclick = (ev) => {
        const idx = parseInt(ev.currentTarget.getAttribute('data-idx'), 10);
        if (!isNaN(idx)) this.showDetail(this._markets[idx]);
      };
    });
  },

  /** 展開詳情：訂單簿 + 價格圖 */
  async showDetail(m) {
    this._selected = m;
    const panel = this._el('detailPanel');
    const title = this._el('detailTitle');
    const meta = this._el('detailMeta');
    const obEl = this._el('orderbook');
    if (!panel) return;
    panel.classList.remove('h');
    if (title) title.textContent = m.question || m.slug || '市場詳情';
    const tokenYes = (m.token_ids && m.token_ids[0]) || '';
    if (meta) meta.innerHTML =
      `Yes <strong>${(m.yes_price * 100).toFixed(1)}%</strong> · ` +
      `No <strong>${(m.no_price * 100).toFixed(1)}%</strong> · ` +
      `Vol ${this._fmtNum(m.volume)}`;
    if (!tokenYes) {
      if (obEl) obEl.innerHTML = '<p class="muted">無 token_id</p>';
      return;
    }
    if (obEl) obEl.innerHTML = '<span class="ld"></span> 載入訂單簿…';
    try {
      const ob = await Api.get(`/api/polymarket/orderbook?token_id=${encodeURIComponent(tokenYes)}`);
      this.renderOrderbook(ob);
    } catch (e) {
      if (obEl) obEl.innerHTML = `<p class="err">${e.message || e}</p>`;
    }
    this.loadPriceChart(tokenYes);
  },

  /** 訂單簿 HTML */
  renderOrderbook(ob) {
    const el = this._el('orderbook');
    if (!el) return;
    const bids = (ob.bids || []).slice(0, 8);
    const asks = (ob.asks || []).slice(0, 8);
    el.innerHTML = `
      <div class="pm-ob-grid">
        <div><strong>買盤</strong>${bids.map(b => `<div>${b.price.toFixed(3)} × ${b.size.toFixed(0)}</div>`).join('') || '<div class="muted">—</div>'}</div>
        <div><strong>賣盤</strong>${asks.map(a => `<div>${a.price.toFixed(3)} × ${a.size.toFixed(0)}</div>`).join('') || '<div class="muted">—</div>'}</div>
      </div>
      <p class="sec-desc">價差 ${ob.spread?.toFixed(4) || '—'} · 中間價 ${ob.mid?.toFixed(4) || '—'}</p>`;
  },

  /** 價格歷史圖（Chart.js） */
  async loadPriceChart(tokenId) {
    const canvas = this._el('priceChart');
    if (!canvas || typeof Chart === 'undefined') return;
    const canvasId = canvas.id;
    try {
      const d = await Api.get(`/api/polymarket/price-history?token_id=${encodeURIComponent(tokenId)}&interval=1d&fidelity=60`);
      const points = d.points || [];
      const labels = points.map(p => new Date(p.ts * 1000).toLocaleDateString());
      const data = points.map(p => p.price);
      if (this._chart && this._chartCanvasId === canvasId) this._chart.destroy();
      this._chartCanvasId = canvasId;
      this._chart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
          labels,
          datasets: [{ label: 'Yes 價格', data, borderColor: '#3b82f6', tension: 0.2, fill: false }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
      });
    } catch (e) {
      console.warn('pm price history', e);
    }
  },

  _fmtNum(n) {
    const v = Number(n) || 0;
    if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
    return v.toFixed(0);
  },

  /** 概率策略信號列表 */
  async loadSignals() {
    const box = this._el('signalsBox');
    if (!box) return;
    box.innerHTML = '<span class="ld"></span> 載入信號…';
    try {
      const d = await Api.get('/api/polymarket/strategy-signals?limit=15');
      const rows = (d.signals || []).map(s => {
        const icon = s.signal === 'bullish' ? '🟢' : s.signal === 'bearish' ? '🔴' : '⚪';
        return `<div style="margin:6px 0">${icon} <strong>${(s.question || '').slice(0, 60)}</strong> — Yes ${(s.yes_price * 100).toFixed(1)}% · ${s.action_hint} · ${s.rationale}</div>`;
      }).join('');
      box.innerHTML = rows || '<span class="muted">暫無信號</span>';
    } catch (e) {
      box.innerHTML = `<span class="err">${e.message || e}</span>`;
    }
  },

  /** 預警規則列表 */
  async loadRules() {
    const box = this._el('rulesBox');
    if (!box) return;
    try {
      const d = await Api.get('/api/polymarket/alerts/rules');
      const rules = d.rules || [];
      if (!rules.length) {
        box.innerHTML = '尚無規則。選中市場後點「為選中市場添加」。';
        return;
      }
      box.innerHTML = rules.map(r => {
        const parts = [];
        if (r.yes_above != null) parts.push(`Yes≥${(r.yes_above * 100).toFixed(0)}%`);
        if (r.yes_below != null) parts.push(`Yes≤${(r.yes_below * 100).toFixed(0)}%`);
        if (r.prob_change_pct != null) parts.push(`變動≥${r.prob_change_pct}%`);
        return `<div>• ${r.name || r.market_key} — ${parts.join(' · ') || '未設閾值'}</div>`;
      }).join('');
    } catch (e) {
      box.innerHTML = `<span class="err">${e.message || e}</span>`;
    }
  },

  /** 為當前選中市場添加規則（需登錄寫入） */
  async addRuleForSelected() {
    const m = this._selected;
    if (!m) {
      alert('請先點擊市場列查看詳情以選中');
      return;
    }
    const key = m.slug || m.market_id;
    const body = {
      market_key: key,
      name: (m.question || key).slice(0, 120),
      question: m.question || '',
      enabled: true,
    };
    const ya = this._el('ruleYesAbove')?.value;
    const yb = this._el('ruleYesBelow')?.value;
    const ch = this._el('ruleChangePct')?.value;
    if (ya) body.yes_above = parseFloat(ya);
    if (yb) body.yes_below = parseFloat(yb);
    if (ch) body.prob_change_pct = parseFloat(ch);
    if (!body.yes_above && !body.yes_below && !body.prob_change_pct) {
      body.yes_above = 0.75;
      body.prob_change_pct = 10;
    }
    try {
      await Api.post('/api/polymarket/alerts/rules', body);
      await this.loadRules();
      alert('規則已保存');
    } catch (e) {
      alert('保存失敗: ' + (e.message || e) + '（演示模式需登錄）');
    }
  },

  /** 手動觸發預警評估 */
  async evaluateAlerts() {
    try {
      const d = await Api.post('/api/polymarket/alerts/evaluate', {});
      alert(`評估完成：${d.triggered ?? 0} 條觸發`);
    } catch (e) {
      alert('評估失敗: ' + (e.message || e) + '（需登錄）');
    }
  },
};
