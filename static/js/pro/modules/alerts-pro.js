/* global Api, Utils */

(() => {
  const $id = (id) => document.getElementById(id);
  const PAGE_SIZE = 20;
  let bound = false;
  let logOffset = 0;
  let histOffset = 0;

  function esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toast(msg, type = 'inf') {
    window.StockQPro?.App?.toast?.(msg, type);
  }

  function renderRules(rules) {
    const tb = $id('al-tb');
    if (!tb) return;
    const items = Object.entries(rules || {}).map(([code, r]) => ({ code, ...(r || {}) }));
    if (!items.length) {
      tb.innerHTML = '<tr><td colspan="7" class="al-empty">尚無預警規則</td></tr>';
      return;
    }
    tb.innerHTML = items.map((it) => `
      <tr>
        <td class="ac">${esc(it.code)}</td>
        <td>${esc(it.name || it.code)}</td>
        <td>${it.change_pct != null ? `${esc(it.change_pct)}%` : '--'}</td>
        <td>${it.price_above != null ? esc(it.price_above) : '--'}</td>
        <td>${it.price_below != null ? esc(it.price_below) : '--'}</td>
        <td>${[it.volume_mult ? '量×'+it.volume_mult : '', it.rsi_above ? 'RSI>'+it.rsi_above : '', it.macd_cross ? 'MACD' : ''].filter(Boolean).join(' ') || '--'}</td>
        <td><button class="btn btn-s" type="button" data-edit="${esc(it.code)}">編輯</button>
            <button class="btn btn-s btn-rd" type="button" data-del="${esc(it.code)}">刪除</button></td>
      </tr>
    `).join('');

    tb.querySelectorAll('[data-edit]').forEach((b) => {
      b.addEventListener('click', async () => {
        const code = b.getAttribute('data-edit');
        const d = await Api.getAlertRules().catch(() => null);
        const rules = d?.rules || d || {};
        fillForm(code, rules[code] || {});
        const form = $id('al-rule-form');
        if (form) form.hidden = false;
      });
    });
    tb.querySelectorAll('[data-del]').forEach((b) => {
      b.addEventListener('click', async () => {
        const code = b.getAttribute('data-del');
        const ok = typeof Utils !== 'undefined' && Utils.confirm
          ? await Utils.confirm(`刪除 ${code} 預警規則？`, { variant: 'danger' })
          : window.confirm(`刪除 ${code} 預警規則？`);
        if (!ok) return;
        const d = await Api.deleteAlertRule(code).catch((e) => ({ error: e?.message || e }));
        if (d?.success) toast('已刪除', 'ok');
        else toast(d?.error || d?.message || '刪除失敗（可能需要登入）', 'er');
        await loadRules();
      });
    });
  }

  async function loadRules() {
    const d = await Api.getAlertRules().catch(() => null);
    renderRules(d?.rules || d || {});
  }

  function renderChannels(channels) {
    const el = $id('al-channels');
    if (!el) return;
    const list = Array.isArray(channels) ? channels : [];
    if (!list.length) {
      el.innerHTML = '<div class="al-empty">無法載入通知渠道</div>';
      return;
    }
    el.innerHTML = list.map((ch) => {
      const on = ch.enabled ? '<span class="badge b-gn">啟用</span>' : '<span class="badge">關閉</span>';
      const cfg = ch.configured ? '<span class="badge b-bl">已配置</span>' : '<span class="badge">未配置</span>';
      return `<div class="al-channel-item"><span class="al-channel-name">${esc(ch.name)}</span>${on}${cfg}</div>`;
    }).join('');
  }

  async function loadChannels() {
    const d = await Api.getNotifyChannels().catch(() => null);
    renderChannels(d?.channels || []);
  }

  function renderLogs(d) {
    const el = $id('al-log-list');
    const meta = $id('al-log-meta');
    if (!el) return;
    const alerts = d?.alerts || [];
    const total = Number(d?.total || 0);
    const offset = Number(d?.offset || 0);
    if (meta) meta.textContent = total ? `${offset + 1}–${offset + alerts.length} / ${total}` : '0';
    if (!alerts.length) {
      el.innerHTML = '<div class="state-empty"><span class="state-icon">🔔</span><span class="state-text">暫無預警記錄</span></div>';
      return;
    }
    el.innerHTML = alerts.map((a) => `
      <div class="al-log-row">
        <div class="al-log-msg">${esc(a.message || a.rule_type || '-')}</div>
        <div class="al-log-meta">${esc(a.code || '')} · ${esc(a.triggered_at || '')}</div>
      </div>
    `).join('');
  }

  async function loadLogs() {
    const d = await Api.getAlerts(PAGE_SIZE, null, logOffset).catch(() => null);
    renderLogs(d || {});
    const total = Number(d?.total || 0);
    const prev = $id('al-log-prev');
    const next = $id('al-log-next');
    if (prev) prev.disabled = logOffset <= 0;
    if (next) next.disabled = !d?.has_more && (logOffset + PAGE_SIZE) >= total;
  }

  function renderHistory(d) {
    const el = $id('al-hist-list');
    const meta = $id('al-hist-meta');
    if (!el) return;
    const rows = d?.history || [];
    const total = Number(d?.total || 0);
    const offset = Number(d?.offset || 0);
    if (meta) meta.textContent = total ? `${offset + 1}–${offset + rows.length} / ${total}` : '0';
    if (!rows.length) {
      el.innerHTML = '<div class="state-empty"><span class="state-icon">📨</span><span class="state-text">尚無發送記錄</span></div>';
      return;
    }
    el.innerHTML = rows.map((r) => {
      const ok = r.status === 'ok';
      const badge = ok ? '<span class="badge b-gn">成功</span>' : '<span class="badge b-rd">失敗</span>';
      const extra = r.error ? `<div class="al-log-meta">${esc(r.error)}</div>` : '';
      return `
        <div class="al-log-row">
          <div class="al-log-msg">${badge} ${esc(r.channel || '')} · ${esc((r.message || '').slice(0, 120))}</div>
          <div class="al-log-meta">${esc(r.created_at || '')} · 嘗試 ${esc(r.attempts || 1)}</div>
          ${extra}
        </div>`;
    }).join('');
  }

  async function loadHistory() {
    const d = await Api.getNotifyHistory(PAGE_SIZE, histOffset).catch(() => null);
    renderHistory(d || {});
    const total = Number(d?.total || 0);
    const prev = $id('al-hist-prev');
    const next = $id('al-hist-next');
    if (prev) prev.disabled = histOffset <= 0;
    if (next) next.disabled = (histOffset + PAGE_SIZE) >= total;
  }

  async function testChannels() {
    const btn = $id('al-test-notify');
    if (btn) btn.disabled = true;
    try {
      const d = await Api.testNotify().catch((e) => ({ error: e?.message || e }));
      if (d?.success) toast('已送出測試通知', 'ok');
      else toast(d?.error || d?.message || '測試失敗', 'er');
      await loadHistory();
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function fillForm(code, rule) {
    const set = (id, v) => { const el = $id(id); if (el) el.value = v == null || v === '' ? '' : String(v); };
    set('al-f-code', code || '');
    set('al-f-name', rule.name || '');
    set('al-f-above', rule.price_above);
    set('al-f-below', rule.price_below);
    set('al-f-pct', rule.change_pct);
    set('al-f-vol', rule.volume_mult);
    set('al-f-rsi-hi', rule.rsi_above);
    set('al-f-rsi-lo', rule.rsi_below);
    const macd = $id('al-f-macd');
    if (macd) macd.checked = !!rule.macd_cross;
    const codeEl = $id('al-f-code');
    if (codeEl) codeEl.readOnly = !!code;
  }

  async function saveRule() {
    const code = ($id('al-f-code')?.value || '').trim();
    if (!code) return toast('請輸入代碼', 'er');
    const num = (id) => {
      const v = $id(id)?.value;
      if (v === '' || v == null) return null;
      const n = parseFloat(v);
      return Number.isFinite(n) ? n : null;
    };
    const body = {};
    body[code] = {
      name: ($id('al-f-name')?.value || '').trim() || code,
      price_above: num('al-f-above'),
      price_below: num('al-f-below'),
      change_pct: num('al-f-pct'),
      volume_mult: num('al-f-vol'),
      rsi_above: num('al-f-rsi-hi'),
      rsi_below: num('al-f-rsi-lo'),
      macd_cross: !!$id('al-f-macd')?.checked,
    };
    const d = await Api.updateAlertRules(body).catch((e) => ({ error: e?.message || e }));
    if (d?.success || d?.rules) {
      toast('規則已保存', 'ok');
      const form = $id('al-rule-form');
      if (form) form.hidden = true;
      await loadRules();
    } else toast(d?.error || d?.message || '保存失敗', 'er');
  }

  async function fillFromPrice() {
    const code = ($id('al-f-code')?.value || '').trim();
    if (!code) return toast('請先填代碼', 'er');
    const d = await Api.suggestAlertRule(code, { above_pct: 3, below_pct: 3, change_pct: 5 }).catch(() => null);
    if (!d?.rule) return toast('無法取得現價', 'er');
    fillForm(code, { ...d.rule, macd_cross: $id('al-f-macd')?.checked });
    toast(`已依現價 ${d.price} 填充`, 'ok');
  }

  function bind() {
    if (bound) return;
    bound = true;
    $id('al-add-rule')?.addEventListener('click', () => {
      fillForm('', {});
      const codeEl = $id('al-f-code');
      if (codeEl) codeEl.readOnly = false;
      const form = $id('al-rule-form');
      if (form) form.hidden = false;
    });
    $id('al-save-rule')?.addEventListener('click', () => saveRule());
    $id('al-fill-price')?.addEventListener('click', () => fillFromPrice());
    $id('al-cancel-rule')?.addEventListener('click', () => {
      const form = $id('al-rule-form');
      if (form) form.hidden = true;
    });
    $id('al-reload')?.addEventListener('click', () => loadAll());
    $id('al-test-notify')?.addEventListener('click', () => testChannels());
    $id('al-log-prev')?.addEventListener('click', () => {
      logOffset = Math.max(0, logOffset - PAGE_SIZE);
      loadLogs();
    });
    $id('al-log-next')?.addEventListener('click', () => {
      logOffset += PAGE_SIZE;
      loadLogs();
    });
    $id('al-hist-prev')?.addEventListener('click', () => {
      histOffset = Math.max(0, histOffset - PAGE_SIZE);
      loadHistory();
    });
    $id('al-hist-next')?.addEventListener('click', () => {
      histOffset += PAGE_SIZE;
      loadHistory();
    });
  }

  async function loadAll() {
    await Promise.all([loadRules(), loadChannels(), loadLogs(), loadHistory()]);
  }

  function init() {
    bind();
    loadAll().catch(() => toast('載入預警失敗', 'er'));
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.alerts = { init, onShow: init };
})();
