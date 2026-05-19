/**
 * tasks.js — 任務面板 Tab（完整任務管理界面）
 */

const Tasks = {
  _pollTimer: null,
  _pollInterval: 3000,
  _searchDebounce: null,

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
    running: '⏳', completed: '✅', failed: '❌', cancelled: '🚫', pending: '⏸️',
  },

  STATUS_COLORS: {
    running: '#38bdf8', completed: '#22c55e', failed: '#ef4444', cancelled: '#94a3b8', pending: '#f59e0b',
  },

  /**
   * 初始化：綁定事件、啟動輪詢
   */
  init() {
    const searchInput = document.getElementById('taskSearch');
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        clearTimeout(this._searchDebounce);
        this._searchDebounce = setTimeout(() => this.refresh(), 300);
      });
    }

    const typeFilter = document.getElementById('taskTypeFilter');
    if (typeFilter) typeFilter.addEventListener('change', () => this.refresh());

    const statusFilter = document.getElementById('taskStatusFilter');
    if (statusFilter) statusFilter.addEventListener('change', () => this.refresh());
  },

  /**
   * Tab 載入時調用
   */
  async load() {
    this.init();
    await this.refresh();
    this._startPolling();
  },

  /**
   * Tab 離開時調用
   */
  unload() {
    this._stopPolling();
  },

  _startPolling() {
    this._stopPolling();
    this._pollTimer = setInterval(() => this.refresh(), this._pollInterval);
  },

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  },

  /**
   * 獲取當前篩選參數
   */
  _getFilters() {
    const search = (document.getElementById('taskSearch')?.value || '').trim().toLowerCase();
    const taskType = document.getElementById('taskTypeFilter')?.value || '';
    const status = document.getElementById('taskStatusFilter')?.value || '';
    return { search, taskType, status };
  },

  /**
   * 刷新所有數據
   */
  async refresh() {
    const { taskType, status } = this._getFilters();
    const d = await Api.getTasks(taskType || null, status || null, 100);
    if (!d) return;

    this._renderStats(d.stats);
    this._renderRunningTasks(d.tasks);
    this._renderTaskTable(d.tasks);
    this._updateNavBadge(d.stats);
  },

  /**
   * 渲染統計卡片
   */
  _renderStats(stats) {
    if (!stats) return;
    const grid = document.getElementById('taskStatsGrid');
    if (!grid) return;

    grid.innerHTML = `
      <div class="c stat-card"><h3>📋 總任務數</h3><div class="v">${stats.total || 0}</div><div class="stat-hint">所有任務</div></div>
      <div class="c stat-card"><h3>⏳ 運行中</h3><div class="v" style="color:#38bdf8">${stats.running || 0}</div><div class="stat-hint">正在執行</div></div>
      <div class="c stat-card"><h3>✅ 已完成</h3><div class="v" style="color:#22c55e">${stats.completed || 0}</div><div class="stat-hint">成功完成</div></div>
      <div class="c stat-card"><h3>❌ 失敗</h3><div class="v" style="color:#ef4444">${stats.failed || 0}</div><div class="stat-hint">執行失敗</div></div>`;
  },

  /**
   * 渲染運行中任務（帶進度條）
   */
  _renderRunningTasks(tasks) {
    const section = document.getElementById('taskRunningSection');
    const list = document.getElementById('taskRunningList');
    const countEl = document.getElementById('taskRunningCount');
    if (!section || !list) return;

    const running = tasks.filter(t => t.status === 'running');
    if (running.length === 0) {
      section.style.display = 'none';
      return;
    }

    section.style.display = 'block';
    if (countEl) countEl.textContent = running.length + ' 個';

    list.innerHTML = running.map(t => {
      const typeName = this.TYPE_NAMES[t.task_type] || t.task_type;
      const progress = t.progress || 0;
      return `
        <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:10px;padding:14px;margin-bottom:10px;position:relative;overflow:hidden">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="animation:pulse 1.5s infinite;color:#38bdf8">⏳</span>
              <span style="font-weight:600">${t.title || typeName}</span>
              <span style="font-size:11px;color:var(--text-dim);background:var(--bg-secondary);padding:2px 8px;border-radius:4px">${typeName}</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:14px;font-weight:700;color:#38bdf8">${progress}%</span>
              <button class="btn danger" style="padding:3px 10px;font-size:11px" onclick="Tasks.cancelTask('${t.task_id}')">取消</button>
            </div>
          </div>
          <div style="background:var(--bg-secondary);border-radius:6px;height:8px;overflow:hidden">
            <div style="height:100%;width:${progress}%;background:linear-gradient(90deg,#38bdf8,#6366f1);border-radius:6px;transition:width 0.5s ease;position:relative">
              <div style="position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.15),transparent);animation:shimmer 1.5s infinite"></div>
            </div>
          </div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:6px">創建於 ${t.created_at || '-'}</div>
        </div>`;
    }).join('');
  },

  /**
   * 渲染任務表格
   */
  _renderTaskTable(tasks) {
    const tbody = document.getElementById('taskTableBody');
    const countEl = document.getElementById('taskListCount');
    if (!tbody) return;

    // 前端搜索過濾
    const { search } = this._getFilters();
    let filtered = tasks;
    if (search) {
      filtered = tasks.filter(t => {
        const title = (t.title || '').toLowerCase();
        const type = (t.task_type || '').toLowerCase();
        const typeName = (this.TYPE_NAMES[t.task_type] || '').toLowerCase();
        return title.includes(search) || type.includes(search) || typeName.includes(search);
      });
    }

    if (countEl) countEl.textContent = filtered.length + ' 個';

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7"><div class="state-empty"><span class="state-icon">📋</span><span class="state-text">暫無任務記錄</span></div></td></tr>';
      return;
    }

    tbody.innerHTML = filtered.map(t => {
      const typeName = this.TYPE_NAMES[t.task_type] || t.task_type;
      const icon = this.STATUS_ICONS[t.status] || '❓';
      const color = this.STATUS_COLORS[t.status] || '#94a3b8';
      const canView = t.status === 'completed' && t.has_result;
      const canCancel = t.status === 'running' || t.status === 'pending';
      const statusText = t.status === 'running' ? `${t.progress || 0}%` : t.status;

      return `<tr>
        <td><span style="color:${color};font-weight:600">${icon} ${statusText}</span></td>
        <td>${typeName}</td>
        <td style="font-weight:500">${t.title || '-'}</td>
        <td>${t.status === 'running' ? `<div style="background:var(--bg-secondary);border-radius:4px;height:6px;width:80px;display:inline-block;vertical-align:middle"><div style="height:100%;width:${t.progress || 0}%;background:#38bdf8;border-radius:4px"></div></div>` : (t.progress || 0) + '%'}</td>
        <td style="font-size:11px;color:var(--text-dim)">${t.created_at || '-'}</td>
        <td style="font-size:11px;color:var(--text-dim)">${t.completed_at || '-'}</td>
        <td>
          ${canView ? `<button class="btn s" style="padding:3px 8px;font-size:10px" onclick="Tasks.viewResult('${t.task_id}')">查看結果</button>` : ''}
          ${canCancel ? `<button class="btn danger" style="padding:3px 8px;font-size:10px" onclick="Tasks.cancelTask('${t.task_id}')">取消</button>` : ''}
          ${t.error ? `<span style="color:#ef4444;font-size:10px;cursor:pointer" title="${String(t.error).replace(/"/g, '&quot;')}">⚠ 錯誤</span>` : ''}
        </td>
      </tr>`;
    }).join('');
  },

  /**
   * 更新側邊欄徽章
   */
  _updateNavBadge(stats) {
    const badge = document.getElementById('navBadgeTasks');
    if (!badge) return;
    const running = stats?.running || 0;
    if (running > 0) {
      badge.textContent = running;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  },

  /**
   * 取消任務
   */
  async cancelTask(taskId) {
    const d = await Api.cancelTask(taskId);
    if (d && d.success) {
      Utils.toast('任務已取消', 2000, 'success');
      this.refresh();
    } else {
      Utils.toast('取消失敗', 2000, 'error');
    }
  },

  /**
   * 清理超時任務
   */
  async cleanup() {
    const d = await Api.cleanupTasks();
    if (d && d.success) {
      Utils.toast(`已清理 ${d.cleaned || 0} 個超時任務`, 2000, 'success');
      this.refresh();
    }
  },

  /**
   * 查看任務結果（複用 App._viewTaskResult 的邏輯）
   */
  async viewResult(taskId) {
    const d = await Api.getTask(taskId);
    if (!d || !d.task) return;

    const task = d.task;
    if (!task.result) {
      Utils.toast('此任務暫無結果', 2000, 'warning');
      return;
    }

    const r = task.result;
    const typeName = this.TYPE_NAMES[task.task_type] || task.task_type;
    let content = '';

    if (task.task_type === 'backtest' || task.task_type === 'backtest_advanced') {
      content = `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0">
          <div class="c"><h3>收益率</h3><div class="v ${(r.total_return_pct || 0) >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(r.total_return_pct || 0)}</div></div>
          <div class="c"><h3>夏普比率</h3><div class="v">${Utils.formatNum(r.sharpe_ratio || 0, 4)}</div></div>
          <div class="c"><h3>最大回撤</h3><div class="v rd">${Utils.formatPct(-(r.max_drawdown_pct || 0))}</div></div>
          <div class="c"><h3>勝率</h3><div class="v">${Utils.formatNum(r.win_rate_pct || 0, 1)}%</div></div>
          <div class="c"><h3>交易次數</h3><div class="v">${r.total_trades || 0}</div></div>
          <div class="c"><h3>年化收益</h3><div class="v">${Utils.formatPct(r.annual_return_pct || 0)}</div></div>
          <div class="c"><h3>Sortino</h3><div class="v">${Utils.formatNum(r.sortino_ratio || 0, 4)}</div></div>
          <div class="c"><h3>最終市值</h3><div class="v">¥${(r.final_value || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}</div></div>
        </div>
        ${r.equity_curve ? `<div style="margin-top:12px"><h4>收益曲線</h4><canvas id="taskResultChart" height="200"></canvas></div>` : ''}
        <div style="margin-top:8px">
          <button class="btn s" onclick="Utils.closeModal();App._loadBacktestResult('${taskId}')">📊 在回測頁查看完整結果</button>
        </div>`;

      Utils.showModal(content);

      // 繪製收益曲線
      if (r.equity_curve && r.equity_curve.length > 0) {
        setTimeout(() => {
          const canvas = document.getElementById('taskResultChart');
          if (!canvas || typeof Chart === 'undefined') return;
          const colors = typeof Charts !== 'undefined' && Charts.getThemeColors ? Charts.getThemeColors() : { text: '#94a3b8', grid: '#1e293b' };
          new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
              labels: r.equity_curve.map((_, i) => i),
              datasets: [{
                data: r.equity_curve,
                borderColor: '#38bdf8',
                backgroundColor: 'rgba(56,189,248,0.1)',
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
        }, 100);
      }
      return;
    }

    if (task.task_type === 'backtest_multi') {
      const results = Array.isArray(r) ? r : (r.results || []);
      const rows = results.slice(0, 10).map(item => `
        <tr>
          <td>${item.strategy}</td>
          <td class="r"><span class="b ${(item.total_return_pct || 0) >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(item.total_return_pct || 0)}</span></td>
          <td class="r">${Utils.formatNum(item.sharpe_ratio || 0, 2)}</td>
          <td class="r">${Utils.formatPct(-(item.max_drawdown_pct || 0))}</td>
          <td class="r">${Utils.formatNum(item.win_rate_pct || 0, 1)}%</td>
        </tr>
      `).join('');
      content = `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div class="table-wrap" style="margin-top:8px"><table>
          <tr><th>策略</th><th>收益率</th><th>夏普</th><th>回撤</th><th>勝率</th></tr>
          ${rows || '<tr><td colspan="5" style="text-align:center;color:var(--text-dim)">無數據</td></tr>'}
        </table></div>`;
      Utils.showModal(content);
      return;
    }

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
      content = `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div class="table-wrap" style="margin-top:8px"><table>
          <tr><th>#</th><th>參數</th><th>夏普</th><th>回撤</th><th>勝率</th></tr>
          ${rows || '<tr><td colspan="5" style="text-align:center;color:var(--text-dim)">無數據</td></tr>'}
        </table></div>`;
      Utils.showModal(content);
      return;
    }

    if (task.task_type === 'portfolio') {
      content = `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0">
          <div class="c"><h3>收益率</h3><div class="v ${(r.total_return_pct || 0) >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(r.total_return_pct || 0)}</div></div>
          <div class="c"><h3>夏普比率</h3><div class="v">${Utils.formatNum(r.sharpe_ratio || 0, 4)}</div></div>
          <div class="c"><h3>最大回撤</h3><div class="v rd">${Utils.formatPct(-(r.max_drawdown_pct || 0))}</div></div>
        </div>`;
      Utils.showModal(content);
      return;
    }

    // 通用結果
    const json = JSON.stringify(r, null, 2);
    content = `
      <h3>${typeName}結果 — ${task.title}</h3>
      <pre style="background:var(--bg-secondary);padding:12px;border-radius:8px;overflow:auto;max-height:400px;font-size:12px">${json.substring(0, 3000)}${json.length > 3000 ? '\n...(截斷)' : ''}</pre>`;
    Utils.showModal(content);
  },
};

// 添加 shimmer 動畫（如果尚未存在）
if (!document.getElementById('taskShimmerStyle')) {
  const style = document.createElement('style');
  style.id = 'taskShimmerStyle';
  style.textContent = '@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}';
  document.head.appendChild(style);
}

window.Tasks = Tasks;
