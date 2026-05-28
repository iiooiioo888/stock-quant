import { getGlobals, getProApp, toast } from '../core/api-bridge.mjs';

export const pageId = 'tasks';

const STORAGE_AUTO = 'sq_pro_tasks_auto_refresh';

const state = {
  bound: false,
  pollTimer: null,
  pollInterval: 6000,
  maxPolls: 500,
  pollCount: 0,
  lastData: null,
  loadError: '',
  searchDebounce: null,
  sortCol: 'created_at',
  sortAsc: false,
  detailId: null,
  paramsCache: new Map(),
  selectedIds: new Set(),
  wsHandler: null,
  sse: null,
  sseRetry: 0,
  todayOnly: false,
  hasResultOnly: false,
};

function $id(id) {
  return document.getElementById(id);
}

function isAutoRefreshEnabled() {
  const el = $id('tk-auto-refresh');
  return el ? el.checked : sessionStorage.getItem(STORAGE_AUTO) !== '0';
}

function setSidebarBadge(n) {
  const badge = $id('task-sb-badge');
  if (!badge) return;
  badge.textContent = n > 99 ? '99+' : String(n);
  badge.style.display = n > 0 ? '' : 'none';
}

function setTopbarBadge(n) {
  const dot = $id('notif-task-dot');
  if (!dot) return;
  dot.style.display = n > 0 ? '' : 'none';
  dot.title = n > 0 ? `${n} 個進行中任務` : '';
}

async function refreshSidebarBadge() {
  const { Api } = getGlobals();
  if (!Api?.getTasks) return;
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
  const dot = $id('tk-live-dot');
  if (!dot) return;
  const app = getProApp();
  const on = !!(app?._ws && app._ws.readyState === WebSocket.OPEN);
  dot.classList.toggle('on', on);
  dot.classList.toggle('off', !on);
  dot.title = on ? 'WebSocket 已連接' : '輪詢模式';
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  if (!isAutoRefreshEnabled()) return;
  state.pollTimer = setInterval(() => {
    if (!isAutoRefreshEnabled()) {
      stopPolling();
      return;
    }
    if (++state.pollCount > state.maxPolls) {
      stopPolling();
      return;
    }
    refresh(true);
  }, state.pollInterval);
}

function unbindWsEvents() {
  const app = getProApp();
  const ws = app?._ws;
  if (state.wsHandler && ws) {
    try { ws.removeEventListener('message', state.wsHandler); } catch (_) {}
  }
  state.wsHandler = null;
}

function bindWsEvents() {
  unbindWsEvents();
  const app = getProApp();
  const ws = app?._ws;
  if (!ws) return;

  state.wsHandler = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (!data?.type) return;
      if (data.type === 'task_log' && data.task_id) {
        appendLiveLog(data.task_id, data.log);
        return;
      }
      if (!String(data.type).startsWith('task_')) return;
      if (data.type === 'task_progress' && patchTaskFromWs(data)) return;
      state.pollCount = 0;
      refresh(true);
    } catch (_) {}
  };
  ws.addEventListener('message', state.wsHandler);
}

function unbindSseEvents() {
  const es = state.sse;
  if (!es) return;
  try { es.close(); } catch (_) {}
  state.sse = null;
}

function bindSseEvents() {
  if (state.sse) return;
  if (typeof EventSource === 'undefined') return;
  const app = getProApp();
  if (app?.current && app.current !== 'tasks') return;

  const es = new EventSource('/api/task-events');
  state.sse = es;
  state.sseRetry = 0;

  const onAny = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (!data?.type) return;
      if (data.type === 'task_log' && data.task_id) {
        appendLiveLog(data.task_id, data.log);
        return;
      }
      if (!String(data.type).startsWith('task_')) return;
      if (data.type === 'task_progress' && patchTaskFromWs(data)) return;
      state.pollCount = 0;
      refresh(true);
    } catch (_) {}
  };

  [
    'task_created', 'task_started', 'task_retrying',
    'task_progress', 'task_update',
    'task_completed', 'task_failed', 'task_cancelled',
    'task_log',
  ].forEach((t) => es.addEventListener(t, onAny));
  es.onmessage = onAny;
  es.onerror = () => {
    state.sseRetry += 1;
    if (state.sseRetry >= 5) {
      try { es.close(); } catch (_) {}
      state.sse = null;
    }
  };
}

