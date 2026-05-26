/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);

  function buildFilters(preset) {
    switch (preset) {
      case 'ma_bullish': return { ma_bullish: true };
      case 'above_ma20': return { above_ma: { period: 20 } };
      case 'near_52w_high': return { near_52w_high: { pct: 5 } };
      case 'volume_surge': return { volume_surge: { days: 5, ratio: 2.0 } };
      case 'price_change_5d': return { price_change_ndays: { days: 5, min_pct: 5 } };
      default: return {};
    }
  }

  function renderResults(items) {
    const cnt = $id('scan-cnt');
    const res = $id('scan-res');
    if (cnt) cnt.textContent = String(items?.length ?? 0);
    if (!res) return;
    if (!items?.length) {
      res.innerHTML = '<div class="pro-empty"><span class="pro-empty-icon">🔍</span>無符合條件的股票<br><span style="font-size:.66rem;color:var(--t4)">可調整市場或預設條件後重試</span></div>';
      return;
    }
    res.innerHTML = items.slice(0, 60).map((it) => {
      const code = it.code || '';
      const name = it.name || code;
      const passed = (it.filters_passed || []).slice(0, 2).join(' · ');
      const info = it.data || {};
      const price = info.current_price ?? info.close ?? '--';
      return `
        <div class="scan-row">
          <span class="scan-row-code">${code}</span>
          <span class="scan-row-name">${name}</span>
          <span class="scan-row-price">${price}</span>
          <span class="badge b-bl">${passed || 'pass'}</span>
          <button class="btn s" type="button" data-bt="${code}">回測</button>
          <button class="btn s btn-gn" type="button" data-add="${code}" data-name="${name}">+ 自選</button>
        </div>
      `;
    }).join('');

    res.querySelectorAll('[data-bt]').forEach((b) => {
      b.addEventListener('click', () => {
        const code = b.getAttribute('data-bt');
        window.StockQPro?.App?.nav?.('backtest', { syncHash: true });
        if (window.StockQPro?.backtestSymbol?.setSymbol) {
          window.StockQPro.backtestSymbol.setSymbol(code);
        }
      });
    });
    res.querySelectorAll('[data-add]').forEach((b) => {
      b.addEventListener('click', async () => {
        const code = b.getAttribute('data-add');
        const name = b.getAttribute('data-name') || '';
        const d = await Api.addToWatchlist(code, name, { auto_rule: true }).catch((e) => ({ error: e?.message || e }));
        if (d?.success) window.StockQPro?.App?.toast?.(d.message || '已加入', 'ok');
        else window.StockQPro?.App?.toast?.(d?.error || '加入失敗', 'er');
      });
    });
  }

  let lastScanItems = [];

  function exportScanCsv() {
    if (!lastScanItems.length) {
      return window.StockQPro?.App?.toast?.('尚無掃描結果', 'inf');
    }
    const header = ['code', 'name', 'filters_passed', 'current_price'];
    const lines = [header.join(',')];
    lastScanItems.forEach((it) => {
      const info = it.data || {};
      const row = [
        it.code || '',
        it.name || '',
        (it.filters_passed || []).join('|'),
        info.current_price ?? info.close ?? '',
      ];
      lines.push(row.map((v) => {
        const s = String(v);
        return s.includes(',') ? `"${s.replace(/"/g, '""')}"` : s;
      }).join(','));
    });
    Api.downloadBlob(lines.join('\n'), `screener_${Date.now()}.csv`, 'text/csv;charset=utf-8');
    window.StockQPro?.App?.toast?.('已匯出掃描結果', 'ok');
  }

  async function run() {
    const btn = $id('scan-run');
    if (btn) btn.disabled = true;
    const res = $id('scan-res');
    if (res) res.innerHTML = '<div class="pro-empty"><span class="pro-empty-icon">⏳</span>掃描中…</div>';

    try {
      const market = $id('scan-market')?.value || 'all';
      const preset = $id('scan-preset')?.value || 'ma_bullish';
      const list = await Api.getStockList(market);
      const stocks = list?.stocks || [];
      const codes = stocks.slice(0, 1200).map((s) => s.code); // 避免一次掃全市場太慢
      const filters = buildFilters(preset);
      const d = await Api.screenStocks({ filters, codes });
      lastScanItems = d?.results || [];
      renderResults(lastScanItems);
    } catch (e) {
      window.StockQPro?.App?.toast?.(`掃描失敗：${e?.message || e}`, 'er');
      lastScanItems = [];
      renderResults([]);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function init() {
    $id('scan-run')?.addEventListener('click', run);
    $id('scan-export')?.addEventListener('click', exportScanCsv);
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.scanner = { init };
})();

