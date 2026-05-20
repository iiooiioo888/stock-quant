/**
 * scheduler.js — 定時任務 Tab（APScheduler 管理）
 */

/** 避免與瀏覽器原生 window.Scheduler API 衝突 */
const SchedulerTab = {
  _pollTimer: null,
  _pollInterval: 15000,
  _catalog: [],

  async load() {
    await this.refresh();
    this._startPolling();
  },

  unload() {
    this._stopPolling();
  },

  _startPolling() {
    this._stopPolling();
    this._pollTimer = setInterval(() => this.refresh(true), this._pollInterval);
  },

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  },

  async refresh(silent = false) {
    const loading = document.getElementById('schedLoading');
    if (loading && !silent) loading.style.display = 'flex';

    try {
      const d = await Api.getSchedulerCatalog();
      if (!d) return;
      this._catalog = d.catalog || [];
      this._renderStats(d);
      this._renderTable(d);
      this._renderActiveJobs(d.jobs || []);
    } catch (e) {
      if (!silent) Utils.toast('載入定時任務失敗', 3000, 'error');
    } finally {
      if (loading) loading.style.display = 'none';
    }
  },

  _renderStats(d) {
    const grid = document.getElementById('schedStatsGrid');
    if (!grid) return;

    const catalog = d.catalog || [];
    const jobs = d.jobs || [];
    const enabled = catalog.filter(c => c.enabled).length;
    const nextRuns = jobs
      .filter(j => j.next_run)
      .map(j => ({ id: j.id, name: j.name, next_run: j.next_run }))
      .sort((a, b) => a.next_run.localeCompare(b.next_run));
    const next = nextRuns[0];

    grid.innerHTML = `
      <div class="c stat-card"><h3>📋 任務目錄</h3><div class="v bl">${catalog.length}</div><div class="stat-hint">可配置項</div></div>
      <div class="c stat-card"><h3>✅ 已啟用</h3><div class="v gn">${enabled}</div><div class="stat-hint">當前註冊中</div></div>
      <div class="c stat-card"><h3>⏰ 下次執行</h3><div class="v" style="font-size:14px">${next ? this._esc(next.name) : '-'}</div><div class="stat-hint">${next ? this._esc(next.next_run) : '暫無計劃'}</div></div>
      <div class="c stat-card"><h3>🔧 引擎</h3><div class="v">APScheduler</div><div class="stat-hint">Asia/Shanghai</div></div>`;
  },

  _renderActiveJobs(jobs) {
    const el = document.getElementById('schedActiveList');
    if (!el) return;

    if (!jobs.length) {
      el.innerHTML = '<p class="sched-empty-hint">尚無已註冊任務，點擊「註冊默認任務」或對下方任務點「啟用」</p>';
      return;
    }

    el.innerHTML = jobs.map(j => `
      <span class="sched-active-chip">
        <strong>${this._esc(j.name || j.id)}</strong>
        <span class="sched-chip-time">下次 ${this._esc(j.next_run || '-')}</span>
      </span>
    `).join('');
  },

  _renderTable(d) {
    const tbody = document.getElementById('schedTableBody');
    if (!tbody) return;

    const catalog = d.catalog || [];
    const jobMap = Object.fromEntries((d.jobs || []).map(j => [j.id, j]));

    if (!catalog.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-dim);padding:24px">無任務定義</td></tr>';
      return;
    }

    tbody.innerHTML = catalog.map(c => {
      const j = jobMap[c.id];
      const enabled = c.enabled;
      const statusHtml = enabled
        ? '<span class="chip on">已啟用</span>'
        : '<span class="chip">未啟用</span>';

      return `<tr class="${enabled ? 'sched-row-on' : ''}">
        <td>
          <div class="sched-job-name">${this._esc(c.name)}</div>
          <div class="sched-job-id">${this._esc(c.id)}</div>
        </td>
        <td style="font-size:12px;max-width:200px">${this._esc(c.schedule)}</td>
        <td style="font-size:12px;color:var(--text-dim)">${this._esc(c.description)}</td>
        <td>${statusHtml}</td>
        <td style="font-size:12px;white-space:nowrap">${j?.next_run ? this._esc(j.next_run) : '-'}</td>
        <td class="sched-actions">
          <button class="btn s sched-btn" type="button" data-action="run" data-id="${this._esc(c.id)}">▶ 執行</button>
          ${enabled
            ? `<button class="btn s sched-btn" type="button" data-action="disable" data-id="${this._esc(c.id)}">禁用</button>`
            : `<button class="btn s sched-btn" type="button" data-action="enable" data-id="${this._esc(c.id)}">啟用</button>`}
        </td>
      </tr>`;
    }).join('');

    tbody.querySelectorAll('button[data-action]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.id;
        const action = btn.dataset.action;
        if (action === 'run') this.runNow(id);
        else if (action === 'enable') this.enableJob(id);
        else if (action === 'disable') this.disableJob(id);
      });
    });
  },

  _esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },

  async setupAll() {
    const btn = document.getElementById('schedSetupBtn');
    if (btn) Utils.btnLoading(btn, true, '註冊中...');
    try {
      const d = await Api.setupScheduler();
      if (d) {
        Utils.toast(d.message || '定時任務已註冊', 3000, 'success');
        await this.refresh(true);
      }
    } finally {
      if (btn) Utils.btnLoading(btn, false, '⏰ 註冊默認任務');
    }
  },

  async disableAll() {
    if (!confirm('確定禁用全部定時任務？')) return;
    const d = await Api.disableScheduler();
    if (d) {
      Utils.toast(d.message || '已全部禁用', 3000, 'success');
      await this.refresh(true);
    }
  },

  async runNow(jobId) {
    const d = await Api.runSchedulerJob(jobId);
    if (d) {
      Utils.toast(d.message || `已觸發 ${jobId}`, 2500, 'success');
      setTimeout(() => this.refresh(true), 800);
    }
  },

  async enableJob(jobId) {
    const d = await Api.enableSchedulerJob(jobId);
    if (d) {
      Utils.toast(d.message || '已啟用', 2000, 'success');
      await this.refresh(true);
    }
  },

  async disableJob(jobId) {
    const d = await Api.disableSchedulerJob(jobId);
    if (d) {
      Utils.toast(d.message || '已禁用', 2000, 'success');
      await this.refresh(true);
    }
  },
};

window.SchedulerTab = SchedulerTab;