function getFilters() {
  return {
    search: ($id('taskSearch')?.value || '').trim().toLowerCase(),
    taskType: $id('taskTypeFilter')?.value || '',
    status: $id('taskStatusFilter')?.value || '',
  };
}

function getFilteredTasks(tasks) {
  const { TaskCommon } = getGlobals();
  const { search, taskType, status } = getFilters();
  let list = tasks || [];
  if (taskType) list = list.filter((t) => t.task_type === taskType);
  if (status) list = list.filter((t) => t.status === status);
  if (state.todayOnly) {
    const today = new Date().toISOString().slice(0, 10);
    list = list.filter((t) => (t.created_at || '').slice(0, 10) === today);
  }
  if (state.hasResultOnly) {
    list = list.filter((t) => t.has_result || (t.status === 'completed' && t.result));
  }
  if (!search) return list;
  return list.filter((t) => {
    const hay = [t.title, t.task_type, TaskCommon?.typeName?.(t.task_type)].join(' ').toLowerCase();
    return hay.includes(search);
  });
}

function skeletonHtml(count = 5) {
  return Array.from({ length: count }, () => `
    <div class="tk-card tk-card--skeleton" aria-hidden="true">
      <div class="tk-skel-line tk-skel-title skeleton"></div>
      <div class="tk-skel-line tk-skel-meta skeleton"></div>
      <div class="tk-skel-bar skeleton"></div>
    </div>`).join('');
}

function setLoading(loading) {
  const el = $id('taskLoadingIndicator');
  if (el) el.style.display = 'none';
  const list = $id('tkTaskList');
  if (loading && !state.lastData && list) list.innerHTML = skeletonHtml(5);
}

function showLoadError() {
  const banner = $id('taskLoadErrorBanner');
  if (banner) {
    banner.style.display = 'block';
    banner.textContent = state.loadError;
    return;
  }
  const list = $id('tkTaskList');
  if (list) {
    list.innerHTML = `<div class="tk-empty"><span class="tk-empty-icon">⚠️</span><p>${state.loadError}</p><button type="button" class="btn s" id="tk-retry-load">重試</button></div>`;
    $id('tk-retry-load')?.addEventListener('click', () => refresh());
  }
}

function hideLoadError() {
  const banner = $id('taskLoadErrorBanner');
  if (banner) {
    banner.style.display = 'none';
    banner.textContent = '';
  }
}

function renderCapacity(stats) {
  const el = $id('tkCapacityBar');
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
}

function renderStats(stats) {
  const { TaskCommon } = getGlobals();
  if (!stats) return;
  const grid = $id('taskStatsGrid');
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
}

function updateBatchBar() {
  const bar = $id('taskBatchBar');
  if (!bar) return;
  const n = state.selectedIds.size;
  bar.style.display = n > 0 ? 'flex' : 'none';
  const countEl = $id('taskBatchCount');
  if (countEl) countEl.textContent = n;
}

function toggleSelect(taskId, checked) {
  if (!taskId) return;
  if (checked) state.selectedIds.add(taskId);
  else state.selectedIds.delete(taskId);
  updateBatchBar();
}

function renderQueue(snapshot) {
  const { TaskCommon } = getGlobals();
  const grid = $id('taskQueueGrid');
  if (!grid || !TaskCommon?.renderQueueSection) return;
  grid.innerHTML = TaskCommon.renderQueueSection(snapshot || {}, false);
  grid.querySelectorAll('[data-tk-queue-action]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = btn.getAttribute('data-tk-queue-action');
      const id = btn.getAttribute('data-task-id');
      if (action === 'cancel') cancelTask(id);
      else if (action === 'retry') retryTask(id);
      else if (action === 'result') viewResult(id);
    });
  });
  grid.querySelectorAll('[data-tk-goto]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.getAttribute('data-tk-goto');
      if (id) TaskCommon.navigateToResult(id);
    });
  });
}

