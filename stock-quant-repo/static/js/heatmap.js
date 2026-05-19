/**
 * heatmap.js — 熱力圖 Tab
 */

const HM_PARAMS = {
  dual_ma: { fast: 'int', slow: 'int' },
  macd: { fast: 'int', slow: 'int', signal: 'int' },
  bollinger: { period: 'int', devfactor: 'float' },
  bollinger_squeeze: { period: 'int', devfactor: 'float', squeeze_threshold: 'float' },
  kdj: { period: 'int', overbought: 'int', oversold: 'int' },
  rsi: { period: 'int', overbought: 'int', oversold: 'int' },
  grid: { grid_pct: 'float', position_pct: 'float' },
  turtle: { entry_period: 'int', exit_period: 'int', atr_period: 'int', risk_pct: 'float' },
  dual_thrust: { period: 'int', k_up: 'float', k_down: 'float' },
  momentum: { lookback: 'int', hold_period: 'int' },
  mean_reversion: { period: 'int', entry_zscore: 'float', exit_zscore: 'float' },
  volume_price: { price_ma: 'int', volume_ma: 'int', volume_ratio: 'float' },
  vwap: { period: 'int', deviation_pct: 'float' },
  obv: { obv_ma_period: 'int', price_ma_period: 'int' },
  envelope: { period: 'int', deviation_pct: 'int' },
  adx_trend: { adx_period: 'int', adx_threshold: 'int', di_period: 'int' },
  parabolic_sar: { af_start: 'float', af_step: 'float', af_max: 'float' },
  breakout: { period: 'int', atr_period: 'int', atr_multiplier: 'float' },
  composite: { min_agreement: 'int', ma_fast: 'int', ma_slow: 'int' },
};

const Heatmap = {
  updateParams() {
    const strat = document.getElementById('hmStrategy').value;
    const params = HM_PARAMS[strat] || {};
    const keys = Object.keys(params);

    ['hmParamX', 'hmParamY'].forEach(id => {
      const sel = document.getElementById(id);
      if (!sel) return;
      sel.innerHTML = keys.map((k, i) =>
        `<option value="${k}" ${(i === 0 && id === 'hmParamX') || (i === 1 && id === 'hmParamY') ? 'selected' : ''}>${k}</option>`
      ).join('');
    });
  },

  async run() {
    const code = document.getElementById('hmCode').value;
    const strategy = document.getElementById('hmStrategy').value;
    const paramX = document.getElementById('hmParamX').value;
    const paramY = document.getElementById('hmParamY').value;
    const grid = parseInt(document.getElementById('hmGrid').value) || 8;
    const btn = document.getElementById('hmBtn');

    Utils.btnLoading(btn, true, '計算中...');

    const d = await Api.runHeatmap({
      code, strategy,
      paramX, paramY,
      grid,
    });

    Utils.btnLoading(btn, false, '生成熱力圖');

    if (!d || !d.success) return Utils.toast('失敗: ' + (d?.detail || ''), 3000, 'error');

    const r = d.result;
    document.getElementById('hmStats').innerHTML = `
      <div class="c"><h3>最佳參數</h3><div class="v gn">${paramX}=${r.best_params[paramX]}, ${paramY}=${r.best_params[paramY]}</div></div>
      <div class="c"><h3>最佳分數</h3><div class="v bl">${Utils.formatNum(r.best_score, 4)}</div></div>
      <div class="c"><h3>網格</h3><div class="v">${r.x_values.length}×${r.y_values.length}</div></div>`;

    Charts.drawHeatmap('hmCanvas', r);
    document.getElementById('hmResult').classList.remove('h');
  },
};

window.Heatmap = Heatmap;
