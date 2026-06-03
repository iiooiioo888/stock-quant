/**
 * 對外接口檢查頁
 */
const ConnectivityPage = {
  _bound: false,

  _categoryZh: {
    system: '系統',
    a_share: 'A股',
    crypto: '加密',
    forex: '外匯',
    exchange: '交易所',
    bond_fx: '債券/匯率',
    wealth: '銀行理財',
    fund: '基金',
    insurance: '保險',
    metals: '貴金屬',
    futures: '期貨',
    notify: '通知',
    error: '錯誤',
  },

  _ensureBound() {
    if (this._bound) return;
    this._bound = true;
    const runBtn = document.getElementById('extRunBtn');
    const regBtn = document.getElementById('extRegistryBtn');
    if (runBtn) runBtn.onclick = () => this.runFullCheck();
    if (regBtn) regBtn.onclick = () => this.loadRegistry();
    if (!window._extOpsListener) {
      window._extOpsListener = true;
      window.addEventListener('stockq:ops-updated', () => {
        if (document.getElementById('tab-connectivity')) {
          ConnectivityPage._renderOpsBanner().catch(() => {});
        }
      });
    }
  },

  init() {
    this.load();
  },

  async _renderOpsBanner() {
    const tab = document.getElementById('tab-connectivity');
    if (!tab) return;
    let host = document.getElementById('extOpsBanner');
    if (!host) {
      host = document.createElement('div');
      host.id = 'extOpsBanner';
      host.className = 'ext-ops-banner';
      const anchor = tab.querySelector('.fr');
      if (anchor) tab.querySelector('.sec')?.insertBefore(host, anchor);
      else tab.querySelector('.sec')?.prepend(host);
    }
    let data = null;
    try {
      data = window.StockQPro?.services?.opsMonitor?.getLast?.() || null;
      if (!data?.sop) {
        data = await (Api.getHealthSop?.() || Api.get('/api/health/sop', { silent: true }));
      }
    } catch (_) {
      data = null;
    }
    const sop = data?.sop;
    if (!sop?.verdict) {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    const tone = sop.verdict === 'ok' ? 'gn' : sop.verdict === 'critical' ? 'rd' : 'ac';
    const degraded = (data?.data_sources?.degraded_categories || []).length;
    const hint = degraded > 0 ? ` · 數據源降級 ${degraded} 類` : '';
    host.className = `ext-ops-banner ext-ops-banner--${tone}`;
    host.innerHTML = (
      `<span class="ext-ops-verdict">運維 SOP：${sop.verdict_zh || sop.verdict}${hint}</span>` +
      '<button type="button" class="btn s ext-ops-btn" data-ext-ops-settings>運維詳情</button>' +
      '<button type="button" class="btn s ext-ops-btn" data-ext-ops-refresh>刷新 SOP</button>'
    );
    if (!host.dataset.opsBound) {
      host.dataset.opsBound = '1';
      host.addEventListener('click', (e) => {
        if (e.target.closest('[data-ext-ops-settings]')) {
          if (window.StockQPro?.services?.opsMonitor?.navigateToOps) {
            window.StockQPro.services.opsMonitor.navigateToOps();
          } else if (window.StockQPro?.App?.nav) {
            window.StockQPro.App.nav('settings', { syncHash: true });
          }
          return;
        }
        if (e.target.closest('[data-ext-ops-refresh]')) {
          const mon = window.StockQPro?.services?.opsMonitor;
          Promise.resolve(mon?.tick?.())
            .then((d) => {
              ConnectivityPage._renderOpsBanner();
              const zh = d?.sop?.verdict_zh || '—';
              window.StockQPro?.App?.toast?.(`運維：${zh}`, 'ok');
            })
            .catch(() => window.StockQPro?.App?.toast?.('SOP 刷新失敗', 'er'));
        }
      });
    }
  },

  load() {
    this._ensureBound();
    this.loadLastOrRegistry();
    this._renderOpsBanner().catch(() => {});
  },

  /** 新 API 404 時降級到舊版 /api/data-sources */
  async _fetchRegistry() {
    let d = await Api.get('/api/external/check/registry', { silent: true });
    if (d && (d.registry || d.sources)) {
      return { data: d, fallback: false };
    }
    const legacy = await Api.get('/api/data-sources', { silent: true });
    if (legacy && legacy.sources) {
      return {
        data: {
          registry: legacy.sources,
          sources: legacy.sources,
          checked_at: new Date().toLocaleString(),
        },
        fallback: true,
      };
    }
    return { data: null, fallback: false };
  },

  _showRestartHint() {
    const meta = document.getElementById('extSummaryMeta');
    if (meta) {
      meta.innerHTML = '⚠️ 後端尚未載入新路由，請<strong>重啟</strong> <code>python main.py serve</code> 後再點「立即檢測」。';
    }
  },

  async loadLastOrRegistry() {
    const d = await Api.get('/api/external/check', { silent: true });
    if (d && Array.isArray(d.probes) && d.probes.length) {
      this.renderResult(d);
      return;
    }
    await this.loadRegistry();
  },

  async loadRegistry() {
    const tbody = document.getElementById('extProbeTable');
    const box = document.getElementById('extRegistryBox');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6"><span class="ld"></span> 載入…</td></tr>';
    try {
      const { data: d, fallback } = await this._fetchRegistry();
      if (!d) {
        if (tbody) {
          tbody.innerHTML = '<tr><td colspan="6" class="err">無法載入數據源狀態。請重啟服務後刷新頁面。</td></tr>';
        }
        this._showRestartHint();
        return;
      }
      const reg = d.registry || d.sources || {};
      this.renderRegistry(reg);
      if (box) this.renderRegistryDetail(reg, d.sources);
      if (tbody) {
        const hint = fallback
          ? '（降級：僅註冊表；重啟服務後可使用完整探測）'
          : '尚未執行全量探測。點「立即檢測」發起 HTTP 探活。';
        tbody.innerHTML = `<tr><td colspan="6" class="muted">${hint}</td></tr>`;
      }
      this.renderSummaryCards(null);
      const meta = document.getElementById('extSummaryMeta');
      if (meta) {
        meta.textContent = fallback
          ? `註冊表（舊 API）· ${d.checked_at || ''}`
          : `註冊表快照 · ${d.checked_at || ''}`;
      }
      if (fallback) this._showRestartHint();
    } catch (e) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="err">${e.message || e}</td></tr>`;
    }
  },

  async runFullCheck() {
    const btn = document.getElementById('extRunBtn');
    const tbody = document.getElementById('extProbeTable');
    if (btn) { btn.disabled = true; btn.textContent = '檢測中…'; }
    if (tbody) tbody.innerHTML = '<tr><td colspan="6"><span class="ld"></span> 正在探測外部接口（約 10–30 秒）…</td></tr>';
    try {
      const d = await Api.post('/api/external/check/run', {});
      if (!d) {
        if (tbody) {
          tbody.innerHTML = '<tr><td colspan="6" class="err">探測 API 不可用（404）。請停止並重新執行 <code>python main.py serve</code>，登錄後再試。</td></tr>';
        }
        this._showRestartHint();
        return;
      }
      this.renderResult(d);
      this._renderOpsBanner().catch(() => {});
    } catch (e) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="err">${e.message || e}（演示模式需登錄）</td></tr>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '▶ 立即檢測'; }
    }
  },

  renderSummaryCards(summary) {
    const el = document.getElementById('extSummaryCards');
    if (!el) return;
    if (!summary) {
      el.innerHTML = '<div class="dash-kpi"><span class="dash-kpi-label">狀態</span><span class="dash-kpi-value">待檢測</span></div>';
      return;
    }
    el.innerHTML = `
      <div class="dash-kpi"><span class="dash-kpi-label">總體</span><span class="dash-kpi-value">${summary.status || '—'}</span></div>
      <div class="dash-kpi"><span class="dash-kpi-label">通過</span><span class="dash-kpi-value pos">${summary.ok ?? 0}</span></div>
      <div class="dash-kpi"><span class="dash-kpi-label">失敗</span><span class="dash-kpi-value neg">${summary.fail ?? 0}</span></div>
      <div class="dash-kpi"><span class="dash-kpi-label">耗時</span><span class="dash-kpi-value">${summary.duration_ms != null ? summary.duration_ms + 'ms' : '—'}</span></div>`;
  },

  renderResult(d) {
    if (!d) return;
    const probes = d.probes || [];
    const sum = d.summary || {};
    this.renderSummaryCards({
      status: d.status,
      ok: sum.ok,
      fail: sum.fail,
      duration_ms: d.duration_ms,
    });
    const meta = document.getElementById('extSummaryMeta');
    if (meta) {
      meta.textContent = `上次檢測 ${d.checked_at || ''} · ${sum.ok ?? 0}/${sum.total ?? 0} 通過`;
    }
    const tbody = document.getElementById('extProbeTable');
    if (!tbody) return;
    if (!probes.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">無探測結果</td></tr>';
      return;
    }
    tbody.innerHTML = probes.map(p => {
      const icon = p.ok ? '✅' : '❌';
      const cat = this._categoryZh[p.category] || p.category;
      const lat = p.latency_ms != null ? `${p.latency_ms} ms` : '—';
      const ep = (p.endpoint || '').slice(0, 60);
      const msg = (p.message || '').replace(/"/g, '&quot;');
      return `<tr>
        <td>${icon}</td>
        <td>${p.name || p.id}</td>
        <td>${cat}</td>
        <td>${lat}</td>
        <td title="${msg}">${(p.message || '').slice(0, 80)}</td>
        <td class="muted" style="font-size:11px">${ep}</td>
      </tr>`;
    }).join('');
    if (d.registry) {
      const box = document.getElementById('extRegistryBox');
      if (box) this.renderRegistryDetail(d.registry, null);
    }
    this._renderOpsBanner().catch(() => {});
  },

  renderRegistry() {},

  renderRegistryDetail(reg) {
    const box = document.getElementById('extRegistryBox');
    if (!box || !reg) return;
    const lines = Object.entries(reg).map(([cat, info]) => {
      const st = info.status === 'ok' ? '✅' : '⚠️';
      const srcs = (info.sources || []).map(s =>
        `${s.name}${s.ok ? '' : ' (熔斷)'}`
      ).join(', ');
      return `<div style="margin:6px 0">${st} <strong>${cat}</strong> — ${info.available}/${info.total} 可用 · ${srcs}</div>`;
    });
    box.innerHTML = lines.join('') || '無註冊數據源';
  },
};
