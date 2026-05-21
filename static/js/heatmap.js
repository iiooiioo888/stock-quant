/**
 * heatmap.js — 熱力圖 Tab
 */

const HM_TAB = 'tab-heatmap';

const HM_PARAMS = {
  dual_ma: { fast: 'int', slow: 'int' },
  macd: { fast: 'int', slow: 'int', signal: 'int' },
  bollinger: { period: 'int', devfactor: 'float' },
  bollinger_squeeze: { period: 'int', devfactor: 'float', squeeze_threshold: 'float', squeeze_lookback: 'int' },
  kdj: { period: 'int', period_dfast: 'int', period_dslow: 'int', overbought: 'int', oversold: 'int' },
  rsi: { period: 'int', overbought: 'int', oversold: 'int' },
  grid: { grid_pct: 'float', position_pct: 'float' },
  turtle: { entry_period: 'int', exit_period: 'int', atr_period: 'int', risk_pct: 'float' },
  dual_thrust: { period: 'int', k_up: 'float', k_down: 'float' },
  momentum: { lookback: 'int', hold_period: 'int' },
  mean_reversion: { period: 'int', entry_zscore: 'float', exit_zscore: 'float' },
  volume_price: { price_ma: 'int', volume_ma: 'int', volume_ratio: 'float' },
  vwap: { period: 'int', deviation_pct: 'float' },
  obv: { obv_ma_period: 'int', price_ma_period: 'int' },
  envelope: { period: 'int', deviation_pct: 'float' },
  adx_trend: { adx_period: 'int', adx_threshold: 'int', di_period: 'int' },
  parabolic_sar: { af_start: 'float', af_step: 'float', af_max: 'float' },
  breakout: { period: 'int', atr_period: 'int', atr_multiplier: 'float' },
  composite: {
    min_agreement: 'int', ma_fast: 'int', ma_slow: 'int',
    macd_fast: 'int', macd_slow: 'int', macd_signal: 'int',
    rsi_period: 'int', rsi_overbought: 'int', rsi_oversold: 'int',
    boll_period: 'int', boll_dev: 'float',
  },
};

/** 內建策略參數兜底（API/緩存未就緒時） */
const HM_PARAM_FALLBACK = {
  dual_ma: ['fast', 'slow'],
  macd: ['fast', 'slow', 'signal'],
  bollinger: ['period', 'devfactor'],
  bollinger_squeeze: ['period', 'devfactor'],
  kdj: ['period', 'overbought', 'oversold'],
  rsi: ['period', 'overbought', 'oversold'],
  grid: ['grid_pct', 'position_pct'],
  turtle: ['entry_period', 'exit_period'],
  dual_thrust: ['period', 'k_up'],
  momentum: ['lookback', 'hold_period'],
  mean_reversion: ['period', 'entry_zscore'],
  volume_price: ['price_ma', 'volume_ma'],
  vwap: ['period', 'deviation_pct'],
  obv: ['obv_ma_period', 'price_ma_period'],
  envelope: ['period', 'deviation_pct'],
  adx_trend: ['adx_period', 'adx_threshold'],
  parabolic_sar: ['af_start', 'af_step'],
  breakout: ['period', 'atr_multiplier'],
  composite: ['ma_fast', 'ma_slow'],
};

