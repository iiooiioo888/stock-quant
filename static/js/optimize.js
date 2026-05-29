/**
 * optimize.js — 優化 Tab（支持方法卡片 + 目標卡片）
 */

const Optimize = {
  _method: 'grid',
  _objective: 'sharpe',

  collectRiskParams() {
    const num = (id) => {
      const v = parseFloat(document.getElementById(id)?.value);
      return Number.isFinite(v) && v > 0 ? v : undefined;
    };
    const out = {
      stop_loss_pct: num('optStopLoss'),
      take_profit_pct: num('optTakeProfit'),
      trailing_stop_pct: num('optTrailStop'),
      circuit_breaker_dd: num('optCircuitDd'),
      max_position_pct: num('optMaxPos'),
      slippage_pct: num('optSlippage'),
    };
    return Object.fromEntries(Object.entries(out).filter(([, v]) => v != null));
  },

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
    if (this._running) return;
    const codeRaw = document.getElementById('optCode').value.trim();
    if (!codeRaw) return Utils.toast('請輸入股票代碼', 3000, 'error');
    const codes = codeRaw.split(/[\s,，;；]+/).map(s => s.trim()).filter(Boolean);
    const strategy = document.getElementById('optStrategy').value;
    const method = this._method;
    const objective = this._objective;
    const btn = document.getElementById('optBtn');
    this._running = true;

    Utils.btnLoading(btn, true, '優化中...');
    try {
      const risk = this.collectRiskParams();
      // 多股模式：逐個提交，最後合併結果
      if (codes.length > 1) {
        Utils.toast(`📋 批量優化 ${codes.length} 隻股票…`, 2000, 'info');
        const allResults = [];
        for (const code of codes) {
          try {
            const d = await Api.runOptimize({ code, strategy, method, objective, n_trials: 50, ...risk });
            if (!d || !d.success) { allResults.push({ code, error: d?.error || '失敗' }); continue; }
            if (d.is_duplicate) { allResults.push({ code, message: d.message || '執行中' }); continue; }
            const resolved = await Api.resolveTaskResponse(d);
            const results = resolved?.results || resolved?.result || resolved?.task?.result;
            if (results) allResults.push({ code, results });
            else allResults.push({ code, error: '未取得結果' });
          } catch (e) {
            allResults.push({ code, error: e.message || String(e) });
          }
        }
        // 渲染第一個有結果的
        const first = allResults.find(r => r.results);
        if (first) {
          this.renderResults(first.results, strategy);
          const ok = allResults.filter(r => r.results).length;
          Utils.toast(`✅ ${ok}/${codes.length} 隻優化完成`, 3000, 'success');
        } else {
          Utils.toast('全部優化失敗', 3000, 'error');
        }
      } else {
        const d = await Api.runOptimize({ code: codes[0], strategy, method, objective, n_trials: 50, ...risk });
        if (!d || !d.success) return;
        if (d.is_duplicate) {
          Utils.toast('⏳ ' + (d.message || '相同優化執行中，等待完成...'), 3000, 'warning');
        } else if (d.async && d.task_id) {
          Utils.toast('📋 優化任務已提交', 2000, 'info');
        }
        const resolved = await Api.resolveTaskResponse(d);
        const results = resolved?.results || resolved?.result || resolved?.task?.result;
        if (!results) {
          Utils.toast('未取得優化結果', 3000, 'error');
          return;
        }
        this.renderResults(results, strategy);
      }
    } catch (e) {
      Utils.toast('優化失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      this._running = false;
      Utils.btnLoading(btn, false, '🔍 開始優化');
    }
  },
          </div>
          <div style="margin-top:4px;font-size:10px;color:var(--text-dim)">${Object.entries(b.params).map(([k, v]) => k + '=' + v).join(', ')}</div>
        </div>`;
      }
    } else {
      h = '<div class="table-wrap"><table><thead><tr><th>#</th><th>評分</th><th>收益率</th><th>夏普</th><th>回撤</th><th>勝率</th><th>參數</th></tr></thead><tbody>';
      results.forEach((r, i) => {
        const riskHint = r.risk?.circuit_breaker_hit
          ? ' <span title="觸發熔斷懲罰" style="color:var(--quote-down)">⚡</span>'
          : '';
        h += `<tr>
          <td>${i + 1}</td>
          <td class="r">${Utils.formatNum(r.score, 4)}${riskHint}</td>
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
    const labels = top.map((r, i) => {
      const sk = r.strategy;
      if (sk && typeof SignalLabels !== 'undefined') {
        return SignalLabels.strategyName(sk, 'chart');
      }
      return sk || `第 ${i + 1} 組`;
    });

    chartSec.innerHTML = `
      <h2>📊 優化結果對比</h2>
      <div id="optOverfitWarning"></div>
      <div class="cw"><canvas id="optCompareChart"></canvas></div>
      <div class="cw mt-md"><canvas id="optOOSChart"></canvas></div>`;

    // 過擬合風險警告
    const warnDiv = document.getElementById('optOverfitWarning');
    if (warnDiv) {
      const overfitItems = top.filter(r => {
        const isR = r.total_return_pct || 0;
        const oosR = r.oos_return_pct;
        return oosR != null && isR > 5 && (isR - oosR) / Math.max(Math.abs(isR), 1) > 0.5;
      });
      if (overfitItems.length > 0) {
        warnDiv.innerHTML = `<div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:12px;margin-bottom:16px;font-size:13px">
          ⚠️ <strong>過擬合風險</strong>：${overfitItems.length}/${top.length} 個參數組的樣本內收益遠超樣本外（差距 > 50%），建議增加樣本外驗證或降低參數自由度。
        </div>`;
      } else if (top.some(r => r.oos_return_pct != null)) {
        warnDiv.innerHTML = `<div style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);border-radius:8px;padding:12px;margin-bottom:16px;font-size:13px">
          ✅ <strong>過擬合風險較低</strong>：樣本內/外表現差異在合理範圍內。
        </div>`;
      }
    }

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
    if (this._running) return;
    const btn = document.getElementById('autoOptBtn');
    this._running = true;
    Utils.btnLoading(btn, true, '全自動優化中...');

    try {
    const d = await Api.runAutoOptimize({ method: 'optuna', n_trials: 30, objective: 'sharpe' });

    if (!d || !d.success) return Utils.toast('失敗', 3000, 'error');

      if (d.is_duplicate) {
        Utils.toast('⏳ ' + (d.message || '全自動優化正在執行中，等待完成...'), 3000, 'warning');
      } else if (d.task_id) {
        Utils.toast('📋 任務已建立，執行中...', 2000, 'info');
      }
      const resolved = await Api.resolveTaskResponse(d, { timeout: 1800000 });
      const r = Api.extractResult(resolved);
      if (!r) {
        Utils.toast('未取得自動優化結果', 3000, 'error');
        return;
      }
      document.getElementById('autoOptOutput').textContent =
        r.summary || JSON.stringify(r, null, 2);
      document.getElementById('autoOptResult').classList.remove('h');
      Utils.toast('全自動優化完成', 3000, 'success');
    } catch (e) {
      Utils.toast('自動優化失敗: ' + (e.message || e), 3000, 'error');
    } finally {
      this._running = false;
      Utils.btnLoading(btn, false, '⚡ 全自動優化');
    }
  },
};

window.Optimize = Optimize;
