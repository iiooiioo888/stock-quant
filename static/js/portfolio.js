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

  init() {
    this._initMethodCards();
  },

  _initMethodCards() {
    const grid = document.getElementById('pfMethodGrid');
    if (!grid) return;

    grid.addEventListener('click', e => {
      const card = e.target.closest('.pf-method-card');
      if (!card) return;

      // 更新選中狀態
      grid.querySelectorAll('.pf-method-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');

      this._currentMethod = card.dataset.method;
      this._renderMethodParams();
    });
  },

  _renderMethodParams() {
    const params = this._methodParams[this._currentMethod] || [];
    const container = document.getElementById('pfMethodParams');
    const fields = document.getElementById('pfParamFields');
    const title = document.getElementById('pfParamsTitle');

    if (!params.length) {
      container.style.display = 'none';
      return;
    }

    // 設置標題
    title.textContent = `${this._methodLabels[this._currentMethod] || ''} 參數`;

    // 渲染參數字段
    fields.innerHTML = params.map(p => {
      if (p.type === 'select') {
        const opts = p.options.map(o => `<option value="${o.value}">${o.text}</option>`).join('');
        return `<div class="fg">
          <label>${p.label}</label>
          <select id="${p.id}">${opts}</select>
          ${p.hint ? `<span class="pf-hint">${p.hint}</span>` : ''}
        </div>`;
      }
      const step = p.step ? `step="${p.step}"` : '';
      return `<div class="fg">
        <label>${p.label}</label>
        <input id="${p.id}" type="number" value="${p.value}" ${step} style="width:90px">
        ${p.hint ? `<span class="pf-hint">${p.hint}</span>` : ''}
      </div>`;
    }).join('');

    container.style.display = 'block';
  },

  async loadPresets() {
    const d = await Api.getConfig();
    if (!d) return;

    const p = d.portfolio_presets || {};
    const riskIcons = {
      conservative: '🛡️', balanced: '⚖️', aggressive: '🔥',
      trend_follower: '📈', value_trap_avoider: '📊',
    };

    document.getElementById('presetCards').innerHTML = Object.entries(p).map(([k, v]) => {
      const icon = riskIcons[k] || '💼';
      const stratTags = (v.allocations || []).slice(0, 3).map(a =>
        `<span style="display:inline-block;background:var(--accent-bg);color:var(--accent);font-size:9px;padding:1px 5px;border-radius:3px;margin-right:3px">${a.strategy}</span>`
      ).join('');
      return `<div class="pc-item" onclick="Portfolio.runPreset('${k}')">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
          <span style="font-size:20px">${icon}</span>
          <h4 style="margin:0">${v.name}</h4>
        </div>
        <p>${v.desc}</p>
        <div style="margin-top:6px">${stratTags}</div>
        <span class="pc-badge">${v.allocations.length} 子策略 · ${v.rebalance === 'periodic' ? '定期再平衡' : '不再平衡'}</span>
      </div>`;
    }).join('');
  },

  async runPreset(name) {
    const btn = event?.target?.closest('.pc-item');
    if (btn) btn.style.opacity = '0.5';

    const d = await Api.runPresetPortfolio(name);
    if (btn) btn.style.opacity = '1';

    if (!d || !d.success) return Utils.toast('失敗', 3000, 'error');
    try {
      const resolved = await Api.resolveTaskResponse(d);
      const r = Api.extractResult(resolved);
      if (!r) return Utils.toast('未取得組合回測結果', 3000, 'error');
      this._showResult(r);
      Utils.toast(d.preset + ' 回測完成');
    } catch (e) {
      Utils.toast('組合回測失敗: ' + (e.message || e), 3000, 'error');
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
    const alloc = [];
    codes.forEach(c => strategies.forEach(s => alloc.push({ strategy: s, code: c })));
    return alloc;
  },

  async run() {
    const method = this._currentMethod;
    const btn = document.getElementById('pfBtn');

    const allocations = this._buildAllocations();
    if (!allocations.length) return Utils.toast('請輸入股票代碼和策略', 3000, 'error');

    // 驗證代碼格式
    const codes = document.getElementById('pfCodes').value.split(',').map(s => s.trim()).filter(Boolean);
    const invalid = codes.filter(c => !Utils.isValidCode(c));
    if (invalid.length) return Utils.toast('無效代碼: ' + invalid.join(', '), 3000, 'error');

    Utils.btnLoading(btn, true, '回測中...');
    const cash = undefined;
    let d;

    switch (method) {
      case 'basic': {
        const rebalance = document.getElementById('pfRebalance').value;
        d = await Api.runPortfolio({ allocations, rebalance, rebalance_freq_days: 20 });
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

    Utils.btnLoading(btn, false, '🚀 開始回測');
    if (!d || !d.success) return Utils.toast('失敗: ' + (d?.detail || ''), 3000, 'error');
    try {
      if (d.async && d.task_id) {
        Utils.toast('📋 組合回測已提交', 2000, 'info');
      }
      const resolved = await Api.resolveTaskResponse(d);
      const r = Api.extractResult(resolved);
      if (!r) return Utils.toast('未取得組合回測結果', 3000, 'error');
      this._showResult(r);
    } catch (e) {
      Utils.toast('組合回測失敗: ' + (e.message || e), 3000, 'error');
    }
  },

  _showResult(r) {
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
    if (series.length) Charts.drawLineChart('pfChart', series);

    // 配置餅圖 — 各子策略權重分配
    this._drawWeightPie(subs);

    // 子策略對比柱狀圖 — 收益率、夏普、回撤
    this._drawSubStrategyBars(subs);

    document.getElementById('pfResult').classList.remove('h');
    // 滾動到結果
    document.getElementById('pfResult').scrollIntoView({ behavior: 'smooth', block: 'start' });
  },
  showResult(r) {
    this._showResult(r);
  },
};

window.Portfolio = Portfolio;
