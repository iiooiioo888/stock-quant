/* global Api */

/**
 * 運維 SOP UI — 總覽卡片 / 設定頁面板共用
 */
(() => {
  const UI = window.StockQPro?.UI;
  if (!UI) return;

  const Ops = {};

  Ops.tone = (verdict) => {
    if (verdict === 'ok') return 'gn';
    if (verdict === 'critical') return 'rd';
    return 'ac';
  };

  Ops._host = (hostOrId) => {
    if (!hostOrId) return null;
    if (typeof hostOrId === 'string') return UI.id(hostOrId);
    return hostOrId;
  };

  Ops.renderCompact = (hostOrId, payload) => {
    const host = Ops._host(hostOrId);
    if (!host) return;
    const sop = payload?.sop;
    if (!sop) {
      UI.mount(host, UI.h('p', { class: 'dash-ops-empty' }, '無法讀取運維狀態'));
      return;
    }
    const tone = Ops.tone(sop.verdict);
    const checks = (sop.checks || []).slice(0, 5);
    const rec = (sop.recommendations || [])[0] || '';
    UI.mount(host, UI.h('div', { class: `dash-ops-inner dash-ops-inner--${tone}` },
      UI.h('div', { class: 'dash-ops-head' },
        UI.h('span', { class: `dash-ops-verdict dash-ops-verdict--${tone}` }, sop.verdict_zh || '—'),
        UI.h('button', {
          type: 'button',
          class: 'dash-ops-link tbtn tbtn--ghost',
          title: '前往設定查看運維詳情',
          onclick: () => window.StockQPro?.services?.opsMonitor?.navigateToOps?.(),
        }, '詳情'),
      ),
      UI.h('ul', { class: 'dash-ops-checks' },
        ...checks.map((c) => UI.h('li', { class: `dash-ops-check ${c.ok ? 'ok' : 'bad'}` },
          UI.h('span', { class: 'dash-ops-check-mark' }, c.ok ? '✓' : '!'),
          UI.h('span', { class: 'dash-ops-check-text' }, `${c.name || ''}：${c.detail || ''}`),
        )),
      ),
      rec ? UI.h('p', { class: 'dash-ops-rec' }, rec) : null,
    ));
  };

  Ops.renderExpanded = (hostOrId, metricsHostOrId, payload) => {
    const host = Ops._host(hostOrId);
    const metricsHost = Ops._host(metricsHostOrId);
    if (!host) return;

    const sop = payload?.sop;
    if (!sop) {
      UI.mount(host, UI.h('p', { class: 'dash-ops-empty' }, '無法讀取運維狀態'));
      if (metricsHost) UI.clear(metricsHost);
      return;
    }

    const tone = Ops.tone(sop.verdict);
    const checks = sop.checks || [];
    const recs = sop.recommendations || [];
    const pipe = payload?.pipeline_metrics?.cache || {};
    const ia = payload?.index_audit || {};
    const degraded = payload?.data_sources?.degraded_categories || [];

    UI.mount(host, UI.h('div', { class: `dash-ops-inner dash-ops-inner--${tone} set-ops-expanded` },
      UI.h('div', { class: 'dash-ops-head' },
        UI.h('span', { class: `dash-ops-verdict dash-ops-verdict--${tone}` }, sop.verdict_zh || '—'),
        UI.h('span', { class: 'set-ops-verdict-code' }, sop.verdict || ''),
      ),
      UI.h('ul', { class: 'dash-ops-checks' },
        ...checks.map((c) => UI.h('li', { class: `dash-ops-check ${c.ok ? 'ok' : 'bad'}` },
          UI.h('span', { class: 'dash-ops-check-mark' }, c.ok ? '✓' : '!'),
          UI.h('span', { class: 'dash-ops-check-text' }, `${c.name || ''}：${c.detail || ''}`),
        )),
      ),
      recs.length
        ? UI.h('div', { class: 'set-ops-recs' },
          UI.h('p', { class: 'set-ops-recs-title' }, '建議'),
          UI.h('ul', { class: 'set-ops-recs-list' },
            ...recs.map((r) => UI.h('li', {}, r)),
          ),
        )
        : null,
      UI.h('p', { class: 'set-ops-cli-hint' },
        '本機：',
        UI.h('code', {}, 'python main.py ops check'),
        ' · HTTP：',
        UI.h('code', {}, 'python main.py ops probe --ci'),
        ' · 全面：',
        UI.h('code', {}, 'python scripts/ops_audit.py --with-probe'),
      ),
    ));

    if (!metricsHost) return;
    const checked = payload?.checked_at
      ? new Date(Number(payload.checked_at) * 1000).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : '—';
    const items = [
      ['伺服器檢查', checked],
      ['快取待清理', pipe.pending_deferred ?? '—'],
      ['索引', ia.ok ? `完整 ${ia.present_count}/${ia.expected_count}` : `缺 ${ia.missing_count ?? '?'}`],
      ['數據源降級', degraded.length ? degraded.join(', ') : '無'],
      ['版本', payload?.version || '—'],
    ];
    UI.mount(metricsHost, UI.h('div', { class: 'set-ops-metrics-grid' },
      ...items.map(([k, v]) => UI.h('div', { class: 'set-ops-metric' },
        UI.h('span', { class: 'set-ops-metric-k' }, k),
        UI.h('span', { class: 'set-ops-metric-v' }, String(v)),
      )),
    ));
  };

  Ops.fetchSop = () => (
    Api.getHealthSop?.() || Api.get('/api/health/sop', { silent: true, timeout: 12000 })
  ).catch(() => null);

  Ops.formatRelativeTime = (ts) => {
    if (!ts) return '—';
    const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (sec < 60) return '剛剛';
    if (sec < 3600) return `${Math.floor(sec / 60)} 分鐘前`;
    return new Date(ts).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
  };

  UI.OpsStatus = Ops;
})();
