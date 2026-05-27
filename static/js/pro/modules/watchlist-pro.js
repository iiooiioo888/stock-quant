/* global Api, echarts */

(() => {
  const $id = (id) => document.getElementById(id);
  let chart = null;
  let selectedCode = null;
  let rtTimer = null;
  let rtLoading = false;

  function normalizeCode(raw) {
    const c = String(raw || '').trim();
    if (/^\d{1,6}$/.test(c)) return c.padStart(6, '0');
    return c;
  }

  function pctClass(pct) {
    const p = Number(pct);
    if (!Number.isFinite(p)) return '';
    return p >= 0 ? 'up' : 'down';
  }

  function fmtPct(pct) {
    const p = Number(pct);
    if (!Number.isFinite(p)) return '--';
    return `${p >= 0 ? '+' : ''}${p.toFixed(2)}%`;
  }

  function fmtPrice(price) {
    const p = Number(price);
    if (!Number.isFinite(p)) return '--';
    return p.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function initChart() {
    const el = $id('wl-ch');
    if (!el) return null;
    if (chart) return chart;
    chart = echarts.init(el);
    return chart;
  }

  function renderTable(items) {
    const tb = $id('wl-tb');
    if (!tb) return;
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--t3)">尚無自選股，在上方輸入 6 位代碼後點「添加」</td></tr>';
      return;
    }

    tb.innerHTML = rows.map((it) => {
      const cls = pctClass(it.change_pct);
      const sel = it.code === selectedCode ? ' wl-row--sel' : '';
      return `
      <tr class="wl-row${sel}" data-code="${it.code}">
        <td class="ac">${it.code}</td>
        <td>${it.name || it.code}</td>
        <td class="r" data-rt-field="price">${fmtPrice(it.price)}</td>
        <td class="tbl ${cls === 'up' ? 'pos' : cls === 'down' ? 'neg' : ''}" data-rt-field="change_pct">${fmtPct(it.change_pct)}</td>
        <td>${it.price_above != null ? it.price_above : '--'}</td>
        <td>${it.price_below != null ? it.price_below : '--'}</td>
        <td class="wl-actions">
          <button class="btn btn-s btn-bl" type="button" data-detail="${it.code}" title="詳情">詳情</button>
          <button class="btn btn-s btn-gn" type="button" data-bt="${it.code}" title="回測">回測</button>
          <button class="btn btn-s btn-rd" type="button" data-rm="${it.code}" title="移除">移除</button>
        </td>
      </tr>`;
    }).join('');

    tb.querySelectorAll('.wl-row').forEach((tr) => {
      tr.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        const code = tr.getAttribute('data-code');
        if (code) selectRow(code);
      });
    });

    tb.querySelectorAll('[data-bt]').forEach((b) => {
      b.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const c = b.getAttribute('data-bt');
        window.StockQPro?.App?.nav?.('backtest', { syncHash: true });
        if (window.StockQPro?.backtestSymbol?.setSymbol) {
          window.StockQPro.backtestSymbol.setSymbol(c);
        } else {
          const inp = $id('bt-code');
          if (inp) inp.value = c;
        }
      });
    });

    tb.querySelectorAll('[data-detail]').forEach((b) => {
      b.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const c = b.getAttribute('data-detail');
        if (c && window.StockQPro?.openAsset) window.StockQPro.openAsset(c);
      });
    });

    tb.querySelectorAll('[data-rm]').forEach((b) => {
      b.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const c = b.getAttribute('data-rm');
        if (!c) return;
        const d = await Api.removeFromWatchlist(c).catch((e) => ({ detail: e?.message }));
        if (d?.success) {
          window.StockQPro?.App?.toast?.(d.message || '已移除', 'ok');
          if (selectedCode === c) selectedCode = null;
          await load();
        } else {
          window.StockQPro?.App?.toast?.(d?.detail || d?.error || '移除失敗', 'er');
        }
      });
    });
  }

  function pollMs() {
    const sec = Number(window.StockQPro?.Prefs?.get?.('marketPollSec'));
    if (!Number.isFinite(sec) || sec <= 0) return 0;
    // watchlist 報價更新不要太頻繁；最小 10 秒
    return Math.max(10, sec) * 1000;
  }

  function stopRealtime() {
    if (rtTimer) clearInterval(rtTimer);
    rtTimer = null;
  }

  function applyRealtimeMap(rtMap) {
    if (!rtMap || typeof rtMap !== 'object') return;
    const tb = $id('wl-tb');
    if (!tb) return;
    tb.querySelectorAll('tr.wl-row').forEach((tr) => {
      const code = tr.getAttribute('data-code');
      if (!code) return;
      const rt = rtMap[code];
      if (!rt) return;

      const priceEl = tr.querySelector('[data-rt-field="price"]');
      const chgEl = tr.querySelector('[data-rt-field="change_pct"]');

      if (priceEl && rt.price != null) priceEl.textContent = fmtPrice(rt.price);
      if (chgEl && rt.change_pct != null) {
        const cls = pctClass(rt.change_pct);
        chgEl.textContent = fmtPct(rt.change_pct);
        chgEl.classList.toggle('pos', cls === 'up');
        chgEl.classList.toggle('neg', cls === 'down');
      }
    });
  }

  async function refreshRealtimeOnce() {
    if (rtLoading) return;
    const tb = $id('wl-tb');
    if (!tb) return;

    const codes = Array.from(tb.querySelectorAll('tr.wl-row'))
      .map((tr) => tr.getAttribute('data-code'))
      .filter(Boolean);
    if (!codes.length) return;

    rtLoading = true;
    try {
      const d = await Api.getRealtime(codes.join(',')).catch(() => null);
      if (Array.isArray(d?.quotes)) {
        const map = {};
        d.quotes.forEach((q) => {
          const c = String(q?.code || q?.symbol || q?.ts_code || '').trim();
          if (!c) return;
          map[c] = {
            price: q.price ?? q.last ?? q.close ?? q.realtime_price,
            change_pct: q.change_pct ?? q.pct_chg ?? q.realtime_change_pct,
          };
        });
        applyRealtimeMap(map);
      } else {
        const rtMap = d?.realtime || d?.data || d;
        applyRealtimeMap(rtMap);
      }
    } finally {
      rtLoading = false;
    }
  }

  function startRealtime() {
    stopRealtime();
    const ms = pollMs();
    if (ms <= 0) return;
    // 先跑一次，避免要等一個 interval 才看到更新
    refreshRealtimeOnce().catch(() => {});
    rtTimer = setInterval(() => refreshRealtimeOnce().catch(() => {}), ms);
  }

  async function selectRow(code) {
    selectedCode = code;
    const rows = Array.from(document.querySelectorAll('.wl-row'));
    rows.forEach((tr) => {
      tr.classList.toggle('wl-row--sel', tr.getAttribute('data-code') === code);
    });
    await drawMiniKline(code);
  }

  async function drawMiniKline(code) {
    const ch = initChart();
    if (!ch) return;
    const d = await Api.getKline(code, null, null, 120).catch(() => null);
    const rows = d?.kline || d?.data || [];
    const xs = rows.map((x) => x.date || x.time || '');
    const ys = rows.map((x) => Number(x.close ?? x.c ?? 0));
    ch.setOption({
      grid: { top: 14, right: 12, bottom: 24, left: 50 },
      tooltip: { trigger: 'axis', backgroundColor: '#252842', borderColor: '#2d3158', textStyle: { color: '#eeeef2', fontFamily: 'JetBrains Mono', fontSize: 10 } },
      xAxis: { type: 'category', data: xs, axisLine: { lineStyle: { color: '#1e2138' } }, axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 8 }, axisTick: { show: false } },
      yAxis: { type: 'value', scale: true, axisLine: { show: false }, splitLine: { lineStyle: { color: '#1d2033' } }, axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 9 } },
      series: [{ type: 'line', data: ys, smooth: true, showSymbol: false, lineStyle: { color: '#e8b830', width: 1.6 }, areaStyle: { color: 'rgba(232,184,48,.06)' } }],
    }, true);
  }

  function itemsFromAlertRules(rules) {
    if (!rules || typeof rules !== 'object') return [];
    return Object.entries(rules).map(([code, rule]) => ({
      code,
      name: rule?.name || code,
      price: null,
      change_pct: null,
      price_above: rule?.price_above,
      price_below: rule?.price_below,
    }));
  }

  async function load() {
    let data = await Api.getWatchlist().catch(() => null);
    if (!data?.success) {
      const legacy = await Api.getAlertRules().catch(() => null);
      if (legacy?.rules) {
        data = { success: true, items: itemsFromAlertRules(legacy.rules) };
      }
    }
    if (!data?.success) {
      window.StockQPro?.App?.toast?.('載入自選失敗（請重啟後端以載入新版 API）', 'er');
      renderTable([]);
      return;
    }
    const items = data.items || [];
    renderTable(items);
    const cnt = $id('wl-count');
    if (cnt) cnt.textContent = `${items.length} 只`;
    startRealtime();
    if (!selectedCode && items.length) {
      await selectRow(items[0].code);
    } else if (selectedCode && items.some((x) => x.code === selectedCode)) {
      await selectRow(selectedCode);
    } else if (items.length) {
      await selectRow(items[0].code);
    }
  }

  async function add() {
    const input = $id('wl-code-input');
    const nameInput = $id('wl-name-input');
    const code = normalizeCode(input?.value);
    if (!code || !/^\d{6}$/.test(code)) {
      window.StockQPro?.App?.toast?.('請輸入 6 位 A 股代碼', 'er');
      input?.focus();
      return;
    }
    const name = String(nameInput?.value || '').trim();
    const autoRule = !!$id('wl-auto-rule')?.checked;
    const d = await Api.addToWatchlist(code, name, { auto_rule: autoRule }).catch((e) => null);
    if (!d) {
      window.StockQPro?.App?.toast?.('添加失敗：未登錄或網絡錯誤', 'er');
      return;
    }
    if (d.success) {
      window.StockQPro?.App?.toast?.(d.message || '已添加', 'ok');
      if (input) input.value = '';
      if (nameInput) nameInput.value = '';
      if (Array.isArray(d.items) && d.items.length) renderTable(d.items);
      await load();
      await selectRow(code);
    } else {
      window.StockQPro?.App?.toast?.(d.detail || d.message || '添加失敗', 'er');
    }
  }

  function bindOnce() {
    const root = $id('pg-watchlist');
    if (!root || root.dataset.bound) return;
    root.dataset.bound = '1';

    $id('wl-add')?.addEventListener('click', () => add());
    $id('wl-reload')?.addEventListener('click', () => load());
    $id('wl-code-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') add();
    });
  }

  function init() {
    bindOnce();
    load().catch(() => window.StockQPro?.App?.toast?.('載入自選失敗', 'er'));
  }

  window.addEventListener('resize', () => chart?.resize());
  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.watchlist = {
    init,
    load,
    unload: () => stopRealtime(),
  };
})();
