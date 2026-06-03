/* global Api */

/**
 * 全域運維 SOP 輪詢 — 頂欄 / 總覽 / 設定 / 任務中心共用
 */
(() => {
  const STORAGE_KEY = 'stockq:ops_last';
  const VERDICT_PREV_KEY = 'stockq:ops_verdict_prev';
  const POLL_MS = 60000;
  const VERDICT_RANK = { ok: 0, attention: 1, critical: 2 };

  let _timer = null;
  let _last = null;
  let _inflight = null;

  const M = {};

  M.getLast = () => _last;

  M.getLastMeta = () => {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    } catch {
      return null;
    }
  };

  M._notifyVerdictChange = (prev, cur, payload) => {
    const app = proApp();
    if (!app?.toast || !payload?.sop) return;
    const zh = payload.sop.verdict_zh || cur;
    const prevR = VERDICT_RANK[prev] ?? 0;
    const curR = VERDICT_RANK[cur] ?? 0;
    if (curR > prevR) {
      const type = cur === 'critical' ? 'er' : 'warn';
      app.toast(`運維狀態變更：${zh}`, type);
    } else if (curR < prevR && prevR > 0) {
      app.toast(`運維已恢復：${zh}`, 'ok');
    }
  };

  M._persist = (payload) => {
    const cur = payload?.sop?.verdict;
    let prev = null;
    try {
      prev = sessionStorage.getItem(VERDICT_PREV_KEY);
    } catch (_) {}
    if (prev && cur && prev !== cur) {
      M._notifyVerdictChange(prev, cur, payload);
    }
    if (cur) {
      try {
        sessionStorage.setItem(VERDICT_PREV_KEY, cur);
      } catch (_) {}
    }

    _last = payload;
    const meta = {
      at: Date.now(),
      verdict: cur,
      verdict_zh: payload?.sop?.verdict_zh,
    };
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(meta));
    } catch (_) {}
    window.dispatchEvent(new CustomEvent('stockq:ops-updated', { detail: payload }));
  };

  M.tick = async () => {
    const fetchSop = window.StockQPro?.UI?.OpsStatus?.fetchSop;
    if (!fetchSop) return null;
    if (_inflight) return _inflight;
    _inflight = fetchSop()
      .then((d) => {
        if (d) M._persist(d);
        return d;
      })
      .finally(() => {
        _inflight = null;
      });
    return _inflight;
  };

  M._onVisibility = () => {
    if (document.hidden) {
      M.stop();
    } else {
      M.start();
    }
  };

  M.start = () => {
    M.stop();
    if (document.hidden) return;
    M.tick().catch(() => {});
    _timer = setInterval(() => M.tick().catch(() => {}), POLL_MS);
  };

  M.stop = () => {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
  };

  M.formatCheckedAt = (ts) => {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
  };

  M.renderNotifBadge = (payload) => {
    const dot = document.getElementById('notif-ops-dot');
    if (!dot) return;
    const v = payload?.sop?.verdict;
    if (v && v !== 'ok') {
      dot.style.display = '';
      dot.classList.toggle('dot-ops--critical', v === 'critical');
      dot.title = `運維：${payload.sop.verdict_zh || v}`;
    } else {
      dot.style.display = 'none';
    }
  };

  M.renderTopbar = (payload) => {
    const pill = document.getElementById('ops-status-pill');
    const dot = document.getElementById('ops-status-dot');
    const text = document.getElementById('ops-status-text');
    if (!pill || !text) return;
    const sop = payload?.sop;
    if (!sop) {
      pill.hidden = true;
      return;
    }
    pill.hidden = false;
    const tone = window.StockQPro?.UI?.OpsStatus?.tone?.(sop.verdict) || 'ac';
    pill.className = `ops-status-pill ops-status-pill--${tone}`;
    pill.title = `運維 SOP：${sop.verdict_zh}（點擊查看設定）`;
    if (dot) {
      dot.className = `ops-status-dot ops-status-dot--${tone}`;
    }
    text.textContent = `運維 ${sop.verdict_zh}`;
    const meta = M.getLastMeta();
    const footer = document.getElementById('ops-status-footer');
    if (footer && meta?.at) {
      footer.hidden = false;
      footer.textContent = `SOP ${sop.verdict_zh} · ${M.formatCheckedAt(meta.at)}`;
    }
  };

  M.renderTasksStrip = (payload) => {
    const host = document.getElementById('tk-ops-strip');
    if (!host) return;
    const sop = payload?.sop;
    if (!sop) {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    const tone = window.StockQPro?.UI?.OpsStatus?.tone?.(sop.verdict) || 'ac';
    const meta = M.getLastMeta();
    const at = meta?.at ? M.formatCheckedAt(meta.at) : '—';
    const pending = payload?.pipeline_metrics?.cache?.pending_deferred;
    const missing = payload?.index_audit?.missing_count;
    const degraded = (payload?.data_sources?.degraded_categories || []).length;
    const hints = [];
    if (pending > 0) hints.push(`快取待清理 ${pending}`);
    if (missing > 0) hints.push(`索引缺 ${missing}`);
    if (degraded > 0) hints.push(`數據源降級 ${degraded}`);
    const hintStr = hints.length ? ` · ${hints.join(' · ')}` : '';
    host.className = `tk-ops-strip tk-ops-strip--${tone}`;
    host.innerHTML = `
      <span class="tk-ops-verdict">運維 ${escapeHtml(sop.verdict_zh)}</span>
      <span class="tk-ops-meta">更新 ${escapeHtml(at)}${escapeHtml(hintStr)}</span>
      <button type="button" class="btn s tk-ops-btn" data-ops-settings>詳情</button>
      <button type="button" class="btn s tk-ops-btn" data-ops-refresh>刷新 SOP</button>
    `;
    if (!host.dataset.opsBound) {
      host.dataset.opsBound = '1';
      host.addEventListener('click', (e) => {
        if (e.target.closest('[data-ops-settings]')) {
          window.StockQPro?.App?.nav?.('settings', { syncHash: true });
          return;
        }
        if (e.target.closest('[data-ops-refresh]')) {
          M.tick()
            .then(() => proApp()?.toast?.('SOP 已更新', 'ok'))
            .catch(() => proApp()?.toast?.('SOP 刷新失敗', 'er'));
        }
      });
    }
  };

  function escapeHtml(s) {
    return String(s ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;');
  }

  const proApp = () => window.StockQPro?.App;

  M.onUpdated = (payload) => {
    M.renderTopbar(payload);
    M.renderNotifBadge(payload);
    M.renderTasksStrip(payload);
    if (window.StockQPro?.App?.current === 'dashboard') {
      window.StockQPro?.UI?.Dashboard?.renderOpsStatus?.(payload);
    }
    if (window.StockQPro?.App?.current === 'settings') {
      window.StockQPro?.UI?.OpsStatus?.renderExpanded?.(
        'set-ops-root',
        'set-ops-metrics',
        payload,
      );
    }
  };

  M.navigateToOps = () => {
    try {
      sessionStorage.setItem('stockq:scroll-ops', '1');
    } catch (_) {}
    window.StockQPro?.App?.nav?.('settings', { syncHash: true });
  };

  M.scrollToOpsPanel = () => {
    const panel = document.getElementById('set-ops-panel');
    if (!panel) return;
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    panel.classList.add('set-ops-panel--highlight');
    setTimeout(() => panel.classList.remove('set-ops-panel--highlight'), 1600);
  };

  M.init = () => {
    if (M._inited) return;
    M._inited = true;
    const pill = document.getElementById('ops-status-pill');
    pill?.addEventListener('click', () => M.navigateToOps());
    window.addEventListener('stockq:ops-updated', (e) => M.onUpdated(e.detail));
    document.addEventListener('visibilitychange', M._onVisibility);
    M.start();
  };

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.services = window.StockQPro.services || {};
  window.StockQPro.services.opsMonitor = M;
})();
