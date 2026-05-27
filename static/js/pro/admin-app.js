/* global Api, Utils */

(() => {
  const $id = (id) => document.getElementById(id);

  const AdminApp = {
    user: null,

    async init() {
      try { if (typeof Api !== 'undefined' && Api.init) Api.init(); } catch (_) {}
      this._bindNav();
      this._bindAuthButtons();
      await this._gate();
    },

    _bindNav() {
      document.querySelectorAll('.admin-nav button[data-panel]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = btn.getAttribute('data-panel');
          document.querySelectorAll('.admin-nav button').forEach((b) => b.classList.remove('on'));
          btn.classList.add('on');
          document.querySelectorAll('.admin-panel').forEach((p) => p.classList.remove('on'));
          const panel = $id(`panel-${id}`);
          if (panel) panel.classList.add('on');
          if (id === 'users') this.loadUsers();
          if (id === 'controls') this.loadControls();
          if (id === 'system') this.loadSystem();
        });
      });
    },

    _bindAuthButtons() {
      $id('admin-login-btn')?.addEventListener('click', () => Api.showLoginModal?.(false));
      $id('admin-logout-btn')?.addEventListener('click', () => {
        Api.logout?.();
        this._showGate('已登出，請使用管理員賬號重新登錄。');
      });
    },

    async _gate() {
      const shell = $id('admin-shell');
      const gate = $id('admin-gate');
      if (!Api.isLoggedIn?.()) {
        this._showGate('請先登錄管理員賬號以進入後台。');
        return;
      }
      const res = await Api.get('/api/auth/me', { silent: true }).catch(() => null);
      const me = res?.user;
      if (!me || me.role !== 'admin') {
        this._showGate(me ? '當前賬號無管理員權限。' : '無法驗證身份，請重新登錄。');
        return;
      }
      this.user = me;
      if (gate) gate.style.display = 'none';
      if (shell) shell.style.display = '';
      const who = $id('admin-who');
      if (who) who.textContent = `${me.username} · 管理員`;
      document.querySelector('.admin-nav button[data-panel="overview"]')?.click();
    },

    _showGate(msg) {
      const shell = $id('admin-shell');
      const gate = $id('admin-gate');
      if (shell) shell.style.display = 'none';
      if (gate) {
        gate.style.display = 'block';
        const p = gate.querySelector('.gate-msg');
        if (p) p.textContent = msg || '需要管理員權限';
      }
    },

    async loadUsers() {
      const tbody = $id('users-tbody');
      if (!tbody) return;
      tbody.innerHTML = '<tr><td colspan="5">載入中…</td></tr>';
      const data = await Api.get('/api/admin/users', { silent: true }).catch(() => null);
      if (!data?.users?.length) {
        tbody.innerHTML = '<tr><td colspan="5">暫無用戶或無權限</td></tr>';
        return;
      }
      tbody.innerHTML = data.users.map((u) => {
        const role = u.role === 'admin' ? 'admin' : 'user';
        const badge = role === 'admin' ? 'badge-admin' : 'badge-user';
        const toggleRole = role === 'admin' ? 'user' : 'admin';
        const canDelete = this.user && u.id !== this.user.id;
        return `<tr>
          <td>${u.id}</td>
          <td>${escapeHtml(u.username)}</td>
          <td><span class="badge ${badge}">${role}</span></td>
          <td style="color:var(--t3);font-size:.68rem">${escapeHtml(u.created_at || '--')}</td>
          <td>
            <button type="button" class="admin-btn admin-btn-sm" data-role="${u.id}" data-new="${toggleRole}">設為 ${toggleRole}</button>
            ${canDelete ? `<button type="button" class="admin-btn admin-btn-sm admin-btn-danger" data-del="${u.id}">刪除</button>` : ''}
          </td>
        </tr>`;
      }).join('');

      tbody.querySelectorAll('[data-role]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-role');
          const role = btn.getAttribute('data-new');
          try {
            await Api.put(`/api/admin/users/${id}/role`, { role });
            Utils.toast?.('角色已更新', 2500, 'success');
            this.loadUsers();
          } catch (e) {
            Utils.toast?.(e.message || '更新失敗', 3000, 'error');
          }
        });
      });
      tbody.querySelectorAll('[data-del]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-del');
          if (!confirm('確定刪除此用戶？')) return;
          try {
            await Api.delete(`/api/admin/users/${id}`);
            Utils.toast?.('用戶已刪除', 2500, 'success');
            this.loadUsers();
          } catch (e) {
            Utils.toast?.(e.message || '刪除失敗', 3000, 'error');
          }
        });
      });
    },

    async loadSystem() {
      const grid = $id('system-stats');
      if (!grid) return;
      const [health, detailed] = await Promise.all([
        fetch('/api/health').then((r) => r.json()).catch(() => null),
        fetch('/api/health/detailed').then((r) => r.json()).catch(() => null),
      ]);
      const items = [
        ['版本', health?.version || '--'],
        ['運行時間', health?.uptime || '--'],
        ['本地標的', health?.total_stocks ?? '--'],
        ['日 K 記錄', health?.total_klines ?? '--'],
        ['數據庫', detailed?.database?.status === 'ok' ? '已連接' : (detailed?.database?.status || '--')],
        ['庫大小 MB', detailed?.database?.db_size_mb ?? '--'],
      ];
      grid.innerHTML = items.map(([l, v]) => `
        <div class="admin-stat"><div class="v">${escapeHtml(String(v))}</div><div class="l">${escapeHtml(l)}</div></div>
      `).join('');
    },

    async loadControls() {
      const s = $id('ctl-status');
      const setStatus = (msg) => { if (s) s.textContent = msg || ''; };
      setStatus('載入中…');
      const data = await Api.get('/api/admin/controls', { silent: true }).catch(() => null);
      const c = data?.controls || {};
      const scopes = c.scopes || {};
      const feat = scopes.features || {};
      const strat = scopes.strategies || {};
      const tasks = scopes.tasks || {};
      const $pub = $id('ctl-public-enabled');
      const $feat = $id('ctl-features-enabled');
      const $strat = $id('ctl-strategies-enabled');
      const $tasks = $id('ctl-tasks-enabled');
      if ($pub) $pub.checked = !!c.public_enabled;
      if ($feat) $feat.checked = !!(feat.enabled ?? c.features_enabled);
      if ($strat) $strat.checked = !!(strat.enabled ?? c.strategies_enabled);
      if ($tasks) $tasks.checked = !!(tasks.enabled ?? c.tasks_enabled);

      // features
      if ($id('ctl-feat-backtest')) $id('ctl-feat-backtest').checked = !!feat.backtest;
      if ($id('ctl-feat-backtest-adv')) $id('ctl-feat-backtest-adv').checked = !!feat.backtest_advanced;
      if ($id('ctl-feat-backtest-multi')) $id('ctl-feat-backtest-multi').checked = !!feat.backtest_multi;
      if ($id('ctl-feat-optimize')) $id('ctl-feat-optimize').checked = !!feat.optimize;
      if ($id('ctl-feat-portfolio')) $id('ctl-feat-portfolio').checked = !!feat.portfolio;
      if ($id('ctl-feat-walkforward')) $id('ctl-feat-walkforward').checked = !!feat.walkforward;
      if ($id('ctl-feat-auto-optimize')) $id('ctl-feat-auto-optimize').checked = !!feat.auto_optimize;
      if ($id('ctl-feat-target-search')) $id('ctl-feat-target-search').checked = !!feat.target_search;

      // strategies
      if ($id('ctl-strat-list')) $id('ctl-strat-list').checked = !!strat.list;
      if ($id('ctl-strat-params')) $id('ctl-strat-params').checked = !!strat.params;
      if ($id('ctl-strat-create')) $id('ctl-strat-create').checked = !!strat.create;
      if ($id('ctl-strat-builtin')) $id('ctl-strat-builtin').checked = !!strat.builtin_enabled;
      if ($id('ctl-strat-user')) $id('ctl-strat-user').checked = !!strat.user_enabled;
      if ($id('ctl-strat-allowed')) $id('ctl-strat-allowed').value = Array.isArray(strat.allowed_names) ? strat.allowed_names.join(',') : '';
      if ($id('ctl-strat-blocked')) $id('ctl-strat-blocked').value = Array.isArray(strat.blocked_names) ? strat.blocked_names.join(',') : '';

      // tasks
      if ($id('ctl-task-list')) $id('ctl-task-list').checked = !!tasks.list;
      if ($id('ctl-task-queue')) $id('ctl-task-queue').checked = !!tasks.queue;
      if ($id('ctl-task-types')) $id('ctl-task-types').checked = !!tasks.types;
      if ($id('ctl-task-detail')) $id('ctl-task-detail').checked = !!tasks.detail;
      if ($id('ctl-task-logs')) $id('ctl-task-logs').checked = !!tasks.logs;
      if ($id('ctl-task-cancel')) $id('ctl-task-cancel').checked = !!tasks.cancel;
      if ($id('ctl-task-delete')) $id('ctl-task-delete').checked = !!tasks.delete;
      if ($id('ctl-task-retry')) $id('ctl-task-retry').checked = !!tasks.retry;
      setStatus('已載入');

      const reloadBtn = $id('ctl-reload-btn');
      const saveBtn = $id('ctl-save-btn');
      if (reloadBtn) reloadBtn.onclick = () => this.loadControls();
      if (!saveBtn) return;
      saveBtn.onclick = async () => {
        setStatus('保存中…');
        const parseList = (id) => {
          const v = String($id(id)?.value || '').trim();
          if (!v) return [];
          return v.split(',').map(s => s.trim()).filter(Boolean);
        };
        const controls = {
          public_enabled: !!$pub?.checked,
          // v1 fallback（保留）
          features_enabled: !!$feat?.checked,
          strategies_enabled: !!$strat?.checked,
          tasks_enabled: !!$tasks?.checked,
          // v2 scopes
          scopes: {
            features: {
              enabled: !!$feat?.checked,
              backtest: !!$id('ctl-feat-backtest')?.checked,
              backtest_advanced: !!$id('ctl-feat-backtest-adv')?.checked,
              backtest_multi: !!$id('ctl-feat-backtest-multi')?.checked,
              optimize: !!$id('ctl-feat-optimize')?.checked,
              portfolio: !!$id('ctl-feat-portfolio')?.checked,
              walkforward: !!$id('ctl-feat-walkforward')?.checked,
              auto_optimize: !!$id('ctl-feat-auto-optimize')?.checked,
              target_search: !!$id('ctl-feat-target-search')?.checked,
            },
            strategies: {
              enabled: !!$strat?.checked,
              list: !!$id('ctl-strat-list')?.checked,
              params: !!$id('ctl-strat-params')?.checked,
              create: !!$id('ctl-strat-create')?.checked,
              builtin_enabled: !!$id('ctl-strat-builtin')?.checked,
              user_enabled: !!$id('ctl-strat-user')?.checked,
              allowed_names: parseList('ctl-strat-allowed'),
              blocked_names: parseList('ctl-strat-blocked'),
            },
            tasks: {
              enabled: !!$tasks?.checked,
              list: !!$id('ctl-task-list')?.checked,
              queue: !!$id('ctl-task-queue')?.checked,
              types: !!$id('ctl-task-types')?.checked,
              detail: !!$id('ctl-task-detail')?.checked,
              logs: !!$id('ctl-task-logs')?.checked,
              cancel: !!$id('ctl-task-cancel')?.checked,
              delete: !!$id('ctl-task-delete')?.checked,
              retry: !!$id('ctl-task-retry')?.checked,
            },
          },
        };
        try {
          await Api.put('/api/admin/controls', { controls });
          Utils.toast?.('已保存', 2000, 'success');
          setStatus('已保存');
        } catch (e) {
          Utils.toast?.(e.message || '保存失敗', 3000, 'error');
          setStatus('保存失敗');
        }
      };
    },
  };

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  document.addEventListener('DOMContentLoaded', () => AdminApp.init());
})();
