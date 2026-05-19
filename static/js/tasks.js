/**
 * tasks.js — 任務面板 Tab（完整任務管理界面）v2
 *
 * 優化：使用 TaskCommon 共享模塊、CSS 類、timeAgo、載入狀態、
 * 錯誤詳情、參數展開、執行耗時、列排序、刪除功能、空狀態引導。
 */

const Tasks = {
  _pollTimer: null,
  _pollInterval: 4000,
  _maxPolls: 300,
  _pollCount: 0,
  _searchDebounce: null,
  _sortCol: 'created_at',
  _sortAsc: false,
  _expandedRows: new Set(),
  _paramsCache: new Map(),

  /**
   * 初始化：綁定事件
   */
  init() {
    const searchInput = document.getElementById('taskSearch');
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        clearTimeout(this._searchDebounce);
        this._searchDebounce = setTimeout(() => this.refresh(), 300);
      });
    }
    ['taskTypeFilter', 'taskStatusFilter'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('change', () => this.refresh());
    });

    // 表頭排序
    document.querySelectorAll('#taskTableHead th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const col = th.dataset.sort;
        if (this._sortCol === col) {
          this._sortAsc = !this._sortAsc;
        } else {
          this._sortCol = col;
          this._sortAsc = true;
        }
        this.refresh();
      });
    });
  },

  async load() {
    this.init();
    this._pollCount = 0;
    this._expandedRows.clear();
    await this.refresh();
    this._startPolling();
  },

  unload() {
    this._stopPolling();
  },

  _startPolling() {
    this._stopPolling();
    this._pollTimer = setInterval(() => {
      if (++this._pollCount > this._maxPolls) {
        this._stopPolling();
        return;
      }
      this.refresh(true);
    }, this._pollInterval);
  },

  _stopPolling() {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
  },

  _getFilters() {
    return {
      search: (document.getElementById('taskSearch')?.value || '').trim().toLowerCase(),
      taskType: document.getElementById('taskTypeFilter')?.value || '',
      status: document.getElementById('taskStatusFilter')?.value || '',
    };
  },

  /**
   * 刷新所有數據
   */
  async refresh(silent) {
    const { taskType, status } = this._getFilters();
    if (!silent) this._setLoading(true);

    const d = await Api.getTasks(taskType || null, status || null, 200);
    if (!silent) this._setLoading(false);
    if (!d) return;

    const queue = d.queue || await Api.getTaskQueue();
    this._renderStats(d.stats);
    this._renderQueue(queue);
    this._renderRunningTasks(d.tasks);
    this._renderTaskTable(d.tasks);
    this._updateNavBadge(d.stats);
    for (const id of this._expandedRows) {
      this._loadParams(id);
    }
  },

  _renderQueue(snapshot) {
    const grid = document.getElementById('taskQueueGrid');
    if (!grid || typeof TaskCommon === 'undefined') return;
    grid.innerHTML = TaskCommon.renderQueueSection(snapshot || {}, false);
    const recent = TaskCommon.splitQueue(snapshot || {}).recent;
    if (recent?.task_id) {
      const prev = sessionStorage.getItem('lastSeenCompletedId');
      if (prev && prev !== recent.task_id && typeof Utils !== 'undefined') {
        Utils.toast('✅ 任務完成: ' + (recent.title || ''), 3000, 'success');
      }
      sessionStorage.setItem('lastSeenCompletedId', recent.task_id);
    }
  },

  _setLoading(loading) {
    const indicator = document.getElementById('taskLoadingIndicator');
    if (indicator) indicator.style.display = loading ? 'flex' : 'none';
  },

  // ── 統計卡片 ──────────────────────────────────────────────

  _renderStats(stats) {
    if (!stats) return;
    const grid = document.getElementById('taskStatsGrid');
    if (!grid) return;

    const maxW = stats.max_workers || '-';
    const inFlight = stats.in_flight ?? stats.running ?? 0;
    const items = [
      { icon: '📋', label: '總任務數', value: stats.total || 0, color: '' },
      { icon: '⚙️', label: '並行槽', value: `${inFlight}/${maxW}`, color: '#38bdf8' },
      { icon: '⏸️', label: '等待中', value: stats.pending || 0, color: '#f59e0b' },
      { icon: '⏳', label: '運行中', value: stats.running || 0, color: '#38bdf8' },
      { icon: '✅', label: '已完成', value: stats.completed || 0, color: '#22c55e' },
      { icon: '❌', label: '失敗', value: stats.failed || 0, color: '#ef4444' },
      { icon: '🚫', label: '已取消', value: stats.cancelled || 0, color: '#94a3b8' },
    ];
    grid.innerHTML = items.map(i =>
      `<div class="c stat-card"><h3>${i.icon} ${i.label}</h3>` +
      `<div class="v" ${i.color ? `style="color:${i.color}"` : ''}>${i.value}</div></div>`
    ).join('');
  },

  // ── 運行中任務 ────────────────────────────────────────────

  _renderRunningTasks(tasks) {
    const section = document.getElementById('taskRunningSection');
    const list = document.getElementById('taskRunningList');
    const countEl = document.getElementById('taskRunningCount');
    if (!section || !list) return;

    const running = tasks.filter(t => t.status === 'running' || t.status === 'pending');
    section.style.display = running.length ? 'block' : 'none';
    if (countEl) countEl.textContent = running.length ? `${running.length} 個` : '';

    list.innerHTML = running.map(t => {
      const typeName = TaskCommon.typeName(t.task_type);
      const progress = t.progress || 0;
      const icon = t.status === 'pending' ? '⏸️' : '⏳';
      const pulse = t.status === 'running' ? 'animation:pulse 1.5s infinite;' : '';
      const sub = TaskCommon.formatTaskSubtitle(t);
      return `
        <div class="sec" style="padding:12px;margin-bottom:8px;animation:tabFadeIn .3s ease">
          <div class="status-row">
            <span style="${pulse}font-size:16px">${icon}</span>
            <span style="font-weight:600">${t.title || typeName}</span>
            <span class="chip cfg">${typeName}</span>
            <span class="flex-spacer"></span>
            <span style="font-size:15px;font-weight:700;color:#38bdf8">${progress}%</span>
            <button class="btn danger" style="padding:3px 10px;font-size:11px" onclick="Tasks.cancelTask('${t.task_id}')">取消</button>
          </div>
          ${sub ? `<div style="font-size:12px;color:#38bdf8;margin:6px 0 4px">${sub}</div>` : ''}
          <div class="progress-bar-wrap">
            <div class="progress-bar" style="width:${progress}%">
              <div style="position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.15),transparent);animation:shimmer 1.5s infinite"></div>
            </div>
          </div>
          <div style="font-size:11px;color:var(--text-dim)">創建於 ${Utils.timeAgo(t.created_at)}</div>
        </div>`;
    }).join('');
  },

  // ── 任務表格 ──────────────────────────────────────────────

  _renderTaskTable(tasks) {
    const tbody = document.getElementById('taskTableBody');
    const countEl = document.getElementById('taskListCount');
    if (!tbody) return;

    // 前端搜索過濾
    const { search } = this._getFilters();
    let filtered = tasks;
    if (search) {
      filtered = tasks.filter(t => {
        const haystack = [t.title, t.task_type, TaskCommon.typeName(t.task_type)].join(' ').toLowerCase();
        return haystack.includes(search);
      });
    }

    // 排序
    filtered.sort((a, b) => {
      let va = a[this._sortCol] ?? '';
      let vb = b[this._sortCol] ?? '';
      if (this._sortCol === 'progress') { va = Number(va); vb = Number(vb); }
      else { va = String(va).toLowerCase(); vb = String(vb).toLowerCase(); }
      if (va < vb) return this._sortAsc ? -1 : 1;
      if (va > vb) return this._sortAsc ? 1 : -1;
      return 0;
    });

    if (countEl) countEl.textContent = `${filtered.length} 個`;

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="7">
        <div class="empty-state">
          <span class="empty-icon">📋</span>
          <p><strong>暫無任務記錄</strong></p>
          <p>前往回測或優化頁面提交任務後，將在此顯示</p>
        </div>
      </td></tr>`;
      return;
    }

    // 更新排序指示器
    document.querySelectorAll('#taskTableHead th[data-sort]').forEach(th => {
      const col = th.dataset.sort;
      th.textContent = th.textContent.replace(/ [▲▼]$/, '');
      if (col === this._sortCol) {
        th.textContent += this._sortAsc ? ' ▲' : ' ▼';
      }
    });

    tbody.innerHTML = filtered.map(t => this._renderRow(t)).join('');
  },

  _renderRow(t) {
    const TC = TaskCommon;
    const typeName = TC.typeName(t.task_type);
    const icon = TC.STATUS_ICONS[t.status] || '❓';
    const color = TC.STATUS_COLORS[t.status] || '#94a3b8';
    const isExpanded = this._expandedRows.has(t.task_id);
    const sub = TC.formatTaskSubtitle(t);
    const canView = t.status === 'completed' && t.has_result;
    const canCancel = t.status === 'running' || t.status === 'pending';
    const canDelete = ['completed', 'failed', 'cancelled'].includes(t.status);

    // 狀態顯示
    let statusHtml;
    if (t.status === 'running') {
      statusHtml = `<span style="color:${color};font-weight:600">${icon} ${t.progress || 0}%</span>`;
    } else {
      statusHtml = `<span class="${TC.STATUS_CHIP[t.status] || 'chip'}">${icon} ${t.status}</span>`;
    }

    // 進度列
    let progressHtml;
    if (t.status === 'running') {
      progressHtml = `<div class="progress-bar-wrap" style="width:80px;display:inline-block;vertical-align:middle"><div class="progress-bar" style="width:${t.progress || 0}%"></div></div>`;
    } else {
      progressHtml = `<span style="color:var(--text-dim)">${t.progress || 0}%</span>`;
    }

    // 操作按鈕
    let actions = '';
    if (canView) {
      actions += TaskCommon.renderNavigateButton(t.task_id, '前往') + ' ';
      actions += `<button class="btn s" style="padding:2px 8px;font-size:10px" onclick="Tasks.viewResult('${t.task_id}')">📊 結果</button> `;
    }
    if (canCancel) actions += `<button class="btn danger" style="padding:2px 8px;font-size:10px" onclick="Tasks.cancelTask('${t.task_id}')">取消</button> `;
    if (canDelete) actions += `<button class="btn s" style="padding:2px 8px;font-size:10px;color:var(--text-dim)" onclick="Tasks.deleteTask('${t.task_id}')">🗑️</button> `;
    actions += `<button class="btn s" style="padding:2px 8px;font-size:10px" onclick="Tasks.toggleExpand('${t.task_id}')">${isExpanded ? '收起' : '詳情'}</button>`;

    // 展開詳情行
    let detailRow = '';
    if (isExpanded) {
      const elapsed = TC.elapsed(t.started_at || t.created_at, t.completed_at);
      const elapsedStr = TC.formatElapsed(elapsed);
      detailRow = `
        <tr id="detail-${t.task_id}" class="task-detail-row">
          <td colspan="7" style="padding:0">
            <div style="background:var(--bg-primary);border-top:1px solid var(--border-color);padding:12px 16px;animation:tabFadeIn .2s ease">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div>
                  <div style="font-size:12px;font-weight:600;color:var(--text-dim);margin-bottom:6px">📋 任務參數</div>
                  <div id="params-${t.task_id}" style="font-size:12px">載入中...</div>
                </div>
                <div>
                  <div style="font-size:12px;font-weight:600;color:var(--text-dim);margin-bottom:6px">ℹ️ 執行信息</div>
                  <table style="font-size:12px;width:100%">
                    <tr><td style="color:var(--text-dim)">任務ID</td><td style="word-break:break-all">${t.task_id}</td></tr>
                    <tr><td style="color:var(--text-dim)">類型</td><td>${typeName}</td></tr>
                    <tr><td style="color:var(--text-dim)">創建時間</td><td>${t.created_at || '-'}</td></tr>
                    <tr><td style="color:var(--text-dim)">完成時間</td><td>${t.completed_at || '-'}</td></tr>
                    <tr><td style="color:var(--text-dim)">執行耗時</td><td>${elapsedStr}</td></tr>
                  </table>
                </div>
              </div>
              ${t.error ? TC.renderError(t.error) : ''}
            </div>
          </td>
        </tr>`;

      // 異步載入參數
      setTimeout(() => this._loadParams(t.task_id), 0);
    }

    return `
      <tr style="cursor:pointer" onclick="Tasks.toggleExpand('${t.task_id}')">
        <td>${statusHtml}</td>
        <td><span style="font-size:12px">${typeName}</span></td>
        <td style="font-weight:500">${t.title || '-'}${sub ? `<div style="font-size:11px;color:#38bdf8;font-weight:400;margin-top:2px">${sub}</div>` : ''}</td>
        <td>${progressHtml}</td>
        <td style="font-size:11px;color:var(--text-dim)" title="${t.created_at || ''}">${Utils.timeAgo(t.created_at)}</td>
        <td style="font-size:11px;color:var(--text-dim)" title="${t.completed_at || ''}">${t.completed_at ? Utils.timeAgo(t.completed_at) : '-'}</td>
        <td onclick="event.stopPropagation()">${actions}</td>
      </tr>${detailRow}`;
  },

  /**
   * 展開/收起詳情行
   */
  async toggleExpand(taskId) {
    if (this._expandedRows.has(taskId)) {
      this._expandedRows.delete(taskId);
    } else {
      this._expandedRows.add(taskId);
    }
    await this.refresh(true);
  },

  /**
   * 異步載入任務參數
   */
  async _loadParams(taskId) {
    const container = document.getElementById(`params-${taskId}`);
    if (!container) return;

    if (this._paramsCache.has(taskId)) {
      container.innerHTML = this._paramsCache.get(taskId);
      return;
    }

    const d = await Api.getTaskParams(taskId);
    if (!d || !d.task) {
      container.innerHTML = '<span style="color:var(--text-dim)">無法載入（任務可能已過期，請刷新列表）</span>';
      return;
    }
    const html = TaskCommon.renderParams(d.task.params, d.task.task_type);
    this._paramsCache.set(taskId, html);
    container.innerHTML = html;
  },

  // ── 操作 ──────────────────────────────────────────────────

  _updateNavBadge(stats) {
    const badge = document.getElementById('navBadgeTasks');
    if (!badge) return;
    const active = (stats?.running || 0) + (stats?.pending || 0);
    badge.textContent = active;
    badge.style.display = active > 0 ? 'inline-block' : 'none';
  },

  async cancelTask(taskId) {
    const d = await Api.cancelTask(taskId);
    if (d?.success) { Utils.toast('任務已取消', 2000, 'success'); this.refresh(); }
    else Utils.toast('取消失敗', 2000, 'error');
  },

  async deleteTask(taskId) {
    const d = await Api.deleteTask(taskId);
    if (d?.success) {
      this._expandedRows.delete(taskId);
      this._paramsCache.delete(taskId);
      Utils.toast('已刪除', 2000, 'success');
      this.refresh();
    } else {
      Utils.toast(d?.detail || '刪除失敗（運行中的任務需先取消）', 3000, 'error');
    }
  },

  async cleanup() {
    const d = await Api.cleanupTasks();
    if (d?.success) {
      Utils.toast(`已清理 ${d.cleaned || 0} 個超時任務`, 2000, 'success');
      this.refresh();
    }
  },

  // ── 查看結果 ──────────────────────────────────────────────

  async viewResult(taskId) {
    const d = await Api.getTask(taskId);
    if (!d?.task) return;

    const task = d.task;
    if (!task.result) { Utils.toast('此任務暫無結果', 2000, 'warning'); return; }

    Utils.showModal(TaskCommon.renderResultModal(task));

    // 繪製收益曲線
    if (task.result?.equity_curve) {
      setTimeout(() => TaskCommon.renderResultChart('taskResultChart', task.result.equity_curve), 100);
    }
  },
};

// shimmer 動畫
if (!document.getElementById('taskShimmerStyle')) {
  const style = document.createElement('style');
  style.id = 'taskShimmerStyle';
  style.textContent = '@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}';
  document.head.appendChild(style);
}

window.Tasks = Tasks;
