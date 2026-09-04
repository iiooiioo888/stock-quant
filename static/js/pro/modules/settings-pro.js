/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);
  const Prefs = () => window.StockQPro?.Prefs;
  const UI = () => window.StockQPro?.UI;
  let _healthTimer = null;
  let _topbarModalMounted = false;
  let _topbarCatalogCache = null;

  function updatePreview() {
    const box = $id('set-color-preview');
    if (!box) return;
    const up = box.querySelector('.settings-preview-chip.up');
    const down = box.querySelector('.settings-preview-chip.down');
    if (up) up.textContent = '+1.28%';
    if (down) down.textContent = '-0.85%';
  }

  function readForm() {
    const scheme = document.querySelector('input[name="set-quote-scheme"]:checked')?.value
      || Prefs()?.DEFAULTS?.quoteColorScheme;
    return {
      quoteColorScheme: scheme,
      chartDays: Number($id('set-chart-days')?.value) || 90,
      marketPollSec: Number($id('set-poll-sec')?.value),
      compactTopbar: !!$id('set-compact-topbar')?.checked,
    };
  }

  function fillForm(p) {
    const scheme = p.quoteColorScheme || 'cn-red-up';
    document.querySelectorAll('input[name="set-quote-scheme"]').forEach((el) => {
      el.checked = el.value === scheme;
    });
    if ($id('set-chart-days')) $id('set-chart-days').value = String(p.chartDays ?? 90);
    if ($id('set-poll-sec')) $id('set-poll-sec').value = String(p.marketPollSec ?? 90);
    if ($id('set-compact-topbar')) $id('set-compact-topbar').checked = p.compactTopbar !== false;
    updatePreview();
  }

  async function loadIndicesCatalog() {
    if (_topbarCatalogCache) return _topbarCatalogCache;
    const d = await Api.get('/api/indices/catalog', { silent: true, timeout: 12000, retries: 1 }).catch(() => null);
    const instruments = Array.isArray(d?.instruments) ? d.instruments : [];
    const group_order = Array.isArray(d?.group_order) ? d.group_order : [];
    const group_labels = (d?.group_labels && typeof d.group_labels === 'object') ? d.group_labels : {};
    _topbarCatalogCache = { instruments, group_order, group_labels };
    return _topbarCatalogCache;
  }

  function ensureTopbarModal() {
    const ui = UI();
    if (!ui || _topbarModalMounted) return;
    const modal = ui.Modal({
      id: 'm-topbar-indices',
      title: '頂欄指數 · 加入 / 移走',
      width: 'min(860px,92vw)',
      body: [
        ui.h('div', { style: { display: 'grid', gap: '10px' } },
          ui.h('div', { class: 'pro-toolbar pro-toolbar--row', style: { margin: '0' } },
            ui.h('input', { id: 'topbar-q', class: 'inp', type: 'search', placeholder: '搜尋：名稱 / 代碼（例如 SPX、BTC、上證）', style: { minWidth: '220px', flex: '1' } }),
            ui.h('button', { class: 'btn s', type: 'button', id: 'topbar-reset' }, '恢復預設'),
            ui.h('button', { class: 'btn btn-ac', type: 'button', id: 'topbar-save' }, '保存'),
          ),
          ui.h('div', { id: 'topbar-picked', class: 'pro-meta-bar', style: { margin: '0' } }, '已選 0 個'),
          ui.h('div', { id: 'topbar-groups', style: { display: 'grid', gap: '12px' } }),
        ),
      ],
      footer: [
        ui.h('div', { style: { fontSize: '.66rem', color: 'var(--t3)', lineHeight: '1.6' } },
          '提示：頂欄顯示數量建議 8–18 個（太多會變擁擠）。此設定只保存到本機瀏覽器。',
        ),
        ui.h('span', { style: { flex: '1' } }),
        ui.h('button', { class: 'btn s', type: 'button', 'data-close': 'm-topbar-indices' }, '關閉'),
      ],
    });
    document.body.appendChild(modal);
    ui.init();
    _topbarModalMounted = true;
  }

  function renderTopbarGroups(catalog, selectedSyms, q) {
    const ui = UI();
    const host = $id('topbar-groups');
    if (!ui || !host) return;
    const query = String(q || '').trim().toLowerCase();
    const items = (catalog?.instruments || []).map((i) => ({
      symbol: String(i.symbol || '').toUpperCase(),
      name: String(i.name || ''),
      group: String(i.group || ''),
      asset_class: String(i.asset_class || ''),
      topbar: i.topbar !== false,
    })).filter((i) => i.symbol);

    const match = (it) => {
      if (!query) return true;
      return it.symbol.toLowerCase().includes(query) || it.name.toLowerCase().includes(query);
    };

    const groupOrder = Array.isArray(catalog?.group_order) ? catalog.group_order : [];
    const groupLabels = catalog?.group_labels || {};

    const byGroup = new Map();
    items.filter(match).forEach((it) => {
      const gid = it.group || 'other';
      if (!byGroup.has(gid)) byGroup.set(gid, []);
      byGroup.get(gid).push(it);
    });

    const groups = groupOrder.length ? groupOrder : Array.from(byGroup.keys()).sort();

    UI().clear(host);
    const sections = [];
    groups.forEach((gid) => {
      const list = byGroup.get(gid) || [];
      if (!list.length) return;
      list.sort((a, b) => {
        const ao = selectedSyms.has(a.symbol) ? 0 : 1;
        const bo = selectedSyms.has(b.symbol) ? 0 : 1;
        if (ao !== bo) return ao - bo;
        return a.name.localeCompare(b.name);
      });
      const title = groupLabels[gid] || gid;
      const grid = ui.h('div', {
        style: {
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))',
          gap: '10px',
        },
      },
      ...list.map((it) => {
        const id = `tb-${gid}-${it.symbol}`.replaceAll(/[^a-zA-Z0-9_-]/g, '-');
        const checked = selectedSyms.has(it.symbol);
        const row = ui.h('label', {
          class: 'pnl',
          style: {
            padding: '10px 12px',
            cursor: 'pointer',
            borderColor: checked ? 'var(--bf)' : 'var(--bd)',
            background: checked ? 'linear-gradient(165deg,rgba(122,162,247,.10),var(--bg0))' : 'linear-gradient(165deg,rgba(255,255,255,.03),var(--bg0))',
          },
        },
        ui.h('div', { style: { display: 'flex', alignItems: 'flex-start', gap: '10px' } },
          ui.h('input', {
            type: 'checkbox',
            id,
            checked: checked ? 'checked' : null,
            dataset: { sym: it.symbol },
            style: { marginTop: '2px' },
          }),
          ui.h('div', { style: { minWidth: '0', flex: '1' } },
            ui.h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' } },
              ui.h('strong', { style: { fontSize: '.76rem' } }, it.name || it.symbol),
              ui.h('span', { class: 'badge b-bl', style: { fontSize: '.58rem' } }, it.symbol),
            ),
            ui.h('div', { style: { marginTop: '4px', fontSize: '.64rem', color: 'var(--t3)' } },
              it.asset_class ? `類別：${it.asset_class}` : '—',
              it.topbar ? '' : ' · 非預設頂欄',
            ),
          ),
        ));
        return row;
      }));

      sections.push(
        ui.h('section', {},
          ui.h('div', { class: 'ph', style: { padding: '0 2px', marginBottom: '6px' } },
            ui.h('div', { class: 'pt', style: { fontSize: '.78rem' } }, title),
            ui.h('div', { class: 'pa', style: { fontSize: '.66rem', color: 'var(--t3)' } }, `${list.length} 檔`),
          ),
          grid,
        ),
      );
    });
    sections.forEach((s) => host.appendChild(s));
  }

  function topbarSelectedFromPrefs() {
    const p = Prefs()?.load?.() || {};
    const list = Array.isArray(p.topbarSymbols) ? p.topbarSymbols : [];
    return list.map((s) => String(s || '').trim().toUpperCase()).filter(Boolean);
  }

  async function openTopbarEditor() {
    ensureTopbarModal();
    const ui = UI();
    if (!ui) return;
    ui.modalOpen('m-topbar-indices');

    const pickedEl = $id('topbar-picked');
    const qEl = $id('topbar-q');
    const resetBtn = $id('topbar-reset');
    const saveBtn = $id('topbar-save');

    const catalog = await loadIndicesCatalog().catch(() => null);
    if (!catalog) {
      window.StockQPro?.App?.toast?.('載入指數目錄失敗', 'er');
      return;
    }

    let selected = new Set(topbarSelectedFromPrefs());

    const syncPicked = () => {
      const n = selected.size;
      if (pickedEl) pickedEl.textContent = `已選 ${n} 個` + (n ? ` · ${Array.from(selected).slice(0, 10).join(', ')}${n > 10 ? '…' : ''}` : '（使用預設）');
    };

    const rerender = () => {
      renderTopbarGroups(catalog, selected, qEl?.value);
      syncPicked();
    };

    rerender();

    const groupsHost = $id('topbar-groups');
    if (groupsHost && !groupsHost.dataset.bound) {
      groupsHost.dataset.bound = '1';
      groupsHost.addEventListener('change', (e) => {
        const cb = e.target?.closest?.('input[type="checkbox"][data-sym]');
        if (!cb) return;
        const sym = String(cb.dataset.sym || '').toUpperCase();
        if (!sym) return;
        if (cb.checked) selected.add(sym);
        else selected.delete(sym);
        syncPicked();
      });
    }

    if (qEl && !qEl.dataset.bound) {
      qEl.dataset.bound = '1';
      qEl.addEventListener('input', () => rerender());
    } else if (qEl) {
      qEl.value = '';
    }

    if (resetBtn && !resetBtn.dataset.bound) {
      resetBtn.dataset.bound = '1';
      resetBtn.addEventListener('click', () => {
        selected = new Set(); // empty -> default backend topbar
        if (qEl) qEl.value = '';
        rerender();
      });
    }

    if (saveBtn && !saveBtn.dataset.bound) {
      saveBtn.dataset.bound = '1';
      saveBtn.addEventListener('click', () => {
        const list = Array.from(selected);
        Prefs()?.save?.({ topbarSymbols: list });
        window.StockQPro?.MarketTicker?.refreshTopbar?.();
        window.StockQPro?.App?.toast?.('頂欄指數已保存', 'ok');
        ui.modalClose('m-topbar-indices');
      });
    }
  }

  function fillLlmForm(settings, defaults = {}) {
    if ($id('set-llm-base')) {
      $id('set-llm-base').value = settings?.api_base || defaults?.api_base || '';
    }
    if ($id('set-llm-model')) {
      $id('set-llm-model').value = settings?.model || defaults?.model || '';
    }
    if ($id('set-llm-key')) {
      $id('set-llm-key').value = '';
      $id('set-llm-key').placeholder = settings?.has_api_key
        ? `已保存 ${settings.api_key_masked || '****'}（留空不修改）`
        : 'sk-…';
    }
  }

  function updateLlmStatusLine(text, ok) {
    const el = $id('set-llm-status');
    if (!el) return;
    el.textContent = text.startsWith('狀態') ? text : `狀態：${text}`;
    el.style.color = ok ? 'var(--quote-up)' : 'var(--t3)';
    syncLlmSourceDot();
  }

  async function loadLlmSettings() {
    const local = typeof Api.getLlmConfig === 'function' ? Api.getLlmConfig() : {};
    if (!Api.isLoggedIn?.()) {
      fillLlmForm({ has_api_key: !!local.api_key, api_key_masked: local.api_key ? '本機' : '' }, local);
      updateLlmStatusLine('未登錄：僅本機 Key 可用', false);
      return;
    }
    try {
      const d = await Api.getLlmSettings();
      const st = d?.settings || {};
      const defs = d?.defaults || {};
      fillLlmForm(st, defs);
      if (local.api_base && !$id('set-llm-base')?.value) $id('set-llm-base').value = local.api_base;
      if (local.model && !$id('set-llm-model')?.value) $id('set-llm-model').value = local.model;
      const envOk = !!d?.env_configured;
      const configured = d?.configured || !!local.api_key;
      const parts = [];
      if (st.has_api_key) parts.push('帳號已存 Key');
      else if (envOk) parts.push('環境變量 Key');
      if (local.api_key) parts.push('本機 Key');
      updateLlmStatusLine(
        configured ? `已就緒${parts.length ? `（${parts.join(' · ')}）` : ''}` : '未配置 Key',
        configured,
      );
    } catch (e) {
      fillLlmForm({ has_api_key: !!local.api_key }, local);
      updateLlmStatusLine(`載入失敗：${e?.message || e}`, false);
    }
  }

  async function saveLlmSettings() {
    const key = String($id('set-llm-key')?.value || '').trim();
    const api_base = String($id('set-llm-base')?.value || '').trim();
    const model = String($id('set-llm-model')?.value || '').trim();
    const localOnly = !!$id('set-llm-local-only')?.checked;

    const localPatch = {};
    if (api_base) localPatch.api_base = api_base;
    if (model) localPatch.model = model;
    if (key) localPatch.api_key = key;
    if (typeof Api.setLlmConfig === 'function') Api.setLlmConfig(localPatch);

    if (localOnly) {
      window.StockQPro?.App?.toast?.('LLM 設置已保存到本機', 'ok');
      await loadLlmSettings();
      return;
    }

    if (!Api.isLoggedIn?.()) {
      window.StockQPro?.App?.toast?.('已保存到本機；登錄後可同步到帳號', 'inf');
      return;
    }

    const llm = {};
    if (key) llm.api_key = key;
    if (api_base) llm.api_base = api_base;
    if (model) llm.model = model;

    if (!Object.keys(llm).length) {
      window.StockQPro?.App?.toast?.('請填寫 API Key、Base 或模型，或勾選「僅保存到本機」', 'inf');
      return;
    }

    try {
      const d = await Api.saveLlmSettings(llm);
      if (!d?.success) throw new Error(d?.message || '保存失敗');
      if ($id('set-llm-key')) $id('set-llm-key').value = '';
      window.StockQPro?.App?.toast?.('LLM 設置已保存到帳號', 'ok');
      await loadLlmSettings();
    } catch (e) {
      window.StockQPro?.App?.toast?.(`保存失敗：${e?.message || e}`, 'er');
    }
  }

  async function clearLlmKey() {
    if (typeof Api.setLlmConfig === 'function') {
      const c = Api.getLlmConfig();
      delete c.api_key;
      Api.setLlmConfig(c);
    }
    if ($id('set-llm-key')) $id('set-llm-key').value = '';
    if (Api.isLoggedIn?.()) {
      try {
        await Api.saveLlmSettings({ clear: true });
      } catch (_) { /* ignore */ }
    }
    window.StockQPro?.App?.toast?.('已清除 API Key', 'ok');
    await loadLlmSettings();
  }

  function setSourceRow(dotId, statusId, ok, text) {
    const dot = $id(dotId);
    const st = $id(statusId);
    if (dot) {
      dot.classList.remove('ok', 'warn', 'err', 'pending');
      dot.classList.add(ok === true ? 'ok' : ok === false ? 'err' : ok === 'warn' ? 'warn' : 'pending');
    }
    if (st && text != null) st.textContent = text;
  }

  function syncLlmSourceDot() {
    const llmLine = $id('set-llm-status');
    const hint = $id('set-src-llm-hint');
    if (!llmLine) return;
    const txt = llmLine.textContent || '';
    const ready = /已就緒|本機 Key|環境變量/.test(txt);
    const fail = /失敗|未配置/.test(txt);
    if (hint) hint.textContent = txt.replace(/^狀態：?/, '').trim() || txt;
    setSourceRow('set-src-llm-dot', null, ready ? true : fail ? false : 'warn', null);
  }

  async function loadOpsSop() {
    const Ops = window.StockQPro?.UI?.OpsStatus;
    const mon = window.StockQPro?.services?.opsMonitor;
    if (!Ops?.renderExpanded) return null;
    const data = mon?.getLast?.() || await (mon?.tick?.() || Ops.fetchSop?.());
    Ops.renderExpanded?.('set-ops-root', 'set-ops-metrics', data);
    return data;
  }

  async function loadDataSourceHealth() {
    setSourceRow('set-src-tv-dot', 'set-src-tv', 'pending', '檢測中…');
    setSourceRow('set-src-ib-dot', 'set-src-ib', 'pending', '檢測中…');

    const cfg = await Api.getConfig().catch(() => ({}));
    if (cfg?.tradingview_enabled === false) {
      setSourceRow('set-src-tv-dot', 'set-src-tv', 'warn', '伺服器已關閉 TV 行情');
    }
    if (cfg && !cfg.ib_enabled) {
      setSourceRow('set-src-ib-dot', 'set-src-ib', 'warn', '未啟用 IB 整合');
    }

    let providers = null;
    try {
      providers = await Api.get('/api/indices/providers', { silent: true, timeout: 8000, retries: 2 });
    } catch (_) {
      providers = null;
    }

    if (cfg?.tradingview_enabled !== false) {
      if (providers?.tradingview) {
        const tv = providers.tradingview;
        const ok = !!tv.ok;
        const reason = tv.reason || tv.probe?.reason || '';
        const quotes = tv.quotes != null ? ` · ${tv.quotes} 檔` : '';
        setSourceRow(
          'set-src-tv-dot',
          'set-src-tv',
          ok,
          ok ? `在線${quotes}` : (reason ? `離線（${reason}）` : '離線'),
        );
      } else {
        setSourceRow('set-src-tv-dot', 'set-src-tv', false, '探測失敗，請稍後重試');
      }
    }

    if (providers?.ib && cfg?.ib_enabled !== false) {
      const ib = providers.ib;
      const connected = !!(ib.connected || ib.ok);
      const enabled = ib.enabled !== false;
      if (!enabled) {
        setSourceRow('set-src-ib-dot', 'set-src-ib', 'warn', '未啟用');
      } else if (connected) {
        const q = ib.quotes != null ? ` · ${ib.quotes} 檔` : '';
        setSourceRow('set-src-ib-dot', 'set-src-ib', true, `已連線${q}`);
      } else {
        const reason = ib.reason || '未連線';
        setSourceRow('set-src-ib-dot', 'set-src-ib', 'warn', reason);
      }
    } else if (cfg?.ib_enabled) {
      setSourceRow('set-src-ib-dot', 'set-src-ib', false, '探測失敗');
    }

    syncLlmSourceDot();
    return { cfg, providers };
  }

  async function loadServerConfig() {
    const cfg = await Api.getConfig().catch(() => ({}));
    if (cfg && typeof cfg === 'object') {
      if (cfg.backtest_commission != null && $id('set-commission')) {
        $id('set-commission').value = Number(cfg.backtest_commission) * 100;
      }
      if (cfg.task_max_workers != null && $id('set-max-parallel')) {
        $id('set-max-parallel').value = Number(cfg.task_max_workers) || 4;
      }
      if (cfg.data_fetch_buffer_hours != null && $id('set-data-buffer')) {
        $id('set-data-buffer').value = Number(cfg.data_fetch_buffer_hours);
      }
    }
    await Promise.all([loadDataSourceHealth(), loadOpsSop()]);
    return cfg;
  }

  function startHealthPolling() {
    stopHealthPolling();
    _healthTimer = setInterval(() => {
      loadDataSourceHealth().catch(() => {});
      loadOpsSop().catch(() => {});
    }, 60000);
  }

  function stopHealthPolling() {
    if (_healthTimer) {
      clearInterval(_healthTimer);
      _healthTimer = null;
    }
  }

  function load() {
    const p = Prefs()?.load?.() || {};
    fillForm(p);
    return Promise.all([loadServerConfig(), loadLlmSettings()]);
  }

  function save() {
    const partial = readForm();
    Prefs()?.save?.(partial);
    window.StockQPro?.MarketTicker?.setPollInterval?.(partial.marketPollSec * 1000);
    window.StockQPro?.MarketTicker?.refresh?.();
    window.StockQPro?.App?.toast?.('偏好已保存（本機）', 'ok');
  }

  async function applyMaxParallel() {
    const n = Number($id('set-max-parallel')?.value);
    const buf = Number($id('set-data-buffer')?.value);
    if (!Number.isFinite(n) || n < 1 || n > 32) {
      window.StockQPro?.App?.toast?.('並行數須為 1～32', 'er');
      return;
    }
    if (!Number.isFinite(buf) || buf < 0 || buf > 168) {
      window.StockQPro?.App?.toast?.('緩衝小時須為 0～168', 'er');
      return;
    }
    const d = await (Api.setTaskCapacity
      ? Api.setTaskCapacity(Math.round(n), null, buf)
      : Api.put('/api/tasks/capacity', {
          max_workers: Math.round(n),
          buffer_hours: buf,
        })
    ).catch(() => null);
    if (d?.success) {
      window.StockQPro?.App?.toast?.(
        `並行 ${d.max_workers}，緩衝 ${d.buffer_hours} 小時`,
        'ok',
      );
    } else {
      window.StockQPro?.App?.toast?.(d?.detail || '套用失敗（需登錄）', 'er');
    }
  }

  async function clearCaches() {
    try {
      if (typeof Api.clearGetCache === 'function') Api.clearGetCache();
      await Api.post('/api/cache/clear', {}).catch(() => null);
      window.StockQPro?.App?.toast?.('已清除前端與服務端緩存', 'ok');
    } catch (_) {
      window.StockQPro?.App?.toast?.('清除緩存失敗', 'er');
    }
  }

  function bindSchemePreview() {
    document.querySelectorAll('input[name="set-quote-scheme"]').forEach((el) => {
      el.addEventListener('change', () => {
        Prefs()?.save?.(readForm());
        updatePreview();
      });
    });
  }

  async function loadBillingSummary() {
    const el = $id('set-billing-summary');
    if (!el) return;
    if (!Api?.isLoggedIn?.()) {
      el.textContent = '未登錄 — 登錄後可同步方案與配額';
      return;
    }
    el.textContent = '載入方案中…';
    const data = await Api.getBillingMe?.().catch(() => null);
    if (!data?.plan_id) {
      el.textContent = '無法載入方案資訊';
      return;
    }
    const lim = data.limits || {};
    const use = data.usage || {};
    const trial = data.status === 'trialing' ? '（試用）' : '';
    el.textContent = `${data.plan_name || data.plan_id}${trial} · 回測 ${use.backtests_today || 0}/${lim.daily_backtests} · 組合 ${use.portfolio_runs_today || 0}/${lim.daily_portfolio_runs}`;
  }

  function init() {
    if ($id('set-billing-go') && !$id('set-billing-go').dataset.bound) {
      $id('set-billing-go').dataset.bound = '1';
      $id('set-billing-go').addEventListener('click', () => {
        window.StockQPro?.App?.nav?.('pricing', { syncHash: true });
      });
    }
    if ($id('set-save-btn') && !$id('set-save-btn').dataset.bound) {
      $id('set-save-btn').dataset.bound = '1';
      $id('set-save-btn').addEventListener('click', () => save());
      $id('set-apply-parallel')?.addEventListener('click', () => applyMaxParallel());
      $id('set-reload-btn')?.addEventListener('click', () => {
        load().catch(() => window.StockQPro?.App?.toast?.('載入設定失敗', 'er'));
      });
      $id('set-clear-cache')?.addEventListener('click', () => clearCaches());
      $id('set-reset-prefs')?.addEventListener('click', () => {
        localStorage.removeItem(Prefs()?.STORAGE_KEY || 'stockq:pro_prefs_v1');
        if (Prefs()) Prefs().save({ ...Prefs().DEFAULTS });
        fillForm(Prefs().DEFAULTS);
        window.StockQPro?.App?.toast?.('已恢復預設偏好', 'ok');
      });
      $id('set-logout-btn')?.addEventListener('click', () => {
        if (typeof Api !== 'undefined' && Api.isLoggedIn?.()) {
          Api.logout?.();
          window.StockQPro?.App?.toast?.('已登出', 'ok');
        } else {
          window.StockQPro?.App?.toast?.('尚未登錄', 'inf');
        }
      });
      $id('set-llm-save')?.addEventListener('click', () => saveLlmSettings());
      $id('set-llm-clear')?.addEventListener('click', () => clearLlmKey());
      $id('set-src-refresh')?.addEventListener('click', () => {
        Promise.all([loadDataSourceHealth(), loadOpsSop()])
          .then(() => window.StockQPro?.App?.toast?.('已更新運維與數據源狀態', 'ok'))
          .catch(() => window.StockQPro?.App?.toast?.('檢測失敗', 'er'));
      });
      $id('set-src-connectivity')?.addEventListener('click', () => {
        window.StockQPro?.App?.nav?.('connectivity', { syncHash: true });
      });
      $id('set-ops-refresh')?.addEventListener('click', () => {
        loadOpsSop()
          .then(() => window.StockQPro?.App?.toast?.('SOP 健檢已更新', 'ok'))
          .catch(() => window.StockQPro?.App?.toast?.('SOP 健檢失敗', 'er'));
      });
      $id('set-ops-copy')?.addEventListener('click', async () => {
        const data = window.StockQPro?.services?.opsMonitor?.getLast?.()
          || await loadOpsSop();
        if (!data) {
          window.StockQPro?.App?.toast?.('尚無運維報告', 'warn');
          return;
        }
        const text = JSON.stringify(data, null, 2);
        try {
          await navigator.clipboard.writeText(text);
          window.StockQPro?.App?.toast?.('已複製運維報告', 'ok');
        } catch {
          window.StockQPro?.App?.toast?.('複製失敗', 'er');
        }
      });
      $id('set-ops-download')?.addEventListener('click', async () => {
        const data = window.StockQPro?.services?.opsMonitor?.getLast?.()
          || await loadOpsSop();
        if (!data) {
          window.StockQPro?.App?.toast?.('尚無運維報告', 'warn');
          return;
        }
        const text = JSON.stringify(data, null, 2);
        const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const blob = new Blob([text], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `stock-quant-ops-sop-${ts}.json`;
        a.click();
        URL.revokeObjectURL(url);
        window.StockQPro?.App?.toast?.('已下載運維報告', 'ok');
      });
      bindSchemePreview();
    }
    if ($id('set-topbar-edit') && !$id('set-topbar-edit').dataset.bound) {
      $id('set-topbar-edit').dataset.bound = '1';
      $id('set-topbar-edit').addEventListener('click', () => {
        openTopbarEditor().catch(() => window.StockQPro?.App?.toast?.('頂欄編輯器打開失敗', 'er'));
      });
    }
    load().catch(() => window.StockQPro?.App?.toast?.('載入設定失敗', 'er'));
    loadBillingSummary().catch(() => {});
    window.addEventListener('stockq:auth-changed', () => loadBillingSummary().catch(() => {}));
  }

  function onShow() {
    startHealthPolling();
    loadDataSourceHealth().catch(() => {});
    loadOpsSop().catch(() => {});
    loadBillingSummary().catch(() => {});
    try {
      if (sessionStorage.getItem('stockq:scroll-ops') === '1') {
        sessionStorage.removeItem('stockq:scroll-ops');
        requestAnimationFrame(() => {
          window.StockQPro?.services?.opsMonitor?.scrollToOpsPanel?.();
        });
      }
    } catch (_) {}
  }

  function onUnload() {
    stopHealthPolling();
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.settings = {
    init,
    load,
    save,
    loadLlmSettings,
    loadDataSourceHealth,
    onShow,
    onUnload,
  };
})();