function renderCard(t) {
  const { TaskCommon, Utils } = getGlobals();
  const TC = TaskCommon;
  const typeName = TC?.typeName?.(t.task_type) || t.task_type || '';
  const schedBadge = t.is_scheduled ? '<span class="badge b-am tk-scheduled-badge" title="定時任務">定時</span>' : '';
  const icon = TC?.STATUS_ICONS?.[t.status] || '❓';
  const color = TC?.STATUS_COLORS?.[t.status] || '#94a3b8';
  const isActive = ['running', 'pending', 'retrying'].includes(t.status);
  const sub = TC?.formatTaskSubtitle?.(t) || '';
  const preview = TC?.formatResultPreview?.(t) || '';
  const selected = state.selectedIds.has(t.task_id);
  const isDetail = state.detailId === t.task_id;
  const progress = Number(t.progress) || 0;
  const elapsed = t.elapsed_sec > 0 && TC?.formatElapsed ? TC.formatElapsed(Math.round(t.elapsed_sec)) : '';
  const eta = t.eta_sec > 0 && t.status === 'running' && TC?.formatEta ? TC.formatEta(t.eta_sec) : '';

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
          <div class="tk-card-meta">${typeName} · ${Utils?.timeAgo ? Utils.timeAgo(t.created_at) : (t.created_at || '')}</div>
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
}

function renderTaskList(tasks) {
  const list = $id('tkTaskList');
  if (!list) return;
  const filtered = getFilteredTasks(tasks);
  filtered.sort((a, b) => {
    let va = a[state.sortCol] ?? '';
    let vb = b[state.sortCol] ?? '';
    if (state.sortCol === 'progress') {
      va = Number(va);
      vb = Number(vb);
    } else {
      va = String(va).toLowerCase();
      vb = String(vb).toLowerCase();
    }
    if (va < vb) return state.sortAsc ? -1 : 1;
    if (va > vb) return state.sortAsc ? 1 : -1;
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
    html += active.map((t) => renderCard(t)).join('');
  }
  if (done.length) {
    html += `<div class="tk-list-section-hd">歷史 · ${done.length}</div>`;
    html += done.map((t) => renderCard(t)).join('');
  }
  list.innerHTML = html;

  list.querySelectorAll('.tk-card-chk').forEach((cb) => {
    cb.addEventListener('click', (e) => e.stopPropagation());
    cb.addEventListener('change', () => toggleSelect(cb.getAttribute('data-id'), cb.checked));
  });
  list.querySelectorAll('[data-action]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = btn.getAttribute('data-action');
      const id = btn.getAttribute('data-id');
      const { TaskCommon } = getGlobals();
      if (action === 'cancel') cancelTask(id);
      else if (action === 'delete') deleteTask(id);
      else if (action === 'retry') retryTask(id);
      else if (action === 'result') viewResult(id);
      else if (action === 'goto') TaskCommon?.navigateToResult?.(id);
      else if (action === 'detail') openDetail(id);
    });
  });

  if (state.detailId) {
    list.querySelectorAll('.tk-card').forEach((c) => {
      c.classList.toggle('is-selected', c.getAttribute('data-task-id') === state.detailId);
    });
  }
}

function renderFromPayload(d) {
  const tasks = d?.tasks || [];
  renderCapacity(d?.stats);
  renderStats(d?.stats);
  renderQueue(d?.queue || {});
  renderTaskList(tasks);
  updateNavBadge(d?.stats);
  hideLoadError();
}

function findTask(id) {
  return (state.lastData?.tasks || []).find((t) => t.task_id === id) || null;
}

