/**
 * portfolio.js — 組合 Tab（支持 12 種組合方法）
 * 
 * Redesigned: method cards + animated params panel
 */

const Portfolio = {
  _methodParams: {
    basic: [],
    risk_parity: [],
    mvo: [
      { id: 'pfObjective', label: '優化目標', type: 'select', options: [
        { value: 'max_sharpe', text: '最大夏普' },
        { value: 'min_volatility', text: '最小波動' },
        { value: 'max_return', text: '最大收益' },
      ]},
      { id: 'pfSimulations', label: '模擬次數', type: 'number', value: 5000, hint: '越多越精確，越慢' },
    ],
    vol_target: [
      { id: 'pfTargetVol', label: '目標波動率', type: 'number', value: 0.15, step: 0.01, hint: '年化，如 0.15 = 15%' },
      { id: 'pfLookback', label: '回看天數', type: 'number', value: 20, hint: '計算波動率的窗口' },
    ],
    max_diversification: [
      { id: 'pfSimulations', label: '模擬次數', type: 'number', value: 5000 },
    ],
    anti_correlation: [
      { id: 'pfSimulations', label: '模擬次數', type: 'number', value: 5000 },
    ],
    regime_switch: [
      { id: 'pfRegimeMethod', label: '狀態判定', type: 'select', options: [
        { value: 'volatility', text: '波動率' },
        { value: 'trend', text: '趨勢' },
      ]},
      { id: 'pfRegimeLookback', label: '回看天數', type: 'number', value: 60 },
    ],
    dynamic: [
      { id: 'pfRollingWindow', label: '滾動窗口', type: 'number', value: 60, hint: '天數' },
      { id: 'pfRebalanceFreq', label: '調整頻率', type: 'number', value: 20, hint: '天數' },
    ],
    kelly: [
      { id: 'pfFractionLimit', label: '倉位上限', type: 'number', value: 0.5, step: 0.1, hint: '0~1，保守用 0.25' },
    ],
    degradation: [
      { id: 'pfLookbackDays', label: '回看天數', type: 'number', value: 30 },
      { id: 'pfThresholdDays', label: '閾值天數', type: 'number', value: 5, hint: '連續跑輸幾天觸發' },
      { id: 'pfWeightReduction', label: '降權比例', type: 'number', value: 0.5, step: 0.1 },
    ],
    arbitrate: [
      { id: 'pfRollingWindow', label: '滾動窗口', type: 'number', value: 60 },
    ],
    frontier: [],
  },

  // 方法描述（用於參數面板標題）
  _methodLabels: {
    basic: '基礎等權', risk_parity: '風險平價', mvo: '均值方差',
    vol_target: '波動率目標', max_diversification: '最大分散化',
    anti_correlation: '低相關', regime_switch: '狀態切換',
    dynamic: '動態組合', kelly: 'Kelly 公式',
    degradation: '衰減分析', arbitrate: '信號仲裁', frontier: '有效前沿',
  },

  _currentMethod: 'basic',
  _methodFilter: 'all',
  _strategyList: null,
  /** 由配置欄匯入：code -> weight (0~1) */
  _allocationWeightMap: null,
  _STRAT_PRESETS: {
    trend: ['dual_ma', 'macd', 'adx_trend', 'momentum', 'breakout'],
    mean: ['bollinger', 'rsi', 'mean_reversion', 'kdj', 'cci'],
  },

  init() {
    this._initMethodZone();
    this._initPortfolioQuickAdd();
    this._initStrategyPicker();
    this._initSummaryBindings();
    this._initOpenTasks();
    this._initAllocationBridge();
    this.updateSummary();
  },

  _initAllocationBridge() {
    if (this._allocationBridgeBound) return;
    this._allocationBridgeBound = true;
    window.addEventListener('stockq:allocation-import-portfolio', (ev) => {
      const { codes, weightMap, strategy } = ev.detail || {};
      if (!Array.isArray(codes) || !codes.length) return;
      this._allocationWeightMap = weightMap && typeof weightMap === 'object' ? { ...weightMap } : null;
      this._setCodes(codes);
      if (strategy) this._setStrategies([strategy]);
      this.updateSummary();
      const wHint = this._allocationWeightMap
        ? Object.keys(this._allocationWeightMap).length
        : 0;
      Utils.toast(
        `已載入 ${codes.length} 檔${wHint ? `（${wHint} 檔帶市值權重）` : ''}，策略：${strategy || '—'}`,
        2800,
        'success',
      );
    });
  },

  updateSummary() {
    const codes = this._parseCsv(document.getElementById('pfCodes')?.value);
    const strategies = this._parseCsv(document.getElementById('pfStrategies')?.value);
    const nCodes = codes.length;
    const nStrats = strategies.length;
    const total = nCodes * nStrats;
    const methodLabel = this._methodLabels[this._currentMethod] || this._currentMethod;

    const set = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    set('pfCodesCount', `${nCodes} 檔`);
    set('pfStratsCount', `${nStrats} 個`);
    set('pfSummaryCodes', `標的 ${nCodes}`);
    set('pfSummaryStrats', `策略 ${nStrats}`);
    set('pfSummaryMethod', methodLabel);

    const eq = document.getElementById('pfSummaryEq');
    if (eq) {
      if (!nCodes && !nStrats) {
        eq.innerHTML = '請選擇標的與策略';
      } else if (!total) {
        eq.innerHTML = `${nCodes || 0} × ${nStrats || 0} = <strong>0</strong>`;
      } else {
        eq.innerHTML = `${nCodes} × ${nStrats} = <strong>${total}</strong>`;
      }
    }

    const hint = document.getElementById('pfSummaryHint');
    if (hint) {
      if (!total) {
        hint.textContent = '至少需 1 檔標的與 1 個策略才能提交';
        hint.classList.add('pf-summary-hint--warn');
      } else if (total > 80) {
        hint.textContent = `子策略較多（${total}），建議分批提交以縮短等待`;
        hint.classList.add('pf-summary-hint--warn');
      } else {
        hint.textContent = '提交後立即進入任務列表，可連續建立多筆回測';
        hint.classList.remove('pf-summary-hint--warn');
      }
    }

    const bar = document.getElementById('pfSummaryBar');
    if (bar) bar.classList.toggle('pf-summary-bar--empty', total === 0);

    const preview = document.getElementById('pfActionPreview');
    if (preview) {
      preview.textContent = total
        ? `將提交約 ${total} 個子策略 · ${methodLabel}`
        : '請先完成標的與策略選擇';
    }

    const btn = document.getElementById('pfBtn');
    if (btn) btn.disabled = total === 0;
  },

  _renderSelectedStrategyPills() {
    const host = document.getElementById('pfStratSelected');
    if (!host) return;
    const keys = this._parseCsv(document.getElementById('pfStrategies')?.value);
    if (!keys.length) {
      host.innerHTML = '<span class="pf-strat-empty">尚未選擇策略，請點下方標籤</span>';
      return;
    }
    const list = this._strategyList || [];
    host.innerHTML = keys.map((k) => {
      const hit = list.find((s) => String(s.key).toLowerCase() === k.toLowerCase()
        || String(s.name).toLowerCase() === k.toLowerCase());
      const label = hit?.display || k;
      return `<button type="button" class="pf-strat-pill" data-strat="${String(hit?.key || k)}" title="${String(k)}">
        ${String(label)}<span class="pf-strat-pill-x" aria-hidden="true">×</span>
      </button>`;
    }).join('');
  },

  _initSummaryBindings() {
    const bar = document.getElementById('pfSummaryBar');
    if (!bar || bar.dataset.bound === '1') return;
    bar.dataset.bound = '1';
    const codes = document.getElementById('pfCodes');
    const strats = document.getElementById('pfStrategies');
    const onChange = () => {
      this.updateSummary();
      this._renderSelectedStrategyPills();
    };
    codes?.addEventListener('input', onChange);
    codes?.addEventListener('change', onChange);
    strats?.addEventListener('input', onChange);
    strats?.addEventListener('change', onChange);
  },

  _initOpenTasks() {
    const btn = document.getElementById('pfOpenTasks');
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => {
      try {
        window.StockQPro?.App?.nav?.('tasks', { syncHash: true });
      } catch (_) {
        location.hash = '#/tasks';
      }
    });
  },

  _portfolioRoot() {
    return document.getElementById('tab-portfolio')
      || document.querySelector('#pg-portfolio .legacy-mount #tab-portfolio')
      || document.querySelector('#pg-portfolio #tab-portfolio');
  },

  _initMethodZone() {
    const root = this._portfolioRoot();
    if (!root) return;

    this._pfMethodAbort?.abort();
    this._pfMethodAbort = new AbortController();
    const { signal } = this._pfMethodAbort;

    const grid = root.querySelector('#pfMethodGrid');
    const filterHost = root.querySelector('#pfMethodFilter');
    const filterMeta = root.querySelector('#pfMethodFilterMeta');
    const emptyEl = root.querySelector('#pfMethodEmpty');
    const statusName = root.querySelector('#pfMethodStatusName');
    const statusDesc = root.querySelector('#pfMethodStatusDesc');
    if (!grid || !filterHost) return;

    const FILTER_LABELS = { all: '全部', basic: '基礎', risk: '風險', adv: '進階' };

    const selectCard = (card) => {
      if (!card || !card.dataset.method) return;
      grid.querySelectorAll('.pf-method-card[data-method]').forEach((c) => {
        c.classList.remove('active');
        c.setAttribute('aria-pressed', 'false');
      });
      card.classList.add('active');
      card.setAttribute('aria-pressed', 'true');
      this._currentMethod = card.dataset.method;
      const nameEl = card.querySelector('.pf-method-name');
      const descEl = card.querySelector('.pf-method-desc');
      if (statusName) statusName.textContent = nameEl?.textContent?.trim() || this._methodLabels[this._currentMethod] || '';
      if (statusDesc) statusDesc.textContent = descEl?.textContent?.trim() || '';
      this._renderMethodParams();
      this.updateSummary();
    };

    const applyFilter = (cat) => {
      this._methodFilter = cat || 'all';
      filterHost.querySelectorAll('[data-pf-filter]').forEach((b) => {
        const on = b.dataset.pfFilter === this._methodFilter;
        b.classList.toggle('on', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
      });

      const cards = [...grid.querySelectorAll('.pf-method-card[data-method]')];
      let visibleCount = 0;
      cards.forEach((card) => {
        const c = card.dataset.pfCat || 'basic';
        const show = this._methodFilter === 'all' || c === this._methodFilter;
        card.classList.toggle('pf-method-hidden', !show);
        card.hidden = !show;
        card.setAttribute('aria-hidden', show ? 'false' : 'true');
        if (show) visibleCount += 1;
      });

      if (emptyEl) emptyEl.hidden = visibleCount > 0;
      if (filterMeta) {
        const label = FILTER_LABELS[this._methodFilter] || this._methodFilter;
        filterMeta.textContent = visibleCount
          ? `${label} · 顯示 ${visibleCount} / ${cards.length} 種`
          : `${label} · 此分類暫無可用方法`;
      }

      const active = grid.querySelector('.pf-method-card.active[data-method]');
      if (!active || active.classList.contains('pf-method-hidden') || active.hidden) {
        const first = grid.querySelector('.pf-method-card[data-method]:not(.pf-method-hidden):not([hidden])');
        if (first) selectCard(first);
      }
    };

    filterHost.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-pf-filter]');
      if (!btn) return;
      e.preventDefault();
      applyFilter(btn.dataset.pfFilter || 'all');
    }, { signal });

    grid.querySelectorAll('.pf-method-card[data-method]').forEach((card) => {
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', card.classList.contains('active') ? '0' : '-1');
      card.setAttribute('aria-pressed', card.classList.contains('active') ? 'true' : 'false');
    });

    grid.addEventListener('click', (e) => {
      const card = e.target.closest('.pf-method-card[data-method]');
      if (!card || card.classList.contains('pf-method-hidden') || card.hidden) return;
      e.preventDefault();
      selectCard(card);
      grid.querySelectorAll('.pf-method-card[data-method]').forEach((c) => {
        c.setAttribute('tabindex', c === card ? '0' : '-1');
      });
    }, { signal });

    grid.addEventListener('keydown', (e) => {
      const visible = [...grid.querySelectorAll('.pf-method-card[data-method]:not(.pf-method-hidden):not([hidden])')];
      if (!visible.length) return;
      let idx = visible.findIndex((c) => c.classList.contains('active'));
      if (idx < 0) idx = 0;

      if (e.key === 'Enter' || e.key === ' ') {
        const card = e.target.closest('.pf-method-card[data-method]');
        if (card && !card.classList.contains('pf-method-hidden')) {
          e.preventDefault();
          selectCard(card);
        }
        return;
      }
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft' && e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      e.preventDefault();
      const delta = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : -1;
      const next = visible[(idx + delta + visible.length) % visible.length];
      selectCard(next);
      next.focus();
    }, { signal });

    const initial = grid.querySelector('.pf-method-card.active[data-method]:not(.pf-method-hidden)')
      || grid.querySelector('.pf-method-card[data-method]:not(.pf-method-hidden)')
      || grid.querySelector('.pf-method-card[data-method]');
    if (initial) selectCard(initial);
    applyFilter(this._methodFilter || 'all');
  },

  _parseCsv(value) {
    return String(value || '')
      .split(/[\s,，;；]+/)
      .map(s => s.trim())
      .filter(Boolean);
  },

  _dedupePreserve(arr) {
    const seen = new Set();
    const out = [];
    arr.forEach((x) => {
      const k = String(x || '').trim().toUpperCase();
      if (!k) return;
      if (seen.has(k)) return;
      seen.add(k);
      out.push(String(x).trim());
    });
    return out;
  },

  _setCodes(codes) {
    const input = document.getElementById('pfCodes');
    const manual = document.querySelector('[data-stock-picker-for="pfCodes"] [data-sp-manual]');
    const joined = this._dedupePreserve(codes).join(',');
    if (input) input.value = joined;
    if (manual) manual.value = joined;
    if (input) {
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
    this.updateSummary();
  },

  _setStrategies(strategies) {
    const input = document.getElementById('pfStrategies');
    const joined = this._dedupePreserve(strategies).join(',');
    if (input) {
      input.value = joined;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
    this.updateSummary();
    this._renderSelectedStrategyPills();
  },

  _initPortfolioQuickAdd() {
    const btnHold = document.getElementById('pfAddHoldings');
    const btnWatch = document.getElementById('pfAddWatchlist');
    const btnClear = document.getElementById('pfClearCodes');
    if (btnHold && !btnHold.dataset.bound) {
      btnHold.dataset.bound = '1';
      btnHold.addEventListener('click', async () => {
        try {
          const d = await Api.getPortfolioSummary();
          const codes = (d?.positions || [])
            .map(p => String(p.code || '').trim())
            .filter(Boolean);
          if (!codes.length) return Utils.toast('尚無持有標的（或尚未登錄）', 2500, 'info');
          const cur = this._parseCsv(document.getElementById('pfCodes')?.value);
          this._setCodes([...cur, ...codes]);
          Utils.toast(`已加入持有 ${codes.length} 檔`, 2000, 'success');
        } catch (e) {
          Utils.toast('讀取持有失敗：' + (e?.message || e), 2500, 'error');
        }
      });
    }
    if (btnWatch && !btnWatch.dataset.bound) {
      btnWatch.dataset.bound = '1';
      btnWatch.addEventListener('click', async () => {
        try {
          const d = await Api.getWatchlist();
          const codes = (d?.items || []).map(x => String(x.code || '').trim()).filter(Boolean);
          if (!codes.length) return Utils.toast('自選為空', 2000, 'info');
          const cur = this._parseCsv(document.getElementById('pfCodes')?.value);
          this._setCodes([...cur, ...codes]);
          Utils.toast(`已加入自選 ${codes.length} 檔`, 2000, 'success');
        } catch (e) {
          Utils.toast('讀取自選失敗：' + (e?.message || e), 2500, 'error');
        }
      });
    }
    if (btnClear && !btnClear.dataset.bound) {
      btnClear.dataset.bound = '1';
      btnClear.addEventListener('click', () => {
        this._setCodes([]);
        Utils.toast('已清空標的', 1500, 'info');
      });
    }
  },

  async _ensureStrategyList() {
    if (this._strategyList) return this._strategyList;
    try {
      const d = await Api.getStrategies();
      const list = [];
      (d?.builtin || []).forEach((s) => list.push({ ...s, _group: 'builtin' }));
      (d?.user || []).forEach((s) => list.push({ ...s, _group: 'user' }));
      this._strategyList = list.filter(x => x?.name).map(x => ({
        key: x.backend_key || x.name,
        name: x.name,
        display: x.display_name || x.name,
        group: x._group,
        status: x.status || '',
      }));
    } catch (_) {
      this._strategyList = [];
    }
    return this._strategyList;
  },

  _renderStrategyChips(query = '') {
    const host = document.getElementById('pfStratChips');
    if (!host) return;
    const q = String(query || '').trim().toLowerCase();
    const selected = new Set(this._parseCsv(document.getElementById('pfStrategies')?.value).map(s => s.toLowerCase()));
    const list = (this._strategyList || []).filter((s) => {
      if (!q) return true;
      return String(s.name).toLowerCase().includes(q)
        || String(s.display).toLowerCase().includes(q)
        || String(s.key).toLowerCase().includes(q);
    });
    if (!list.length) {
      host.innerHTML = '<span style="color:var(--t3);font-size:.66rem">未找到策略</span>';
      return;
    }
    this._renderSelectedStrategyPills();
    host.innerHTML = list.slice(0, 80).map((s) => {
      const on = selected.has(String(s.key).toLowerCase()) || selected.has(String(s.name).toLowerCase());
      const label = s.display || s.name;
      return `<button type="button" class="pf-strat-chip${on ? ' on' : ''}" data-strat="${String(s.key)}" title="${String(s.name)}">
        ${String(label)} <code>${String(s.key)}</code>
      </button>`;
    }).join('');
  },

  _initStrategyPicker() {
    const input = document.getElementById('pfStrategies');
    const search = document.getElementById('pfStratSearch');
    const clear = document.getElementById('pfStratClear');
    const host = document.getElementById('pfStratChips');
    if (!input || !host) return;
    if (host.dataset.bound === '1') return;
    host.dataset.bound = '1';

    const syncFromInput = () => {
      this._renderStrategyChips(search?.value || '');
      this.updateSummary();
    };
    input.addEventListener('input', syncFromInput);

    const presetTrend = document.getElementById('pfStratPresetTrend');
    const presetMean = document.getElementById('pfStratPresetMean');
    if (presetTrend && !presetTrend.dataset.bound) {
      presetTrend.dataset.bound = '1';
      presetTrend.addEventListener('click', () => {
        this._setStrategies(this._STRAT_PRESETS.trend);
        this._renderStrategyChips(search?.value || '');
        Utils.toast('已套用趨勢策略包', 1500, 'info');
      });
    }
    if (presetMean && !presetMean.dataset.bound) {
      presetMean.dataset.bound = '1';
      presetMean.addEventListener('click', () => {
        this._setStrategies(this._STRAT_PRESETS.mean);
        this._renderStrategyChips(search?.value || '');
        Utils.toast('已套用均值策略包', 1500, 'info');
      });
    }

    const selectedHost = document.getElementById('pfStratSelected');
    if (selectedHost && !selectedHost.dataset.bound) {
      selectedHost.dataset.bound = '1';
      selectedHost.addEventListener('click', (e) => {
        const pill = e.target.closest('.pf-strat-pill');
        if (!pill) return;
        const key = pill.dataset.strat || '';
        const cur = this._parseCsv(input.value);
        const upper = String(key).toUpperCase();
        this._setStrategies(cur.filter((x) => String(x).toUpperCase() !== upper));
        this._renderStrategyChips(search?.value || '');
      });
    }

    if (clear) {
      clear.addEventListener('click', () => {
        this._setStrategies([]);
        Utils.toast('已清空策略', 1500, 'info');
      });
    }

    if (search && !search.dataset.bound) {
      search.dataset.bound = '1';
      const debounced = Utils.debounce(() => this._renderStrategyChips(search.value), 200);
      search.addEventListener('input', debounced);
    }

    host.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-strat]');
      if (!btn) return;
      const key = btn.dataset.strat || '';
      if (!key) return;
      const cur = this._parseCsv(input.value);
      const upper = String(key).toUpperCase();
      const idx = cur.findIndex((x) => String(x).toUpperCase() === upper);
      if (idx >= 0) cur.splice(idx, 1);
      else cur.push(key);
      this._setStrategies(cur);
      this._renderStrategyChips(search?.value || '');
    });

    this._ensureStrategyList().then(() => {
      this._renderStrategyChips('');
      this.updateSummary();
    });
  },

  _renderMethodParams() {
    const root = this._portfolioRoot();
    const params = this._methodParams[this._currentMethod] || [];
    const container = root?.querySelector('#pfMethodParams') || document.getElementById('pfMethodParams');
    const fields = root?.querySelector('#pfParamFields') || document.getElementById('pfParamFields');
    const title = root?.querySelector('#pfParamsTitle') || document.getElementById('pfParamsTitle');

    if (!container || !fields || !title) return;

    if (!params.length) {
      container.hidden = true;
      return;
    }

    title.textContent = `${this._methodLabels[this._currentMethod] || ''} 參數`;

    fields.innerHTML = params.map(p => {
      if (p.type === 'select') {
        const opts = p.options.map(o => `<option value="${o.value}">${o.text}</option>`).join('');
        return `<div class="fg pf-param-fg">
          <label>${p.label}</label>
          <select class="sel" id="${p.id}">${opts}</select>
          ${p.hint ? `<span class="pf-hint">${p.hint}</span>` : ''}
        </div>`;
      }
      const step = p.step ? `step="${p.step}"` : '';
      return `<div class="fg pf-param-fg">
        <label>${p.label}</label>
        <input class="inp pf-param-inp" id="${p.id}" type="number" value="${p.value}" ${step}>
        ${p.hint ? `<span class="pf-hint">${p.hint}</span>` : ''}
      </div>`;
    }).join('');

    container.hidden = false;
  },

  async loadPresets() {
    const d = await Api.getConfig();
    if (!d) return;

    const p = d.portfolio_presets || {};
    const riskMeta = {
      conservative: { icon: '🛡️', tone: 'safe' },
      balanced: { icon: '⚖️', tone: 'balanced' },
      aggressive: { icon: '🔥', tone: 'hot' },
      trend_follower: { icon: '📈', tone: 'trend' },
      value_trap_avoider: { icon: '📊', tone: 'volume' },
    };

    const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

    document.getElementById('presetCards').innerHTML = Object.entries(p).map(([k, v]) => {
      const meta = riskMeta[k] || { icon: '💼', tone: 'default' };
      const strategies = [...new Set((v.allocations || []).map((a) => a.strategy))].slice(0, 4);
      const stratTags = strategies.map((s) => `<span class="pc-tag">${esc(s)}</span>`).join('');
      const rebLabel = v.rebalance === 'periodic' ? '定期再平衡' : '不再平衡';
      return `<button type="button" class="pc-item" data-risk="${meta.tone}" onclick="Portfolio.runPreset('${k}', event)">
        <div class="pc-item-top">
          <span class="pc-icon" aria-hidden="true">${meta.icon}</span>
          <div class="pc-titles">
            <h4 class="pc-name">${esc(v.name)}</h4>
            <p class="pc-desc">${esc(v.desc)}</p>
          </div>
        </div>
        <div class="pc-tags">${stratTags}</div>
        <div class="pc-foot">
          <span class="pc-badge">${(v.allocations || []).length} 子策略</span>
          <span class="pc-badge pc-badge--muted">${rebLabel}</span>
        </div>
      </button>`;
    }).join('');
  },

  async runPreset(name, evt) {
    if (typeof Api !== 'undefined' && !Api.isLoggedIn()) {
      Utils.toast('預設組合回測需先登錄', 3000, 'warning');
      Api.showLoginModal();
      return;
    }
    const btn = evt?.target?.closest('.pc-item');
    // 單卡片防抖：允許連續點不同模板加入任務
    if (btn?.dataset?.inflight === '1') return;
    if (btn) {
      btn.dataset.inflight = '1';
      btn.classList.add('is-loading');
    }

    try {
      const d = await Api.runPresetPortfolio(name);

      if (!d) return;
      if (!d.success) return Utils.toast('失敗: ' + (d.detail || ''), 3000, 'error');

      // 核心需求：點擊後立即加入任務列表，允許馬上加入下一個任務（不等待完成）
      if (d.task_id) {
        const shortId = String(d.task_id).slice(0, 8);
        const hint = d.is_duplicate
          ? (d.message || `相同任務已在隊列（#${shortId}…）`)
          : `已加入任務列表（#${shortId}…）`;
        Utils.toast(hint, 2200, d.is_duplicate ? 'info' : 'success');
        try { window.StockQPro?.Tasks?.refresh?.(true); } catch (_) {}
        try { window.StockQPro?.pages?.tasks?.refreshSidebarBadge?.(); } catch (_) {}
        return;
      }

      // 兼容：若後端返回同步結果，仍照常顯示
      const r = Api.extractResult(d);
      if (r && !(typeof r === 'object' && r.error)) {
        this._showResult(r);
        Utils.toast((d.preset || '預設組合') + ' 回測完成', 2000, 'success');
      } else {
        Utils.toast('已提交', 1800, 'info');
      }
    } catch (e) {
      Utils.toast('組合回測失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      if (btn) {
        btn.classList.remove('is-loading');
        delete btn.dataset.inflight;
      }
    }
  },

  /**
   * 配置餅圖 — 各子策略權重分配
   */
  _drawWeightPie(subs) {
    if (!subs || !subs.length) return;
    const labels = subs.map(s => (s.strategy || '-') + (s.code ? '(' + s.code + ')' : ''));
    const weights = subs.map(s => s.weight != null ? s.weight * 100 : (100 / subs.length));
    Charts.drawDoughnutChart('pfWeightPie', labels, weights, '策略權重分配');
  },

  /**
   * 子策略對比柱狀圖 — 收益率、夏普、回撤
   */
  _drawSubStrategyBars(subs) {
    if (!subs || !subs.length) return;

    const canvas = document.getElementById('pfSubBars');
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const labels = subs.map(s => (s.strategy || '-').substring(0, 8));
    const colors = Charts.getThemeColors();

    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: '收益率 (%)',
            data: subs.map(s => s.total_return_pct || 0),
            backgroundColor: 'rgba(56,189,248,0.6)',
            borderColor: '#38bdf8',
            borderWidth: 1,
          },
          {
            label: '夏普比率',
            data: subs.map(s => s.sharpe_ratio || 0),
            backgroundColor: 'rgba(167,139,250,0.6)',
            borderColor: '#a78bfa',
            borderWidth: 1,
          },
          {
            label: '最大回撤 (%)',
            data: subs.map(s => -(s.max_drawdown_pct || 0)),
            backgroundColor: 'rgba(239,68,68,0.4)',
            borderColor: '#ef4444',
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: colors.text, font: { size: 10 } } },
          tooltip: {
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
          },
        },
        scales: {
          x: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
          y: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
        },
      },
    });
  },

  _buildAllocations() {
    const codes = document.getElementById('pfCodes').value.split(',').map(s => s.trim()).filter(Boolean);
    const strategies = document.getElementById('pfStrategies').value.split(',').map(s => s.trim()).filter(Boolean);
    const wm = this._allocationWeightMap;
    const alloc = [];
    codes.forEach((c) => {
      const key = String(c).trim().toUpperCase();
      const w = wm && wm[key] != null ? Number(wm[key]) : null;
      strategies.forEach((s) => {
        const row = { strategy: s, code: c };
        if (w != null && Number.isFinite(w) && w > 0) row.weight = w;
        alloc.push(row);
      });
    });
    return alloc;
  },

  async run() {
    if (typeof Api !== 'undefined' && !Api.isLoggedIn()) {
      Utils.toast('組合回測需先登錄', 3000, 'warning');
      Api.showLoginModal();
      return;
    }

    const method = this._currentMethod;
    const btn = document.getElementById('pfBtn');
    // 允許連續提交多個自定義組合任務：只在「送出請求中」短暫鎖住按鈕，避免連點重複送同一筆
    if (btn?.dataset?.inflight === '1') return;
    if (btn) btn.dataset.inflight = '1';

    const allocations = this._buildAllocations();
    if (!allocations.length) {
      if (btn) delete btn.dataset.inflight;
      return Utils.toast('請輸入股票代碼和策略', 3000, 'error');
    }

    // 驗證代碼格式
    const codes = document.getElementById('pfCodes').value.split(',').map(s => s.trim()).filter(Boolean);
    const invalid = codes.filter(c => !Utils.isValidCode(c));
    if (invalid.length) {
      if (btn) delete btn.dataset.inflight;
      return Utils.toast('無效代碼: ' + invalid.join(', '), 3000, 'error');
    }

    if (btn) Utils.btnLoading(btn, true, '提交中…');
    try {
    const cash = undefined;
    let d;

    switch (method) {
      case 'basic': {
        const rebalance = document.getElementById('pfRebalance').value;
        const weights = codes.map((c) => {
          const w = this._allocationWeightMap?.[String(c).trim().toUpperCase()];
          return w != null && Number.isFinite(w) ? w : null;
        });
        const hasWeights = weights.some((w) => w != null && w > 0);
        d = await Api.runPortfolio({
          allocations,
          rebalance,
          rebalance_freq_days: 20,
          weights: hasWeights ? weights : undefined,
        });
        break;
      }
      case 'risk_parity':
        d = await Api.post('/api/portfolio/risk-parity', { allocations, cash });
        break;
      case 'mvo': {
        const objective = document.getElementById('pfObjective')?.value || 'max_sharpe';
        const n_sims = parseInt(document.getElementById('pfSimulations')?.value) || 5000;
        d = await Api.post('/api/portfolio/mvo', { allocations, objective, cash, n_simulations: n_sims });
        break;
      }
      case 'vol_target': {
        const target_vol = parseFloat(document.getElementById('pfTargetVol')?.value) || 0.15;
        const lookback = parseInt(document.getElementById('pfLookback')?.value) || 20;
        d = await Api.post('/api/portfolio/vol-target', { allocations, target_vol, lookback_days: lookback, cash });
        break;
      }
      case 'max_diversification': {
        const n_sims = parseInt(document.getElementById('pfSimulations')?.value) || 5000;
        d = await Api.post('/api/portfolio/max-diversification', { allocations, cash, n_simulations: n_sims });
        break;
      }
      case 'anti_correlation': {
        const n_sims = parseInt(document.getElementById('pfSimulations')?.value) || 5000;
        d = await Api.post('/api/portfolio/anti-correlation', { allocations, cash, n_simulations: n_sims });
        break;
      }
      case 'regime_switch': {
        const regime_method = document.getElementById('pfRegimeMethod')?.value || 'volatility';
        const lookback = parseInt(document.getElementById('pfRegimeLookback')?.value) || 60;
        d = await Api.post('/api/portfolio/regime-switch', { allocations, regime_method, lookback_days: lookback, cash });
        break;
      }
      case 'dynamic': {
        const rolling_window = parseInt(document.getElementById('pfRollingWindow')?.value) || 60;
        const rebalance_freq_days = parseInt(document.getElementById('pfRebalanceFreq')?.value) || 20;
        d = await Api.post('/api/portfolio/dynamic', { allocations, rolling_window, rebalance_freq_days, cash });
        break;
      }
      case 'kelly': {
        const fraction_limit = parseFloat(document.getElementById('pfFractionLimit')?.value) || 0.5;
        d = await Api.post('/api/portfolio/kelly', { allocations, cash, fraction_limit });
        break;
      }
      case 'degradation': {
        const lookback_days = parseInt(document.getElementById('pfLookbackDays')?.value) || 30;
        const threshold_days = parseInt(document.getElementById('pfThresholdDays')?.value) || 5;
        const weight_reduction = parseFloat(document.getElementById('pfWeightReduction')?.value) || 0.5;
        d = await Api.post('/api/portfolio/degradation', { allocations, lookback_days, threshold_days, weight_reduction, cash });
        break;
      }
      case 'arbitrate': {
        const rolling_window = parseInt(document.getElementById('pfRollingWindow')?.value) || 60;
        const strategy_signals = allocations.map(a => ({
          strategy: a.strategy, code: a.code, signal: 'hold', confidence: 0.5,
        }));
        d = await Api.post('/api/portfolio/arbitrate', { strategy_signals, allocations, rolling_window, cash });
        break;
      }
      case 'frontier':
        d = await Api.post('/api/portfolio/frontier', { allocations, cash, n_points: 20 });
        break;
      default:
        d = await Api.runPortfolio({ allocations, rebalance: 'none' });
    }

    if (!d) return;
    if (!d.success) return Utils.toast('失敗: ' + (d?.detail || ''), 3000, 'error');

      // 核心需求：像預設模板一樣「立即加入任務列表」，不等待完成
      if (d.task_id) {
        const shortId = String(d.task_id).slice(0, 8);
        const hint = d.is_duplicate
          ? (d.message || `相同任務已在隊列（#${shortId}…）`)
          : `已加入任務列表（#${shortId}…）`;
        Utils.toast(hint, 2200, d.is_duplicate ? 'info' : 'success');
        try { window.StockQPro?.Tasks?.refresh?.(true); } catch (_) {}
        try { window.StockQPro?.pages?.tasks?.refreshSidebarBadge?.(); } catch (_) {}
        return;
      }

      // 兼容：同步返回結果（少見），仍可直接顯示
      const r = Api.extractResult(d);
      if (r && !(typeof r === 'object' && r.error)) {
        this._showResult(r, method);
      } else {
        Utils.toast('已提交', 1800, 'info');
      }
    } catch (e) {
      Utils.toast('組合回測失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      if (btn) {
        Utils.btnLoading(btn, false, '提交組合回測');
        delete btn.dataset.inflight;
      }
    }
  },

  _setPfTableHead(cells) {
    const tr = document.querySelector('#pfResult table thead tr');
    if (tr) tr.innerHTML = cells.map(c => `<th>${c}</th>`).join('');
  },

  _resetPfTableHead() {
    this._setPfTableHead(['策略', '股票', '權重', '收益率', '夏普', '回撤']);
  },

  _drawFrontierChart(r) {
    const canvas = document.getElementById('pfChart');
    if (!canvas || !r.points?.length) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();
    const colors = Charts.getThemeColors();
    new Chart(canvas.getContext('2d'), {
      type: 'scatter',
      data: {
        datasets: [{
          label: '有效前沿',
          data: r.points.map(p => ({ x: p.risk, y: p.return })),
          backgroundColor: 'rgba(56,189,248,0.5)',
          borderColor: '#38bdf8',
          pointRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: colors.text } },
          title: { display: true, text: '風險-收益有效前沿 (%)', color: colors.text },
        },
        scales: {
          x: { title: { display: true, text: '風險 %', color: colors.text }, ticks: { color: colors.text }, grid: { color: colors.grid } },
          y: { title: { display: true, text: '收益 %', color: colors.text }, ticks: { color: colors.text }, grid: { color: colors.grid } },
        },
      },
    });
  },

  _showKellyResult(r) {
    this._setPfTableHead(['策略', '股票', 'Kelly%', '建議倉位', '勝率', '備註']);
    const rows = r.kelly_results || [];
    document.getElementById('pfStats').innerHTML = `
      <div class="c"><h3>總資金</h3><div class="v">${Utils.formatNum(r.total_capital, 0)}</div></div>
      <div class="c"><h3>倉位上限</h3><div class="v">${((r.fraction_limit || 0) * 100).toFixed(0)}%</div></div>
      <div class="c"><h3>子策略數</h3><div class="v">${rows.length}</div></div>
      <div class="c"><h3>方法</h3><div class="v">Kelly</div></div>`;
    document.getElementById('pfTable').innerHTML = rows.map(s =>
      `<tr>
        <td>${s.strategy || '-'}</td>
        <td>${s.code || '-'}</td>
        <td class="r">${s.kelly_fraction != null ? (s.kelly_fraction * 100).toFixed(1) + '%' : '-'}</td>
        <td class="r">${s.recommended_position != null ? Utils.formatNum(s.recommended_position, 0) : '-'}</td>
        <td class="r">${s.win_rate != null ? s.win_rate + '%' : '-'}</td>
        <td class="r">${s.note || s.error || '-'}</td>
      </tr>`
    ).join('');
    document.getElementById('pfResult').classList.remove('h');
    document.getElementById('pfResult').scrollIntoView({ behavior: 'smooth', block: 'start' });
  },

  _showDegradationResult(r) {
    this._setPfTableHead(['策略', '股票', '狀態', '連續跑輸天', '調整權重', '說明']);
    const rows = r.degradation_status || [];
    document.getElementById('pfStats').innerHTML = `
      <div class="c"><h3>回看</h3><div class="v">${r.lookback_days || '-'} 天</div></div>
      <div class="c"><h3>觸發閾值</h3><div class="v">${r.threshold_days || '-'} 天</div></div>
      <div class="c"><h3>降權比例</h3><div class="v">${((r.weight_reduction || 0) * 100).toFixed(0)}%</div></div>
      <div class="c"><h3>方法</h3><div class="v">衰減分析</div></div>`;
    const adj = r.adjusted_weights || [];
    document.getElementById('pfTable').innerHTML = rows.map((s, i) =>
      `<tr>
        <td>${s.strategy || '-'}</td>
        <td>${s.code || '-'}</td>
        <td class="r">${s.is_degraded ? '⚠️ 衰退' : '✅ 正常'}</td>
        <td class="r">${s.consecutive_underperform_days ?? '-'}</td>
        <td class="r">${adj[i] != null ? (adj[i] * 100).toFixed(0) + '%' : '-'}</td>
        <td class="r">${s.is_degraded ? '連續跑輸基準' : '-'}</td>
      </tr>`
    ).join('');
    document.getElementById('pfResult').classList.remove('h');
    document.getElementById('pfResult').scrollIntoView({ behavior: 'smooth', block: 'start' });
  },

  _showArbitrateResult(r) {
    this._setPfTableHead(['策略', '股票', '信號', '權重', '投票值', '-']);
    const actionLabel = { buy: '買入', sell: '賣出', hold: '觀望' }[r.final_action] || r.final_action;
    document.getElementById('pfStats').innerHTML = `
      <div class="c"><h3>仲裁結果</h3><div class="v gn">${actionLabel}</div></div>
      <div class="c"><h3>信心</h3><div class="v">${((r.confidence || 0) * 100).toFixed(1)}%</div></div>
      <div class="c"><h3>衝突程度</h3><div class="v">${r.conflict_level || '-'}</div></div>
      <div class="c"><h3>投票</h3><div class="v" style="font-size:12px">買 ${r.buy_score} / 賣 ${r.sell_score} / 持 ${r.hold_score}</div></div>`;
    const votes = r.vote_details || [];
    document.getElementById('pfTable').innerHTML = votes.map(s =>
      `<tr>
        <td>${s.strategy || '-'}</td>
        <td>${s.code || '-'}</td>
        <td class="r">${s.signal || '-'}</td>
        <td class="r">${s.weight != null ? Utils.formatNum(s.weight, 2) : '-'}</td>
        <td class="r">${s.vote_value != null ? Utils.formatNum(s.vote_value, 2) : '-'}</td>
        <td class="r">-</td>
      </tr>`
    ).join('');
    document.getElementById('pfResult').classList.remove('h');
    document.getElementById('pfResult').scrollIntoView({ behavior: 'smooth', block: 'start' });
  },

  _showFrontierResult(r) {
    this._setPfTableHead(['子策略', '-', '-', '-', '-', '-']);
    const ms = r.max_sharpe || {};
    const mr = r.min_risk || {};
    document.getElementById('pfStats').innerHTML = `
      <div class="c"><h3>前沿點數</h3><div class="v">${(r.points || []).length}</div></div>
      <div class="c"><h3>最大夏普</h3><div class="v">${Utils.formatNum(ms.sharpe, 2)}</div></div>
      <div class="c"><h3>最優收益</h3><div class="v gn">${ms.return != null ? ms.return + '%' : '-'}</div></div>
      <div class="c"><h3>最小風險</h3><div class="v">${mr.risk != null ? mr.risk + '%' : '-'}</div></div>`;
    document.getElementById('pfTable').innerHTML = (r.labels || []).map((lb, i) =>
      `<tr><td colspan="6">${lb}</td></tr>`
    ).join('') || '<tr><td colspan="6">見下方有效前沿圖</td></tr>';
    this._drawFrontierChart(r);
    document.getElementById('pfResult').classList.remove('h');
    document.getElementById('pfResult').scrollIntoView({ behavior: 'smooth', block: 'start' });
  },

  _showResult(r, method) {
    if (r.kelly_results) return this._showKellyResult(r);
    if (r.degradation_status) return this._showDegradationResult(r);
    if (r.points && (r.max_sharpe || r.min_risk)) return this._showFrontierResult(r);
    if (r.final_action != null && r.vote_details) return this._showArbitrateResult(r);

    this._resetPfTableHead();
    const pm = r.portfolio || r;
    document.getElementById('pfStats').innerHTML = `
      <div class="c"><h3>組合收益</h3><div class="v ${Utils.badgeClass(pm.total_return_pct)}">${Utils.formatPct(pm.total_return_pct)}</div></div>
      <div class="c"><h3>年化</h3><div class="v">${Utils.formatPct(pm.annual_return_pct)}</div></div>
      <div class="c"><h3>夏普</h3><div class="v">${Utils.formatNum(pm.sharpe_ratio, 4)}</div></div>
      <div class="c"><h3>回撤</h3><div class="v rd">${Utils.formatPct(-pm.max_drawdown_pct)}</div></div>`;

    const subs = r.sub_strategies || r.strategies || [];
    document.getElementById('pfTable').innerHTML = subs.map(s =>
      `<tr>
        <td>${s.strategy || '-'}</td>
        <td>${s.code || '-'}</td>
        <td class="r">${s.weight != null ? (s.weight * 100).toFixed(0) + '%' : '-'}</td>
        <td class="r"><span class="b ${Utils.badgeClass(s.total_return_pct)}">${Utils.formatPct(s.total_return_pct)}</span></td>
        <td class="r">${Utils.formatNum(s.sharpe_ratio, 2)}</td>
        <td class="r">${Utils.formatPct(-s.max_drawdown_pct)}</td>
      </tr>`
    ).join('');

    const series = [];
    if (r.portfolio_nav) series.push({ label: '組合', data: r.portfolio_nav, dates: r.dates });
    if (r.equal_weight_nav) series.push({ label: '等權', data: r.equal_weight_nav, dates: r.dates });
    if (r.nav) series.push({ label: '組合', data: r.nav, dates: r.dates });
    if (series.length) {
      if (typeof Charts !== 'undefined' && typeof Charts.drawAreaChart === 'function') {
        Charts.drawAreaChart('pfChart', series.map((s, i) => ({
          ...s,
          color: CHART_COLORS[i % CHART_COLORS.length],
          fill: i === 0 ? 'origin' : false,
        })));
      } else {
        Charts.drawLineChart('pfChart', series);
      }
    }

    // 配置餅圖 — 各子策略權重分配
    this._drawWeightPie(subs);

    // 子策略對比柱狀圖 — 收益率、夏普、回撤
    this._drawSubStrategyBars(subs);

    document.getElementById('pfResult').classList.remove('h');
    // 滾動到結果
    document.getElementById('pfResult').scrollIntoView({ behavior: 'smooth', block: 'start' });
  },
  showResult(r) {
    this._showResult(r, this._currentMethod);
  },
};

window.Portfolio = Portfolio;
