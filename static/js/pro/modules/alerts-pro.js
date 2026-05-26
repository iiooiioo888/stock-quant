/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);

  function render(rules) {
    const tb = $id('al-tb');
    if (!tb) return;
    const items = Object.entries(rules || {}).map(([code, r]) => ({ code, ...r }));
    tb.innerHTML = items.map((it) => `
      <tr>
        <td class="ac">${it.code}</td>
        <td>${it.name || it.code}</td>
        <td>${it.change_pct != null ? `${it.change_pct}%` : '--'}</td>
        <td>${it.price_above != null ? it.price_above : '--'}</td>
        <td>${it.price_below != null ? it.price_below : '--'}</td>
        <td><button class="btn btn-s btn-rd" type="button" data-del="${it.code}">刪除</button></td>
      </tr>
    `).join('');

    tb.querySelectorAll('[data-del]').forEach((b) => {
      b.addEventListener('click', async () => {
        const code = b.getAttribute('data-del');
        const ok = window.confirm(`刪除 ${code} 預警規則？`);
        if (!ok) return;
        const d = await Api.deleteAlertRule(code).catch((e) => ({ error: e?.message || e }));
        if (d?.success) window.StockQPro?.App?.toast?.('已刪除', 'ok');
        else window.StockQPro?.App?.toast?.(d?.error || d?.message || '刪除失敗（可能需要登入）', 'er');
        await load();
      });
    });
  }

  async function load() {
    const d = await Api.getAlertRules().catch(() => null);
    render(d?.rules || d || {});
  }

  function init() {
    $id('al-reload')?.addEventListener('click', () => load());
    load().catch(() => window.StockQPro?.App?.toast?.('載入預警失敗', 'er'));
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.alerts = { init };
})();