function updateNavBadge(stats) {
  const active = (stats?.running || 0) + (stats?.pending || 0) + (stats?.retrying || 0);
  setSidebarBadge(active);
  setTopbarBadge(active);
}

async function refresh(silent) {
  const { Api } = getGlobals();
  if (!Api?.getTasks) return;

  const { taskType, status } = getFilters();
  if (!silent) setLoading(true);

  const d = await Api.getTasks(taskType || null, status || null, 200, {
    silent: !!silent,
    noCache: !!silent,
  });
  if (!silent) setLoading(false);

  if (!d || d._rateLimited) {
    if (d?._rateLimited && state.lastData) renderFromPayload(state.lastData);
    else if (!silent) {
      state.loadError = d?._rateLimited ? '請求過於頻繁，稍後自動重試' : '任務列表載入失敗';
      showLoadError();
    }
    return;
  }

  state.loadError = '';
  state.lastData = d;
  renderFromPayload(d);
  markSynced();
  if (state.detailId) renderDetail(findTask(state.detailId));
}

function markSynced() {
  const el = $id('tk-last-sync');
  if (!el) return;
  const now = new Date();
  el.textContent = `更新 ${now.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
  updateLiveDot();
}

function openDetail(taskId) {
  if (!taskId) return;
  state.detailId = taskId;
  const panel = $id('tkDetailPanel');
  if (panel) panel.hidden = false;
  renderDetail(findTask(taskId));
  document.querySelectorAll('.tk-card').forEach((c) => {
    c.classList.toggle('is-selected', c.getAttribute('data-task-id') === taskId);
  });
}

function closeDetail() {
  state.detailId = null;
  const panel = $id('tkDetailPanel');
  if (panel) panel.hidden = true;
  document.querySelectorAll('.tk-card.is-selected').forEach((c) => c.classList.remove('is-selected'));
}

function appendLiveLog(taskId, entry) {
  const el = $id('tk-detail-logs');
  if (!el || !entry || state.detailId !== taskId) return;
  const line = `[${entry.ts || ''}] ${entry.message || ''}\n`;
  if (el.textContent === '載入中…') el.textContent = '';
  el.textContent += line;
  el.scrollTop = el.scrollHeight;
}

async function loadLogs(taskId, elId = 'tk-detail-logs') {
  const { Api } = getGlobals();
  const el = $id(elId);
  if (!el || !Api?.getTaskLogs) return;
  const d = await Api.getTaskLogs(taskId, 200);
  const logs = d?.logs || [];
  el.textContent = logs.length ? logs.map((l) => `[${l.ts}] ${l.message}`).join('\n') : '（暫無日誌）';
  el.scrollTop = el.scrollHeight;
}

async function loadParams(taskId, elId = 'tk-detail-params') {
  const { Api, TaskCommon } = getGlobals();
  const container = $id(elId);
  if (!container || !Api?.getTaskParams) return;
  if (state.paramsCache.has(taskId)) {
    container.innerHTML = state.paramsCache.get(taskId);
    return;
  }
  const d = await Api.getTaskParams(taskId);
  if (!d?.task) {
    container.innerHTML = '<span style="color:var(--t3)">無法載入參數</span>';
    return;
  }
  const html = TaskCommon?.renderParams ? TaskCommon.renderParams(d.task.params, d.task.task_type) : '<span style="color:var(--t3)">（無參數渲染器）</span>';
  state.paramsCache.set(taskId, html);
  container.innerHTML = html;
}

async function renderDetail(task) {
  const { TaskCommon } = getGlobals();
  const body = $id('tk-detail-body');
  const actions = $id('tk-detail-actions');
  if (!body || !actions) return;
  if (!task) {
    body.innerHTML = '<p style="color:var(--t3)">任務不存在或已刪除</p>';
    actions.innerHTML = '';
    return;
  }
  const TC = TaskCommon;
  const typeName = TC?.typeName?.(task.task_type) || task.task_type || '';
  const elapsed = task.started_at && TC?.elapsed && TC?.formatElapsed
    ? TC.formatElapsed(TC.elapsed(task.started_at, task.completed_at))
    : '-';

  body.innerHTML = `
    <div class="tk-detail-kv">
      <div class="tk-dk"><span>狀態</span><span>${TC?.STATUS_ICONS?.[task.status] || ''} ${task.status}</span></div>
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
    ${task.error && TC?.renderError ? TC.renderError(task.error) : ''}
    <div class="tk-detail-block">
      <div class="tk-detail-block-hd">參數</div>
      <div id="tk-detail-params">載入中…</div>
    </div>
    <div class="tk-detail-block">
      <div class="tk-detail-block-hd">執行日誌</div>
      <pre id="tk-detail-logs" class="task-log-panel">載入中…</pre>
    </div>`;

  body.querySelector('[data-copy-id]')?.addEventListener('click', () => copyTaskId(task.task_id));

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
      const { TaskCommon } = getGlobals();
      if (action === 'cancel') cancelTask(id);
      else if (action === 'delete') deleteTask(id);
      else if (action === 'retry') retryTask(id);
      else if (action === 'result') viewResult(id);
      else if (action === 'goto') TaskCommon?.navigateToResult?.(id);
    });
  });

  loadParams(task.task_id, 'tk-detail-params');
  loadLogs(task.task_id, 'tk-detail-logs');
}

async function copyTaskId(taskId) {
  try {
    await navigator.clipboard.writeText(String(taskId || ''));
    toast('已複製任務 ID', 'success');
  } catch (_) {
    toast('複製失敗', 'error');
  }
}

function patchTaskFromWs(data) {
  if (!data?.task_id || !state.lastData?.tasks) return false;
  const idx = state.lastData.tasks.findIndex((t) => t.task_id === data.task_id);
  if (idx < 0) return false;
  const cur = state.lastData.tasks[idx];
  const next = {
    ...cur,
    status: data.status ?? cur.status,
    progress: data.progress ?? cur.progress,
    error: data.error ?? cur.error,
  };
  state.lastData.tasks[idx] = next;
  const card = document.querySelector(`[data-task-id="${data.task_id}"]`);
  if (card) {
    const fill = card.querySelector('.tk-card-progress-fill');
    const pct = card.querySelector('.tk-pct');
    if (fill) fill.style.width = `${next.progress || 0}%`;
    if (pct) pct.textContent = `${next.progress || 0}%`;
  }
  if (state.detailId === data.task_id) renderDetail(next);
  return true;
}

async function viewResult(taskId) {
  const { Api, Utils, TaskCommon } = getGlobals();
  if (!Api?.getTask) return;
  const d = await Api.getTask(taskId);
  const task = d?.task;
  if (!task?.result) {
    toast('此任務暫無結果', 'warning');
    return;
  }
  if (Utils?.showModal && TaskCommon?.renderResultModal) Utils.showModal(TaskCommon.renderResultModal(task));
  if (task.result?.equity_curve && TaskCommon?.renderResultChart) {
    setTimeout(() => TaskCommon.renderResultChart('taskResultChart', task.result.equity_curve), 80);
  }
}

async function retryTask(taskId) {
  const { Api } = getGlobals();
  if (!Api?.retryTask) return;
  const d = await Api.retryTask(taskId);
  if (d?.success) {
    toast(d.message || '已提交重試', 'success');
    refresh();
  } else toast('重試失敗', 'error');
}

async function cancelTask(taskId) {
  const { Api } = getGlobals();
  if (!Api?.cancelTask) return;
  const d = await Api.cancelTask(taskId);
  if (d?.success) {
    toast('任務已取消', 'success');
    refresh();
  } else toast('取消失敗', 'error');
}

async function deleteTask(taskId) {
  const { Api } = getGlobals();
  if (!Api?.deleteTask) return;
  const d = await Api.deleteTask(taskId);
  if (d?.success) {
    state.paramsCache.delete(taskId);
    if (state.detailId === taskId) closeDetail();
    toast('已刪除', 'success');
    refresh();
  } else toast(d?.detail || '刪除失敗', 'error');
}

async function batchCancel() {
  const { Api } = getGlobals();
  const ids = [...state.selectedIds];
  if (!ids.length || !Api?.batchCancelTasks) return;
  if (!confirm(`確定取消 ${ids.length} 個任務？`)) return;
  const d = await Api.batchCancelTasks(ids);
  if (d?.success) {
    toast(`已取消 ${(d.cancelled || []).length} 個`, 'success');
    state.selectedIds.clear();
    updateBatchBar();
    refresh();
  }
}

async function batchDelete() {
  const { Api } = getGlobals();
  const ids = [...state.selectedIds];
  if (!ids.length || !Api?.batchDeleteTasks) return;
  if (!confirm(`確定刪除 ${ids.length} 個任務？`)) return;
  const d = await Api.batchDeleteTasks(ids);
  if (d?.success) {
    toast(`已刪除 ${(d.deleted || []).length} 個`, 'success');
    ids.forEach((id) => {
      state.paramsCache.delete(id);
      if (state.detailId === id) closeDetail();
    });
    state.selectedIds.clear();
    updateBatchBar();
    refresh();
  }
}

async function cancelAllPending() {
  const { Api } = getGlobals();
  if (!Api?.cancelAllPendingTasks) return;
  if (!confirm('確定取消所有排隊中的任務？')) return;
  const d = await Api.cancelAllPendingTasks();
  if (d?.success) {
    toast(`已取消 ${d.cancelled || 0} 個排隊任務`, 'success');
    refresh();
  }
}

async function clearCompleted() {
  const { Api } = getGlobals();
  if (!Api?.clearCompletedTasks) return;
  if (!confirm('確定清空已結束的任務記錄？')) return;
  const d = await Api.clearCompletedTasks(true, true);
  if (d?.success) {
    toast(`已清除 ${d.deleted || 0} 條`, 'success');
    state.selectedIds.clear();
    closeDetail();
    refresh();
  }
}

async function cleanup() {
  const { Api } = getGlobals();
  if (!Api?.cleanupTasks) return;
  const d = await Api.cleanupTasks();
  if (d?.success) {
    toast(`已清理 ${d.cleaned || 0} 個超時任務`, 'success');
    refresh();
  }
}

function exportTaskList() {
  const { Api } = getGlobals();
  if (!Api?.downloadBlob) return;
  const tasks = getFilteredTasks(state.lastData?.tasks || []);
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
  toast(`已匯出 ${tasks.length} 條`, 'success');
}

function bindToolbar() {
  const map = [
    ['tk-refresh', () => refresh()],
    ['tk-export', () => exportTaskList()],
    ['tk-cancel-pending', () => cancelAllPending()],
    ['tk-clear-done', () => clearCompleted()],
    ['tk-cleanup', () => cleanup()],
  ];
  map.forEach(([id, fn]) => {
    const el = $id(id);
    if (!el || el._tkBound) return;
    el._tkBound = true;
    el.addEventListener('click', () => { try { fn(); } catch (_) {} });
  });

  const auto = $id('tk-auto-refresh');
  if (auto && !auto._tkBound) {
    auto._tkBound = true;
    const saved = sessionStorage.getItem(STORAGE_AUTO);
    if (saved === '0') auto.checked = false;
    auto.addEventListener('change', () => {
      sessionStorage.setItem(STORAGE_AUTO, auto.checked ? '1' : '0');
      if (auto.checked) startPolling();
      else stopPolling();
      getProApp()?.toast?.(auto.checked ? '已開啟自動刷新' : '已暫停自動刷新', 'inf');
    });
  }
}

function bindQuickFilters() {
  const wrap = $id('tk-quick-filters');
  if (!wrap || wrap._tkBound) return;
  wrap._tkBound = true;
  wrap.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-tk-status], [data-tk-filter]');
    if (!btn) return;
    wrap.querySelectorAll('.tk-pill').forEach((p) => p.classList.remove('on'));
    btn.classList.add('on');
    const status = btn.getAttribute('data-tk-status');
    const filter = btn.getAttribute('data-tk-filter');
    const statusSel = $id('taskStatusFilter');
    if (status !== null && statusSel) {
      statusSel.value = status;
      state.todayOnly = false;
      state.hasResultOnly = false;
    } else if (filter === 'today') {
      if (statusSel) statusSel.value = '';
      state.todayOnly = true;
      state.hasResultOnly = false;
    } else if (filter === 'has_result') {
      if (statusSel) statusSel.value = '';
      state.todayOnly = false;
      state.hasResultOnly = true;
    }
    refresh();
  });
}

function bindStatCards() {
  const grid = $id('taskStatsGrid');
  if (!grid || grid._tkStatBound) return;
  grid._tkStatBound = true;
  const activate = (filter) => {
    const statusSel = $id('taskStatusFilter');
    const wrap = $id('tk-quick-filters');
    state.todayOnly = false;
    state.hasResultOnly = false;
    if (statusSel) statusSel.value = filter || '';
    wrap?.querySelectorAll('.tk-pill').forEach((p) => {
      const st = p.getAttribute('data-tk-status');
      const extra = p.getAttribute('data-tk-filter');
      p.classList.toggle('on', !extra && st === (filter || ''));
    });
    refresh();
  };
  grid.addEventListener('click', (e) => {
    const card = e.target.closest('.task-stat-card');
    if (!card) return;
    activate(card.getAttribute('data-stat-filter') || '');
  });
}

function bindNotifButton() {
  const btn = $id('notif-btn');
  if (!btn || btn._tkBound) return;
  btn._tkBound = true;
  btn.addEventListener('click', () => getProApp()?.nav?.('tasks', { syncHash: true }));
}

function initOnce() {
  if (state.bound) return;
  state.bound = true;

  $id('taskSearch')?.addEventListener('input', () => {
    clearTimeout(state.searchDebounce);
    state.searchDebounce = setTimeout(() => refresh(), 280);
  });
  ['taskTypeFilter', 'taskStatusFilter'].forEach((id) => {
    $id(id)?.addEventListener('change', () => refresh());
  });
  $id('taskBatchCancelBtn')?.addEventListener('click', () => batchCancel());
  $id('taskBatchDeleteBtn')?.addEventListener('click', () => batchDelete());
  $id('tk-detail-close')?.addEventListener('click', () => closeDetail());

  const list = $id('tkTaskList');
  if (list) {
    list.addEventListener('click', (e) => {
      const card = e.target.closest('.tk-card');
      if (!card) return;
      if (e.target.closest('button, input, a, label')) return;
      openDetail(card.getAttribute('data-task-id'));
    });
  }
}

export function init() {
  initOnce();
  bindToolbar();
  bindQuickFilters();
  bindStatCards();
  bindNotifButton();
}

export async function onShow() {
  init();
  const { TaskCommon } = getGlobals();
  try {
    if (TaskCommon?.loadTypes) {
      await TaskCommon.loadTypes();
      // Populate filter (TaskCommon already mutates global state used by renderers)
      const sel = $id('taskTypeFilter');
      if (sel && TaskCommon?.TYPE_NAMES) {
        const current = sel.value;
        let html = '<option value="">全部類型</option>';
        const types = TaskCommon._asyncTypes?.length
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
      }
    }
  } catch (_) {}

  state.pollCount = 0;
  state.selectedIds.clear();
  updateBatchBar();
  bindWsEvents();
  bindSseEvents();
  await refresh();
  startPolling();
  updateLiveDot();
  refreshSidebarBadge();
}

export function unload() {
  stopPolling();
  unbindWsEvents();
  unbindSseEvents();
  closeDetail();
}

export function rebindWs() {
  if (!state.bound) return;
  updateLiveDot();
  bindWsEvents();
}

