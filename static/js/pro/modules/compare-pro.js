/* global Api, echarts */

(() => {
  const $id = (id) => document.getElementById(id);
  const LS_KEY = 'sq_cmp_stocks';
  const LS_CUSTOM_PRESETS = 'sq_cmp_custom_presets';
  const MAX_STOCKS = 8;
  const MAX_CUSTOM_PRESETS = 12;
  const pickData = () => window.StockQPro?.stockPickData;

  const STOCK_COLORS = ['#e8b830', '#60a5fa', '#34d399', '#f472b6', '#a78bfa', '#fb923c', '#22d3ee', '#94a3b8'];

  const METRIC_LABELS = {
    total_return_pct: '總收益率',
    sharpe_ratio: '夏普比率',
    sortino_ratio: '索提諾比率',
    calmar_ratio: '卡瑪比率',
    max_drawdown_pct: '最大回撤',
    win_rate_pct: '勝率',
    annual_return_pct: '年化收益',
    total_trades: '交易次數',
  };

  const METRIC_HIGHER_BETTER = new Set([
    'total_return_pct', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio',
    'win_rate_pct', 'annual_return_pct',
  ]);

  let strategyDisplayNames = {};

  let chart = null;
  let corrChart = null;
  let bound = false;
  let namesMap = {};
  let catalogAshare = [];
  let searchTimer = null;
  let pickMode = 'hot';

  const state = {
    mode: 'strategies',
    chips: [],
    strategyResults: null,
    strategyResultsByCode: {},
    strategySessionActive: false,
    strategyPollToken: 0,
    strategyEnqueueInFlight: new Set(),
    stockComparison: null,
    correlation: null,
    benchmark: null,
    excessReturn: null,
    indexOverlay: null,
    running: false,
  };

  function normalizeCode(raw) {
    const SU = window.StockQPro?.SymbolUtils;
    if (SU?.normalizeCompareCode) return SU.normalizeCompareCode(raw);
    const s = String(raw || '').trim();
    if (/^\d{1,6}$/.test(s)) return s.padStart(6, '0');
    return s.toUpperCase();
  }

  function isValidCompareSymbol(code) {
    const SU = window.StockQPro?.SymbolUtils;
    if (SU?.isValidCompareSymbol) return SU.isValidCompareSymbol(code);
    return /^\d{6}$/.test(code);
  }

  /** @deprecated 使用 isValidCompareSymbol */
  function isValidAshare(code) {
    return isValidCompareSymbol(code);
  }

  function resolveName(code) {
    const hit = state.chips.find((c) => c.code === code);
    if (hit?.name) return hit.name;
    return namesMap[code] || catalogAshare.find((x) => x.code === code)?.name || code;
  }

  function quoteUp() {
    return getComputedStyle(document.documentElement).getPropertyValue('--quote-up').trim() || '#f87171';
  }

  function quoteDown() {
    return getComputedStyle(document.documentElement).getPropertyValue('--quote-down').trim() || '#34d399';
  }

  function saveChips() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(state.chips));
      if (typeof LocalStore !== 'undefined') {
        LocalStore.set('compareChips', state.chips);
      }
    } catch (_) { /* ignore */ }
  }

  function loadChipsFromStorage() {
    try {
      let arr = null;
      if (typeof LocalStore !== 'undefined') {
        const fromStore = LocalStore.get('compareChips');
        if (Array.isArray(fromStore) && fromStore.length) arr = fromStore;
      }
      if (!arr) {
        const raw = localStorage.getItem(LS_KEY);
        if (raw) arr = JSON.parse(raw);
      }
      if (!arr) return;
      if (!Array.isArray(arr)) return;
      state.chips = arr
        .map((x) => ({ code: normalizeCode(x.code), name: x.name || '' }))
        .filter((x) => isValidCompareSymbol(x.code))
        .slice(0, MAX_STOCKS);
    } catch (_) { /* ignore */ }
  }

  function renderChips() {
    const el = $id('cmp-chips');
    if (!el) return;
    if (!state.chips.length) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML = state.chips.map((c, i) => `
      <span class="cmp-chip${i === 0 && state.mode === 'stocks' ? ' cmp-chip-bench' : ''}" data-idx="${i}" title="${i === 0 && state.mode === 'stocks' ? '基準檔（雙擊其他 chip 可設為基準）' : '雙擊設為基準'}">
        <span class="cmp-chip-code">${c.code}</span>
        <span class="cmp-chip-name" title="${(c.name || '').replace(/"/g, '&quot;')}">${c.name || c.code}</span>
        <button type="button" class="cmp-chip-x" data-rm="${c.code}" aria-label="移除 ${c.code}">×</button>
      </span>`).join('');
    el.querySelectorAll('[data-rm]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        removeChip(btn.getAttribute('data-rm'));
      });
    });
    el.querySelectorAll('.cmp-chip').forEach((chip) => {
      chip.addEventListener('dblclick', () => {
        const idx = Number(chip.getAttribute('data-idx'));
        if (!Number.isFinite(idx) || idx <= 0) return;
        const item = state.chips[idx];
        state.chips.splice(idx, 1);
        state.chips.unshift(item);
        renderChips();
        window.StockQPro?.App?.toast?.(`已將 ${item.code} 設為基準（首檔）`, 'ok');
        syncCompareHash();
      });
    });
    saveChips();
    syncCompareHash();
    if (state.mode === 'strategies') syncStrategyViewForPrimary();
  }

  function syncStrategyViewForPrimary() {
    const code = primaryCode();
    if (!code) {
      state.strategyResults = null;
      clearCharts();
      updateSummaryBadge();
      return;
    }
    const cached = state.strategyResultsByCode[code];
    if (cached?.length) {
      state.strategyResults = cached;
      renderStrategies();
    } else {
      state.strategyResults = null;
      clearCharts();
    }
    updateSummaryBadge();
  }

  function refreshTasksUi() {
    try {
      window.StockQPro?.Tasks?.refresh?.(true);
    } catch (_) { /* ignore */ }
    try {
      window.StockQPro?.pages?.tasks?.refreshSidebarBadge?.();
    } catch (_) { /* ignore */ }
  }

  async function enqueueStrategyCompare(code, opts = {}) {
    const c = normalizeCode(code);
    if (!isValidCompareSymbol(c)) return false;
    if (state.strategyEnqueueInFlight.has(c)) {
      if (!opts.silent) window.StockQPro?.App?.toast?.(`${c} 任務提交中…`, 'inf');
      return false;
    }
    state.strategyEnqueueInFlight.add(c);
    try {
      const d = await Api.runMultiBacktest(c);
      if (!d?.success) throw new Error(d?.error || d?.detail || '提交失敗');
      const taskId = d.task_id;
      if (taskId) {
        const shortId = String(taskId).slice(0, 8);
        const hint = d.is_duplicate
          ? (d.message || `相同多策略對比進行中（#${shortId}…）`)
          : `已加入任務中心（#${shortId}…）`;
        if (!opts.silent) window.StockQPro?.App?.toast?.(hint, d.is_duplicate ? 'inf' : 'ok');
        refreshTasksUi();
        pollStrategyTaskInBackground(c, taskId);
      } else {
        const resolved = await Api.resolveTaskResponse(d, { timeout: 600000 });
        applyStrategyResultsForCode(c, Api.extractResult(resolved));
        if (!opts.silent) window.StockQPro?.App?.toast?.(`已完成 ${c} 策略對比`, 'ok');
      }
      state.strategySessionActive = true;
      return true;
    } catch (e) {
      if (!opts.silent) window.StockQPro?.App?.toast?.(`加入任務失敗：${e?.message || e}`, 'er');
      return false;
    } finally {
      state.strategyEnqueueInFlight.delete(c);
    }
  }

  function applyStrategyResultsForCode(code, raw) {
    const rows = (Array.isArray(raw) ? raw : [])
      .map((x) => normalizeStrategyRow(x))
      .filter(Boolean);
    if (!rows.length) return false;
    state.strategyResultsByCode[code] = rows;
    if (primaryCode() === code) {
      state.strategyResults = rows;
      renderStrategies();
      updateSummaryBadge();
    }
    return true;
  }

  async function pollStrategyTaskInBackground(code, taskId) {
    const token = ++state.strategyPollToken;
    const hd = $id('cmp-metric-hd');
    if (primaryCode() === code && hd) {
      hd.textContent = `多策略回測執行中（${code}）…`;
    }
    try {
      const task = await Api.pollTask(taskId, {
        timeout: 600000,
        onProgress: (t) => {
          if (token !== state.strategyPollToken || primaryCode() !== code) return;
          const p = Number(t?.progress);
          if (hd && Number.isFinite(p) && p > 0) {
            hd.textContent = `多策略回測 ${code} · ${Math.round(p)}%`;
          }
        },
      });
      if (token !== state.strategyPollToken) return;
      if (!task || task.status !== 'completed') {
        throw new Error(task?.error || '任務未完成');
      }
      const ok = applyStrategyResultsForCode(code, task.result);
      if (primaryCode() === code) {
        if (ok) window.StockQPro?.App?.toast?.(`已完成 ${code} 的 ${task.result?.length || state.strategyResults?.length || 0} 個策略對比`, 'ok');
        else window.StockQPro?.App?.toast?.(`任務完成但無有效結果：${code}`, 'er');
        if (hd) hd.textContent = '';
      } else if (ok) {
        window.StockQPro?.App?.toast?.(`${code} 多策略對比已完成，點選該標的可查看`, 'ok');
      }
    } catch (e) {
      if (primaryCode() === code) {
        state.strategyResults = null;
        clearCharts();
        if (hd) hd.textContent = '';
        window.StockQPro?.App?.toast?.(`對比失敗（${code}）：${e?.message || e}`, 'er');
      }
    } finally {
      if (primaryCode() === code && hd && !state.strategyResults) {
        hd.textContent = '';
      }
      updateSummaryBadge();
    }
  }

  function addChip(code, name = '', opts = {}) {
    const c = normalizeCode(code);
    if (!isValidCompareSymbol(c)) {
      window.StockQPro?.App?.toast?.('請輸入有效代碼（A股/港股/美股等）', 'er');
      return false;
    }
    const n = name || resolveName(c) || c;
    const prevPrimary = state.chips[0]?.code;
    if (state.chips.some((x) => x.code === c)) {
      if (state.mode === 'strategies' && state.strategySessionActive && !opts.skipEnqueue) {
        enqueueStrategyCompare(c, { silent: opts.silent });
      } else if (!opts.silent) {
        window.StockQPro?.App?.toast?.(`${c} 已在列表中`, 'inf');
      }
      return false;
    }
    const max = state.mode === 'strategies' ? 1 : MAX_STOCKS;
    if (state.chips.length >= max) {
      if (state.mode === 'strategies') {
        state.chips = [{ code: c, name: n }];
      } else {
        window.StockQPro?.App?.toast?.(`最多選擇 ${MAX_STOCKS} 檔`, 'inf');
        return false;
      }
    } else {
      state.chips.push({ code: c, name: n });
    }
    renderChips();
    if (!opts.silent) {
      const switched = state.mode === 'strategies' && prevPrimary && prevPrimary !== c;
      window.StockQPro?.App?.toast?.(
        switched ? `已切換為 ${c} ${n}` : `已加入 ${c} ${n}`,
        'ok',
      );
    }
    if (state.mode === 'strategies' && state.strategySessionActive && c !== prevPrimary && !opts.skipEnqueue) {
      enqueueStrategyCompare(c, { silent: opts.silent });
    }
    return true;
  }

  function removeChip(code) {
    const c = normalizeCode(code);
    state.chips = state.chips.filter((x) => x.code !== c);
    renderChips();
  }

  function clearChips() {
    state.chips = [];
    state.strategyPollToken += 1;
    state.strategyResults = null;
    renderChips();
  }

  function primaryCode() {
    return state.chips[0]?.code || '';
  }

  function setMode(mode) {
    state.mode = mode === 'stocks' ? 'stocks' : 'strategies';
    document.querySelectorAll('[data-cmp-mode]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-cmp-mode') === state.mode);
    });
    const hint = $id('cmp-mode-hint');
    if (hint) {
      hint.textContent = state.mode === 'stocks'
        ? `選 2～${MAX_STOCKS} 檔（A股/港股/美股等），對比區間相對收益`
        : '選 1 檔股票對比全部策略；執行後再點其他股票會加入任務中心';
    }
    document.querySelectorAll('.cmp-ctl-strat').forEach((el) => {
      el.style.display = state.mode === 'strategies' ? '' : 'none';
    });
    document.querySelectorAll('.cmp-ctl-stock').forEach((el) => {
      el.style.display = state.mode === 'stocks' ? '' : 'none';
    });
    if (state.mode === 'stocks') renderPresets();
    if (state.mode === 'strategies' && state.chips.length > 1) {
      state.chips = [state.chips[0]];
      renderChips();
      window.StockQPro?.App?.toast?.('多策略模式僅保留第一檔標的', 'inf');
    }
    updateSummaryBadge();
    syncCompareHash();
    if (state.mode === 'strategies' && state.strategyResults) renderStrategies();
    else if (state.mode === 'stocks' && state.stockComparison) renderStocks();
    else clearCharts();
  }

  function updateSummaryBadge() {
    const el = $id('cmp-summary-badge');
    if (!el) return;
    const n = state.chips.length;
    if (state.mode === 'stocks') {
      el.textContent = n ? `${n} 檔股票` : '未選標的';
    } else {
      const code = primaryCode();
      el.textContent = code ? `${code} · 策略對比` : '未選標的';
    }
  }

  function initChart() {
    const el = $id('cmp-ch');
    if (!el) return null;
    if (chart) {
      chart.resize();
      return chart;
    }
    const reg = window.StockQPro?.ECharts;
    chart = reg?.get
      ? reg.get('compare', 'cmp-ch', el, { renderer: 'canvas' })
      : echarts.init(el, null, { renderer: 'canvas' });
    return chart;
  }

  function clearCharts() {
    const ch = chart || initChart();
    if (ch) ch.clear();
    if (corrChart) corrChart.clear();
    const hd = $id('cmp-metric-hd');
    if (hd) hd.textContent = '';
    const stats = $id('cmp-stats-row');
    if (stats) stats.innerHTML = '';
    const corr = $id('cmp-corr-panel');
    if (corr) corr.hidden = true;
    const heat = $id('cmp-corr-heat');
    if (heat) heat.innerHTML = '';
    const tb = $id('cmp-tb');
    const thead = $id('cmp-thead');
    if (tb) tb.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--t3);padding:28px">選擇標的後點擊「執行對比」</td></tr>';
    if (thead) thead.innerHTML = '';
  }

  function syncCompareHash() {
    try {
      if (window.StockQPro?.App?.current && window.StockQPro.App.current !== 'compare') return;
      const qs = new URLSearchParams();
      qs.set('mode', state.mode);
      if (state.chips.length) qs.set('codes', state.chips.map((c) => c.code).join(','));
      const days = $id('cmp-days')?.value;
      if (days && state.mode === 'stocks') qs.set('days', days);
      const idx = $id('cmp-index')?.value;
      if (idx && state.mode === 'stocks') qs.set('index', idx);
      const want = `#/compare?${qs.toString()}`;
      if (location.hash !== want) history.replaceState(null, '', want);
    } catch (_) { /* ignore */ }
  }

  function parseCompareFromHash() {
    const h = String(location.hash || '');
    if (!h.includes('compare')) return;
    const qIdx = h.indexOf('?');
    if (qIdx < 0) return;
    const qs = new URLSearchParams(h.slice(qIdx + 1));
    const mode = qs.get('mode');
    if (mode === 'stocks' || mode === 'strategies') state.mode = mode;
    const codes = qs.get('codes');
    if (codes) {
      const list = codes.split(/[,，\s]+/).map((x) => normalizeCode(x)).filter(isValidCompareSymbol);
      if (list.length) {
        state.chips = list.slice(0, MAX_STOCKS).map((code) => ({ code, name: resolveName(code) }));
      }
    }
    const days = qs.get('days');
    if (days && $id('cmp-days')) $id('cmp-days').value = days;
    const idx = qs.get('index');
    if (idx != null && $id('cmp-index')) $id('cmp-index').value = idx;
  }

  function loadCustomPresets() {
    try {
      if (typeof LocalStore !== 'undefined') {
        const fromStore = LocalStore.get('compareCustomPresets');
        if (Array.isArray(fromStore)) return fromStore.slice(0, MAX_CUSTOM_PRESETS);
      }
      const raw = localStorage.getItem(LS_CUSTOM_PRESETS);
      if (raw) {
        const arr = JSON.parse(raw);
        return Array.isArray(arr) ? arr.slice(0, MAX_CUSTOM_PRESETS) : [];
      }
    } catch (_) { /* ignore */ }
    return [];
  }

  function saveCustomPresets(list) {
    const trimmed = list.slice(0, MAX_CUSTOM_PRESETS);
    try {
      localStorage.setItem(LS_CUSTOM_PRESETS, JSON.stringify(trimmed));
      if (typeof LocalStore !== 'undefined') {
        LocalStore.set('compareCustomPresets', trimmed);
      }
    } catch (_) { /* ignore */ }
    return trimmed;
  }

  function saveCurrentAsPreset() {
    if (state.chips.length < 2) {
      return window.StockQPro?.App?.toast?.('至少 2 檔才能儲存組合', 'inf');
    }
    const name = String($id('cmp-preset-name')?.value || '').trim()
      || `組合 ${new Date().toLocaleDateString('zh-TW')}`;
    const presets = loadCustomPresets();
    const entry = {
      id: `custom_${Date.now()}`,
      label: name.slice(0, 24),
      codes: state.chips.map((c) => c.code),
      savedAt: Date.now(),
    };
    const next = [entry, ...presets.filter((p) => p.label !== entry.label)].slice(0, MAX_CUSTOM_PRESETS);
    saveCustomPresets(next);
    if ($id('cmp-preset-name')) $id('cmp-preset-name').value = '';
    renderPresets();
    window.StockQPro?.App?.toast?.(`已儲存「${entry.label}」`, 'ok');
  }

  function deleteCustomPreset(id) {
    const next = loadCustomPresets().filter((p) => p.id !== id);
    saveCustomPresets(next);
    renderPresets();
    window.StockQPro?.App?.toast?.('已刪除自訂組合', 'ok');
  }

  function renderPresets() {
    const wrap = $id('cmp-presets');
    const customWrap = $id('cmp-custom-presets');
    const presets = pickData()?.COMPARE_PRESETS || [];
    if (wrap) {
      wrap.innerHTML = presets.map((p) => `
        <button type="button" class="cmp-preset-btn" data-preset="${p.id}" title="${p.codes.join(', ')}">${p.label}</button>
      `).join('');
      wrap.querySelectorAll('[data-preset]').forEach((btn) => {
        btn.addEventListener('click', () => applyPreset(btn.getAttribute('data-preset')));
      });
    }
    if (customWrap) {
      const custom = loadCustomPresets();
      if (!custom.length) {
        customWrap.innerHTML = '<p class="bt-pick-hint" style="margin:4px 0 0">尚無自訂組合</p>';
      } else {
        customWrap.innerHTML = custom.map((p) => `
          <span class="cmp-preset-btn cmp-preset-custom" title="${(p.codes || []).join(', ')}">
            <button type="button" class="cmp-preset-load" data-custom-preset="${p.id}">${p.label}</button>
            <button type="button" class="cmp-preset-rm" data-rm-preset="${p.id}" aria-label="刪除">×</button>
          </span>`).join('');
        customWrap.querySelectorAll('[data-custom-preset]').forEach((btn) => {
          btn.addEventListener('click', () => applyPreset(btn.getAttribute('data-custom-preset')));
        });
        customWrap.querySelectorAll('[data-rm-preset]').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteCustomPreset(btn.getAttribute('data-rm-preset'));
          });
        });
      }
    }
  }

  function applyPreset(presetId) {
    const custom = loadCustomPresets().find((x) => x.id === presetId);
    const builtin = (pickData()?.COMPARE_PRESETS || []).find((x) => x.id === presetId);
    const p = custom || builtin;
    if (!p?.codes?.length) return;
    setMode('stocks');
    state.chips = [];
    p.codes.forEach((code) => addChip(code, resolveName(code), { silent: true, skipEnqueue: true }));
    window.StockQPro?.App?.toast?.(`已載入組合：${p.label}`, 'ok');
    syncCompareHash();
  }

  async function fillWatchlistToChips() {
    setMode('stocks');
    let items = [];
    try {
      const d = await Api.getWatchlist();
      items = (d?.items || []).map((x) => ({ code: x.code, name: x.name }));
    } catch (_) { /* ignore */ }
    items = items.filter((x) => isValidCompareSymbol(normalizeCode(x.code))).slice(0, MAX_STOCKS);
    if (!items.length) return window.StockQPro?.App?.toast?.('自選為空', 'inf');
    state.chips = items.map((x) => ({ code: normalizeCode(x.code), name: x.name || resolveName(x.code) }));
    renderChips();
    window.StockQPro?.App?.toast?.(`已加入 ${items.length} 檔自選`, 'ok');
  }

  function copyCodesToClipboard() {
    const text = state.chips.map((c) => c.code).join(',');
    if (!text) return window.StockQPro?.App?.toast?.('尚無標的', 'inf');
    const done = () => window.StockQPro?.App?.toast?.('已複製代碼', 'ok');
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => {
        window.StockQPro?.App?.toast?.('複製失敗', 'er');
      });
      return;
    }
    window.StockQPro?.App?.toast?.(text, 'inf');
  }

  function shareCompareLink() {
    syncCompareHash();
    const url = `${location.origin}${location.pathname}${location.hash}`;
    const done = () => window.StockQPro?.App?.toast?.('已複製分享連結', 'ok');
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(() => window.StockQPro?.App?.toast?.('複製失敗', 'er'));
      return;
    }
    window.StockQPro?.App?.toast?.(url, 'inf');
  }

  function initCorrChart() {
    const el = $id('cmp-corr-heat');
    if (!el) return null;
    if (corrChart) {
      corrChart.resize();
      return corrChart;
    }
    const reg = window.StockQPro?.ECharts;
    corrChart = reg?.get
      ? reg.get('compare', 'cmp-corr-heat', el, { renderer: 'canvas' })
      : echarts.init(el, null, { renderer: 'canvas' });
    return corrChart;
  }

  function renderCorrelationPanel() {
    const panel = $id('cmp-corr-panel');
    const corr = state.correlation;
    if (!panel) return;
    if (!corr?.matrix?.length || !(corr.codes?.length >= 2)) {
      panel.hidden = true;
      if (corrChart) corrChart.clear();
      return;
    }
    panel.hidden = false;
    const codes = corr.codes;
    const labels = codes.map((c) => `${c}\n${resolveName(c).slice(0, 4)}`);
    const heatData = [];
    corr.matrix.forEach((row, i) => {
      row.forEach((v, j) => {
        heatData.push([j, i, Number(v)]);
      });
    });

    const ch = initCorrChart();
    if (!ch) return;

    ch.setOption({
      ...baseChartOpts(),
      grid: { top: 36, right: 48, bottom: 52, left: 72 },
      tooltip: {
        position: 'top',
        backgroundColor: '#252842',
        borderColor: '#2d3158',
        formatter: (p) => {
          const v = p.data?.[2];
          const i = p.data?.[1];
          const j = p.data?.[0];
          return `<b>${codes[i]} × ${codes[j]}</b><br/>相關係數：${Number(v).toFixed(3)}`;
        },
      },
      xAxis: {
        type: 'category',
        data: labels,
        splitArea: { show: true },
        axisLabel: { color: '#9b9ab4', fontSize: 9, interval: 0 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'category',
        data: labels,
        splitArea: { show: true },
        axisLabel: { color: '#9b9ab4', fontSize: 9, interval: 0 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      visualMap: {
        min: -0.2,
        max: 1,
        calculable: false,
        orient: 'vertical',
        right: 0,
        top: 'center',
        itemHeight: 120,
        text: ['高', '低'],
        textStyle: { color: '#9b9ab4', fontSize: 9 },
        inRange: {
          color: ['#2d3158', '#4a5568', '#5c6b8a', '#60a5fa', '#93c5fd'],
        },
      },
      series: [{
        name: '相關性',
        type: 'heatmap',
        data: heatData,
        label: {
          show: codes.length <= 8,
          color: '#eeeef2',
          fontSize: 9,
          formatter: (p) => {
            const v = Number(p.data?.[2]);
            return Number.isFinite(v) ? v.toFixed(2) : '';
          },
        },
        emphasis: {
          itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,.35)' },
        },
        itemStyle: {
          borderColor: '#0f1117',
          borderWidth: 2,
        },
      }],
      title: {
        text: `日收益相關性熱力圖 · ${corr.sample_days || 0} 交易日交集`,
        left: 0,
        top: 0,
        textStyle: { color: '#9b9ab4', fontSize: 11, fontWeight: 600 },
      },
    }, true);
  }

  function sortStockCodes(codes, comp) {
    const mode = $id('cmp-stock-sort')?.value || 'return_desc';
    const statsOf = (code) => comp[code]?.stats || {};
    return [...codes].sort((a, b) => {
      if (mode === 'code') return a.localeCompare(b);
      const sa = statsOf(a);
      const sb = statsOf(b);
      if (mode === 'vol_asc') return Number(sa.volatility_pct ?? 0) - Number(sb.volatility_pct ?? 0);
      const ra = Number(sa.total_return_pct ?? comp[a]?.relative_return?.slice(-1)[0] ?? 0);
      const rb = Number(sb.total_return_pct ?? comp[b]?.relative_return?.slice(-1)[0] ?? 0);
      return mode === 'return_asc' ? ra - rb : rb - ra;
    });
  }

  function filterStrategyRows(rows) {
    const q = String($id('cmp-strat-q')?.value || '').trim().toLowerCase();
    const minTrades = Number($id('cmp-strat-min-trades')?.value || 0);
    let out = rows;
    if (q) {
      out = out.filter((r) => (
        String(r.label || '').toLowerCase().includes(q)
        || String(r.key || '').toLowerCase().includes(q)
      ));
    }
    if (minTrades > 0) out = out.filter((r) => Number(r.trades) >= minTrades);
    return out;
  }

  function metricLabel(key) {
    return METRIC_LABELS[key] || key;
  }

  function metricHigherIsBetter(key) {
    return METRIC_HIGHER_BETTER.has(key);
  }

  function maxDrawdownFromNav(nav) {
    if (!Array.isArray(nav) || nav.length < 2) return 0;
    let peak = Number(nav[0]) || 1;
    let maxDd = 0;
    nav.forEach((raw) => {
      const v = Number(raw);
      if (!Number.isFinite(v)) return;
      if (v > peak) peak = v;
      if (peak > 0) maxDd = Math.max(maxDd, ((peak - v) / peak) * 100);
    });
    return maxDd;
  }

  function normalizeStrategyRow(r) {
    if (!r || typeof r !== 'object') return null;
    const key = String(r.strategy || r.strategy_key || '').trim();
    const totalReturn = Number(r.total_return_pct);
    let maxDd = Number(r.max_drawdown_pct);
    if (
      Number.isFinite(totalReturn) && Number.isFinite(maxDd)
      && maxDd > 30 && Math.abs(maxDd - totalReturn) < 1
      && Array.isArray(r.nav) && r.nav.length > 1
    ) {
      maxDd = maxDrawdownFromNav(r.nav);
    }
    if (!Number.isFinite(maxDd)) maxDd = maxDrawdownFromNav(r.nav || []);
    const won = Number(r.won_trades);
    const lost = Number(r.lost_trades);
    let winRate = Number(r.win_rate_pct);
    const trades = Number(r.total_trades);
    if (!Number.isFinite(winRate) && Number.isFinite(won) && Number.isFinite(lost) && (won + lost) > 0) {
      winRate = (won / (won + lost)) * 100;
    }
    return {
      ...r,
      strategy: key,
      strategy_name: strategyDisplayNames[key] || r.strategy_name || key,
      total_return_pct: Number.isFinite(totalReturn) ? totalReturn : 0,
      max_drawdown_pct: Number.isFinite(maxDd) ? maxDd : 0,
      sharpe_ratio: Number(r.sharpe_ratio ?? 0),
      win_rate_pct: Number.isFinite(winRate) ? winRate : 0,
      total_trades: Number.isFinite(trades) ? trades : 0,
    };
  }

  function formatMetricValue(key, v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '--';
    if (key === 'max_drawdown_pct') return `-${Math.abs(n).toFixed(2)}%`;
    if (String(key).includes('pct')) return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
    if (key === 'total_trades') return String(Math.round(n));
    return n.toFixed(3);
  }

  function valueClass(key, v) {
    const n = Number(v);
    if (key === 'max_drawdown_pct') return 'neg';
    if (key === 'total_trades') return '';
    return n >= 0 ? 'pos' : 'neg';
  }

  function sortRows(rows, valueKey, order) {
    const metricKey = $id('cmp-metric')?.value || 'total_return_pct';
    const higherBetter = metricHigherIsBetter(metricKey);
    const dir = order === 'asc' ? 1 : -1;
    const mul = higherBetter ? dir : -dir;
    return [...rows].sort((a, b) => mul * (Number(a[valueKey] ?? 0) - Number(b[valueKey] ?? 0)));
  }

  function renderStats(rows, metric) {
    const el = $id('cmp-stats-row');
    if (!el || !rows.length) {
      if (el) el.innerHTML = '';
      return;
    }
    const vals = rows.map((r) => Number(r.v ?? 0)).filter((x) => Number.isFinite(x));
    if (!vals.length) {
      el.innerHTML = '';
      return;
    }
    const higherBetter = metricHigherIsBetter(metric);
    const best = higherBetter
      ? vals.reduce((a, b) => (b > a ? b : a), vals[0])
      : vals.reduce((a, b) => (b < a ? b : a), vals[0]);
    const worst = higherBetter
      ? vals.reduce((a, b) => (b < a ? b : a), vals[0])
      : vals.reduce((a, b) => (b > a ? b : a), vals[0]);
    const avg = vals.reduce((s, x) => s + x, 0) / vals.length;
    const bestLbl = metric === 'max_drawdown_pct' ? '回撤最小' : '最佳';
    const worstLbl = metric === 'max_drawdown_pct' ? '回撤最大' : '最差';
    const cards = [
      { lbl: bestLbl, val: best },
      { lbl: worstLbl, val: worst },
      { lbl: '平均', val: avg },
      { lbl: '策略數', val: rows.length, raw: true },
    ];
    el.innerHTML = cards.map((c) => {
      const txt = c.raw ? String(c.val) : formatMetricValue(metric, c.val);
      const cls = c.raw ? '' : valueClass(metric, c.val);
      return `<div class="cmp-stat-card"><div class="cmp-stat-lbl">${c.lbl}</div><div class="cmp-stat-val ${cls}">${txt}</div></div>`;
    }).join('');
  }

  function baseChartOpts() {
    return {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'JetBrains Mono, DM Sans, sans-serif' },
    };
  }

  function renderStrategyBar(rows, metric, isPct) {
    const ch = initChart();
    if (!ch) return;
    const names = rows.map((r) => r.label);
    const values = rows.map((r) => r.v);
    ch.setOption({
      ...baseChartOpts(),
      grid: { top: 28, right: 24, bottom: 24, left: 108, containLabel: false },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: '#252842',
        borderColor: '#2d3158',
        textStyle: { color: '#eeeef2', fontSize: 11 },
        formatter: (params) => {
          const p = Array.isArray(params) ? params[0] : params;
          const row = rows[p?.dataIndex];
          if (!row) return '';
          return [
            `<b>${row.label}</b>`,
            `${metricLabel(metric)}: ${formatMetricValue(metric, row.v)}`,
            `夏普: ${formatMetricValue('sharpe_ratio', row.sharpe)}`,
            `回撤: ${formatMetricValue('max_drawdown_pct', row.max_dd)}`,
            `勝率: ${formatMetricValue('win_rate_pct', row.win_rate)}`,
          ].join('<br/>');
        },
      },
      xAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: '#1e2138' } },
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: {
          color: '#5c5b72',
          fontSize: 10,
          formatter: isPct ? (v) => `${v}%` : '{value}',
        },
      },
      yAxis: {
        type: 'category',
        data: names,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#9b9ab4', fontSize: 10, width: 96, overflow: 'truncate' },
      },
      dataZoom: rows.length > 12 ? [{ type: 'slider', yAxisIndex: 0, width: 12, right: 4 }] : [],
      series: [{
        type: 'bar',
        data: values.map((v) => ({
          value: v,
          itemStyle: {
            color: isPct
              ? (v >= 0 ? quoteUp() : quoteDown())
              : new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: '#3b3f5c' },
                { offset: 1, color: '#e8b830' },
              ]),
          },
        })),
        barMaxWidth: 22,
        label: {
          show: rows.length <= 16,
          position: 'right',
          fontSize: 10,
          color: '#9b9ab4',
          formatter: (p) => formatMetricValue(metric, p.value),
        },
        markLine: isPct ? {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#5c5b72', type: 'dashed' },
          data: [{ xAxis: 0 }],
        } : undefined,
      }],
    }, true);
  }

  function renderStrategyScatter(rows) {
    const ch = initChart();
    if (!ch) return;
    const data = rows.map((r) => {
      const ret = Number(r.raw?.total_return_pct ?? r.v) || 0;
      return {
        name: r.label,
        value: [Number(r.sharpe) || 0, ret, Number(r.trades) || 0],
        itemStyle: { color: ret >= 0 ? quoteUp() : quoteDown() },
      };
    });
    ch.setOption({
      ...baseChartOpts(),
      grid: { top: 36, right: 28, bottom: 48, left: 56 },
      tooltip: {
        trigger: 'item',
        backgroundColor: '#252842',
        borderColor: '#2d3158',
        formatter: (p) => {
          const d = p.data;
          return `<b>${d.name}</b><br/>夏普: ${formatMetricValue('sharpe_ratio', d.value[0])}<br/>收益: ${formatMetricValue('total_return_pct', d.value[1])}<br/>交易: ${d.value[2]}`;
        },
      },
      xAxis: {
        name: '夏普',
        nameLocation: 'middle',
        nameGap: 28,
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: { color: '#5c5b72', fontSize: 10 },
      },
      yAxis: {
        name: '總收益 %',
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: { color: '#5c5b72', fontSize: 10, formatter: '{value}%' },
      },
      series: [{
        type: 'scatter',
        symbolSize: (val) => Math.min(36, Math.max(10, Math.sqrt(val[2] || 1) * 3)),
        data,
        emphasis: { focus: 'self', scale: 1.2 },
      }],
    }, true);
  }

  function renderStrategyNav(rows) {
    const ch = initChart();
    if (!ch) return;
    const withNav = rows.filter((r) => r.nav && r.nav.length > 1);
    if (!withNav.length) {
      renderStrategyBar(rows, $id('cmp-metric')?.value || 'total_return_pct', true);
      return;
    }
    const top = [...withNav].sort((a, b) => Number(b.v) - Number(a.v)).slice(0, 5);
    let dates = top[0].dates || [];
    if (!dates.length && top[0].nav.length) {
      dates = top[0].nav.map((_, i) => String(i));
    }
    ch.setOption({
      ...baseChartOpts(),
      color: STOCK_COLORS,
      legend: { top: 4, textStyle: { color: '#9b9ab4', fontSize: 10 }, type: 'scroll' },
      grid: { top: 48, right: 20, bottom: 56, left: 52 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#252842',
        borderColor: '#2d3158',
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { color: '#5c5b72', fontSize: 9, hideOverlap: true },
        axisLine: { lineStyle: { color: '#1e2138' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: { color: '#5c5b72', fontSize: 10 },
      },
      series: top.map((r, i) => ({
        name: r.label,
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        data: r.nav,
      })),
    }, true);
  }

  function renderStrategyTable(rows, metric) {
    const thead = $id('cmp-thead');
    const tb = $id('cmp-tb');
    if (!tb) return;
    if (thead) {
      thead.innerHTML = `<tr>
        <th class="cmp-rank">排名</th>
        <th>策略</th>
        <th>${metricLabel(metric)}</th>
        <th>夏普比率</th>
        <th>最大回撤</th>
        <th>勝率</th>
        <th>交易次數</th>
      </tr>`;
    }
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--t3);padding:24px">無資料</td></tr>';
      return;
    }
    tb.innerHTML = rows.map((r, i) => {
      const rankCls = i < 3 ? 'cmp-rank top' : 'cmp-rank';
      return `<tr>
        <td class="${rankCls}">${i + 1}</td>
        <td title="${r.key || ''}">${r.label}</td>
        <td class="${valueClass(metric, r.v)}">${formatMetricValue(metric, r.v)}</td>
        <td>${formatMetricValue('sharpe_ratio', r.sharpe)}</td>
        <td class="neg">${formatMetricValue('max_drawdown_pct', r.max_dd)}</td>
        <td>${formatMetricValue('win_rate_pct', r.win_rate)}</td>
        <td>${formatMetricValue('total_trades', r.trades)}</td>
      </tr>`;
    }).join('');
  }

  function renderStrategies() {
    const raw = state.strategyResults;
    if (!raw?.length) {
      clearCharts();
      return;
    }
    const metric = $id('cmp-metric')?.value || 'total_return_pct';
    const sortOrder = $id('cmp-sort')?.value || 'desc';
    const topN = Number($id('cmp-topn')?.value || 0);
    const chartType = $id('cmp-chart-type')?.value || 'bar';
    const isPct = String(metric).includes('pct');

    let rows = raw.map((r) => normalizeStrategyRow(r)).filter(Boolean).map((r) => ({
      label: r.strategy_name || r.strategy || '—',
      key: r.strategy || '',
      v: Number(r[metric] ?? 0),
      sharpe: Number(r.sharpe_ratio ?? 0),
      max_dd: Number(r.max_drawdown_pct ?? 0),
      win_rate: Number(r.win_rate_pct ?? 0),
      trades: Number(r.total_trades ?? 0),
      nav: r.nav || [],
      dates: r.dates || [],
      raw: r,
    }));
    rows = sortRows(rows, 'v', sortOrder);
    const beforeFilter = rows.length;
    rows = filterStrategyRows(rows);
    if (topN > 0) rows = rows.slice(0, topN);

    const hd = $id('cmp-metric-hd');
    const code = primaryCode();
    if (hd) {
      const filtHint = beforeFilter !== rows.length ? ` · 篩選後 ${rows.length}` : '';
      hd.innerHTML = `<span class="lib-legend-item"><b>${code}</b></span>
        <span class="lib-legend-item">指標：${metricLabel(metric)}</span>
        <span class="lib-legend-item">共 ${raw.length} 策略 · 顯示 ${rows.length}${filtHint}</span>`;
    }

    renderStats(rows, metric);
    if (chartType === 'scatter') renderStrategyScatter(rows);
    else if (chartType === 'nav') renderStrategyNav(rows);
    else renderStrategyBar(rows, metric, isPct);
    renderStrategyTable(rows, metric);
  }

  function renderStocks() {
    const comp = state.stockComparison;
    const ch = initChart();
    if (!ch || !comp || !Object.keys(comp).length) {
      clearCharts();
      return;
    }
    const codes = sortStockCodes(Object.keys(comp), comp);
    const dates = comp[codes[0]]?.dates || [];
    const normalize = $id('cmp-normalize')?.checked !== false;
    const vsBench = $id('cmp-vs-benchmark')?.checked && state.chips.length > 0;
    const chartKind = $id('cmp-stock-chart')?.value || 'line';
    const benchCode = state.benchmark || primaryCode();
    const idx = state.indexOverlay;
    const showIndex = idx?.relative_return?.length && ($id('cmp-normalize')?.checked !== false || vsBench);

    const series = codes.map((code) => {
      const item = comp[code];
      let data = item.relative_return || [];
      if (vsBench && state.excessReturn?.[code]) data = state.excessReturn[code];
      else if (!normalize && item.close) data = item.close;
      const base = {
        name: `${code} ${resolveName(code)}`,
        type: chartKind === 'area' ? 'line' : 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        data,
      };
      if (chartKind === 'area') {
        base.areaStyle = { opacity: 0.12 };
      }
      return base;
    });

    if (showIndex) {
      series.push({
        name: `${idx.code} ${idx.name || '指數'}`,
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, type: 'dashed', color: '#94a3b8' },
        itemStyle: { color: '#94a3b8' },
        data: idx.relative_return,
        z: 10,
      });
    }

    const yName = vsBench
      ? `相對 ${benchCode} 超額 %`
      : (normalize ? '相對收益 %' : '收盤價');
    const pctAxis = normalize || vsBench;

    ch.setOption({
      ...baseChartOpts(),
      color: STOCK_COLORS,
      legend: { top: 4, type: 'scroll', textStyle: { color: '#9b9ab4', fontSize: 10 } },
      grid: { top: 44, right: 24, bottom: 56, left: 52 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#252842',
        borderColor: '#2d3158',
        valueFormatter: (v) => (pctAxis ? `${Number(v).toFixed(2)}%` : Number(v).toFixed(2)),
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLabel: { color: '#5c5b72', fontSize: 9, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        scale: true,
        name: yName,
        splitLine: { lineStyle: { color: '#1d2033', type: 'dashed' } },
        axisLabel: {
          color: '#5c5b72',
          formatter: pctAxis ? '{value}%' : '{value}',
        },
      },
      series,
    }, true);

    const hd = $id('cmp-metric-hd');
    if (hd) {
      const idxHint = showIndex ? ` · 指數 ${idx.code}` : '';
      hd.innerHTML = `<span class="lib-legend-item">區間：${dates[0] || '—'} → ${dates[dates.length - 1] || '—'}</span>
        <span class="lib-legend-item">${vsBench ? `超額 vs ${benchCode}` : (normalize ? '歸一化累計收益' : '收盤價')}${idxHint}</span>
        <span class="lib-legend-item">${codes.length} 檔</span>`;
    }

    renderStockStats(codes, comp, normalize, vsBench, idx);
    renderStockTable(codes, comp, normalize, vsBench, !!idx);
    renderCorrelationPanel();
  }

  function stockReturnVal(code, comp, normalize, vsBench) {
    const item = comp[code];
    const st = item?.stats || {};
    if (vsBench && state.excessReturn?.[code]?.length) {
      const ex = state.excessReturn[code];
      return ex[ex.length - 1];
    }
    if (st.total_return_pct != null && normalize) return st.total_return_pct;
    const rel = item?.relative_return || [];
    return rel.length ? rel[rel.length - 1] : 0;
  }

  function renderStockStats(codes, comp, normalize, vsBench, idx) {
    const el = $id('cmp-stats-row');
    if (!el) return;
    const rets = codes.map((code) => ({
      code,
      ret: stockReturnVal(code, comp, normalize, vsBench),
      vol: Number(comp[code]?.stats?.volatility_pct ?? 0),
      dd: Number(comp[code]?.stats?.max_drawdown_pct ?? 0),
    }));
    const best = [...rets].sort((a, b) => b.ret - a.ret)[0];
    const worst = [...rets].sort((a, b) => a.ret - b.ret)[0];
    const avgVol = rets.length ? rets.reduce((s, x) => s + x.vol, 0) / rets.length : 0;
    const idxRet = idx?.stats?.total_return_pct;
    const cards = [
      { lbl: vsBench ? '超額最佳' : '區間最佳', val: best ? `${best.code} ${formatMetricValue('total_return_pct', best.ret)}` : '—', cls: 'pos' },
      { lbl: vsBench ? '超額最弱' : '區間最弱', val: worst ? `${worst.code} ${formatMetricValue('total_return_pct', worst.ret)}` : '—', cls: 'neg' },
      { lbl: '平均波動', val: `${avgVol.toFixed(2)}%`, cls: '', raw: true },
    ];
    if (idx && idxRet != null) {
      cards.push({
        lbl: `${idx.name || idx.code}`,
        val: formatMetricValue('total_return_pct', idxRet),
        cls: valueClass('total_return_pct', idxRet),
      });
    } else {
      cards.push({ lbl: '對比檔數', val: codes.length, cls: '', raw: true });
    }
    el.innerHTML = cards.map((c) => `<div class="cmp-stat-card"><div class="cmp-stat-lbl">${c.lbl}</div><div class="cmp-stat-val ${c.cls}">${c.val}</div></div>`).join('');
  }

  function renderStockTable(codes, comp, normalize, vsBench, hasIndex) {
    const thead = $id('cmp-thead');
    const tb = $id('cmp-tb');
    if (!tb) return;
    const retLbl = vsBench ? '超額收益' : (normalize ? '區間收益' : '最新價');
    const betaCol = hasIndex ? '<th>Beta</th><th>Alpha</th>' : '';
    if (thead) {
      thead.innerHTML = `<tr>
        <th class="cmp-rank">#</th>
        <th>代碼</th><th>名稱</th>
        <th>${retLbl}</th>
        <th>波動</th>
        <th>最大回撤</th>
        ${betaCol}
        <th>操作</th>
      </tr>`;
    }
    tb.innerHTML = codes.map((code, i) => {
      const item = comp[code];
      const st = item?.stats || {};
      const ret = stockReturnVal(code, comp, normalize, vsBench);
      const close = item?.close?.length ? item.close[item.close.length - 1] : '--';
      const retTxt = (normalize || vsBench)
        ? formatMetricValue('total_return_pct', ret)
        : close;
      const cls = (normalize || vsBench) ? valueClass('total_return_pct', ret) : '';
      const volTxt = st.volatility_pct != null ? `${Number(st.volatility_pct).toFixed(2)}%` : '—';
      const ddTxt = st.max_drawdown_pct != null ? formatMetricValue('max_drawdown_pct', st.max_drawdown_pct) : '—';
      const betaTxt = st.beta_vs_index != null ? Number(st.beta_vs_index).toFixed(2) : '—';
      const alphaTxt = st.alpha_vs_index_pct != null ? formatMetricValue('total_return_pct', st.alpha_vs_index_pct) : '—';
      const rankCls = i < 3 ? 'cmp-rank top' : 'cmp-rank';
      const betaCells = hasIndex ? `<td>${betaTxt}</td><td class="${valueClass('total_return_pct', st.alpha_vs_index_pct)}">${alphaTxt}</td>` : '';
      return `<tr>
        <td class="${rankCls}">${i + 1}</td>
        <td class="ac">${code}</td>
        <td>${resolveName(code)}</td>
        <td class="${cls}">${retTxt}</td>
        <td>${volTxt}</td>
        <td class="neg">${ddTxt}</td>
        ${betaCells}
        <td class="cmp-row-actions">
          <button type="button" class="btn s" data-cmp-asset="${code}">資產</button>
          <button type="button" class="btn s" data-cmp-bt="${code}">回測</button>
        </td>
      </tr>`;
    }).join('');
    tb.querySelectorAll('[data-cmp-bt]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const code = btn.getAttribute('data-cmp-bt');
        window.StockQPro?.App?.nav?.('backtest', { syncHash: true });
        window.StockQPro?.backtestSymbol?.setSymbol?.(code, resolveName(code));
      });
    });
    tb.querySelectorAll('[data-cmp-asset]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const code = btn.getAttribute('data-cmp-asset');
        window.StockQPro?.openAsset?.(code);
      });
    });
  }

  async function runStrategies() {
    const code = primaryCode();
    if (!code) return window.StockQPro?.App?.toast?.('請先加入一檔股票', 'er');
    const btn = $id('cmp-run');
    if (btn) btn.disabled = true;
    state.running = true;
    state.strategySessionActive = true;
    try {
      await enqueueStrategyCompare(code);
    } finally {
      state.running = false;
      if (btn) btn.disabled = false;
      updateSummaryBadge();
    }
  }

  async function runStocks() {
    const codes = state.chips.map((c) => c.code);
    if (codes.length < 2) return window.StockQPro?.App?.toast?.('多股模式請至少選擇 2 檔', 'er');
    const days = Number($id('cmp-days')?.value || 250);
    const btn = $id('cmp-run');
    if (btn) btn.disabled = true;
    state.running = true;
    try {
      const vsBench = $id('cmp-vs-benchmark')?.checked && state.chips.length > 0;
      const benchmark = vsBench ? primaryCode() : undefined;
      const indexCode = $id('cmp-index')?.value || '';
      const d = await Api.compareStocks(codes, days, { benchmark, index: indexCode || undefined });
      if (!d?.success) throw new Error(d?.error || '對比失敗');
      state.stockComparison = d.comparison || {};
      state.correlation = d.correlation || null;
      state.benchmark = d.benchmark || null;
      state.excessReturn = d.excess_return || null;
      state.indexOverlay = d.index_overlay || null;
      const missing = d.missing || [];
      if (missing.length) {
        window.StockQPro?.App?.toast?.(`部分標的無數據：${missing.join(', ')}`, 'inf');
      }
      if (indexCode && !state.indexOverlay) {
        window.StockQPro?.App?.toast?.('指數數據暫不可用，已略過疊加', 'inf');
      }
      renderStocks();
      window.StockQPro?.App?.toast?.(`已載入 ${d.loaded || 0}/${d.total || codes.length} 檔`, 'ok');
    } catch (e) {
      state.stockComparison = null;
      state.indexOverlay = null;
      clearCharts();
      window.StockQPro?.App?.toast?.(`對比失敗：${e?.message || e}`, 'er');
    } finally {
      state.running = false;
      if (btn) btn.disabled = false;
      updateSummaryBadge();
    }
  }

  async function run() {
    if (state.running) {
      if (state.mode === 'strategies' && primaryCode()) {
        await enqueueStrategyCompare(primaryCode());
      } else {
        window.StockQPro?.App?.toast?.('當前對比仍在提交中，請稍候', 'inf');
      }
      return;
    }
    if (state.mode === 'stocks') await runStocks();
    else await runStrategies();
  }

  function exportChartPng() {
    const ch = chart || initChart();
    if (!ch) return;
    try {
      const url = ch.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#0f1117' });
      const a = document.createElement('a');
      a.href = url;
      a.download = `compare_${state.mode}_${Date.now()}.png`;
      a.click();
      window.StockQPro?.App?.toast?.('已匯出 PNG', 'ok');
    } catch (e) {
      window.StockQPro?.App?.toast?.(`匯出失敗：${e?.message || e}`, 'er');
    }
  }

  function exportCsv() {
    if (state.mode === 'strategies' && state.strategyResults?.length) {
      const metric = $id('cmp-metric')?.value || 'total_return_pct';
      const header = ['strategy', 'strategy_key', metric, 'sharpe_ratio', 'max_drawdown_pct', 'win_rate_pct', 'total_trades'];
      const lines = [header.join(',')];
      state.strategyResults.forEach((r) => {
        lines.push([
          r.strategy_name || r.strategy,
          r.strategy,
          r[metric],
          r.sharpe_ratio,
          r.max_drawdown_pct,
          r.win_rate_pct,
          r.total_trades,
        ].map((v) => {
          const s = String(v ?? '');
          return s.includes(',') ? `"${s.replace(/"/g, '""')}"` : s;
        }).join(','));
      });
      Api.downloadBlob(lines.join('\n'), `strategy_compare_${primaryCode()}_${Date.now()}.csv`, 'text/csv;charset=utf-8');
      window.StockQPro?.App?.toast?.('已匯出 CSV', 'ok');
      return;
    }
    if (state.mode === 'stocks' && state.stockComparison) {
      const codes = Object.keys(state.stockComparison);
      const dates = state.stockComparison[codes[0]]?.dates || [];
      const header = ['date', ...codes];
      const lines = [header.join(',')];
      dates.forEach((dt, i) => {
        lines.push([dt, ...codes.map((c) => state.stockComparison[c]?.relative_return?.[i] ?? '')].join(','));
      });
      lines.push('');
      lines.push('code,total_return_pct,volatility_pct,max_drawdown_pct,annual_return_pct');
      codes.forEach((c) => {
        const st = state.stockComparison[c]?.stats || {};
        lines.push([c, st.total_return_pct, st.volatility_pct, st.max_drawdown_pct, st.annual_return_pct].join(','));
      });
      if (state.indexOverlay?.stats) {
        const ist = state.indexOverlay.stats;
        lines.push([state.indexOverlay.code, ist.total_return_pct, ist.volatility_pct, ist.max_drawdown_pct, ist.annual_return_pct].join(','));
      }
      Api.downloadBlob(lines.join('\n'), `stocks_compare_${Date.now()}.csv`, 'text/csv;charset=utf-8');
      window.StockQPro?.App?.toast?.('已匯出 CSV', 'ok');
      return;
    }
    window.StockQPro?.App?.toast?.('尚無可匯出資料', 'inf');
  }

  function switchPickMode(mode) {
    pickMode = mode;
    document.querySelectorAll('[data-cmp-pick]').forEach((btn) => {
      btn.classList.toggle('on', btn.getAttribute('data-cmp-pick') === mode);
    });
    document.querySelectorAll('[data-cmp-pick-panel]').forEach((pane) => {
      pane.classList.toggle('on', pane.getAttribute('data-cmp-pick-panel') === mode);
    });
    if (mode === 'watch') loadWatchlist();
    if (mode === 'catalog' && !catalogAshare.length) loadCatalog();
    if (mode === 'hot') renderHot();
  }

  function renderPickList(containerId, items, emptyText) {
    const el = $id(containerId);
    if (!el) return;
    if (!items.length) {
      el.innerHTML = `<div class="bt-pick-empty">${emptyText}</div>`;
      return;
    }
    el.innerHTML = items.map((it) => `
      <button type="button" class="bt-pick-item" data-code="${it.code}" data-name="${(it.name || '').replace(/"/g, '&quot;')}">
        <span class="bt-pick-item-code">${it.code}</span>
        <span class="bt-pick-item-name">${it.name || it.code}</span>
        ${it.extra ? `<span class="bt-pick-item-extra">${it.extra}</span>` : ''}
      </button>`).join('');
    el.querySelectorAll('.bt-pick-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        addChip(btn.getAttribute('data-code'), btn.getAttribute('data-name'));
      });
    });
  }

  async function loadNames() {
    try {
      const d = await Api.get('/api/stocks/names');
      namesMap = d?.names || {};
    } catch (_) {
      namesMap = {};
    }
  }

  async function loadStrategyDisplayNames() {
    try {
      const d = await Api.get('/api/strategies/list');
      const map = {};
      [...(d?.builtin || []), ...(d?.user || [])].forEach((s) => {
        if (s?.name) map[s.name] = s.display_name || s.name;
      });
      strategyDisplayNames = map;
    } catch (_) {
      strategyDisplayNames = {};
    }
  }

  async function loadCatalog() {
    const el = $id('cmp-pick-catalog');
    if (el) el.innerHTML = '<div class="bt-pick-empty">載入中…</div>';
    try {
      const loader = pickData()?.loadCatalogAshare;
      catalogAshare = loader ? await loader(namesMap) : [];
      const hint = el?.previousElementSibling?.previousElementSibling;
      if (hint?.classList?.contains('bt-pick-hint') && catalogAshare.length) {
        hint.textContent = `共 ${catalogAshare.length} 檔，點選加入對比`;
      }
      renderPickList('cmp-pick-catalog', catalogAshare, '資產庫暫無 A 股');
    } catch (_) {
      if (el) el.innerHTML = '<div class="bt-pick-empty">載入失敗</div>';
    }
  }

  async function loadWatchlist() {
    const el = $id('cmp-pick-watch');
    if (el) el.innerHTML = '<div class="bt-pick-empty">載入中…</div>';
    let items = [];
    try {
      const d = await Api.getWatchlist();
      items = (d?.items || []).map((x) => ({ code: x.code, name: x.name }));
    } catch (_) { /* ignore */ }
    items = items.filter((x) => isValidCompareSymbol(normalizeCode(x.code)));
    renderPickList('cmp-pick-watch', items, '自選為空');
  }

  async function renderHot() {
    const el = $id('cmp-pick-hot');
    if (el) el.innerHTML = '<div class="bt-pick-empty">載入熱門…</div>';
    const rows = pickData()?.fetchHotAshare
      ? await pickData().fetchHotAshare(namesMap, 48)
      : (pickData()?.FALLBACK_HOT || []);
    renderPickList('cmp-pick-hot', rows, '暫無熱門標的');
  }

  async function runSearch() {
    const q = String($id('cmp-search-q')?.value || '').trim();
    const el = $id('cmp-pick-search');
    if (!q) {
      if (el) el.innerHTML = '<div class="bt-pick-empty">輸入關鍵字</div>';
      return;
    }
    if (el) el.innerHTML = '<div class="bt-pick-empty">搜索中…</div>';
    const rows = pickData()?.searchAshare
      ? await pickData().searchAshare(q, namesMap, 80)
      : [];
    renderPickList('cmp-pick-search', rows, '未找到');
  }

  function onCodeInput() {
    const raw = String($id('cmp-code-input')?.value || '').trim();
    const c = normalizeCode(raw);
    if (isValidAshare(c) && raw.length === 6) {
      addChip(c, resolveName(c), { silent: true, skipEnqueue: true });
      const sug = $id('cmp-code-suggest');
      if (sug) sug.hidden = true;
      if ($id('cmp-code-input')) $id('cmp-code-input').value = '';
      return;
    }
    if (raw.length < 1) {
      const sug = $id('cmp-code-suggest');
      if (sug) sug.hidden = true;
      return;
    }
    const hits = pickData()?.suggestFromNames
      ? pickData().suggestFromNames(raw, namesMap, 20)
      : [];
    const sug = $id('cmp-code-suggest');
    if (!sug) return;
    if (!hits.length) {
      sug.hidden = true;
      return;
    }
    sug.hidden = false;
    sug.innerHTML = hits.map((h) => `
      <button type="button" class="bt-suggest-item" data-code="${h.code}" data-name="${h.name}">
        <span>${h.code}</span> ${h.name}
      </button>`).join('');
    sug.querySelectorAll('.bt-suggest-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        addChip(btn.getAttribute('data-code'), btn.getAttribute('data-name'));
        sug.hidden = true;
        if ($id('cmp-code-input')) $id('cmp-code-input').value = '';
      });
    });
  }

  function bindControls() {
    if (bound) return;
    bound = true;

    document.querySelectorAll('[data-cmp-mode]').forEach((btn) => {
      btn.addEventListener('click', () => setMode(btn.getAttribute('data-cmp-mode')));
    });
    document.querySelectorAll('[data-cmp-pick]').forEach((btn) => {
      btn.addEventListener('click', () => switchPickMode(btn.getAttribute('data-cmp-pick') || 'hot'));
    });

    $id('cmp-add-btn')?.addEventListener('click', () => {
      const c = normalizeCode($id('cmp-code-input')?.value);
      if (isValidAshare(c)) {
        addChip(c, resolveName(c));
        if ($id('cmp-code-input')) $id('cmp-code-input').value = '';
      } else {
        window.StockQPro?.App?.toast?.('請輸入有效代碼', 'er');
      }
    });
    $id('cmp-code-input')?.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(onCodeInput, 200);
    });
    $id('cmp-code-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const c = normalizeCode($id('cmp-code-input')?.value);
        if (isValidAshare(c)) {
          addChip(c, resolveName(c));
          if ($id('cmp-code-input')) $id('cmp-code-input').value = '';
        }
      }
    });
    $id('cmp-search-btn')?.addEventListener('click', runSearch);
    $id('cmp-search-q')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runSearch();
    });
    $id('cmp-clear-chips')?.addEventListener('click', () => {
      clearChips();
      state.strategyResultsByCode = {};
      state.strategySessionActive = false;
      state.stockComparison = null;
      state.correlation = null;
      state.excessReturn = null;
      state.indexOverlay = null;
      clearCharts();
      syncCompareHash();
    });
    $id('cmp-copy-codes')?.addEventListener('click', copyCodesToClipboard);
    $id('cmp-fill-watch')?.addEventListener('click', fillWatchlistToChips);
    $id('cmp-share-link')?.addEventListener('click', shareCompareLink);
    $id('cmp-refresh')?.addEventListener('click', () => {
      if (state.running) return;
      if (state.mode === 'stocks' && state.chips.length >= 2) runStocks();
      else if (state.mode === 'strategies' && primaryCode()) runStrategies();
      else window.StockQPro?.App?.toast?.('請先選擇標的並執行對比', 'inf');
    });
    $id('cmp-preset-save')?.addEventListener('click', saveCurrentAsPreset);
    $id('cmp-use-bt')?.addEventListener('click', () => {
      const sym = window.StockQPro?.backtestSymbol;
      const c = sym?.getSymbol?.() || '';
      if (c) addChip(c, sym?.normalizeCode ? resolveName(c) : '');
      else window.StockQPro?.App?.toast?.('請先在回測頁選擇標的', 'inf');
    });
    $id('cmp-pick-assets-nav')?.addEventListener('click', () => {
      window.StockQPro?.App?.nav?.('assets', { syncHash: true });
    });

    $id('cmp-run')?.addEventListener('click', run);
    $id('cmp-export-png')?.addEventListener('click', exportChartPng);
    $id('cmp-export-csv')?.addEventListener('click', exportCsv);

    ['cmp-metric', 'cmp-sort', 'cmp-topn', 'cmp-chart-type'].forEach((id) => {
      $id(id)?.addEventListener('change', () => {
        if (state.strategyResults?.length) renderStrategies();
      });
    });
    ['cmp-strat-q', 'cmp-strat-min-trades'].forEach((id) => {
      $id(id)?.addEventListener('input', () => {
        if (state.strategyResults?.length) renderStrategies();
      });
      $id(id)?.addEventListener('change', () => {
        if (state.strategyResults?.length) renderStrategies();
      });
    });
    $id('cmp-days')?.addEventListener('change', () => {
      syncCompareHash();
      if (state.stockComparison) runStocks();
    });
    $id('cmp-index')?.addEventListener('change', () => {
      syncCompareHash();
      if (state.stockComparison) runStocks();
    });
    ['cmp-normalize', 'cmp-vs-benchmark', 'cmp-stock-chart', 'cmp-stock-sort'].forEach((id) => {
      $id(id)?.addEventListener('change', () => {
        if (state.stockComparison) {
          if (id === 'cmp-vs-benchmark') runStocks();
          else renderStocks();
        }
      });
    });
  }

  async function init() {
    bindControls();
    loadChipsFromStorage();
    parseCompareFromHash();
    if (!state.chips.length) {
      addChip('600519', '貴州茅台', { silent: true, skipEnqueue: true });
    } else {
      renderChips();
    }
    await Promise.all([loadNames(), loadStrategyDisplayNames()]);
    setMode(state.mode);
    await renderHot();
    clearCharts();
    updateSummaryBadge();
    setTimeout(() => chart?.resize(), 80);
  }

  function onShow() {
    parseCompareFromHash();
    renderChips();
    renderPresets();
    setMode(state.mode);
    if (state.stockComparison) renderStocks();
    setTimeout(() => {
      chart?.resize();
      corrChart?.resize();
    }, 60);
  }

  function unload() {
    try { window.StockQPro?.ECharts?.disposePage?.('compare'); } catch (_) {}
    chart = null;
    corrChart = null;
  }

  window.addEventListener('resize', () => {
    chart?.resize();
    corrChart?.resize();
  });

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.addEventListener('stockq:allocation-import-compare', (ev) => {
    const codes = ev.detail?.codes;
    const names = ev.detail?.names || {};
    if (!Array.isArray(codes) || !codes.length) return;
    state.mode = 'stocks';
    const modeBtn = document.querySelector('[data-cmp-mode="stocks"]');
    if (modeBtn) modeBtn.click();
    state.chips = [];
    codes.forEach((code) => {
      const c = normalizeCode(code);
      const nm = names[code] || names[c] || resolveName(c);
      addChip(c, nm, { silent: true, skipEnqueue: true });
    });
    renderChips();
    window.StockQPro?.App?.toast?.(`已載入 ${state.chips.length} 檔至多股對比（含港股/美股）`, 'ok');
  });

  window.StockQPro.pages.compare = {
    init,
    onShow,
    unload,
    applyFromHash: parseCompareFromHash,
  };
})();
