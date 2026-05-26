/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);
  const MAX_COMPARE = 3;
  let allRows = [];
  const selected = new Set();

  function fmtTime(t) {
    if (!t) return '--';
    const s = String(t);
    return s.length > 16 ? s.slice(0, 16) : s;
  }

  function updateSelectionUi() {
    const n = selected.size;
    const cmpBtn = $id('bh-compare-btn');
    const csvBtn = $id('bh-export-csv-btn');
    const hint = $id('bh-sel-hint');
    if (cmpBtn) cmpBtn.disabled = n < 2;
    if (csvBtn) csvBtn.disabled = n < 1;
    if (hint) hint.textContent = n ? `已選 ${n} / ${MAX_COMPARE}` : `最多選 ${MAX_COMPARE} 筆對比`;
  }

  function toggleSelect(id, checked) {
    const n = Number(id);
    if (!Number.isFinite(n)) return;
    if (checked) {
      if (selected.size >= MAX_COMPARE) {
        window.StockQPro?.App?.toast?.(`最多選擇 ${MAX_COMPARE} 筆`, 'inf');
        const cb = document.querySelector(`[data-bh-id="${n}"]`);
        if (cb) cb.checked = false;
        return;
      }
      selected.add(n);
    } else {
      selected.delete(n);
    }
    updateSelectionUi();
  }

  function loadToBacktest(code, strategy) {
    window.StockQPro?.App?.nav?.('backtest', { syncHash: true });
    if (window.StockQPro?.backtestSymbol?.setSymbol) {
      window.StockQPro.backtestSymbol.setSymbol(code);
    } else {
      const inp = $id('bt-code');
      if (inp) inp.value = code;
    }
    if (strategy) {
      const stratEl = $id('bt-strategy') || document.getElementById('btStrategy');
      if (stratEl) stratEl.value = strategy;
      const catalog = window.StockQPro?.catalog;
      const hit = catalog?.strats?.find((s) => s.backend_key === strategy || s.id === strategy);
      if (hit?.id) window.StockQPro?.showStratDetail?.(hit.id);
    }
  }

  function renderTable(results) {
    const tb = $id('bh-tb');
    if (!tb) return;
    allRows = results || [];
    if (!allRows.length) {
      tb.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--t3);padding:32px">尚無回測記錄</td></tr>';
      return;
    }
    tb.innerHTML = allRows.map((r) => {
      const id = r.id;
      const t = fmtTime(r.created_at || r.time || r.created);
      const code = r.code || '--';
      const strat = r.strategy_name || r.strategy || '--';
      const stratKey = r.strategy || '';
      const ret = Number(r.total_return_pct || 0);
      const sharpe = Number(r.sharpe_ratio || 0);
      const dd = Number(r.max_drawdown_pct || 0);
      const checked = selected.has(Number(id)) ? 'checked' : '';
      return `
        <tr data-row-id="${id}">
          <td><input type="checkbox" class="bh-chk" data-bh-id="${id}" ${checked} aria-label="選取記錄 ${id}" /></td>
          <td style="color:var(--t3);font-size:.68rem">${t}</td>
          <td class="ac">${code}</td>
          <td title="${stratKey}">${strat}</td>
          <td class="${ret >= 0 ? 'pos' : 'neg'}">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</td>
          <td>${sharpe.toFixed(2)}</td>
          <td class="neg">-${Math.abs(dd).toFixed(2)}%</td>
          <td class="bh-actions">
            <button class="btn btn-s btn-gn" type="button" data-load="${code}" data-strat="${stratKey}">回測</button>
            ${id ? `<button class="btn btn-s" type="button" data-dl="${id}">CSV</button>` : ''}
          </td>
        </tr>
      `;
    }).join('');

    tb.querySelectorAll('.bh-chk').forEach((cb) => {
      cb.addEventListener('change', () => toggleSelect(cb.getAttribute('data-bh-id'), cb.checked));
    });
    tb.querySelectorAll('[data-load]').forEach((b) => {
      b.addEventListener('click', () => {
        loadToBacktest(b.getAttribute('data-load'), b.getAttribute('data-strat') || '');
      });
    });
    tb.querySelectorAll('[data-dl]').forEach((b) => {
      b.addEventListener('click', () => exportOne(Number(b.getAttribute('data-dl'))));
    });
    updateSelectionUi();
  }

  function renderComparePanel(results) {
    const el = $id('bh-compare-panel');
    if (!el) return;
    if (!results?.length) {
      el.hidden = true;
      el.innerHTML = '';
      return;
    }
    el.hidden = false;
    const metrics = [
      ['total_return_pct', '總收益 %', (v) => `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`],
      ['sharpe_ratio', '夏普', (v) => Number(v).toFixed(2)],
      ['max_drawdown_pct', '最大回撤 %', (v) => `-${Math.abs(Number(v)).toFixed(2)}%`],
      ['win_rate_pct', '勝率 %', (v) => `${Number(v).toFixed(1)}%`],
      ['total_trades', '交易次數', (v) => String(v ?? '--')],
    ];
    const head = results.map((r) => `<th>${r.code || ''}<br><span style="font-weight:400;color:var(--t3)">${r.strategy_name || r.strategy || ''}</span></th>`).join('');
    const body = metrics.map(([key, label, fmt]) => {
      const cells = results.map((r) => {
        const v = r[key];
        const cls = key === 'total_return_pct' && Number(v) >= 0 ? 'pos' : (key === 'total_return_pct' ? 'neg' : '');
        return `<td class="${cls}">${fmt(v)}</td>`;
      }).join('');
      return `<tr><th style="text-align:left;color:var(--t3)">${label}</th>${cells}</tr>`;
    }).join('');
    el.innerHTML = `
      <div class="bh-compare-hd">並排對比（${results.length} 筆）</div>
      <div class="c" style="overflow-x:auto;margin-top:8px">
        <table class="tbl tbl-compact bh-compare-tbl">
          <thead><tr><th></th>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    `;
  }

  async function exportOne(id) {
    if (!id) return;
    try {
      await Api.downloadAuthenticated(
        `/api/export/backtest/${id}?format=csv`,
        `backtest_${id}.csv`,
      );
      window.StockQPro?.App?.toast?.('已下載 CSV', 'ok');
    } catch (e) {
      window.StockQPro?.App?.toast?.(`匯出失敗：${e?.message || e}`, 'er');
    }
  }

  function rowsToCsv(results) {
    const header = ['id', 'code', 'strategy', 'total_return_pct', 'sharpe_ratio', 'max_drawdown_pct', 'win_rate_pct', 'total_trades', 'created_at'];
    const lines = [header.join(',')];
    (results || []).forEach((r) => {
      lines.push(header.map((k) => {
        const v = r[k];
        const s = v == null ? '' : String(v);
        return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
      }).join(','));
    });
    return lines.join('\n');
  }

  async function exportSelectedCsv() {
    const ids = [...selected];
    if (!ids.length) return;
    try {
      const d = await Api.getBacktestCompare(ids);
      const rows = d?.results || [];
      if (!rows.length) throw new Error('無資料');
      Api.downloadBlob(rowsToCsv(rows), `backtest_compare_${Date.now()}.csv`, 'text/csv;charset=utf-8');
      window.StockQPro?.App?.toast?.('已匯出 CSV', 'ok');
    } catch (e) {
      window.StockQPro?.App?.toast?.(`匯出失敗：${e?.message || e}`, 'er');
    }
  }

  async function runCompare() {
    const ids = [...selected];
    if (ids.length < 2) {
      return window.StockQPro?.App?.toast?.('請至少勾選 2 筆記錄', 'inf');
    }
    try {
      const d = await Api.getBacktestCompare(ids);
      renderComparePanel(d?.results || []);
      window.StockQPro?.App?.toast?.('對比已更新', 'ok');
    } catch (e) {
      window.StockQPro?.App?.toast?.(`對比失敗：${e?.message || e}`, 'er');
    }
  }

  function clearSelection() {
    selected.clear();
    document.querySelectorAll('.bh-chk').forEach((cb) => { cb.checked = false; });
    renderComparePanel([]);
    updateSelectionUi();
  }

  async function load() {
    const code = String($id('bh-filter-code')?.value || '').trim();
    const strategy = String($id('bh-filter-strategy')?.value || '').trim();
    const limit = Number($id('bh-limit')?.value) || 50;
    const d = await Api.getBacktestHistory(code, strategy, limit).catch(() => null);
    renderTable(d?.results || []);
    const total = d?.total ?? (d?.results || []).length;
    const cnt = $id('bh-count');
    if (cnt) cnt.textContent = String(total);
  }

  function init() {
    $id('bh-reload')?.addEventListener('click', () => load().catch(() => window.StockQPro?.App?.toast?.('載入失敗', 'er')));
    $id('bh-compare-btn')?.addEventListener('click', () => runCompare());
    $id('bh-export-csv-btn')?.addEventListener('click', () => exportSelectedCsv());
    $id('bh-clear-sel')?.addEventListener('click', clearSelection);
    $id('bh-filter-code')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') load().catch(() => {});
    });
    $id('bh-filter-strategy')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') load().catch(() => {});
    });
    load().catch(() => window.StockQPro?.App?.toast?.('載入回測歷史失敗', 'er'));
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.backhistory = { init, load };
})();