const Heatmap = {
  /** 僅在熱力圖 Tab 內查找，避免與其他區域同名 id 衝突 */
  $el(id) {
    const tab = document.getElementById(HM_TAB);
    if (tab) {
      const el = tab.querySelector('#' + id);
      if (el) return el;
    }
    return document.getElementById(id);
  },

  async getParamKeys(strategy) {
    const name = (strategy || '').trim();
    if (!name) return [];

    let keys = Object.keys(HM_PARAMS[name] || []);
    if (keys.length >= 2) return keys;

    if (HM_PARAM_FALLBACK[name]?.length >= 2) {
      return HM_PARAM_FALLBACK[name];
    }

    try {
      const d = await Api.getHeatmapParams(name);
      if (d?.params?.length >= 2) return d.params;
      if (d?.defaults) return Object.keys(d.defaults);
    } catch (e) {
      console.warn('getHeatmapParams failed:', e);
    }

    return keys;
  },

  _fillParamSelect(id, keys, selected) {
    const sel = this.$el(id);
    if (!sel || !keys?.length) return;
    sel.innerHTML = keys.map(k =>
      `<option value="${k}"${k === selected ? ' selected' : ''}>${k}</option>`
    ).join('');
  },

  async updateParams() {
    const stratEl = this.$el('hmStrategy');
    let strat = (stratEl?.value || '').trim();
    if (!strat && stratEl?.options?.length) {
      strat = stratEl.options[0].value;
      stratEl.value = strat;
    }
    if (!strat) return;

    const keys = await this.getParamKeys(strat);
    if (keys.length < 2) {
      ['hmParamX', 'hmParamY'].forEach(id => {
        const sel = this.$el(id);
        if (sel) sel.innerHTML = '<option value="">（該策略可調參數不足）</option>';
      });
      return;
    }

    const prevX = this.$el('hmParamX')?.value;
    const prevY = this.$el('hmParamY')?.value;
    this._fillParamSelect('hmParamX', keys, keys.includes(prevX) ? prevX : keys[0]);
    this._fillParamSelect('hmParamY', keys, keys.includes(prevY) ? prevY : keys[1]);
  },

  bindStrategyChange() {
    const sel = this.$el('hmStrategy');
    if (!sel || sel.dataset.hmBound) return;
    sel.dataset.hmBound = '1';
    sel.addEventListener('change', () => this.updateParams());
  },

  async initTab() {
    this.bindStrategyChange();
    await this.updateParams();
  },

  async resolveParamPair(strategy) {
    let paramX = (this.$el('hmParamX')?.value || '').trim();
    let paramY = (this.$el('hmParamY')?.value || '').trim();

    if (!paramX || !paramY) {
      await this.updateParams();
      paramX = (this.$el('hmParamX')?.value || '').trim();
      paramY = (this.$el('hmParamY')?.value || '').trim();
    }

    if (!paramX || !paramY) {
      const keys = await this.getParamKeys(strategy);
      if (keys.length >= 2) {
        paramX = keys[0];
        paramY = keys[1];
        this._fillParamSelect('hmParamX', keys, paramX);
        this._fillParamSelect('hmParamY', keys, paramY);
      }
    }

    return { paramX, paramY };
  },

  async run() {
    if (this._running) return;
    const code = (this.$el('hmCode')?.value || '').trim();
    const strategy = (this.$el('hmStrategy')?.value || '').trim();
    const grid = parseInt(this.$el('hmGrid')?.value, 10) || 8;
    const btn = this.$el('hmBtn');

    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'warning');
    if (!strategy) return Utils.toast('請選擇策略', 3000, 'warning');

    const { paramX, paramY } = await this.resolveParamPair(strategy);
    if (!paramX || !paramY) {
      return Utils.toast('無法取得策略參數列表，請刷新頁面或更換策略', 3000, 'error');
    }
    if (paramX === paramY) {
      return Utils.toast('請選擇兩個不同的參數軸', 3000, 'warning');
    }

    this._running = true;
    Utils.btnLoading(btn, true, '計算中...');

    try {
    const d = await Api.runHeatmap({ code, strategy, paramX, paramY, grid });

    if (!d || !d.success) return;
    if (d.from_cache) Utils.toast('⚡ 使用緩存結果', 2000, 'info');

    const r = d.result;
    if (!r?.best_params || !r?.matrix) {
      return Utils.toast('熱力圖結果不完整', 3000, 'error');
    }

    const stats = this.$el('hmStats');
    if (stats) {
      stats.innerHTML = `
        <div class="c"><h3>最佳參數</h3><div class="v gn">${paramX}=${r.best_params[paramX]}, ${paramY}=${r.best_params[paramY]}</div></div>
        <div class="c"><h3>最佳分數</h3><div class="v bl">${Utils.formatNum(r.best_score, 4)}</div></div>
        <div class="c"><h3>網格</h3><div class="v">${r.x_values.length}×${r.y_values.length}</div></div>`;
    }

    Charts.drawHeatmap('hmCanvas', r);
    this.$el('hmResult')?.classList.remove('h');
    } catch (e) {
      Utils.toast('熱力圖生成失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      this._running = false;
      Utils.btnLoading(btn, false, '生成熱力圖');
    }
  },
};

window.Heatmap = Heatmap;
