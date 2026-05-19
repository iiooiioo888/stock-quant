/**
 * task-common.js — 任務系統共享常量與渲染工具
 *
 * 被 app.js（浮動面板）和 tasks.js（Tab 頁面）共同引用，
 * 消除重複的類型名稱、狀態圖標、結果渲染邏輯。
 */

const TaskCommon = {

  // 任務類型名稱
  TYPE_NAMES: {
    backtest: '📊 回測',
    backtest_advanced: '📊 進階回測',
    backtest_multi: '📊 多策略對比',
    optimize: '⚡ 參數優化',
    portfolio: '📈 組合回測',
    walkforward: '🔄 Walk-Forward',
    auto_optimize: '🤖 自動優化',
    heatmap: '🌡️ 熱力圖',
  },

  STATUS_ICONS: {
    running: '⏳', completed: '✅', failed: '❌',
    cancelled: '🚫', pending: '⏸️',
  },

  STATUS_COLORS: {
    running: '#38bdf8', completed: '#22c55e', failed: '#ef4444',
    cancelled: '#94a3b8', pending: '#f59e0b',
  },

  // chip CSS 類映射
  STATUS_CHIP: {
    running: 'chip cfg', completed: 'chip on', failed: 'chip off',
    cancelled: 'chip', pending: 'chip',
  },

  /**
   * 格式化任務類型名稱
   */
  typeName(taskType) {
    return this.TYPE_NAMES[taskType] || taskType;
  },

  /**
   * 計算任務執行耗時（秒）
   */
  elapsed(startedAt, completedAt) {
    if (!startedAt) return null;
    const start = new Date(startedAt).getTime();
    const end = completedAt ? new Date(completedAt).getTime() : Date.now();
    return Math.max(0, Math.round((end - start) / 1000));
  },

  /**
   * 格式化耗時顯示
   */
  formatElapsed(sec) {
    if (sec == null) return '-';
    if (sec < 60) return sec + '秒';
    if (sec < 3600) return Math.floor(sec / 60) + '分' + (sec % 60) + '秒';
    return Math.floor(sec / 3600) + '時' + Math.floor((sec % 3600) / 60) + '分';
  },

  /**
   * 渲染任務結果模態框（回測/多策略/優化/組合/通用）
   * @returns {string} HTML 字符串
   */
  renderResultModal(task) {
    if (!task || !task.result) return '<p style="color:var(--text-dim)">暫無結果</p>';

    const r = task.result;
    const typeName = this.typeName(task.task_type);

    // 回測 / 進階回測
    if (task.task_type === 'backtest' || task.task_type === 'backtest_advanced') {
      const ret = r.total_return_pct || 0;
      const cards = [
        { label: '收益率', value: Utils.formatPct(ret), cls: ret >= 0 ? 'gn' : 'rd' },
        { label: '年化收益', value: Utils.formatPct(r.annual_return_pct || 0), cls: '' },
        { label: '夏普比率', value: Utils.formatNum(r.sharpe_ratio || 0, 4), cls: '' },
        { label: 'Sortino', value: Utils.formatNum(r.sortino_ratio || 0, 4), cls: '' },
        { label: '最大回撤', value: Utils.formatPct(-(r.max_drawdown_pct || 0)), cls: 'rd' },
        { label: 'Calmar', value: Utils.formatNum(r.calmar_ratio || 0, 4), cls: '' },
        { label: '勝率', value: Utils.formatNum(r.win_rate_pct || 0, 1) + '%', cls: '' },
        { label: '交易次數', value: r.total_trades || 0, cls: '' },
        { label: '波動率', value: Utils.formatPct(r.volatility_pct || 0), cls: '' },
        { label: '最終市值', value: '¥' + (r.final_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }), cls: '' },
      ];
      const cardsHtml = cards.map(c =>
        `<div class="c"><h3>${c.label}</h3><div class="v ${c.cls}">${c.value}</div></div>`
      ).join('');

      const elapsed = task.started_at ? this.formatElapsed(this.elapsed(task.started_at, task.completed_at)) : '';

      return `
        <h3>${typeName}結果 — ${task.title}</h3>
        ${elapsed ? `<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px">⏱️ 執行耗時: ${elapsed}</div>` : ''}
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin:12px 0">${cardsHtml}</div>
        ${r.equity_curve ? `<div style="margin-top:12px"><h4>📈 收益曲線</h4><canvas id="taskResultChart" height="200"></canvas></div>` : ''}
        ${task.task_id ? `<div style="margin-top:8px"><button class="btn s" onclick="Utils.closeModal();App._loadBacktestResult('${task.task_id}')">📊 在回測頁查看完整結果</button></div>` : ''}`;
    }

    // 多策略對比
    if (task.task_type === 'backtest_multi') {
      const results = Array.isArray(r) ? r : (r.results || []);
      const rows = results.slice(0, 10).map(item => `
        <tr>
          <td>${item.strategy}</td>
          <td class="r"><span class="${(item.total_return_pct || 0) >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(item.total_return_pct || 0)}</span></td>
          <td class="r">${Utils.formatNum(item.sharpe_ratio || 0, 2)}</td>
          <td class="r">${Utils.formatPct(-(item.max_drawdown_pct || 0))}</td>
          <td class="r">${Utils.formatNum(item.win_rate_pct || 0, 1)}%</td>
        </tr>
      `).join('');
      return `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div class="table-wrap" style="margin-top:8px"><table>
          <tr><th>策略</th><th>收益率</th><th>夏普</th><th>回撤</th><th>勝率</th></tr>
          ${rows || '<tr><td colspan="5" style="text-align:center;color:var(--text-dim)">無數據</td></tr>'}
        </table></div>`;
    }

    // 參數優化
    if (task.task_type === 'optimize') {
      let rows = '';
      if (typeof r === 'object' && !Array.isArray(r)) {
        for (const [strat, results] of Object.entries(r)) {
          const top3 = Array.isArray(results) ? results.slice(0, 3) : [];
          rows += `<tr><td colspan="5" style="font-weight:600;padding-top:8px">${strat}</td></tr>`;
          top3.forEach((item, i) => {
            rows += `<tr>
              <td>#${i + 1}</td>
              <td style="font-size:11px">${JSON.stringify(item.params || {})}</td>
              <td class="r">${Utils.formatNum(item.sharpe || item.value || 0, 4)}</td>
              <td class="r">${Utils.formatPct(-(item.max_drawdown_pct || 0))}</td>
              <td class="r">${Utils.formatNum(item.win_rate_pct || 0, 1)}%</td>
            </tr>`;
          });
        }
      }
      return `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div class="table-wrap" style="margin-top:8px"><table>
          <tr><th>#</th><th>參數</th><th>夏普</th><th>回撤</th><th>勝率</th></tr>
          ${rows || '<tr><td colspan="5" style="text-align:center;color:var(--text-dim)">無數據</td></tr>'}
        </table></div>`;
    }

    // 組合回測
    if (task.task_type === 'portfolio') {
      return `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0">
          <div class="c"><h3>收益率</h3><div class="v ${(r.total_return_pct || 0) >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(r.total_return_pct || 0)}</div></div>
          <div class="c"><h3>夏普比率</h3><div class="v">${Utils.formatNum(r.sharpe_ratio || 0, 4)}</div></div>
          <div class="c"><h3>最大回撤</h3><div class="v rd">${Utils.formatPct(-(r.max_drawdown_pct || 0))}</div></div>
        </div>`;
    }

    // 通用
    const json = JSON.stringify(r, null, 2);
    return `
      <h3>${typeName}結果 — ${task.title}</h3>
      <pre style="background:var(--bg-secondary);padding:12px;border-radius:8px;overflow:auto;max-height:400px;font-size:12px">${json.substring(0, 5000)}${json.length > 5000 ? '\n...(截斷)' : ''}</pre>`;
  },

  /**
   * 渲染回測結果圖表（收益曲線）
   */
  renderResultChart(canvasId, equityCurve) {
    if (!equityCurve || equityCurve.length === 0) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return;

    const colors = (typeof Charts !== 'undefined' && Charts.getThemeColors)
      ? Charts.getThemeColors()
      : { text: '#94a3b8', grid: '#1e293b' };

    new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: equityCurve.map((_, i) => i),
        datasets: [{
          data: equityCurve,
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,0.08)',
          fill: true,
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false },
          y: { ticks: { color: colors.text }, grid: { color: colors.grid } },
        },
      },
    });
  },

  /**
   * 渲染任務參數詳情 HTML
   */
  renderParams(params) {
    if (!params || Object.keys(params).length === 0) {
      return '<span style="color:var(--text-dim)">無參數</span>';
    }
    const entries = Object.entries(params).slice(0, 12);
    const rows = entries.map(([k, v]) => {
      const val = typeof v === 'object' ? JSON.stringify(v) : String(v);
      return `<tr><td style="font-weight:500;color:var(--text-dim);white-space:nowrap">${k}</td><td style="word-break:break-all">${val}</td></tr>`;
    }).join('');
    return `<table style="font-size:12px;width:100%">${rows}</table>`;
  },

  /**
   * 渲染錯誤詳情 HTML
   */
  renderError(error) {
    if (!error) return '';
    return `
      <div style="background:var(--red-bg);border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:10px;margin-top:8px">
        <div style="font-weight:600;color:var(--red);margin-bottom:4px">❌ 錯誤信息</div>
        <pre style="font-size:12px;color:var(--text-secondary);white-space:pre-wrap;word-break:break-all;margin:0">${error}</pre>
      </div>`;
  },
};

window.TaskCommon = TaskCommon;
