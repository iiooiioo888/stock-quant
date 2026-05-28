/* global Api, Utils, TaskCommon */

/**
 * StockQ Pro 任務中心 — 統一引擎 + 頁面生命週期
 * 列表卡片 + 右側詳情抽屜，WebSocket 優先、輪詢降級
 */
(() => {
  const proApp = () => window.StockQPro?.App;
  const STORAGE_AUTO = 'sq_pro_tasks_auto_refresh';

  const Tasks = {
    _pollTimer: null,
    _pollInterval: 6000,
    _maxPolls: 500,
    _pollCount: 0,
    _lastData: null,
    _loadError: '',
    _searchDebounce: null,
    _sortCol: 'created_at',
    _sortAsc: false,
    _detailId: null,
    _paramsCache: new Map(),
    _bound: false,
    _selectedIds: new Set(),
    _wsHandler: null,
    _todayOnly: false,
    _hasResultOnly: false,

    isAutoRefreshEnabled() {
      if (typeof window.StockQPro?.pages?.tasks?.isAutoRefresh === 'function') {
        return window.StockQPro.pages.tasks.isAutoRefresh();
      }
      const el = document.getElementById('tk-auto-refresh');
      return el ? el.checked : sessionStorage.getItem(STORAGE_AUTO) !== '0';
    },

    toast(msg, type = 'info') {
      const map = { success: 'ok', warning: 'warn', error: 'er', info: 'inf' };
      const app = proApp();
      if (app?.toast) app.toast(String(msg || ''), map[type] || 'inf');
      else if (typeof Utils !== 'undefined') Utils.toast(msg, 3000, type);
    },

    init() {
      if (this._bound) return;
      this._bound = true;

      document.getElementById('taskSearch')?.addEventListener('input', () => {
        clearTimeout(this._searchDebounce);
        this._searchDebounce = setTimeout(() => this.refresh(), 280);
      });
      ['taskTypeFilter', 'taskStatusFilter'].forEach((id) => {
        document.getElementById(id)?.addEventListener('change', () => this.refresh());
      });
      document.getElementById('taskBatchCancelBtn')?.addEventListener('click', () => this.batchCancel());
      document.getElementById('taskBatchDeleteBtn')?.addEventListener('click', () => this.batchDelete());
      document.getElementById('tk-detail-close')?.addEventListener('click', () => this.closeDetail());

      const list = document.getElementById('tkTaskList');
      if (list) {
        list.addEventListener('click', (e) => {
          const card = e.target.closest('.tk-card');
          if (!card) return;
          if (e.target.closest('button, input, a, label')) return;
          this.openDetail(card.getAttribute('data-task-id'));
        });
      }
    },

    async load() {
      this.init();
      if (typeof TaskCommon !== 'undefined') {
        await TaskCommon.loadTypes();
        this._populateTypeFilter();
      }
      this._pollCount = 0;
      this._selectedIds.clear();
      this._updateBatchBar();
      this._bindWsEvents();
      await this.refresh();
      this._startPolling();
    },

    unload() {
      this._stopPolling();
      this._unbindWsEvents();
      this.closeDetail();
    },

    _populateTypeFilter() {
      const sel = document.getElementById('taskTypeFilter');
      if (!sel || typeof TaskCommon === 'undefined') return;
      const current = sel.value;
      let html = '<option value="">全部類型</option>';
      const types = TaskCommon._asyncTypes.length
        ? TaskCommon._asyncTypes
        : Object.keys(TaskCommon.TYPE_NAMES).map((id) => ({
          id,
          label: (TaskCommon.TYPE_NAMES[id] || id).replace(/^[^\s]+\s/, ''),
        }));
      types.forEach((t) => {
        const text = t.icon ? `${t.icon} ${t.label}` : t.label;
        html += `<option value="${t.id}">${text}</option>`;
      });
      sel.innerHTML = html;
      if (current && [...sel.options].some((o) => o.value === current)) sel.value = current;
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
      if (this._pollTimer) {
        clearInterval(this._pollTimer);
        this._pollTimer = null;
      }
    },

    _bindWsEvents() {
      this._unbindWsEvents();
      this._wsHandler = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (!data?.type) return;
          if (data.type === 'task_log' && data.task_id) {
            this._appendLiveLog(data.task_id, data.log);
            return;
          }
          if (!data.type.startsWith('task_')) return;
          if (data.type === 'task_progress' && this._patchTaskFromWs(data)) return;
          this._pollCount = 0;
          this.refresh(true);
        } catch (_) {}
      };
      const ws = proApp()?._ws;
      if (ws) ws.addEventListener('message', this._wsHandler);
    },

    _unbindWsEvents() {
      const ws = proApp()?._ws;
      if (this._wsHandler && ws) {
        try { ws.removeEventListener('message', this._wsHandler); } catch (_) {}
      }
      this._wsHandler = null;
    },

    rebindWs() {
      if (!this._bound) return;
      this._bindWsEvents();
    },


    _patchTaskFromWs(data) {
      if (!data?.task_id || !this._lastData?.tasks) return false;
      const idx = this._lastData.tasks.findIndex((t) => t.task_id === data.task_id);
      if (idx < 0) return false;
      const cur = this._lastData.tasks[idx];
      const next = {
        ...cur,
        status: data.status ?? cur.status,
        progress: data.progress ?? cur.progress,
        error: data.error ?? cur.error,
      };
      this._lastData.tasks[idx] = next;
      const card = document.querySelector(`[data-task-id="${data.task_id}"]`);
      if (card) {
        const fill = card.querySelector('.tk-card-progress-fill');
        const pct = card.querySelector('.tk-pct');
        if (fill) fill.style.width = `${next.progress || 0}%`;
        if (pct) pct.textContent = `${next.progress || 0}%`;
      }
      if (this._detailId === data.task_id) this._renderDetail(next);
      return true;
    },

    _getFilters() {
      return {
        search: (document.getElementById('taskSearch')?.value || '').trim().toLowerCase(),
        taskType: document.getElementById('taskTypeFilter')?.value || '',
        status: document.getElementById('taskStatusFilter')?.value || '',
      };
    },

    _getFilteredTasks(tasks) {
      const { search, taskType, status } = this._getFilters();
      let list = tasks || [];
      if (taskType) list = list.filter((t) => t.task_type === taskType);
      if (status) list = list.filter((t) => t.status === status);
      if (this._todayOnly) {
        const today = new Date().toISOString().slice(0, 10);
        list = list.filter((t) => (t.created_at || '').slice(0, 10) === today);
      }
      if (this._hasResultOnly) {
        list = list.filter((t) => t.has_result || (t.status === 'completed' && t.result));
      }
      if (!search) return list;
      return list.filter((t) => {
        const hay = [t.title, t.task_type, TaskCommon.typeName(t.task_type)].join(' ').toLowerCase();
        return hay.includes(search);
      });
    },

    async refresh(silent) {
      const { taskType, status } = this._getFilters();
      if (!silent) this._setLoading(true);

      const d = await Api.getTasks(taskType || null, status || null, 200, {
        silent: !!silent,
        noCache: !!silent,
      });
      if (!silent) this._setLoading(false);

      if (!d || d._rateLimited) {
        if (d?._rateLimited && this._lastData) this._renderFromPayload(this._lastData);
        else if (!silent) {
          this._loadError = d?._rateLimited ? '請求過於頻繁，稍後自動重試' : '任務列表載入失敗';
          this._showLoadError();
        }
        return;
      }

      this._loadError = '';
      this._lastData = d;
      this._renderFromPayload(d);
      window.StockQPro?.pages?.tasks?.markSynced?.();
      if (this._detailId) this._renderDetail(this._findTask(this._detailId));
    },

    _findTask(id) {
      return (this._lastData?.tasks || []).find((t) => t.task_id === id) || null;
    },

    _renderFromPayload(d) {
      const tasks = d.tasks || [];
      this._renderCapacity(d.stats);
      this._renderStats(d.stats);
      this._renderQueue(d.queue || {});
      this._renderTaskList(tasks);
      this._updateNavBadge(d.stats);
      this._hideLoadError();
    },

    _renderCapacity(stats) {
      const el = document.getElementById('tkCapacityBar');
      if (!el || !stats) return;
      const maxW = Number(stats.max_workers) || 1;
      const inFlight = Number(stats.in_flight ?? stats.running ?? 0);
      const heavyMax = Number(stats.heavy_max_concurrent) || 0;
      const heavyFlight = Number(stats.heavy_in_flight) || 0;
      const pct = Math.min(100, Math.round((inFlight / maxW) * 100));
      const heavyPct = heavyMax ? Math.min(100, Math.round((heavyFlight / heavyMax) * 100)) : 0;
      el.innerHTML = `
        <div class="tk-cap-inner">
          <div class="tk-cap-row">
            <span class="tk-cap-label">API 並行槽</span>
            <span class="tk-cap-val">${inFlight} / ${maxW}</span>
          </div>
          <div class="tk-cap-track"><div class="tk-cap-fill" style="width:${pct}%"></div></div>
          ${heavyMax ? `
          <div class="tk-cap-row" style="margin-top:8px">
            <span class="tk-cap-label">重型任務</span>
            <span class="tk-cap-val">${heavyFlight} / ${heavyMax}</span>
          </div>
          <div class="tk-cap-track tk-cap-track--heavy"><div class="tk-cap-fill tk-cap-fill--heavy" style="width:${heavyPct}%"></div></div>
          ` : ''}
        </div>`;
    },

    _showLoadError() {
      const banner = document.getElementById('taskLoadErrorBanner');
      if (banner) {
        banner.style.display = 'block';
        banner.textContent = this._loadError;
        return;
      }
      const list = document.getElementById('tkTaskList');
      if (list) {
        list.innerHTML = `<div class="tk-empty"><span class="tk-empty-icon">⚠️</span><p>${this._loadError}</p><button type="button" class="btn s" id="tk-retry-load">重試</button></div>`;
        document.getElementById('tk-retry-load')?.addEventListener('click', () => this.refresh());
      }
    },

    _hideLoadError() {
      const banner = document.getElementById('taskLoadErrorBanner');
      if (banner) {
        banner.style.display = 'none';
        banner.textContent = '';
      }
    },

    _skeletonHtml(count = 5) {
      return Array.from({ length: count }, () => `
        <div class="tk-card tk-card--skeleton" aria-hidden="true">
          <div class="tk-skel-line tk-skel-title skeleton"></div>
          <div class="tk-skel-line tk-skel-meta skeleton"></div>
          <div class="tk-skel-bar skeleton"></div>
        </div>`).join('');
    },

    _setLoading(loading) {
      const el = document.getElementById('taskLoadingIndicator');
      if (el) el.style.display = 'none';
      const list = document.getElementById('tkTaskList');
      if (loading && !this._lastData && list) {
        list.innerHTML = this._skeletonHtml(5);
      }
    },

    _renderQueue(snapshot) {
      const grid = document.getElementById('taskQueueGrid');
      if (!grid || typeof TaskCommon === 'undefined') return;
      grid.innerHTML = TaskCommon.renderQueueSection(snapshot || {}, false);
      grid.querySelectorAll('[data-tk-queue-action]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const action = btn.getAttribute('data-tk-queue-action');
          const id = btn.getAttribute('data-task-id');
          if (action === 'cancel') this.cancelTask(id);
          else if (action === 'retry') this.retryTask(id);
          else if (action === 'result') this.viewResult(id);
        });
      });
      grid.querySelectorAll('[data-tk-goto]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const id = btn.getAttribute('data-tk-goto');
          if (id) TaskCommon.navigateToResult(id);
        });
      });
    },

    _renderStats(stats) {
      if (!stats) return;
      const grid = document.getElementById('taskStatsGrid');
      if (!grid) return;
      const maxW = stats.max_workers || '-';
      const inFlight = stats.in_flight ?? stats.running ?? 0;
      const items = [
        { icon: '📋', label: '總數', value: stats.total || 0, color: '', filter: '' },
        { icon: '⚙️', label: '並行', value: `${inFlight}/${maxW}`, color: 'var(--bl)', filter: '' },
        { icon: '📋', label: '隊列', value: stats.pending || 0, color: 'var(--am)', filter: 'pending' },
        { icon: '⏳', label: '運行', value: stats.running || 0, color: 'var(--bl)', filter: 'running' },
        { icon: '✅', label: '完成', value: stats.completed || 0, color: 'var(--quote-up)', filter: 'completed' },
        { icon: '❌', label: '失敗', value: stats.failed || 0, color: 'var(--quote-down)', filter: 'failed' },
      ];
      grid.innerHTML = items.map((i) => `
        <div class="c stat-card task-stat-card" data-stat-filter="${i.filter || ''}" role="button" tabindex="0">
          <h3>${i.icon} ${i.label}</h3>
          <div class="v" ${i.color ? `style="color:${i.color}"` : ''}>${i.value}</div>
        </div>`).join('');
    },

    _renderTaskList(tasks) {
      const list = document.getElementById('tkTaskList');
      if (!list) return;
      const filtered = this._getFilteredTasks(tasks);
      filtered.sort((a, b) => {
        let va = a[this._sortCol] ?? '';
        let vb = b[this._sortCol] ?? '';
        if (this._sortCol === 'progress') {
          va = Number(va);
          vb = Number(vb);
        } else {
          va = String(va).toLowerCase();
          vb = String(vb).toLowerCase();
        }
        if (va < vb) return this._sortAsc ? -1 : 1;
        if (va > vb) return this._sortAsc ? 1 : -1;
        return 0;
      });

      if (!filtered.length) {
        list.innerHTML = `
          <div class="tk-empty">
            <span class="tk-empty-icon">📋</span>
            <p><strong>暫無任務</strong></p>
            <p class="tk-empty-hint">在回測、優化或數據下載提交後會出現在此</p>
          </div>`;
        return;
      }

      const active = filtered.filter((t) => ['running', 'pending', 'retrying'].includes(t.status));
      const done = filtered.filter((t) => !['running', 'pending', 'retrying'].includes(t.status));
      let html = '';
      if (active.length) {
        html += `<div class="tk-list-section-hd">進行中 · ${active.length}</div>`;
        html += active.map((t) => this._renderCard(t)).join('');
      }
      if (done.length) {
        html += `<div class="tk-list-section-hd">歷史 · ${done.length}</div>`;
        html += done.map((t) => this._renderCard(t)).join('');
      }
      list.innerHTML = html;

      list.querySelectorAll('.tk-card-chk').forEach((cb) => {
        cb.addEventListener('click', (e) => e.stopPropagation());
        cb.addEventListener('change', () => this._toggleSelect(cb.getAttribute('data-id'), cb.checked));
      });
      list.querySelectorAll('[data-action]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const action = btn.getAttribute('data-action');
          const id = btn.getAttribute('data-id');
          if (action === 'cancel') this.cancelTask(id);
          else if (action === 'delete') this.deleteTask(id);
          else if (action === 'retry') this.retryTask(id);
          else if (action === 'result') this.viewResult(id);
          else if (action === 'goto') TaskCommon.navigateToResult(id);
          else if (action === 'detail') this.openDetail(id);
        });
      });

      if (this._detailId) {
        list.querySelectorAll('.tk-card').forEach((c) => {
          c.classList.toggle('is-selected', c.getAttribute('data-task-id') === this._detailId);
        });
      }
    },

    _renderCard(t) {
      const TC = TaskCommon;
      const typeName = TC.typeName(t.task_type);
      const schedBadge = t.is_scheduled
        ? '<span class="badge b-am tk-scheduled-badge" title="定時任務">定時</span>'
        : '';
      const icon = TC.STATUS_ICONS[t.status] || '❓';
      const color = TC.STATUS_COLORS[t.status] || '#94a3b8';
      const isActive = ['running', 'pending', 'retrying'].includes(t.status);
      const sub = TC.formatTaskSubtitle(t);
      const preview = TC.formatResultPreview(t);
      const selected = this._selectedIds.has(t.task_id);
      const isDetail = this._detailId === t.task_id;
      const progress = Number(t.progress) || 0;
      const elapsed = t.elapsed_sec > 0 ? TC.formatElapsed(Math.round(t.elapsed_sec)) : '';
      const eta = t.eta_sec > 0 && t.status === 'running' ? TC.formatEta(t.eta_sec) : '';

      let actions = '';
      if (t.status === 'completed' && t.has_result) {
        actions += `<button type="button" class="btn btn-s btn-ac" data-action="goto" data-id="${t.task_id}">查看</button>`;
        actions += `<button type="button" class="btn btn-s" data-action="result" data-id="${t.task_id}">摘要</button>`;
      }
      if (['running', 'pending', 'retrying'].includes(t.status)) {
        actions += `<button type="button" class="btn btn-s btn-rd" data-action="cancel" data-id="${t.task_id}">取消</button>`;
      }
      if (['failed', 'cancelled'].includes(t.status)) {
        actions += `<button type="button" class="btn btn-s" data-action="retry" data-id="${t.task_id}">重試</button>`;
      }
      if (['completed', 'failed', 'cancelled'].includes(t.status)) {
        actions += `<button type="button" class="btn btn-s" data-action="delete" data-id="${t.task_id}">刪除</button>`;
      }

      return `
        <article class="tk-card ${isActive ? 'is-active' : ''} ${isDetail ? 'is-selected' : ''}" data-task-id="${t.task_id}" data-status="${t.status}">
          <div class="tk-card-hd">
            <input type="checkbox" class="tk-card-chk" data-id="${t.task_id}" ${selected ? 'checked' : ''} aria-label="選取" />
            <span class="tk-status-dot" style="--tk-status-color:${color}" title="${t.status}">${icon}</span>
            <div class="tk-card-titles">
              <div class="tk-card-title-row">${schedBadge}<span class="tk-card-title">${t.title || typeName}</span></div>
              <div class="tk-card-meta">${typeName} · ${Utils.timeAgo(t.created_at)}</div>
            </div>
            ${isActive && t.status === 'running' ? `<span class="tk-pct">${progress}%</span>` : ''}
          </div>
          ${sub ? `<div class="tk-card-sub">${sub}</div>` : ''}
          ${preview && !isActive ? `<div class="tk-card-preview">${preview}</div>` : ''}
          ${isActive ? `<div class="tk-card-progress"><div class="tk-card-progress-fill" style="width:${progress}%"></div></div>` : ''}
          ${elapsed ? `<div class="tk-card-time">${elapsed}${eta ? ` · ${eta}` : ''}</div>` : ''}
          ${t.error ? `<div class="tk-card-err">${String(t.error).slice(0, 120)}</div>` : ''}
          <div class="tk-card-ft">${actions}</div>
        </article>`;
    },

    openDetail(taskId) {
      if (!taskId) return;
      this._detailId = taskId;
      const panel = document.getElementById('tkDetailPanel');
      if (panel) panel.hidden = false;
      const task = this._findTask(taskId);
      this._renderDetail(task);
      document.querySelectorAll('.tk-card').forEach((c) => {
        c.classList.toggle('is-selected', c.getAttribute('data-task-id') === taskId);
      });
    },

    closeDetail() {
      this._detailId = null;
      const panel = document.getElementById('tkDetailPanel');
      if (panel) panel.hidden = true;
      document.querySelectorAll('.tk-card.is-selected').forEach((c) => c.classList.remove('is-selected'));
    },

    async _renderDetail(task) {
      const body = document.getElementById('tk-detail-body');
      const actions = document.getElementById('tk-detail-actions');
      if (!body || !actions) return;
      if (!task) {
        body.innerHTML = '<p style="color:var(--t3)">任務不存在或已刪除</p>';
        actions.innerHTML = '';
        return;
      }
      const TC = TaskCommon;
      const typeName = TC.typeName(task.task_type);
      const elapsed = task.started_at
        ? TC.formatElapsed(TC.elapsed(task.started_at, task.completed_at))
        : '-';

      body.innerHTML = `
        <div class="tk-detail-kv">
          <div class="tk-dk"><span>狀態</span><span>${TC.STATUS_ICONS[task.status] || ''} ${task.status}</span></div>
          <div class="tk-dk"><span>類型</span><span>${typeName}</span></div>
          <div class="tk-dk"><span>進度</span><span>${task.progress || 0}%</span></div>
          <div class="tk-dk"><span>耗時</span><span>${elapsed}</span></div>
          <div class="tk-dk"><span>創建</span><span>${task.created_at || '—'}</span></div>
          <div class="tk-dk"><span>完成</span><span>${task.completed_at || '—'}</span></div>
        </div>
        <div class="tk-detail-id">
          <code>${task.task_id}</code>
          <button type="button" class="btn btn-s" data-copy-id="${task.task_id}">複製 ID</button>
        </div>
        ${task.error ? TC.renderError(task.error) : ''}
        <div class="tk-detail-block">
          <div class="tk-detail-block-hd">參數</div>
          <div id="tk-detail-params">載入中…</div>
        </div>
        <div class="tk-detail-block">
          <div class="tk-detail-block-hd">執行日誌</div>
          <pre id="tk-detail-logs" class="task-log-panel">載入中…</pre>
        </div>`;

      body.querySelector('[data-copy-id]')?.addEventListener('click', () => this.copyTaskId(task.task_id));

      let act = '';
      if (task.status === 'completed' && task.has_result) {
        act += `<button type="button" class="btn btn-ac" data-action="goto" data-id="${task.task_id}">前往結果頁</button>`;
        act += `<button type="button" class="btn btn-s" data-action="result" data-id="${task.task_id}">彈窗摘要</button>`;
      }
      if (['running', 'pending', 'retrying'].includes(task.status)) {
        act += `<button type="button" class="btn btn-rd" data-action="cancel" data-id="${task.task_id}">取消任務</button>`;
      }
      if (['failed', 'cancelled'].includes(task.status)) {
        act += `<button type="button" class="btn btn-s" data-action="retry" data-id="${task.task_id}">重試</button>`;
      }
      if (['completed', 'failed', 'cancelled'].includes(task.status)) {
        act += `<button type="button" class="btn btn-s" data-action="delete" data-id="${task.task_id}">刪除記錄</button>`;
      }
      actions.innerHTML = act;
      actions.querySelectorAll('[data-action]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const action = btn.getAttribute('data-action');
          const id = btn.getAttribute('data-id');
          if (action === 'cancel') this.cancelTask(id);
          else if (action === 'delete') this.deleteTask(id);
          else if (action === 'retry') this.retryTask(id);
          else if (action === 'result') this.viewResult(id);
          else if (action === 'goto') TaskCommon.navigateToResult(id);
        });
      });

      this._loadParams(task.task_id, 'tk-detail-params');
      this._loadLogs(task.task_id, 'tk-detail-logs');
    },

    _toggleSelect(taskId, checked) {
      if (!taskId) return;
      if (checked) this._selectedIds.add(taskId);
      else this._selectedIds.delete(taskId);
      this._updateBatchBar();
    },

    _updateBatchBar() {
      const bar = document.getElementById('taskBatchBar');
      if (!bar) return;
      const n = this._selectedIds.size;
      bar.style.display = n > 0 ? 'flex' : 'none';
      const countEl = document.getElementById('taskBatchCount');
      if (countEl) countEl.textContent = n;
    },

    async batchCancel() {
      const ids = [...this._selectedIds];
      if (!ids.length) return;
      if (!confirm(`確定取消 ${ids.length} 個任務？`)) return;
      const d = await Api.batchCancelTasks(ids);
      if (d?.success) {
        this.toast(`已取消 ${(d.cancelled || []).length} 個`, 'success');
        this._selectedIds.clear();
        this._updateBatchBar();
        this.refresh();
      }
    },

    async batchDelete() {
      const ids = [...this._selectedIds];
      if (!ids.length) return;
      if (!confirm(`確定刪除 ${ids.length} 個任務？`)) return;
      const d = await Api.batchDeleteTasks(ids);
      if (d?.success) {
        this.toast(`已刪除 ${(d.deleted || []).length} 個`, 'success');
        ids.forEach((id) => {
          this._paramsCache.delete(id);
          if (this._detailId === id) this.closeDetail();
        });
        this._selectedIds.clear();
        this._updateBatchBar();
        this.refresh();
      }
    },

    async cancelAllPending() {
      if (!confirm('確定取消所有排隊中的任務？')) return;
      const d = await Api.cancelAllPendingTasks();
      if (d?.success) {
        this.toast(`已取消 ${d.cancelled || 0} 個排隊任務`, 'success');
        this.refresh();
      }
    },

    async clearCompleted() {
      if (!confirm('確定清空已結束的任務記錄？')) return;
      const d = await Api.clearCompletedTasks(true, true);
      if (d?.success) {
        this.toast(`已清除 ${d.deleted || 0} 條`, 'success');
        this._selectedIds.clear();
        this.closeDetail();
        this.refresh();
      }
    },

    async retryTask(taskId) {
      const d = await Api.retryTask(taskId);
      if (d?.success) {
        this.toast(d.message || '已提交重試', 'success');
        this.refresh();
      } else this.toast('重試失敗', 'error');
    },

    async cancelTask(taskId) {
      const d = await Api.cancelTask(taskId);
      if (d?.success) {
        this.toast('任務已取消', 'success');
        this.refresh();
      } else this.toast('取消失敗', 'error');
    },

    async deleteTask(taskId) {
      const d = await Api.deleteTask(taskId);
      if (d?.success) {
        this._paramsCache.delete(taskId);
        if (this._detailId === taskId) this.closeDetail();
        this.toast('已刪除', 'success');
        this.refresh();
      } else this.toast(d?.detail || '刪除失敗', 'error');
    },

    async cleanup() {
      const d = await Api.cleanupTasks();
      if (d?.success) {
        this.toast(`已清理 ${d.cleaned || 0} 個超時任務`, 'success');
        this.refresh();
      }
    },

    exportTaskList() {
      const tasks = this._getFilteredTasks(this._lastData?.tasks || []);
      const payload = {
        exported_at: new Date().toISOString(),
        count: tasks.length,
        tasks: tasks.map((t) => ({
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
      Api.downloadBlob(JSON.stringify(payload, null, 2), `tasks_${Date.now()}.json`, 'application/json');
      this.toast(`已匯出 ${tasks.length} 條`, 'success');
    },

    async copyTaskId(taskId) {
      try {
        await navigator.clipboard.writeText(String(taskId || ''));
        this.toast('已複製任務 ID', 'success');
      } catch (_) {
        this.toast('複製失敗', 'error');
      }
    },

    _appendLiveLog(taskId, entry) {
      const el = document.getElementById('tk-detail-logs');
      if (!el || !entry || this._detailId !== taskId) return;
      const line = `[${entry.ts || ''}] ${entry.message || ''}\n`;
      if (el.textContent === '載入中…') el.textContent = '';
      el.textContent += line;
      el.scrollTop = el.scrollHeight;
    },

    async _loadLogs(taskId, elId = 'tk-detail-logs') {
      const el = document.getElementById(elId);
      if (!el) return;
      const d = await Api.getTaskLogs(taskId, 200);
      const logs = d?.logs || [];
      el.textContent = logs.length
        ? logs.map((l) => `[${l.ts}] ${l.message}`).join('\n')
        : '（暫無日誌）';
      el.scrollTop = el.scrollHeight;
    },

    async _loadParams(taskId, elId = 'tk-detail-params') {
      const container = document.getElementById(elId);
      if (!container) return;
      if (this._paramsCache.has(taskId)) {
        container.innerHTML = this._paramsCache.get(taskId);
        return;
      }
      const d = await Api.getTaskParams(taskId);
      if (!d?.task) {
        container.innerHTML = '<span style="color:var(--t3)">無法載入參數</span>';
        return;
      }
      const html = TaskCommon.renderParams(d.task.params, d.task.task_type);
      this._paramsCache.set(taskId, html);
      container.innerHTML = html;
    },

    _updateNavBadge(stats) {
      const active = (stats?.running || 0) + (stats?.pending || 0) + (stats?.retrying || 0);
      window.StockQPro?.pages?.tasks?.updateBadges?.(stats, active);
    },

    async viewResult(taskId) {
      const d = await Api.getTask(taskId);
      const task = d?.task;
      if (!task?.result) {
        this.toast('此任務暫無結果', 'warning');
        return;
      }
      if (typeof Utils !== 'undefined') Utils.showModal(TaskCommon.renderResultModal(task));
      if (task.result?.equity_curve) {
        setTimeout(() => TaskCommon.renderResultChart('taskResultChart', task.result.equity_curve), 80);
      }
    },
  };

  // ── 頁面生命週期（徽章、工具列、WS）────────────────────────
  function patchToast() {
    if (typeof Utils === 'undefined' || Utils._proToastPatched) return;
    const orig = Utils.toast.bind(Utils);
    Utils.toast = (msg, dur, type) => {
      const app = proApp();
      if (app?.toast) {
        const map = { success: 'ok', warning: 'warn', error: 'er', info: 'info' };
        app.toast(String(msg || ''), map[type] || 'info');
        return;
      }
      orig(msg, dur, type);
    };
    Utils._proToastPatched = true;
  }

  function setSidebarBadge(n) {
    const badge = document.getElementById('task-sb-badge');
    if (!badge) return;
    badge.textContent = n > 99 ? '99+' : String(n);
    badge.style.display = n > 0 ? '' : 'none';
  }

  function setTopbarBadge(n) {
    const dot = document.getElementById('notif-task-dot');
    if (!dot) return;
    dot.style.display = n > 0 ? '' : 'none';
    dot.title = n > 0 ? `${n} 個進行中任務` : '';
  }

  async function refreshSidebarBadge() {
    try {
      const d = await Api.getTasks(null, null, 80, { silent: true, noCache: true });
      const n = (d?.tasks || []).filter((t) => ['pending', 'running', 'retrying'].includes(t.status)).length;
      setSidebarBadge(n);
      setTopbarBadge(n);
    } catch (_) {
      setSidebarBadge(0);
      setTopbarBadge(0);
    }
  }

  function updateLiveDot() {
    const dot = document.getElementById('tk-live-dot');
    if (!dot) return;
    const on = !!(proApp()?._ws && proApp()._ws.readyState === WebSocket.OPEN);
    dot.classList.toggle('on', on);
    dot.classList.toggle('off', !on);
    dot.title = on ? 'WebSocket 已連接' : '輪詢模式';
  }

  function bindToolbar() {
    const map = [
      ['tk-refresh', () => Tasks.refresh()],
      ['tk-export', () => Tasks.exportTaskList()],
      ['tk-cancel-pending', () => Tasks.cancelAllPending()],
      ['tk-clear-done', () => Tasks.clearCompleted()],
      ['tk-cleanup', () => Tasks.cleanup()],
    ];
    map.forEach(([id, fn]) => {
      const el = document.getElementById(id);
      if (!el || el._tkBound) return;
      el._tkBound = true;
      el.addEventListener('click', () => { try { fn(); } catch (_) {} });
    });

    const auto = document.getElementById('tk-auto-refresh');
    if (auto && !auto._tkBound) {
      auto._tkBound = true;
      const saved = sessionStorage.getItem(STORAGE_AUTO);
      if (saved === '0') auto.checked = false;
      auto.addEventListener('change', () => {
        sessionStorage.setItem(STORAGE_AUTO, auto.checked ? '1' : '0');
        if (auto.checked) Tasks._startPolling();
        else Tasks._stopPolling();
        proApp()?.toast?.(auto.checked ? '已開啟自動刷新' : '已暫停自動刷新', 'inf');
      });
    }
  }

  function bindQuickFilters() {
    const wrap = document.getElementById('tk-quick-filters');
    if (!wrap || wrap._tkBound) return;
    wrap._tkBound = true;
    wrap.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-tk-status], [data-tk-filter]');
      if (!btn) return;
      wrap.querySelectorAll('.tk-pill').forEach((p) => p.classList.remove('on'));
      btn.classList.add('on');
      const status = btn.getAttribute('data-tk-status');
      const filter = btn.getAttribute('data-tk-filter');
      const statusSel = document.getElementById('taskStatusFilter');
      if (status !== null && statusSel) {
        statusSel.value = status;
        Tasks._todayOnly = false;
        Tasks._hasResultOnly = false;
      } else if (filter === 'today') {
        if (statusSel) statusSel.value = '';
        Tasks._todayOnly = true;
        Tasks._hasResultOnly = false;
      } else if (filter === 'has_result') {
        if (statusSel) statusSel.value = '';
        Tasks._todayOnly = false;
        Tasks._hasResultOnly = true;
      }
      Tasks.refresh();
    });
  }

  function bindStatCards() {
    const grid = document.getElementById('taskStatsGrid');
    if (!grid || grid._tkStatBound) return;
    grid._tkStatBound = true;
    const activate = (filter) => {
      const statusSel = document.getElementById('taskStatusFilter');
      const wrap = document.getElementById('tk-quick-filters');
      Tasks._todayOnly = false;
      Tasks._hasResultOnly = false;
      if (statusSel) statusSel.value = filter || '';
      wrap?.querySelectorAll('.tk-pill').forEach((p) => {
        const st = p.getAttribute('data-tk-status');
        const extra = p.getAttribute('data-tk-filter');
        p.classList.toggle('on', !extra && st === (filter || ''));
      });
      Tasks.refresh();
    };
    grid.addEventListener('click', (e) => {
      const card = e.target.closest('.task-stat-card');
      if (!card) return;
      activate(card.getAttribute('data-stat-filter') || '');
    });
  }

  function bindNotifButton() {
    const btn = document.getElementById('notif-btn');
    if (!btn || btn._tkBound) return;
    btn._tkBound = true;
    btn.addEventListener('click', () => proApp()?.nav?.('tasks', { syncHash: true }));
  }

  const page = {
    _badgeTimer: null,
    _liveTimer: null,

    init() {
      patchToast();
      Tasks.init();
      bindToolbar();
      bindQuickFilters();
      bindStatCards();
      bindNotifButton();
    },

    onShow() {
      patchToast();
      bindToolbar();
      bindQuickFilters();
      bindStatCards();
      updateLiveDot();
      Tasks.load().catch(() => proApp()?.toast?.('任務中心載入失敗', 'er'));
      this._startBadgePoll();
      this._startLivePoll();
    },

    unload() {
      this._stopBadgePoll();
      this._stopLivePoll();
      Tasks.unload();
    },

    rebindWs() {
      updateLiveDot();
      Tasks.rebindWs();
    },

    onWsMessage(e) {
      refreshSidebarBadge();
      updateLiveDot();
      try {
        const data = JSON.parse(e.data);
        if (!data?.type?.startsWith('task_')) return;
        if (proApp()?.current === 'tasks') {
          if (data.type === 'task_created' || data.type === 'task_started') {
            Tasks.refresh(true);
          }
        }
        if (proApp()?.current !== 'tasks') return;
        if (data.type === 'task_completed') {
          proApp()?.toast?.(`任務完成：${data.task?.title || data.title || ''}`, 'ok');
        } else if (data.type === 'task_failed') {
          proApp()?.toast?.('有任務執行失敗', 'er');
        }
      } catch (_) {}
    },

    isAutoRefresh() {
      const el = document.getElementById('tk-auto-refresh');
      if (el) return !!el.checked;
      return sessionStorage.getItem(STORAGE_AUTO) !== '0';
    },

    markSynced() {
      const el = document.getElementById('tk-last-sync');
      if (!el) return;
      const now = new Date();
      el.textContent = `更新 ${now.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
      updateLiveDot();
    },

    updateBadges(stats, active) {
      const n = active ?? ((stats?.running || 0) + (stats?.pending || 0) + (stats?.retrying || 0));
      setSidebarBadge(n);
      setTopbarBadge(n);
    },

    _startBadgePoll() {
      this._stopBadgePoll();
      this._badgeTimer = setInterval(() => refreshSidebarBadge(), 18000);
    },

    _stopBadgePoll() {
      if (this._badgeTimer) {
        clearInterval(this._badgeTimer);
        this._badgeTimer = null;
      }
    },

    _startLivePoll() {
      this._stopLivePoll();
      this._liveTimer = setInterval(updateLiveDot, 5000);
    },

    _stopLivePoll() {
      if (this._liveTimer) {
        clearInterval(this._liveTimer);
        this._liveTimer = null;
      }
    },

    refreshSidebarBadge,
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.Tasks = Tasks;
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.tasks = page;
  window.Tasks = Tasks;

  document.addEventListener('DOMContentLoaded', () => {
    patchToast();
    bindNotifButton();
    refreshSidebarBadge();
  });
})();
