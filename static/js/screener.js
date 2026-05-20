/**
 * screener.js — 篩選器 Tab
 */

const Screener = {
  async run() {
    const filters = {};

    if (document.getElementById('scrMA').checked) filters.ma_bullish = true;
    if (document.getElementById('scrVol').checked) {
      filters.volume_surge = {
        days: 5,
        ratio: parseFloat(document.getElementById('scrVolRatio').value) || 2.0,
      };
    }
    if (document.getElementById('scrHigh').checked) {
      filters.near_52w_high = {
        pct: parseFloat(document.getElementById('scrHighPct').value) || 5,
      };
    }
    if (document.getElementById('scrChange').checked) {
      filters.price_change_ndays = {
        days: parseInt(document.getElementById('scrChangeDays').value) || 5,
        min_pct: parseFloat(document.getElementById('scrChangePct').value) || 5,
      };
    }
    if (document.getElementById('scrAboveMA').checked) {
      filters.above_ma = {
        period: parseInt(document.getElementById('scrMAPeriod').value) || 20,
      };
    }

    if (Object.keys(filters).length === 0) return Utils.toast('請至少選擇一個篩選條件');

    const btn = document.getElementById('scrBtn');
    Utils.btnLoading(btn, true, '篩選中...');

    const d = await Api.screenStocks(filters);
    Utils.btnLoading(btn, false, '開始篩選');

    if (!d) return Utils.toast('失敗', 3000, 'error');

    const stocks = d.results || [];
    document.getElementById('scrCount').textContent = stocks.length + ' 只';
    document.getElementById('scrTable').innerHTML = stocks.map(s =>
      `<tr>
        <td>${s.code}</td>
        <td>${s.name || '-'}</td>
        <td style="font-size:10px">${(s.filters_passed || s.matched || []).join(', ')}</td>
        <td><button class="btn s" style="padding:3px 8px;font-size:10px" onclick="Screener.addToWatchlist('${s.code}')">加入監控</button></td>
      </tr>`
    ).join('') || '<tr><td colspan="4" style="color:var(--text-muted);text-align:center">無匹配結果</td></tr>';

    document.getElementById('scrResult').classList.remove('h');

    // 繪製篩選結果圖表
    this._drawScreenerCharts(stocks, filters);

    Utils.toast(`篩選完成: ${stocks.length} 只匹配`);
  },

  /**
   * 篩選結果圖表 — 條件分佈 + 走勢概覽
   */
  _drawScreenerCharts(stocks, filters) {
    if (!stocks.length) return;

    // 1. 匹配條件分佈餅圖
    const filterCounts = {};
    stocks.forEach(s => {
      (s.filters_passed || s.matched || []).forEach(f => {
        filterCounts[f] = (filterCounts[f] || 0) + 1;
      });
    });
    if (Object.keys(filterCounts).length > 0) {
      const labels = Object.keys(filterCounts);
      const data = Object.values(filterCounts);
      // 確保 canvas 存在
      let chartSec = document.getElementById('scrChartSection');
      if (!chartSec) {
        const resultDiv = document.getElementById('scrResult');
        if (resultDiv) {
          chartSec = document.createElement('div');
          chartSec.id = 'scrChartSection';
          chartSec.className = 'g';
          chartSec.style.cssText = 'grid-template-columns:1fr 1fr;gap:14px;margin-top:14px';
          resultDiv.appendChild(chartSec);
        }
      }
      if (chartSec) {
        chartSec.innerHTML = `
          <div class="sec"><h2>📊 匹配條件分佈</h2><div class="cw"><canvas id="scrFilterPie"></canvas></div></div>
          <div class="sec"><h2>📈 迷你走勢</h2><div class="cw"><canvas id="scrMiniChart"></canvas></div></div>`;
        Charts.drawDoughnutChart('scrFilterPie', labels, data, '匹配次數');
      }
    }

    // 2. 獲取迷你走勢圖
    if (stocks.length > 0) {
      const codes = stocks.slice(0, 10).map(s => s.code);
      Api.get('/api/sparkline?codes=' + codes.join(',') + '&days=20').then(sp => {
        if (!sp || !sp.sparklines) return;
        const series = [];
        for (const [code, v] of Object.entries(sp.sparklines)) {
          if (v.prices && v.prices.length > 2) {
            // 歸一化為收益率
            const base = v.prices[0];
            series.push({
              label: code,
              data: v.prices.map(p => ((p / base) - 1) * 100),
              dates: v.dates || v.prices.map((_, i) => String(i)),
            });
          }
        }
        if (series.length) {
          Charts.drawLineChart('scrMiniChart', series);
        }
      });
    }
  },

  async addToWatchlist(code) {
    if (!confirm(`確定將 ${code} 加入監控列表？\n將依最新價自動生成突破/跌破預警。`)) return;
    const d = await Api.addToWatchlist(code, '', { auto_rule: true });
    if (d && d.success) {
      Utils.toast(d.message);
      // 如果在儀表盤有監控列表，嘗試刷新
      if (typeof Dashboard !== 'undefined') Dashboard.loadRules();
    } else {
      Utils.toast('添加失敗', 3000, 'error');
    }
  },
};

window.Screener = Screener;
