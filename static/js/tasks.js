/**
 * tasks.js — 任務面板 Tab（完整任務管理界面）v3
 *
 * v3 優化：
 * - WebSocket 實時推送，輪詢降級為備用
 * - 批量操作（勾選 + 批量取消/刪除）
 * - 任務重試
 * - 運行中任務顯示已用時間/預估剩餘
 * - 統計卡片數字動畫
 * - 載入骨架屏
 */

const Tasks = {
  _pollTimer: null,
  _pollInterval: 8000,
  _maxPolls: 300,
  _pollCount: 0,
  _lastData: null,
  _loadError: '',
  _searchDebounce: null,
  _sortCol: 'created_at',
  _sortAsc: false,
  _expandedRows: new Set(),
  _paramsCache: new Map(),
  _bound: false,
  _selectedIds: new Set(),
  _wsHandler: null,
  _prevStats: null,
  _todayOnly: false,
  _hasResultOnly: false,

  isAutoRefreshEnabled() {
    if (typeof window.StockQPro?.pages?.tasks?.isAutoRefresh === 'function') {
      return window.StockQPro.pages.tasks.isAutoRefresh();
    }
    return true;
  },

  /**
   * 初始化：綁定事件
   */
  init() {
    if (this._bound) return;
    this._bound = true;
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
    if (typeof TaskCommon !== 'undefined') {
      await TaskCommon.loadTypes();
      this._populateTypeFilter();
    }
    if (typeof App !== 'undefined') App._pauseTaskPoll = true;
    this._pollCount = 0;
    this._expandedRows.clear();
    this._selectedIds.clear();
    this._updateBatchBar();
    this._bindWsEvents();
    await this.refresh();
    this._startPolling();
  },

  _populateTypeFilter() {
    const sel = document.getElementById('taskTypeFilter');
    if (!sel || typeof TaskCommon === 'undefined') return;
    const current = sel.value;
    let html = '<option value="">全部類型</option>';
    const types = TaskCommon._asyncTypes.length
      ? TaskCommon._asyncTypes
      : Object.keys(TaskCommon.TYPE_NAMES).map(id => ({
        id,
        label: (TaskCommon.TYPE_NAMES[id] || id).replace(/^[^\s]+\s/, ''),
        icon: (TaskCommon.TYPE_NAMES[id] || '').split(' ')[0] || '',
      }));
    types.forEach(t => {
      const text = t.icon ? `${t.icon} ${t.label}` : t.label;
      html += `<option value="${t.id}">${text}</option>`;
    });
    sel.innerHTML = html;
    if (current && [...sel.options].some(o => o.value === current)) sel.value = current;
  },

  unload() {
    this._stopPolling();
    this._unbindWsEvents();
    if (typeof App !== 'undefined') App._pauseTaskPoll = false;
  },

  _startPolling() {
    this._stopPolling();
    if (!this.isAutoRefreshEnabled()) return;
    this._pollTimer = setInterval(() => {
      if (!this.isAutoRefreshEnabled()) {
        this._stopPolling();
        return;
      }
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

  // ── WebSocket 實時更新 ────────────────────────────────────

  _bindWsEvents() {
    this._unbindWsEvents();
    this._wsHandler = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (!data || !data.type) return;
        if (data.type === 'task_log' && data.task_id) {
          this._appendLiveLog(data.task_id, data.log);
          return;
        }
        if (!data.type.startsWith('task_')) return;
        this._pollCount = 0;
        this.refresh(true);
      } catch (_) {}
    };
    if (typeof App !== 'undefined' && App._ws) {
      App._ws.addEventListener('message', this._wsHandler);
    }
  },

  _unbindWsEvents() {
    if (this._wsHandler && typeof App !== 'undefined' && App._ws) {
      try { App._ws.removeEventListener('message', this._wsHandler); } catch (_) {}
    }
    this._wsHandler = null;
  },

  /** WebSocket 重連後重新綁定（由 App._connectWS onopen 呼叫） */
  rebindWs() {
    if (!this._bound) return;
    this._bindWsEvents();
  },

  // ── 批量操作 ──────────────────────────────────────────────

  _toggleSelect(taskId) {
    if (this._selectedIds.has(taskId)) {
      this._selectedIds.delete(taskId);
    } else {
      this._selectedIds.add(taskId);
    }
    this._updateBatchBar();
    // 更新 checkbox 視覺
    const cb = document.getElementById(`cb-${taskId}`);
    if (cb) cb.checked = this._selectedIds.has(taskId);
  },

  _toggleSelectAll() {
    const tasks = this._lastData?.tasks || [];
    const filtered = this._getFilteredTasks(tasks);
    const allSelected = filtered.every(t => this._selectedIds.has(t.task_id));
    if (allSelected) {
      filtered.forEach(t => this._selectedIds.delete(t.task_id));
    } else {
      filtered.forEach(t => this._selectedIds.add(t.task_id));
    }
    this._renderTaskTable(tasks);
    this._updateBatchBar();
  },

  _updateBatchBar() {
    const bar = document.getElementById('taskBatchBar');
    if (!bar) return;
    const count = this._selectedIds.size;
    bar.style.display = count > 0 ? 'flex' : 'none';
    const countEl = document.getElementById('taskBatchCount');
    if (countEl) countEl.textContent = count;
  },

  async batchCancel() {
    const ids = [...this._selectedIds];
    if (!ids.length) return;
    if (!await Utils.confirm(`確定要取消 ${ids.length} 個任務？`)) return;
    const d = await Api.batchCancelTasks(ids);
    if (d?.success) {
      const n = (d.cancelled || []).length;
      Utils.toast(`已取消 ${n} 個任務`, 2000, 'success');
      this._selectedIds.clear();
      this._updateBatchBar();
      this.refresh();
    }
  },

  async cancelAllPending() {
    if (!await Utils.confirm('確定取消所有排隊中的任務？')) return;
    const d = await Api.cancelAllPendingTasks();
    if (d?.success) {
      Utils.toast(`已取消 ${d.cancelled || 0} 個排隊任務`, 2000, 'success');
      this.refresh();
    }
  },

  async clearCompleted() {
    if (!await Utils.confirm('確定清空所有已結束的任務記錄？')) return;
    const d = await Api.clearCompletedTasks(true, true);
    if (d?.success) {
      Utils.toast(`已清除 ${d.deleted || 0} 條記錄`, 2000, 'success');
      this._selectedIds.clear();
      this._expandedRows.clear();
      this.refresh();
    }
  },

  async batchDelete() {
    const ids = [...this._selectedIds];
    if (!ids.length) return;
    if (!await Utils.confirm(`確定要刪除 ${ids.length} 個任務？此操作不可撤銷。`, { variant: 'danger' })) return;
    const d = await Api.batchDeleteTasks(ids);
    if (d?.success) {
      const n = (d.deleted || []).length;
      Utils.toast(`已刪除 ${n} 個任務`, 2000, 'success');
      ids.forEach(id => { this._expandedRows.delete(id); this._paramsCache.delete(id); });
      this._selectedIds.clear();
      this._updateBatchBar();
      this.refresh();
    }
  },

  async retryTask(taskId) {
    const d = await Api.retryTask(taskId);
    if (d?.success) {
      Utils.toast(d.message || '已提交重試', 2000, 'success');
      this.refresh();
    } else {
      Utils.toast('重試失敗', 2000, 'error');
    }
  },

  _getFilters() {
    return {
      search: (document.getElementById('taskSearch')?.value || '').trim().toLowerCase(),
      taskType: document.getElementById('taskTypeFilter')?.value || '',
      status: document.getElementById('taskStatusFilter')?.value || '',
    };
  },

  _getFilteredTasks(tasks) {
    const { search } = this._getFilters();
    let list = tasks;
    if (this._todayOnly) {
      const today = new Date().toISOString().slice(0, 10);
      list = list.filter(t => (t.created_at || '').slice(0, 10) === today);
    }
    if (this._hasResultOnly) {
      list = list.filter(t => t.has_result || (t.status === 'completed' && t.result));
    }
    if (!search) return list;
    return list.filter(t => {
      const haystack = [t.title, t.task_type, TaskCommon.typeName(t.task_type)].join(' ').toLowerCase();
      return haystack.includes(search);
    });
  },

  /**
   * 刷新所有數據
   */
  async refresh(silent) {
    const { taskType, status } = this._getFilters();
    if (!silent) this._setLoading(true);

    const pollOpts = { silent: !!silent, noCache: !!silent };
    const d = await Api.getTasks(taskType || null, status || null, 200, pollOpts);
    if (!silent) this._setLoading(false);

    if (!d || d._rateLimited) {
      if (d?._rateLimited && this._lastData) {
        this._renderFromPayload(this._lastData);
      } else if (!silent) {
        this._loadError = d?._rateLimited ? '請求過於頻繁，稍後自動重試' : '任務列表載入失敗，請確認已登錄或刷新頁面';
        this._showLoadError();
      }
      return;
    }

    this._loadError = '';
    this._lastData = d;
    this._renderFromPayload(d);
    if (typeof window.StockQPro?.pages?.tasks?.markSynced === 'function') {
      window.StockQPro.pages.tasks.markSynced();
    }
    for (const id of this._expandedRows) {
      this._loadParams(id);
    }
  },

  _renderFromPayload(d) {
    const queue = d.queue || {};
    const tasks = d.tasks || [];
    this._renderStats(d.stats);
    this._renderQueue(queue);
    this._renderRunningTasks(tasks);
    this._renderTaskTable(tasks);
    this._updateNavBadge(d.stats);
    this._hideLoadError();
  },

  _showLoadError() {
    const banner = document.getElementById('taskLoadErrorBanner');
    if (banner) {
      banner.style.display = 'block';
      banner.textContent = this._loadError || '載入失敗';
      return;
    }
    const tbody = document.getElementById('taskTableBody');
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="9">
      <div class="empty-state">
        <span class="empty-icon">⚠️</span>
        <p><strong>${this._loadError || '載入失敗'}</strong></p>
        <button class="btn s" style="margin-top:8px" onclick="Tasks.refresh()">🔄 重試</button>
      </div>
    </td></tr>`;
  },

  _hideLoadError() {
    const el = document.getElementById('taskLoadErrorBanner');
    if (el) {
      el.style.display = 'none';
      el.textContent = '';
    }
  },

  _renderQueue(snapshot) {
    const grid = document.getElementById('taskQueueGrid');
    if (!grid || typeof TaskCommon === 'undefined') return;
    grid.innerHTML = TaskCommon.renderQueueSection(snapshot || {}, false);
    const recent = TaskCommon.splitQueue(snapshot || {}).recent;
    if (recent?.task_id && typeof App !== 'undefined' && App.markTaskCompletedSeen(recent)) {
      if (typeof Utils !== 'undefined') {
        Utils.toast('✅ 任務完成: ' + (recent.title || ''), 3000, 'success');
      }
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
    const heavyMax = stats.heavy_max_concurrent || '-';
    const heavyFlight = stats.heavy_in_flight ?? 0;
    const inFlight = stats.in_flight ?? stats.running ?? 0;
    const items = [
      { icon: '📋', label: '總任務數', value: stats.total || 0, color: '', filter: '' },
      { icon: '⚙️', label: '並行槽', value: `${inFlight}/${maxW}`, color: '#38bdf8', filter: '' },
      { icon: '🧠', label: '重型併發', value: `${heavyFlight}/${heavyMax}`, color: '#a78bfa', filter: '' },
      { icon: '⏸️', label: '隊列', value: stats.pending || 0, color: '#f59e0b', filter: 'pending' },
      { icon: '⏳', label: '運行中', value: stats.running || 0, color: '#38bdf8', filter: 'running' },
      { icon: '✅', label: '已完成', value: stats.completed || 0, color: '#22c55e', filter: 'completed' },
      { icon: '❌', label: '失敗', value: stats.failed || 0, color: '#ef4444', filter: 'failed' },
      { icon: '🚫', label: '已取消', value: stats.cancelled || 0, color: '#94a3b8', filter: 'cancelled' },
    ];
    grid.innerHTML = items.map(i =>
      `<div class="c stat-card task-stat-card" data-stat-filter="${i.filter || ''}" role="button" tabindex="0" title="${i.filter ? '點擊篩選' : ''}"><h3>${i.icon} ${i.label}</h3>` +
      `<div class="v" ${i.color ? `style="color:${i.color}"` : ''}>${i.value}</div></div>`
    ).join('');
  },

  // ── 運行中任務 ────────────────────────────────────────────

  _renderRunningTasks(tasks) {
    const section = document.getElementById('taskRunningSection');
    const list = document.getElementById('taskRunningList');
    const countEl = document.getElementById('taskRunningCount');
    if (!section || !list) return;

    const running = tasks.filter(t => ['running', 'pending', 'retrying'].includes(t.status));
    section.style.display = running.length ? 'block' : 'none';
    if (countEl) countEl.textContent = running.length ? `${running.length} 個` : '';

    list.innerHTML = running.map(t => {
      const typeName = TaskCommon.typeName(t.task_type);
      const progress = t.progress || 0;
      const icon = t.status === 'pending' ? '⏸️' : (t.status === 'retrying' ? '🔄' : '⏳');
      const pulse = (t.status === 'running' || t.status === 'retrying')
        ? 'animation:pulse 1.5s infinite;' : '';
      const sub = TaskCommon.formatTaskSubtitle(t);
      const elapsed = t.elapsed_sec > 0 ? TaskCommon.formatElapsed(Math.round(t.elapsed_sec)) : '';
      const eta = t.eta_sec > 0 && t.status === 'running' ? TaskCommon.formatEta(t.eta_sec) : '';
      const timeParts = [];
      if (elapsed) timeParts.push(`⏱ ${elapsed}`);
      if (eta) timeParts.push(`⏳ 剩餘 ${eta}`);
      const timeStr = timeParts.join(' · ');
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
          ${timeStr ? `<div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">${timeStr}</div>` : ''}
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
    const filtered = this._getFilteredTasks(tasks);

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
      tbody.innerHTML = `<tr><td colspan="9">
        <div class="empty-state">
          <span class="empty-icon">📋</span>
          <p><strong>暫無任務記錄</strong></p>
          <p>前往回測、組合回測、優化或數據中心提交任務後，將在此顯示</p>
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

    // 更新全選 checkbox 狀態
    const selectAllCb = document.getElementById('taskSelectAll');
    if (selectAllCb) {
      const allSelected = filtered.length > 0 && filtered.every(t => this._selectedIds.has(t.task_id));
      selectAllCb.checked = allSelected;
      selectAllCb.indeterminate = !allSelected && filtered.some(t => this._selectedIds.has(t.task_id));
    }

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
    const canCancel = ['running', 'pending', 'retrying'].includes(t.status);
    const canDelete = ['completed', 'failed', 'cancelled'].includes(t.status);
    const canRetry = ['failed', 'cancelled'].includes(t.status);
    const isSelected = this._selectedIds.has(t.task_id);

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

    // 時間信息
    const elapsed = t.elapsed_sec > 0 ? TC.formatElapsed(Math.round(t.elapsed_sec)) : '';
    const eta = t.eta_sec > 0 && t.status === 'running' ? TC.formatEta(t.eta_sec) : '';
    const timeHtml = elapsed ? `<span title="${eta ? '預估剩餘: ' + eta : ''}">${elapsed}${eta ? ' · ' + eta : ''}</span>` : '-';
    const preview = TC.formatResultPreview(t);
    const previewHtml = preview
      ? `<span class="task-preview" style="color:var(--t2);white-space:normal;line-height:1.35">${preview}</span>`
      : '<span style="color:var(--t3)">—</span>';

    // 操作按鈕
    let actions = '';
    if (canView) {
      actions += TaskCommon.renderNavigateButton(t.task_id, '前往') + ' ';
      actions += `<button class="btn s" style="padding:2px 8px;font-size:10px" onclick="Tasks.viewResult('${t.task_id}')">📊 結果</button> `;
    }
    if (canCancel) actions += `<button class="btn danger" style="padding:2px 8px;font-size:10px" onclick="Tasks.cancelTask('${t.task_id}')">取消</button> `;
    if (canRetry) actions += `<button class="btn s" style="padding:2px 8px;font-size:10px" onclick="Tasks.retryTask('${t.task_id}')">🔄</button> `;
    if (canDelete) actions += `<button class="btn s" style="padding:2px 8px;font-size:10px;color:var(--text-dim)" onclick="Tasks.deleteTask('${t.task_id}')">🗑️</button> `;
    actions += `<button class="btn s" style="padding:2px 8px;font-size:10px" onclick="Tasks.toggleExpand('${t.task_id}')">${isExpanded ? '收起' : '詳情'}</button>`;

    // 展開詳情行
    let detailRow = '';
    if (isExpanded) {
      const elapsedStr = TC.formatElapsed(elapsed ? TC.elapsed(t.started_at || t.created_at, t.completed_at) : null);
      detailRow = `
        <tr id="detail-${t.task_id}" class="task-detail-row">
          <td colspan="9" style="padding:0">
            <div style="background:var(--bg-primary);border-top:1px solid var(--border-color);padding:12px 16px;animation:tabFadeIn .2s ease">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div>
                  <div style="font-size:12px;font-weight:600;color:var(--text-dim);margin-bottom:6px">📋 任務參數</div>
                  <div id="params-${t.task_id}" style="font-size:12px">載入中...</div>
                </div>
                <div>
                  <div style="font-size:12px;font-weight:600;color:var(--text-dim);margin-bottom:6px">ℹ️ 執行信息</div>
                  <table style="font-size:12px;width:100%">
                    <tr><td style="color:var(--text-dim)">任務ID</td><td style="word-break:break-all">${t.task_id}
                      <button type="button" class="btn s" style="margin-left:6px;padding:2px 8px;font-size:10px" onclick="event.stopPropagation();Tasks.copyTaskId('${t.task_id}')">複製</button>
                    </td></tr>
                    <tr><td style="color:var(--text-dim)">類型</td><td>${typeName}</td></tr>
                    <tr><td style="color:var(--text-dim)">創建時間</td><td>${t.created_at || '-'}</td></tr>
                    <tr><td style="color:var(--text-dim)">完成時間</td><td>${t.completed_at || '-'}</td></tr>
                    <tr><td style="color:var(--text-dim)">執行耗時</td><td>${elapsed || '-'}</td></tr>
                  </table>
                </div>
              </div>
                  ${t.error ? TC.renderError(t.error) : ''}
              <div style="margin-top:10px">
                <div style="font-size:12px;font-weight:600;color:var(--text-dim);margin-bottom:6px">📜 執行日誌</div>
                <pre id="logs-${t.task_id}" class="task-log-panel" style="font-size:11px;max-height:200px;overflow:auto;margin:0;padding:8px;background:var(--bg-secondary);border-radius:6px;white-space:pre-wrap">載入中...</pre>
              </div>
            </div>
          </td>
        </tr>`;

      setTimeout(() => {
        this._loadParams(t.task_id);
        this._loadLogs(t.task_id);
      }, 0);
    }

    const cbHtml = `<input type="checkbox" id="cb-${t.task_id}" ${isSelected ? 'checked' : ''} onclick="event.stopPropagation();Tasks._toggleSelect('${t.task_id}')" style="cursor:pointer">`;

    const dbl = canView ? ` ondblclick="event.stopPropagation();TaskCommon.navigateToResult('${t.task_id}')"` : '';

    return `
      <tr class="${isSelected ? 'task-row-selected' : ''}" style="cursor:pointer" onclick="Tasks.toggleExpand('${t.task_id}')"${dbl} title="${canView ? '雙擊前往結果' : ''}">
        <td style="text-align:center">${cbHtml}</td>
        <td>${statusHtml}</td>
        <td><span style="font-size:12px">${typeName}</span></td>
        <td style="font-weight:500">${t.title || '-'}${sub ? `<div style="font-size:11px;color:#38bdf8;font-weight:400;margin-top:2px">${sub}</div>` : ''}</td>
        <td>${progressHtml}</td>
        <td style="font-size:11px;max-width:200px">${previewHtml}</td>
        <td style="font-size:11px;color:var(--text-dim)">${timeHtml}</td>
        <td style="font-size:11px;color:var(--text-dim)" title="${t.created_at || ''}">${Utils.timeAgo(t.created_at)}</td>
        <td onclick="event.stopPropagation()">${actions}</td>
      </tr>${detailRow}`;
  },

  async copyTaskId(taskId) {
    const id = String(taskId || '');
    if (!id) return;
    if (typeof Utils !== 'undefined' && Utils.copyText) {
      await Utils.copyText(id);
      Utils.toast('已複製任務 ID', 1500, 'success');
      return;
    }
    try {
      await navigator.clipboard.writeText(id);
      Utils.toast('已複製任務 ID', 1500, 'success');
    } catch (_) {
      Utils.toast('複製失敗', 2000, 'error');
    }
  },

  exportTaskList() {
    const tasks = this._getFilteredTasks(this._lastData?.tasks || []);
    const payload = {
      exported_at: new Date().toISOString(),
      count: tasks.length,
      tasks: tasks.map(t => ({
        task_id: t.task_id,
        task_type: t.task_type,
        title: t.title,
        status: t.status,
        progress: t.progress,
        created_at: t.created_at,
        completed_at: t.completed_at,
        result_preview: t.result_preview,
        error: t.error,
      })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `tasks_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    Utils.toast(`已匯出 ${tasks.length} 條任務`, 2000, 'success');
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
  _appendLiveLog(taskId, entry) {
    const el = document.getElementById(`logs-${taskId}`);
    if (!el || !entry) return;
    const line = `[${entry.ts || ''}] ${entry.message || ''}\n`;
    if (el.textContent === '載入中...') el.textContent = '';
    el.textContent += line;
    el.scrollTop = el.scrollHeight;
  },

  async _loadLogs(taskId) {
    const el = document.getElementById(`logs-${taskId}`);
    if (!el) return;
    const d = await Api.getTaskLogs(taskId, 150);
    const logs = d?.logs || [];
    if (!logs.length) {
      el.textContent = '（暫無日誌）';
      return;
    }
    el.textContent = logs.map(l => `[${l.ts}] ${l.message}`).join('\n');
    el.scrollTop = el.scrollHeight;
  },

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
    const active = (stats?.running || 0) + (stats?.pending || 0) + (stats?.retrying || 0);
    if (badge) {
      badge.textContent = active;
      badge.style.display = active > 0 ? 'inline-block' : 'none';
    }
    if (typeof window.StockQPro?.pages?.tasks?.updateBadges === 'function') {
      window.StockQPro.pages.tasks.updateBadges(stats, active);
    }
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

// 動態注入任務相關樣式
if (!document.getElementById('taskShimmerStyle')) {
  const style = document.createElement('style');
  style.id = 'taskShimmerStyle';
  style.textContent = `
    @keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
    .task-row-selected{background:rgba(56,189,248,0.06)!important}
    .task-row-selected:hover{background:rgba(56,189,248,0.1)!important}
    .task-time-info{font-size:11px;color:var(--text-dim);margin-top:4px;display:flex;align-items:center;gap:4px}
    .task-batch-bar{display:none;align-items:center;gap:12px;padding:8px 16px;background:var(--bg-secondary);border-radius:8px;margin-bottom:12px;border:1px solid var(--accent)}
    .task-batch-bar .count{font-weight:700;color:var(--accent)}
  `;
  document.head.appendChild(style);
}

window.Tasks = Tasks;
