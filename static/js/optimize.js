/**
 * optimize.js — 優化 Tab（支持方法卡片 + 目標卡片）
 */

const Optimize = {
  _method: 'grid',
  _objective: 'sharpe',

  selectMethod(el) {
    document.querySelectorAll('[data-opt-method]').forEach(c => c.classList.remove('active'));
    el.classList.add('active');
    this._method = el.dataset.optMethod;
  },

  selectObjective(el) {
    document.querySelectorAll('[data-opt-obj]').forEach(c => c.classList.remove('active'));
    el.classList.add('active');
    this._objective = el.dataset.optObj;
  },

  async run() {
    const code = document.getElementById('optCode').value.trim();
    if (!code) return Utils.toast('請輸入股票代碼', 3000, 'error');
    const strategy = document.getElementById('optStrategy').value;
    const method = this._method;
    const objective = this._objective;
    const btn = document.getElementById('optBtn');

    Utils.btnLoading(btn, true, '優化中...');
    const d = await Api.runOptimize({ code, strategy, method, objective, n_trials: 50 });
    Utils.btnLoading(btn, false, '🔍 開始優化');

    if (!d || !d.success) return;

    // 任務去重提示
    if (d.is_duplicate) {
      Utils.toast('⏳ ' + (d.message || '相同優化正在執行中'), 3000, 'warning');
      return;
    }

    if (d.task_id) {
      Utils.toast('📋 任務已建立: ' + d.task_id, 2000, 'info');
    }

    const el = document.getElementById('optOutput');
    let h = '';
    const results = d.results;

    if (strategy === 'all') {
      for (const [n, rl] of Object.entries(results)) {
        if (!rl || !rl.length) {
          h += `<div style="margin-bottom:6px"><strong>${n}</strong>: <span style="color:var(--text-dim)">無結果</span></div>`;
          continue;
        }
        const b = rl[0];
        h += `<div style="margin-bottom:8px;padding:10px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <strong style="color:var(--accent)">${n}</strong>
            <div>
              <span style="margin-left:10px;font-size:12px">夏普 <b>${Utils.formatNum(b.sharpe_ratio, 2)}</b></span>
              <span style="margin-left:10px;font-size:12px">收益 <b>${Utils.formatPct(b.total_return_pct)}</b></span>
            </div>
          </div>
          <div style="margin-top:4px;font-size:10px;color:var(--text-dim)">${Object.entries(b.params).map(([k, v]) => k + '=' + v).join(', ')}</div>
        </div>`;
      }
    } else {
      h = '<div class="table-wrap"><table><thead><tr><th>#</th><th>評分</th><th>收益率</th><th>夏普</th><th>回撤</th><th>勝率</th><th>參數</th></tr></thead><tbody>';
      results.forEach((r, i) => {
        h += `<tr>
          <td>${i + 1}</td>
          <td class="r">${Utils.formatNum(r.score, 4)}</td>
          <td class="r"><span class="b ${Utils.badgeClass(r.total_return_pct)}">${Utils.formatPct(r.total_return_pct)}</span></td>
          <td class="r">${Utils.formatNum(r.sharpe_ratio, 2)}</td>
          <td class="r">${Utils.formatPct(-r.max_drawdown_pct)}</td>
          <td class="r">${Utils.formatNum(r.win_rate_pct, 1)}%</td>
          <td style="font-size:10px;color:var(--text-muted)">${Object.entries(r.params).map(([k, v]) => k + '=' + v).join(', ')}</td>
        </tr>`;
      });
      h += '</tbody></table></div>';
    }

    el.innerHTML = h;
    document.getElementById('optResult').classList.remove('h');
    document.getElementById('optResult').scrollIntoView({ behavior: 'smooth', block: 'start' });

    // 繪製優化結果圖表
    this._drawOptimizeCharts(results, strategy);
  },

  /**
   * 優化結果圖表 — Top 10 參數對比 + OOS 驗證對比
   */
  _drawOptimizeCharts(results, strategy) {
    // 確保圖表容器存在
    let chartSec = document.getElementById('optChartSection');
    if (!chartSec) {
      const resultDiv = document.getElementById('optResult');
      if (resultDiv) {
        chartSec = document.createElement('div');
        chartSec.id = 'optChartSection';
        chartSec.className = 'sec';
        resultDiv.appendChild(chartSec);
      }
    }
    if (!chartSec) return;

    let resultList = [];
    if (strategy === 'all') {
      // 全策略模式：取每個策略的最佳結果
      for (const [name, rl] of Object.entries(results)) {
        if (rl && rl.length) resultList.push({ ...rl[0], strategy: name });
      }
    } else {
      resultList = results || [];
    }

    if (!resultList.length) return;

    // Top 10 收益率 vs 夏普 vs 回撤 對比圖
    const top = resultList.slice(0, 10);
    const labels = top.map((r, i) => r.strategy || `#${i + 1}`);

    chartSec.innerHTML = `
      <h2>📊 優化結果對比</h2>
      <div class="cw"><canvas id="optCompareChart"></canvas></div>
      <div class="cw mt-md"><canvas id="optOOSChart"></canvas></div>`;

    // 收益率 + 夏普 雙軸圖
    const canvas = document.getElementById('optCompareChart');
    if (canvas) {
      const old = Chart.getChart(canvas);
      if (old) old.destroy();
      const colors = Charts.getThemeColors();
      new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: '收益率 (%)',
              data: top.map(r => r.total_return_pct || 0),
              backgroundColor: top.map(r => (r.total_return_pct || 0) >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)'),
              borderColor: top.map(r => (r.total_return_pct || 0) >= 0 ? '#22c55e' : '#ef4444'),
              borderWidth: 1,
              yAxisID: 'y',
            },
            {
              label: '夏普比率',
              data: top.map(r => r.sharpe_ratio || 0),
              type: 'line',
              borderColor: '#38bdf8',
              backgroundColor: 'transparent',
              borderWidth: 2,
              pointRadius: 4,
              pointBackgroundColor: '#38bdf8',
              yAxisID: 'y1',
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: colors.text, font: { size: 10 } } },
            tooltip: { backgroundColor: colors.tooltipBg, borderColor: colors.tooltipBorder, borderWidth: 1, titleColor: colors.tooltipText, bodyColor: colors.tooltipBody },
          },
          scales: {
            x: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
            y: { position: 'left', title: { display: true, text: '收益率 (%)', color: colors.text }, ticks: { color: colors.text }, grid: { color: colors.grid } },
            y1: { position: 'right', title: { display: true, text: '夏普比率', color: colors.text }, ticks: { color: colors.text }, grid: { drawOnChartArea: false } },
          },
        },
      });
    }

    // OOS 驗證對比圖（如果有 oos 數據）
    const hasOOS = top.some(r => r.oos_return_pct != null);
    if (hasOOS) {
      const oosCanvas = document.getElementById('optOOSChart');
      if (oosCanvas) {
        const old = Chart.getChart(oosCanvas);
        if (old) old.destroy();
        const colors = Charts.getThemeColors();
        new Chart(oosCanvas.getContext('2d'), {
          type: 'bar',
          data: {
            labels,
            datasets: [
              {
                label: '樣本內收益 (%)',
                data: top.map(r => r.total_return_pct || 0),
                backgroundColor: 'rgba(56,189,248,0.5)',
                borderColor: '#38bdf8',
                borderWidth: 1,
              },
              {
                label: '樣本外收益 (%)',
                data: top.map(r => r.oos_return_pct != null ? r.oos_return_pct : 0),
                backgroundColor: 'rgba(168,85,247,0.5)',
                borderColor: '#a855f7',
                borderWidth: 1,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: { display: true, text: '⚠️ 樣本內 vs 樣本外收益對比（過擬合檢測）', color: colors.text, font: { size: 12 } },
              legend: { labels: { color: colors.text, font: { size: 10 } } },
              tooltip: { backgroundColor: colors.tooltipBg, borderColor: colors.tooltipBorder, borderWidth: 1, titleColor: colors.tooltipText, bodyColor: colors.tooltipBody },
            },
            scales: {
              x: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
              y: { ticks: { color: colors.text }, grid: { color: colors.grid } },
            },
          },
        });
      }
    } else {
      // 沒有 OOS 數據時隱藏第二個 canvas
      const oosCanvas = document.getElementById('optOOSChart');
      if (oosCanvas) oosCanvas.parentElement.style.display = 'none';
    }
  },

  async runAuto() {
    const btn = document.getElementById('autoOptBtn');
    Utils.btnLoading(btn, true, '全自動優化中...');

    const d = await Api.runAutoOptimize({ method: 'optuna', n_trials: 30, objective: 'sharpe' });
    Utils.btnLoading(btn, false, '⚡ 全自動優化');

    if (!d || !d.success) return Utils.toast('失敗', 3000, 'error');

    // 任務去重提示
    if (d.is_duplicate) {
      Utils.toast('⏳ ' + (d.message || '全自動優化正在執行中'), 3000, 'warning');
      return;
    }

    if (d.task_id) {
      Utils.toast('📋 任務已建立: ' + d.task_id, 2000, 'info');
    }

    document.getElementById('autoOptOutput').textContent = d.result.summary || JSON.stringify(d.result, null, 2);
    document.getElementById('autoOptResult').classList.remove('h');
    Utils.toast('全自動優化完成', 3000, 'success');
  },
};

window.Optimize = Optimize;
