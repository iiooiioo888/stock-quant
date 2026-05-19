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

  init() {
    const tabs = document.getElementById('signalsTabs');
    if (!tabs) return;
    tabs.addEventListener('click', e => {
      const btn = e.target.closest('button[data-stab]');
      if (!btn) return;
      tabs.querySelectorAll('button').forEach(b => b.classList.remove('a'));
      btn.classList.add('a');
      this._currentTab = btn.dataset.stab;
      // toggle sub-tab divs
      ['current', 'history', 'strength'].forEach(t => {
        const el = document.getElementById('stab-' + t);
        if (el) el.classList.toggle('h', t !== this._currentTab);
      });
    });
  },

  load() {
    // called when signals tab is shown
  },

  async loadCurrent() {
    const container = document.getElementById('currentSignals');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

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
    container.innerHTML = signals.map(s => {
      const strategies = (s.strategies || []).map(st => {
        const cls = st.signal === 'buy' ? 'on' : st.signal === 'sell' ? 'off' : 'cfg';
        return `<span class="chip ${cls}">${st.strategy}: ${st.signal}</span>`;
      }).join(' ');
      return `<div style="padding:10px;margin-bottom:8px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <strong>${s.code}</strong>
          <span style="font-size:10px;color:var(--text-dim)">${s.triggered_at || ''}</span>
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin:4px 0">${s.name || ''} · 信號強度: <strong>${s.strength || 0}</strong></div>
        <div>${strategies}</div>
      </div>`;
    }).join('');
  },

  async loadHistory() {
    const container = document.getElementById('historySignals');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getSignalHistory('', '', 30);
    if (!d || !d.success) {
      container.innerHTML = '<p style="color:var(--text-dim)">無歷史信號</p>';
      return;
    }
    const signals = d.signals || [];
    if (!signals.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">無歷史信號記錄</p>';
      return;
    }
    container.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>時間</th><th>代碼</th><th>策略</th><th>信號</th><th>價格</th><th>強度</th></tr></thead>
      <tbody>${signals.map(s => `<tr>
        <td style="font-size:10px">${s.triggered_at || ''}</td>
        <td>${s.code || ''}</td>
        <td>${s.strategy || ''}</td>
        <td><span class="chip ${s.signal === 'buy' ? 'on' : s.signal === 'sell' ? 'off' : 'cfg'}">${s.signal || '-'}</span></td>
        <td class="r">${s.price != null ? s.price.toFixed(2) : '-'}</td>
        <td class="r">${s.strength || '-'}</td>
      </tr>`).join('')}</tbody>
    </table></div>`;

    // 繪製信號時間線圖
    this._drawSignalTimeline(signals);
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

    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 計算中...</p>';

    // 支持多個股票（逗號分隔）
    const codes = code.split(',').map(s => s.trim()).filter(Boolean);
    let html = '';
    for (const c of codes) {
      const d = await Api.getSignalStrength(c);
      if (!d || !d.success) {
        html += `<div style="padding:10px;color:var(--text-dim)">${c}: 獲取失敗</div>`;
        continue;
      }
      const strength = d.strength || 0;
      const cls = strength > 50 ? 'gn' : strength < -50 ? 'rd' : 'bl';
      const label = strength > 50 ? '強烈看多' : strength > 20 ? '看多' : strength < -50 ? '強烈看空' : strength < -20 ? '看空' : '中性';
      html += `<div style="padding:10px;margin-bottom:8px;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <strong>${c}</strong>
          <span class="b ${cls}" style="font-size:18px">${strength}</span>
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px">
          方向: <strong class="${cls}">${label}</strong> · 信號數: ${d.signals_count || 0} · ${d.updated_at || ''}
        </div>
      </div>`;
    }
    container.innerHTML = html || '<p style="color:var(--text-dim)">無數據</p>';

    // 繪製信號強度儀表盤
    this._drawStrengthGauge(codes);
  },

  /**
   * 信號強度儀表盤 — 多股票強度對比雷達圖
   */
  async _drawStrengthGauge(codes) {
    if (!codes || codes.length < 2) return; // 至少 2 只股票才畫圖

    // 確保容器存在
    let chartDiv = document.getElementById('signalsStrengthChart');
    if (!chartDiv) {
      const container = document.getElementById('strengthSignals');
      if (!container) return;
      chartDiv = document.createElement('div');
      chartDiv.id = 'signalsStrengthChart';
      chartDiv.className = 'cw mt-md';
      chartDiv.innerHTML = '<canvas id="sigStrengthRadar"></canvas>';
      container.appendChild(chartDiv);
    }

    // 獲取每只股票的信號數據
    const datasets = [];
    const labels = ['強度', '信號數', '看多程度'];
    const colors = ['#38bdf8', '#22c55e', '#f59e0b', '#ef4444', '#a78bfa'];

    for (let i = 0; i < Math.min(codes.length, 5); i++) {
      const c = codes[i];
      try {
        const d = await Api.getSignalStrength(c);
        if (!d || !d.success) continue;
        const s = d.strength || 0;
        const count = d.signals_count || 0;
        const bullish = Math.max(0, s); // 正值表示看多
        datasets.push({
          label: c,
          data: [Math.abs(s), Math.min(count, 100), bullish],
          borderColor: colors[i % colors.length],
          backgroundColor: colors[i % colors.length] + '20',
          borderWidth: 1.5,
        });
      } catch {}
    }

    if (datasets.length >= 2) {
      Charts.drawRadarChart('sigStrengthRadar', labels, datasets);
    }
  },
};

window.Signals = Signals;
