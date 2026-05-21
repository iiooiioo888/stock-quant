/**
 * signals.js — 信號 Tab（當前/歷史/強度）
 *
 * 修復：適配 index.html 的實際 DOM 結構
 *   - HTML 用 data-stab + stab-* 切換子 tab
 *   - 當前信號寫入 #currentSignals
 *   - 歷史信號寫入 #historySignals
 *   - 強度評分寫入 #strengthSignals
 */

const Signals = {
  _currentTab: 'current',
  _loadingKey: null,

  init() {
    const tabs = document.getElementById('signalsTabs');
    if (!tabs || tabs.dataset.signalsBound) return;
    tabs.dataset.signalsBound = '1';
    tabs.addEventListener('click', e => {
      const btn = e.target.closest('button[data-stab]');
      if (!btn) return;
      tabs.querySelectorAll('button').forEach(b => b.classList.remove('a'));
      btn.classList.add('a');
      this._currentTab = btn.dataset.stab;
      ['current', 'history', 'strength'].forEach(t => {
        const el = document.getElementById('stab-' + t);
        if (el) el.classList.toggle('h', t !== this._currentTab);
      });
      this._loadActiveSubTab();
    });
  },

  load() {
    ['current', 'history', 'strength'].forEach(t => {
      const el = document.getElementById('stab-' + t);
      if (el) el.classList.toggle('h', t !== this._currentTab);
    });
    this._loadActiveSubTab();
  },

  _loadActiveSubTab() {
    if (this._currentTab === 'current') this.loadCurrent();
    else if (this._currentTab === 'history') this.loadHistory();
    else if (this._currentTab === 'strength') this.loadStrength();
  },

  async loadCurrent() {
    const container = document.getElementById('currentSignals');
    if (!container) return;
    if (this._loadingKey === 'current') return;
    this._loadingKey = 'current';
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    try {
      const d = await Api.getCurrentSignals();
      if (!d || !d.success) {
        container.innerHTML = '<p style="color:var(--text-dim)">暫無信號</p>';
        return;
      }
      const signals = d.signals || [];
      if (!signals.length) {
        container.innerHTML = '<p style="color:var(--text-dim)">當前無活躍信號（可能非交易時段）</p>';
        return;
      }
      const SL = typeof SignalLabels !== 'undefined' ? SignalLabels : null;
      container.innerHTML = signals.map(s => {
        if (SL) return SL.renderStockCard(s);
        const strategies = (s.signals || s.strategies || []).map(st => {
          const cls = st.signal === 'buy' ? 'on' : st.signal === 'sell' ? 'off' : 'cfg';
          const stName = SL ? SL.strategyName(st.strategy, 'short') : st.strategy;
          const sigZh = SL ? SL.getSignal(st.signal).zh : st.signal;
          return `<span class="chip ${cls}">${stName}: ${sigZh}</span>`;
        }).join(' ');
        return `<div class="sig-stock-card">
        <strong>${s.code}</strong> · 信號強度: ${s.strength || 0}
        <div>${strategies}</div>
      </div>`;
      }).join('');
      if (typeof Utils !== 'undefined' && Utils.hydrateStockIcons) {
        Utils.hydrateStockIcons(container);
      }
    } finally {
      if (this._loadingKey === 'current') this._loadingKey = null;
    }
  },

  async loadHistory() {
    const container = document.getElementById('historySignals');
    if (!container) return;
    if (this._loadingKey === 'history') return;
    this._loadingKey = 'history';
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    try {
    const rawCodes = document.getElementById('sigCodes')?.value?.trim() || '';
    const filterCodes = rawCodes.split(',').map(s => s.trim()).filter(Boolean);
    let signals = [];
    if (filterCodes.length) {
      const batches = await Promise.all(
        filterCodes.map(c => Api.getSignalHistory(c, '', 30)),
      );
      for (const d of batches) {
        if (d?.success && d.signals?.length) signals.push(...d.signals);
      }
      signals.sort((a, b) => String(b.triggered_at || '').localeCompare(String(a.triggered_at || '')));
    } else {
      const d = await Api.getSignalHistory('', '', 30);
      if (!d || !d.success) {
        container.innerHTML = '<p style="color:var(--text-dim)">無歷史信號</p>';
        return;
      }
      signals = d.signals || [];
    }
    if (!signals.length && filterCodes.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">所選股票無歷史信號（僅記錄買/賣）</p>';
      return;
    }
    if (!signals.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">無歷史信號記錄</p>';
      return;
    }
    const SL = typeof SignalLabels !== 'undefined' ? SignalLabels : null;
    container.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>時間</th><th>代碼</th><th>策略</th><th>信號</th><th>說明</th><th>價格</th><th>強度</th></tr></thead>
      <tbody>${signals.map(s => {
        const stKey = s.strategy || '';
        const sigKey = s.signal || 'hold';
        const stMeta = SL ? SL.getStrategy(stKey) : { name: stKey, full: stKey };
        const sigMeta = SL ? SL.getSignal(sigKey) : { zh: sigKey, cls: 'cfg' };
        const hint = SL ? SL.hintFor(stKey, sigKey) : '';
        return `<tr>
        <td style="font-size:10px">${s.triggered_at || ''}</td>
        <td>${s.code || ''}</td>
        <td title="${SL ? SL._esc(stMeta.desc) : ''}">${stMeta.name}<span style="display:block;font-size:10px;color:var(--text-dim)">${stMeta.full !== stMeta.name ? stMeta.full : ''}</span></td>
        <td><span class="chip ${sigMeta.cls}">${sigMeta.zh}</span></td>
        <td style="font-size:10px;color:var(--text-muted);max-width:200px">${hint}</td>
        <td class="r">${s.price != null ? s.price.toFixed(2) : '-'}</td>
        <td class="r">${s.strength != null ? s.strength : '-'}</td>
      </tr>`;
      }).join('')}</tbody>
    </table></div>`;

    this._drawSignalTimeline(signals);
    } finally {
      if (this._loadingKey === 'history') this._loadingKey = null;
    }
  },

  /**
   * 信號時間線圖 — 最近 30 天的信號觸發時間線
   */
  _drawSignalTimeline(signals) {
    if (!signals || !signals.length) return;

    // 按日期分組，統計每天的買賣信號數
    const dayMap = {};
    signals.forEach(s => {
      const date = (s.triggered_at || '').substring(0, 10);
      if (!date) return;
      if (!dayMap[date]) dayMap[date] = { buy: 0, sell: 0 };
      if (s.signal === 'buy') dayMap[date].buy++;
      else if (s.signal === 'sell') dayMap[date].sell++;
    });

    const dates = Object.keys(dayMap).sort();
    if (!dates.length) return;

    const canvas = document.getElementById('signalsTimelineChart');
    if (!canvas) return;
    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = Charts.getThemeColors();
    const buyCounts = dates.map(d => dayMap[d].buy);
    const sellCounts = dates.map(d => -dayMap[d].sell);
    const shortDates = dates.map(d => d.substring(5));

    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: shortDates,
        datasets: [
          {
            label: '買入信號',
            data: buyCounts,
            backgroundColor: 'rgba(34,197,94,0.6)',
            borderColor: '#22c55e',
            borderWidth: 1,
          },
          {
            label: '賣出信號',
            data: sellCounts,
            backgroundColor: 'rgba(239,68,68,0.6)',
            borderColor: '#ef4444',
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: colors.text, font: { size: 10 } } },
          tooltip: {
            mode: 'index',
            intersect: false,
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
            callbacks: {
              label: function(ctx) {
                const v = Math.abs(ctx.raw);
                return ctx.dataset.label + ': ' + v + ' 個';
              },
            },
          },
        },
        scales: {
          x: { ticks: { color: colors.text, font: { size: 9 }, maxTicksLimit: 15 }, grid: { color: colors.grid } },
          y: {
            ticks: {
              color: colors.text,
              font: { size: 9 },
              callback: v => Math.abs(v),
            },
            grid: { color: colors.grid },
            title: { display: true, text: '信號數量', color: colors.text },
          },
        },
      },
    });
  },

  async loadStrength() {
    const container = document.getElementById('strengthSignals');
    if (!container) return;
    const code = document.getElementById('sigCodes')?.value?.trim();
    if (!code) return Utils.toast('請輸入股票代碼');
    if (this._loadingKey === 'strength') return;
    this._loadingKey = 'strength';

    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 計算中...</p>';

    try {
    const codes = code.split(',').map(s => s.trim()).filter(Boolean);
    const SL = typeof SignalLabels !== 'undefined' ? SignalLabels : null;
    const [cur, ...strengthRows] = await Promise.all([
      Api.getCurrentSignals(),
      ...codes.map(c => Api.getSignalStrength(c)),
    ]);
    const curByCode = Object.fromEntries((cur?.signals || []).map(x => [x.code, x]));
    let html = '';
    codes.forEach((c, i) => {
      let d = strengthRows[i];
      if (!d || !d.success) {
        html += `<div class="sig-stock-card"><p style="color:var(--text-dim)">${c}：獲取失敗</p></div>`;
        return;
      }
      if (!d.signals?.length && curByCode[c]) {
        const row = curByCode[c];
        d = {
          ...d,
          signals: row.signals || [],
          strength: row.strength ?? d.strength,
          updated_at: row.updated_at || d.updated_at,
          name: row.name,
        };
      }
      if (SL) {
        html += SL.renderStockCard({
          code: c,
          name: d.name,
          strength: d.strength,
          updated_at: d.updated_at,
          signals: d.signals || [],
        });
      } else {
        html += `<div class="sig-stock-card"><strong>${c}</strong> · ${d.strength}</div>`;
      }
    });
    container.innerHTML = html || '<p style="color:var(--text-dim)">無數據</p>';
    if (typeof Utils !== 'undefined' && Utils.hydrateStockIcons) {
      Utils.hydrateStockIcons(container);
    }

    this._drawStrengthGauge(codes, strengthRows);
    } finally {
      if (this._loadingKey === 'strength') this._loadingKey = null;
    }
  },

  /**
   * 信號強度儀表盤 — 多股票強度對比雷達圖
   */
  async _drawStrengthGauge(codes, prefetched = []) {
    if (!codes || codes.length < 2) return;

    if (!document.getElementById('sigStrengthRadar')) return;

    const datasets = [];
    const labels = ['強度', '信號數', '看多程度'];
    const colors = ['#38bdf8', '#22c55e', '#f59e0b', '#ef4444', '#a78bfa'];

    for (let i = 0; i < Math.min(codes.length, 5); i++) {
      const d = prefetched[i];
      if (!d || !d.success) continue;
      const s = d.strength || 0;
      const count = d.signals_count ?? (d.signals?.length || 0);
      const bullish = Math.max(0, s);
      datasets.push({
        label: codes[i],
        data: [Math.abs(s), Math.min(count, 100), bullish],
        borderColor: colors[i % colors.length],
        backgroundColor: colors[i % colors.length] + '20',
        borderWidth: 1.5,
      });
    }

    if (datasets.length >= 2) {
      Charts.drawRadarChart('sigStrengthRadar', labels, datasets);
    }
  },
};

window.Signals = Signals;
