/**
 * task-common.js — 任務系統共享常量與渲染工具
 *
 * 供 app.js（浮動面板）與 tasks.js（Tab 頁面）共用，避免重複定義。
 */

const TaskCommon = {

  _typesLoaded: false,
  _typesPromise: null,
  /** 異步任務類型（來自 /api/tasks/types） */
  _asyncTypes: [],

  TYPE_NAMES: {
    backtest: '📊 回測',
    backtest_advanced: '📊 進階回測',
    backtest_multi: '📊 多策略對比',
    optimize: '⚡ 參數優化',
    portfolio: '📈 組合回測',
    walkforward: '🔄 Walk-Forward',
    auto_optimize: '🤖 自動優化',
    stock_universe_sync: '📚 股票庫同步',
    stock_universe_intro: '📝 股票簡介',
    data_download: '📥 市場數據下載',
    data_download_all: '📥 全市場下載',
    data_incremental: '🔄 增量更新',
  },

  STATUS_ICONS: {
    running: '⏳', completed: '✅', failed: '❌',
    cancelled: '🚫', pending: '⏸️',
  },

  STATUS_COLORS: {
    running: '#38bdf8', completed: '#22c55e', failed: '#ef4444',
    cancelled: '#94a3b8', pending: '#f59e0b',
  },

  STATUS_CHIP: {
    running: 'chip cfg', completed: 'chip on', failed: 'chip off',
    cancelled: 'chip', pending: 'chip',
  },

  TAB_MAP: {
    backtest: 'backtest',
    backtest_advanced: 'backtest',
    backtest_multi: 'backtest',
    optimize: 'optimize',
    portfolio: 'portfolio',
    walkforward: 'walkforward',
    auto_optimize: 'optimize',
    stock_universe_sync: 'data',
    stock_universe_intro: 'data',
    data_download: 'data',
    data_download_all: 'data',
    data_incremental: 'data',
  },

  async loadTypes() {
    if (this._typesPromise) return this._typesPromise;
    this._typesPromise = (async () => {
      try {
        const d = await Api.getTaskTypes({ silent: true });
        const types = d?.types || [];
        this._asyncTypes = types;
        types.forEach(t => {
          const label = t.icon ? `${t.icon} ${t.label}` : t.label;
          this.TYPE_NAMES[t.id] = label;
          if (t.tab) this.TAB_MAP[t.id] = t.tab;
        });
        this._typesLoaded = true;
      } catch (e) {
        console.warn('載入任務類型失敗:', e);
      }
    })();
    return this._typesPromise;
  },

  QUEUE_LABELS: {
    current: { icon: '▶', title: '目前執行' },
    next: { icon: '⏭', title: '下一個' },
    recent: { icon: '✅', title: '剛完成' },
  },

  downloadSubtitle(task) {
    if (!task) return '';
    if (task.status_message) return task.status_message;
    const meta = task.meta || {};
    if (meta.message) return meta.message;
    const dl = task.download || meta.download;
    if (!dl) return '';
    if (dl.current_code && dl.total) {
      return `${dl.market_name || dl.market || ''} ${dl.current_code} (${dl.index || 0}/${dl.total})`;
    }
    if (dl.records_total != null) return `已寫入 ${dl.records_total} 條`;
    return '';
  },

  isDownloadTask(taskType) {
    return taskType === 'data_download' || taskType === 'data_download_all' || taskType === 'data_incremental';
  },

  formatTaskSubtitle(task) {
    if (!task) return '';
    if (task.status === 'running' || task.status === 'pending') {
      const sub = this.downloadSubtitle(task);
      if (sub) return sub;
    }
    if (task.download_summary) {
      const s = task.download_summary;
      const parts = [];
      if (s.market_name) parts.push(s.market_name);
      if (s.total_records != null) parts.push(`${Number(s.total_records).toLocaleString()} 條`);
      if (s.success_symbols != null && s.total_symbols != null) {
        parts.push(`${s.success_symbols}/${s.total_symbols} 標的`);
      }
      return parts.join(' · ');
    }
    if (task.status === 'completed' && task.result && this.isDownloadTask(task.task_type)) {
      return this.downloadResultLine(task.result);
    }
    if (task.task_type === 'stock_universe_sync') {
      if (task.status === 'running' || task.status === 'pending') {
        if (task.status_message) return task.status_message;
      }
      const r = task.result;
      if (r && task.status === 'completed') {
        const parts = [`入庫 ${r.saved ?? 0}`];
        if (r.total_pool != null) parts.push(`池內 ${r.total_pool}`);
        return parts.join(' · ');
      }
    }
    if (task.task_type === 'stock_universe_intro') {
      const r = task.result;
      if (r && task.status === 'completed') {
        return `簡介 ${r.enriched ?? 0} / ${r.attempted ?? 0}`;
      }
      if (task.status_message) return task.status_message;
    }
    if (task.task_type === 'portfolio') {
      const p = task.params;
      if (p && p.method) {
        const METHOD_LABELS = {
          preset: '預設',
          dynamic: '動態權重',
          kelly: 'Kelly',
          degradation: '衰退檢測',
          arbitrate: '信號仲裁',
          'risk-parity': '風險平價',
          mvo: '均值方差',
          'vol-target': '波動目標',
          'max-diversification': '最大分散',
          'anti-correlation': '低相關',
          'regime-switch': '狀態切換',
          'black-litterman': 'BL',
          hrp: 'HRP',
          'cvar-optimize': 'CVaR',
          'multi-timeframe': '多週期',
          'dynamic-rebalance': '動態再平衡',
          'sector-limit': '板塊限制',
          voting: '投票式',
          'momentum-of-momentum': '動量動量',
          'adaptive-regime': '自適應',
          frontier: '有效前沿',
          basic: '基礎等權',
        };
        const lab = METHOD_LABELS[p.method] || p.method;
        if (p.preset_display) return `${lab} · ${p.preset_display}`;
        const codes = p.codes;
        if (Array.isArray(codes) && codes.length) {
          const head = codes.slice(0, 3).join(',');
          return `${lab} · ${head}${codes.length > 3 ? '…' : ''}`;
        }
        return lab;
      }
    }
    return '';
  },

  downloadResultLine(result) {
    if (!result) return '';
    const parts = [];
    if (result.market_name || result.market) parts.push(result.market_name || result.market);
    if (result.total_records != null) parts.push(`${result.total_records} 條`);
    if (result.success_symbols != null && result.total_symbols != null) {
      parts.push(`${result.success_symbols}/${result.total_symbols} 標的`);
    }
    return parts.join(' · ');
  },

  typeName(taskType) {
    return this.TYPE_NAMES[taskType] || taskType;
  },

  elapsed(startedAt, completedAt) {
    if (!startedAt) return null;
    const start = new Date(startedAt).getTime();
    const end = completedAt ? new Date(completedAt).getTime() : Date.now();
    return Math.max(0, Math.round((end - start) / 1000));
  },

  formatElapsed(sec) {
    if (sec == null) return '-';
    if (sec < 60) return sec + '秒';
    if (sec < 3600) return Math.floor(sec / 60) + '分' + (sec % 60) + '秒';
    return Math.floor(sec / 3600) + '時' + Math.floor((sec % 3600) / 60) + '分';
  },

  renderResultModal(task) {
    if (!task || !task.result) return '<p style="color:var(--text-dim)">尚無結果</p>';

    const r = task.result;
    const typeName = this.typeName(task.task_type);

    if (task.task_type === 'backtest' || task.task_type === 'backtest_advanced') {
      const ret = r.total_return_pct || 0;
      const cards = [
        { label: '總收益', value: Utils.formatPct(ret), cls: ret >= 0 ? 'gn' : 'rd' },
        { label: '年化收益', value: Utils.formatPct(r.annual_return_pct || 0), cls: '' },
        { label: '夏普比率', value: Utils.formatNum(r.sharpe_ratio || 0, 4), cls: '' },
        { label: 'Sortino', value: Utils.formatNum(r.sortino_ratio || 0, 4), cls: '' },
        { label: '最大回撤', value: Utils.formatPct(-(r.max_drawdown_pct || 0)), cls: 'rd' },
        { label: 'Calmar', value: Utils.formatNum(r.calmar_ratio || 0, 4), cls: '' },
        { label: '勝率', value: Utils.formatNum(r.win_rate_pct || 0, 1) + '%', cls: '' },
        { label: '交易次數', value: r.total_trades || 0, cls: '' },
        { label: '波動率', value: Utils.formatPct(r.volatility_pct || 0), cls: '' },
        { label: '最終淨值', value: '¥' + (r.final_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }), cls: '' },
      ];
      const cardsHtml = cards.map(c =>
        `<div class="c"><h3>${c.label}</h3><div class="v ${c.cls}">${c.value}</div></div>`
      ).join('');

      const elapsed = task.started_at ? this.formatElapsed(this.elapsed(task.started_at, task.completed_at)) : '';

      return `
        <h3>${typeName}結果 — ${task.title}</h3>
        ${elapsed ? `<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px">⏱ 執行耗時: ${elapsed}</div>` : ''}
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin:12px 0">${cardsHtml}</div>
        ${r.equity_curve ? `<div style="margin-top:12px"><h4>📈 權益曲線</h4><canvas id="taskResultChart" height="200"></canvas></div>` : ''}
        ${task.task_id ? `<div style="margin-top:8px"><button class="btn s" onclick="Utils.closeModal();App._loadBacktestResult('${task.task_id}')">↗ 在回測頁查看完整結果</button></div>` : ''}`;
    }

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
          <tr><th>策略</th><th>收益</th><th>夏普</th><th>回撤</th><th>勝率</th></tr>
          ${rows || '<tr><td colspan="5" style="text-align:center;color:var(--text-dim)">無數據</td></tr>'}
        </table></div>`;
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
      return `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div class="table-wrap" style="margin-top:8px"><table>
          <tr><th>#</th><th>參數</th><th>夏普</th><th>回撤</th><th>勝率</th></tr>
          ${rows || '<tr><td colspan="5" style="text-align:center;color:var(--text-dim)">無數據</td></tr>'}
        </table></div>`;
    }

    if (this.isDownloadTask(task.task_type)) {
      return this._renderDownloadResultModal(task, r);
    }

    if (task.task_type === 'portfolio') {
      const pm = r.portfolio || r;
      const ret = pm.total_return_pct ?? r.total_return_pct ?? 0;
      const sharpe = pm.sharpe_ratio ?? r.sharpe_ratio ?? 0;
      const dd = pm.max_drawdown_pct ?? r.max_drawdown_pct ?? 0;
      const subs = r.sub_strategies || [];
      const subHint = subs.length ? `<p class="sec-desc mt-sm">${subs.length} 個子策略 · 點「前往查看」看完整圖表</p>` : '';
      return `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0">
          <div class="c"><h3>組合收益</h3><div class="v ${ret >= 0 ? 'gn' : 'rd'}">${Utils.formatPct(ret)}</div></div>
          <div class="c"><h3>夏普比率</h3><div class="v">${Utils.formatNum(sharpe, 4)}</div></div>
          <div class="c"><h3>最大回撤</h3><div class="v rd">${Utils.formatPct(-dd)}</div></div>
        </div>${subHint}`;
    }

    if (task.task_type === 'stock_universe_sync') {
      const by = r.by_market || {};
      const marketRows = Object.entries(by).map(([k, n]) =>
        `<tr><td>${k}</td><td class="r">${n}</td></tr>`,
      ).join('');
      return `
        <h3>${typeName}結果 — ${task.title}</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin:12px 0">
          <div class="c"><h3>入庫數量</h3><div class="v gn">${r.saved ?? 0}</div></div>
          <div class="c"><h3>池內總數</h3><div class="v">${r.total_pool ?? '-'}</div></div>
          <div class="c"><h3>上限</h3><div class="v">${r.max_count ?? '-'}</div></div>
        </div>
        ${marketRows ? `<div class="table-wrap" style="margin-top:8px"><table>
          <tr><th>市場</th><th class="r">數量</th></tr>${marketRows}
        </table></div>` : ''}
        ${r.note ? `<p class="sec-desc mt-sm">${r.note}</p>` : ''}`;
    }

    const json = JSON.stringify(r, null, 2);
    return `
      <h3>${typeName}結果 — ${task.title}</h3>
      <pre style="background:var(--bg-secondary);padding:12px;border-radius:8px;overflow:auto;max-height:400px;font-size:12px">${json.substring(0, 5000)}${json.length > 5000 ? '\n...(截斷)' : ''}</pre>`;
  },

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

  _renderDownloadResultModal(task, r) {
    const typeName = this.typeName(task.task_type);
    const line = this.downloadResultLine(r);
    let html = `<h3>${typeName} — ${task.title}</h3>`;
    if (line) {
      html += `<div style="margin:8px 0"><span class="chip on">${line}</span></div>`;
    }

    if (r.market_summary && r.market_summary.length) {
      html += `<div class="table-wrap" style="margin-top:12px"><table>
        <tr><th>市場</th><th>記錄數</th><th>成功/總數</th></tr>
        ${r.market_summary.map(m => `<tr>
          <td>${m.market_name || m.market}</td>
          <td class="r">${(m.records || 0).toLocaleString()}</td>
          <td class="r">${m.success || 0}/${m.symbols || 0}</td>
        </tr>`).join('')}
      </table></div>`;
    }

    const details = r.details || [];
    if (details.length) {
      const show = details.slice(0, 50);
      html += `<div class="table-wrap" style="margin-top:12px;max-height:280px;overflow:auto"><table>
        <tr><th>代碼</th><th>市場</th><th>記錄</th></tr>
        ${show.map(d => `<tr>
          <td>${d.code}</td>
          <td>${d.market || '-'}</td>
          <td class="r">${d.records > 0 ? d.records : '<span style="color:var(--red)">0</span>'}</td>
        </tr>`).join('')}
      </table></div>`;
      if (details.length > 50) {
        html += `<p style="font-size:11px;color:var(--text-dim)">… 另有 ${details.length - 50} 個標的</p>`;
      }
    }

    if (r.updated != null) {
      html += `<div style="margin-top:8px;font-size:12px">更新 ${r.updated} 標的，跳過 ${r.skipped || 0} 個，共 ${(r.total_records || 0).toLocaleString()} 條</div>`;
    }
    return html;
  },

  renderParams(params, taskType) {
    if (!params || Object.keys(params).length === 0) {
      return '<span style="color:var(--text-dim)">無參數</span>';
    }

    if (params._legacy && params.note) {
      const count = params.count != null ? `<p style="font-size:12px;margin:0 0 6px">子策略數量：${params.count}</p>` : '';
      return `${count}<p style="font-size:12px;color:var(--text-dim);margin:0">${params.note}</p>`;
    }

    if (taskType === 'portfolio' && Array.isArray(params.allocations) && params.allocations.length) {
      const rows = params.allocations.slice(0, 20).map(a => {
        const code = a.code || '-';
        const strat = a.strategy || '-';
        const w = a.weight != null ? (Number(a.weight) * 100).toFixed(1) + '%' : '-';
        return `<tr><td>${code}</td><td>${strat}</td><td class="r">${w}</td></tr>`;
      }).join('');
      const extra = params.allocations.length > 20
        ? `<p style="font-size:11px;color:var(--text-dim);margin-top:6px">… 另有 ${params.allocations.length - 20} 個子策略</p>` : '';
      const meta = [
        params.rebalance ? `再平衡: ${params.rebalance}` : '',
        params.rebalance_freq_days ? `週期: ${params.rebalance_freq_days} 天` : '',
        params.cash != null ? `初始資金: ${params.cash}` : '',
      ].filter(Boolean).join(' · ');
      return `
        ${meta ? `<p style="font-size:11px;color:var(--text-dim);margin-bottom:8px">${meta}</p>` : ''}
        <div class="table-wrap table-wrap-scroll" style="max-height:200px">
          <table style="font-size:12px;width:100%">
            <thead><tr><th>代碼</th><th>策略</th><th class="r">權重</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        ${extra}`;
    }

    const skipKeys = new Set(['allocations']);
    const entries = Object.entries(params).filter(([k]) => !skipKeys.has(k)).slice(0, 12);
    const rows = entries.map(([k, v]) => {
      const val = typeof v === 'object' ? JSON.stringify(v) : String(v ?? '-');
      return `<tr><td style="font-weight:500;color:var(--text-dim);white-space:nowrap">${k}</td><td style="word-break:break-all">${val}</td></tr>`;
    }).join('');
    return `<table style="font-size:12px;width:100%">${rows}</table>`;
  },

  renderError(error) {
    if (!error) return '';
    return `
      <div style="background:var(--red-bg);border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:10px;margin-top:8px">
        <div style="font-weight:600;color:var(--red);margin-bottom:4px">❌ 錯誤信息</div>
        <pre style="font-size:12px;color:var(--text-secondary);white-space:pre-wrap;word-break:break-all;margin:0">${error}</pre>
      </div>`;
  },

  splitQueue(snapshot) {
    if (snapshot && snapshot.current !== undefined) {
      return {
        current: snapshot.current,
        next: snapshot.next,
        recent: snapshot.recent_completed,
      };
    }
    const tasks = Array.isArray(snapshot) ? snapshot : [];
    const running = tasks.filter(t => t.status === 'running')
      .sort((a, b) => (a.started_at || a.created_at || '').localeCompare(b.started_at || b.created_at || ''));
    const pending = tasks.filter(t => t.status === 'pending')
      .sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
    let next = running.length > 1 ? running[1] : (pending[0] || null);
    const completed = tasks.filter(t => t.status === 'completed' && t.has_result)
      .sort((a, b) => (b.completed_at || '').localeCompare(a.completed_at || ''));
    return {
      current: running[0] || pending[0] || null,
      next: running.length > 1 ? running[1] : (pending[0] && running[0] ? pending[0] : next),
      recent: completed[0] || null,
    };
  },

  _progressBar(progress, status) {
    const pct = status === 'pending' ? 0 : (progress || 0);
    return `<div class="progress-bar-wrap" style="margin-top:8px"><div class="progress-bar" style="width:${pct}%"></div></div>`;
  },

  renderQueueCard(role, task, compact) {
    const meta = this.QUEUE_LABELS[role] || { icon: '📋', title: '任務' };
    const emptyText = role === 'next' ? '暫無等待中的任務' : (role === 'current' ? '目前沒有執行中的任務' : '暫無最近完成的任務');
    const highlight = role === 'current' ? ' task-queue-current' : (role === 'recent' ? ' task-queue-recent' : '');

    if (!task) {
      return `<div class="task-queue-card task-queue-empty${highlight}" data-role="${role}">
        <div class="task-queue-head"><span>${meta.icon} ${meta.title}</span></div>
        <div class="task-queue-body" style="color:var(--text-dim);font-size:12px">${emptyText}</div>
      </div>`;
    }

    const typeName = this.typeName(task.task_type);
    const statusIcon = this.STATUS_ICONS[task.status] || '❓';
    const canNav = task.status === 'completed' && task.has_result;
    const canCancel = task.status === 'running' || task.status === 'pending';
    const progressLabel = task.status === 'running' ? `${task.progress || 0}%` : (task.status === 'pending' ? '等待中' : '');
    const dlSub = this.formatTaskSubtitle(task);

    let actions = '';
    if (canNav) {
      actions += `<button class="btn primary" style="font-size:11px;padding:4px 10px" onclick="event.stopPropagation();TaskCommon.navigateToResult('${task.task_id}')">前往查看</button> `;
      if (!compact && typeof Tasks !== 'undefined') {
        actions += `<button class="btn s" style="font-size:11px;padding:4px 10px" onclick="event.stopPropagation();Tasks.viewResult('${task.task_id}')">查看詳情</button>`;
      }
    }
    if (canCancel && typeof Tasks !== 'undefined') {
      actions += `<button class="btn danger" style="font-size:11px;padding:4px 10px" onclick="event.stopPropagation();Tasks.cancelTask('${task.task_id}')">取消</button>`;
    }

    return `<div class="task-queue-card${highlight}" data-role="${role}">
      <div class="task-queue-head">
        <span>${meta.icon} ${meta.title}</span>
        <span style="font-size:11px;color:var(--text-dim)">${statusIcon} ${progressLabel}</span>
      </div>
      <div class="task-queue-body">
        <div style="font-weight:600;font-size:13px">${task.title || typeName}</div>
        <div style="font-size:11px;color:var(--text-dim);margin-top:4px">${typeName}</div>
        ${dlSub ? `<div style="font-size:11px;color:#38bdf8;margin-top:6px">${dlSub}</div>` : ''}
        ${task.status === 'running' || task.status === 'pending' ? this._progressBar(task.progress, task.status) : ''}
        ${task.error ? `<div style="font-size:10px;color:#ef4444;margin-top:4px">${String(task.error).substring(0, 80)}</div>` : ''}
        ${actions ? `<div class="task-queue-actions">${actions}</div>` : ''}
      </div>
    </div>`;
  },

  renderQueueSection(snapshot, compact) {
    const q = this.splitQueue(snapshot);
    return `${this.renderQueueCard('current', q.current, compact)}
      ${this.renderQueueCard('next', q.next, compact)}
      ${this.renderQueueCard('recent', q.recent, compact)}`;
  },

  renderNavigateButton(taskId, label) {
    return `<button class="btn primary" style="padding:2px 8px;font-size:10px" onclick="event.stopPropagation();TaskCommon.navigateToResult('${taskId}')">${label || '前往查看'}</button>`;
  },

  tabForTaskType(taskType) {
    return this.TAB_MAP[taskType] || 'tasks';
  },

  async navigateToResult(taskId) {
    const d = await Api.getTask(taskId);
    const task = d?.task;
    if (!task?.result) {
      Utils.toast('此任務暫無結果', 2000, 'warning');
      return;
    }

    const tab = this.tabForTaskType(task.task_type);
    const p = task.params || {};
    const r = task.result;

    if (typeof App !== 'undefined' && App.loadTab) App.loadTab(tab);

    if (tab === 'backtest' && typeof Backtest !== 'undefined') {
      const stratEl = document.getElementById('btStrategy');
      if (Backtest.setCode) Backtest.setCode(p.code || r?.code || '');
      if (stratEl && p.strategy) stratEl.value = p.strategy;
      if (task.task_type === 'backtest_multi' && Backtest.displayMultiResults) {
        Backtest.displayMultiResults(Array.isArray(r) ? r : (r.results || []));
      } else if (Backtest._displayResult) {
        Backtest._lastResult = r;
        Backtest._displayResult(r);
      }
    } else if (tab === 'optimize' && typeof Optimize !== 'undefined') {
      const codeEl = document.getElementById('optCode');
      const stratEl = document.getElementById('optStrategy');
      if (codeEl) codeEl.value = p.code || '';
      if (stratEl && p.strategy) stratEl.value = p.strategy;
      if (Optimize.renderResults) Optimize.renderResults(r, p.strategy || 'all');
    } else if (tab === 'portfolio' && typeof Portfolio !== 'undefined') {
      if (Portfolio.showResult) Portfolio.showResult(r);
      else if (Portfolio._showResult) Portfolio._showResult(r);
    } else if (tab === 'walkforward' && typeof App !== 'undefined' && App.renderWalkForwardResult) {
      const codeEl = document.getElementById('wfCode');
      const stratEl = document.getElementById('wfStrategy');
      if (codeEl) codeEl.value = p.code || '';
      if (stratEl && p.strategy) stratEl.value = p.strategy;
      App.renderWalkForwardResult(r);
    } else if ((task.task_type === 'stock_universe_sync' || task.task_type === 'stock_universe_intro') && typeof Data !== 'undefined') {
      const tabs = document.getElementById('dataTabs');
      tabs?.querySelectorAll('button').forEach(b => b.classList.remove('a'));
      const btn = tabs?.querySelector('button[data-dtab="universe"]');
      if (btn) btn.classList.add('a');
      Data._currentTab = 'universe';
      Data._applyTabVisibility();
      Data._onTabActivated('universe');
      if (Data.loadUniverseStats) Data.loadUniverseStats();
      if (Data.searchUniverse) Data.searchUniverse(0);
    } else if (task.task_type === 'data_download_all' && typeof Data !== 'undefined') {
      if (Data.loadUniverseStats) Data.loadUniverseStats();
      if (Data._currentTab === 'universe' && Data.searchUniverse) {
        Data.searchUniverse(Data._universeOffset || 0);
      }
    } else if (tab === 'data' && typeof App !== 'undefined') {
      if (App.loadMarkets) App.loadMarkets();
      if (typeof Tasks !== 'undefined' && Tasks.viewResult) Tasks.viewResult(taskId);
    } else if (typeof Tasks !== 'undefined' && Tasks.viewResult) {
      Tasks.viewResult(taskId);
    }
  },
};

window.TaskCommon = TaskCommon;
