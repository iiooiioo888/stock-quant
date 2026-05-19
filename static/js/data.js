/**
 * data.js — 數據 Tab
 *
 * 功能：
 *   - 板塊行情（表格 + 條形圖）
 *   - 板塊輪動分析（🔥 熱點 / ❄️ 退潮）
 *   - 板塊全景熱力圖（Canvas treemap）
 *   - 資金流向、北向資金、龍虎榜、基本面篩選
 *   - 板塊詳情彈窗（成分股 + 趨勢圖 + 資金流向）
 */

const Data = {
  _currentTab: 'sectors',

  init() {
    const tabs = document.getElementById('dataTabs');
    if (!tabs) return;
    tabs.addEventListener('click', e => {
      const btn = e.target.closest('button[data-dtab]');
      if (!btn) return;
      tabs.querySelectorAll('button').forEach(b => b.classList.remove('a'));
      btn.classList.add('a');
      this._currentTab = btn.dataset.dtab;
      // toggle sub-tab divs
      ['sectors', 'rotation', 'heatmap', 'capital', 'north', 'dragon', 'fundamental', 'basics'].forEach(t => {
        const el = document.getElementById('dtab-' + t);
        if (el) el.classList.toggle('h', t !== this._currentTab);
      });
    });
  },

  load() {
    // called when data tab is shown; user clicks button to load
  },

  // ============================================================
  // 板塊行情（增強版）
  // ============================================================

  async loadSectors() {
    const container = document.getElementById('sectorData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getSectors('industry', 30);
    if (!d || !d.sectors || !d.sectors.length) {
      container.innerHTML = `<p style="color:var(--text-dim)">暫無板塊數據。東財接口可能暫時不可用，請稍後重試；若已保存過快照，可先點「數據」頁其他功能或收盤後執行快照。</p>
        <button class="btn s mt-sm" onclick="Data.loadSectors()">🔄 重試</button>`;
      return;
    }
    let cacheHint = '';
    if (d.hint) {
      cacheHint = `<p style="font-size:11px;color:#f59e0b;margin-bottom:8px">${d.hint}</p>`;
    } else if (d.from_snapshot && d.snapshot_date) {
      cacheHint = `<p style="font-size:11px;color:var(--text-dim);margin-bottom:8px">📦 使用本地快照（${d.snapshot_date}），實時行情暫不可用</p>`;
    } else if (d.source === 'eastmoney_http') {
      cacheHint = `<p style="font-size:11px;color:var(--text-dim);margin-bottom:8px">📡 數據來源：東財直連</p>`;
    } else if (d.source === 'local_kline') {
      cacheHint = `<p style="font-size:11px;color:var(--text-dim);margin-bottom:8px">📊 離線估算（成分股 + 本地日K），非實時行情</p>`;
    }
    container.innerHTML = `${cacheHint}<div class="table-wrap"><table>
      <thead><tr><th>板塊</th><th>漲跌幅</th><th>領漲股</th><th>成交額</th><th>漲/跌家數</th></tr></thead>
      <tbody>${d.sectors.map(s => `<tr>
        <td><strong><a href="javascript:void(0)" onclick="Data.showSectorDetail('${s.name}')" style="color:var(--accent);text-decoration:none">${s.name || '-'}</a></strong></td>
        <td class="r"><span class="b ${Utils.badgeClass(s.change_pct)}">${Utils.formatPct(s.change_pct)}</span></td>
        <td>${s.leader || '-'}</td>
        <td class="r">${s.amount ? Utils.formatLargeNum(s.amount) : '-'}</td>
        <td class="r"><span style="color:#22c55e">${s.rise_count || 0}</span> / <span style="color:#ef4444">${s.fall_count || 0}</span></td>
      </tr>`).join('')}</tbody>
    </table></div>`;

    // 繪製板塊漲跌條形圖
    this._drawSectorBarChart(d.sectors);
  },

  /**
   * 板塊漲跌條形圖 — 行業板塊漲跌幅排行
   */
  _drawSectorBarChart(sectors) {
    if (!sectors || !sectors.length) return;

    const sorted = [...sectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
    const top5 = sorted.slice(0, 5);
    const bottom5 = sorted.slice(-5).reverse();
    const all = [...top5, ...bottom5];
    const seen = new Set();
    const unique = all.filter(s => {
      if (seen.has(s.name)) return false;
      seen.add(s.name);
      return true;
    }).slice(0, 10);

    const labels = unique.map(s => s.name || '-');
    const data = unique.map(s => s.change_pct || 0);

    Charts.drawHorizontalBarChart('dataSectorChart', labels, data, '漲跌幅 (%)');
  },

  // ============================================================
  // 板塊輪動分析
  // ============================================================

  async loadSectorRotation() {
    const container = document.getElementById('rotationData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 分析中...</p>';

    const days = parseInt(document.getElementById('rotationDays')?.value) || 10;
    const d = await Api.getSectorRotation(days);

    if (!d || !d.rotation || !d.rotation.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">板塊輪動需要至少 2 天數據。請先保存每日快照。</p>';
      return;
    }

    const rotation = d.rotation;
    // 分為上升和下降
    const rising = rotation.filter(r => r.rank_change > 0).slice(0, 15);
    const falling = rotation.filter(r => r.rank_change < 0).slice(-15).reverse();

    let html = '';

    // 🔥 新興熱點
    if (rising.length) {
      html += `<div class="sec"><h3>🔥 新興熱點（排名上升）</h3>
        <div class="table-wrap"><table>
        <thead><tr><th>板塊</th><th>排名變化</th><th>當前排名</th><th>前期排名</th><th>平均漲跌</th><th>成交額</th></tr></thead>
        <tbody>${rising.map(r => `<tr>
          <td><strong><a href="javascript:void(0)" onclick="Data.showSectorDetail('${r.name}')" style="color:var(--accent);text-decoration:none">${r.name}</a></strong></td>
          <td class="r"><span class="b" style="background:rgba(34,197,94,0.15);color:#22c55e">↑${r.rank_change}</span></td>
          <td class="r">${r.current_rank}</td>
          <td class="r">${r.prev_rank}</td>
          <td class="r"><span class="b ${Utils.badgeClass(r.avg_change_pct)}">${Utils.formatPct(r.avg_change_pct)}</span></td>
          <td class="r">${r.amount ? Utils.formatLargeNum(r.amount) : '-'}</td>
        </tr>`).join('')}</tbody></table></div></div>`;
    }

    // ❄️ 退潮板塊
    if (falling.length) {
      html += `<div class="sec"><h3>❄️ 退潮板塊（排名下降）</h3>
        <div class="table-wrap"><table>
        <thead><tr><th>板塊</th><th>排名變化</th><th>當前排名</th><th>前期排名</th><th>平均漲跌</th><th>成交額</th></tr></thead>
        <tbody>${falling.map(r => `<tr>
          <td><strong><a href="javascript:void(0)" onclick="Data.showSectorDetail('${r.name}')" style="color:var(--accent);text-decoration:none">${r.name}</a></strong></td>
          <td class="r"><span class="b" style="background:rgba(239,68,68,0.15);color:#ef4444">↓${Math.abs(r.rank_change)}</span></td>
          <td class="r">${r.current_rank}</td>
          <td class="r">${r.prev_rank}</td>
          <td class="r"><span class="b ${Utils.badgeClass(r.avg_change_pct)}">${Utils.formatPct(r.avg_change_pct)}</span></td>
          <td class="r">${r.amount ? Utils.formatLargeNum(r.amount) : '-'}</td>
        </tr>`).join('')}</tbody></table></div></div>`;
    }

    // 條形圖
    html += '<div class="sec"><h3>📊 排名變化</h3><div class="cw" style="height:400px"><canvas id="rotationChart"></canvas></div></div>';

    container.innerHTML = html;

    // 繪製排名變化條形圖
    const top20 = rotation.slice(0, 20);
    const labels = top20.map(r => r.name);
    const data = top20.map(r => r.rank_change);
    Charts.drawHorizontalBarChart('rotationChart', labels, data, '排名變化');
  },

  // ============================================================
  // 板塊全景熱力圖
  // ============================================================

  async loadSectorHeatmap() {
    const container = document.getElementById('heatmapData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getSectorHeatmap('industry');
    if (!d || !d.sectors || !d.sectors.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">暫無板塊數據</p>';
      return;
    }

    container.innerHTML = '<div class="cw" style="position:relative"><canvas id="sectorHeatmapCanvas" style="width:100%;cursor:pointer"></canvas></div>';

    this._drawTreemap(d.sectors);
  },

  /**
   * 用 Canvas 2D 繪製 treemap 熱力圖
   * 面積 = 成交額比例，顏色 = 漲跌幅（紅漲綠跌）
   */
  _drawTreemap(sectors) {
    const canvas = document.getElementById('sectorHeatmapCanvas');
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    const W = canvas.parentElement.clientWidth || 800;
    const H = 500;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // 過濾有效數據，按成交額排序
    const valid = sectors.filter(s => s.amount > 0 && s.name);
    if (!valid.length) {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('暫無數據', W / 2, H / 2);
      return;
    }

    valid.sort((a, b) => b.amount - a.amount);
    const totalAmount = valid.reduce((sum, s) => sum + s.amount, 0);

    // 計算 treemap 布局（簡單的 squarified 算法）
    const rects = this._squarify(valid, totalAmount, 0, 0, W, H);

    // 顏色映射
    const colors = Charts.getThemeColors();

    // 繪製每個方塊
    rects.forEach((rect, i) => {
      const s = valid[i];
      const changePct = s.change_pct || 0;

      // 顏色：紅漲綠跌，深淺代表幅度
      const intensity = Math.min(Math.abs(changePct) / 5, 1);
      let r, g, b;
      if (changePct >= 0) {
        r = Math.round(34 + (220 - 34) * intensity);
        g = Math.round(197 - 100 * intensity);
        b = Math.round(94 - 60 * intensity);
      } else {
        r = Math.round(239 - 100 * intensity);
        g = Math.round(68 + 50 * (1 - intensity));
        b = Math.round(68 + 50 * (1 - intensity));
      }

      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(rect.x, rect.y, rect.w, rect.h);

      // 邊框
      ctx.strokeStyle = 'rgba(0,0,0,0.2)';
      ctx.lineWidth = 1;
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);

      // 文字（只在方塊夠大時顯示）
      if (rect.w > 40 && rect.h > 25) {
        ctx.fillStyle = '#fff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        const fontSize = Math.max(9, Math.min(13, rect.w / 8));
        ctx.font = `bold ${fontSize}px sans-serif`;
        const nameText = s.name.length > 6 ? s.name.slice(0, 6) + '..' : s.name;
        ctx.fillText(nameText, rect.x + rect.w / 2, rect.y + rect.h / 2 - fontSize / 2 - 2);

        ctx.font = `${fontSize - 1}px sans-serif`;
        ctx.fillText(Utils.formatPct(changePct), rect.x + rect.w / 2, rect.y + rect.h / 2 + fontSize / 2 + 2);
      }

      // 保存 rect 信息供點擊用
      rect.sectorName = s.name;
    });

    // 點擊顯示詳情
    canvas._treemapRects = rects;
    canvas.onclick = (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      for (const r of canvas._treemapRects) {
        if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
          this.showSectorDetail(r.sectorName);
          break;
        }
      }
    };

    // Tooltip
    canvas.onmousemove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      let found = false;
      for (const r of canvas._treemapRects) {
        if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
          canvas.title = `${r.sectorName}: ${Utils.formatPct(r.changePct)}`;
          found = true;
          break;
        }
      }
      if (!found) canvas.title = '';
    };
  },

  /**
   * Squarified Treemap 布局算法
   */
  _squarify(items, totalValue, x, y, w, h) {
    const rects = [];
    if (!items.length) return rects;

    // 按值分配面積
    const areas = items.map(it => (it.amount / totalValue) * w * h);

    let remaining = [...areas.map((area, i) => ({ area, index: i }))];
    let cx = x, cy = y, cw = w, ch = h;

    while (remaining.length > 0) {
      const isWide = cw >= ch;
      const side = isWide ? ch : cw;

      // 找到最佳行
      let row = [remaining[0]];
      let bestRatio = this._worstRatio(row, side);
      let bestRow = [...row];

      for (let i = 1; i < remaining.length; i++) {
        row.push(remaining[i]);
        const ratio = this._worstRatio(row, side);
        if (ratio <= bestRatio) {
          bestRatio = ratio;
          bestRow = [...row];
        } else {
          break;
        }
      }

      // 布局這一行
      const rowArea = bestRow.reduce((s, r) => s + r.area, 0);
      const rowLen = rowArea / side;

      let offset = 0;
      bestRow.forEach(r => {
        const itemLen = r.area / rowLen;
        if (isWide) {
          rects[r.index] = { x: cx, y: cy + offset, w: rowLen, h: itemLen };
        } else {
          rects[r.index] = { x: cx + offset, y: cy, w: itemLen, h: rowLen };
        }
        offset += itemLen;
      });

      // 更新剩餘區域
      if (isWide) {
        cx += rowLen;
        cw -= rowLen;
      } else {
        cy += rowLen;
        ch -= rowLen;
      }

      remaining = remaining.slice(bestRow.length);
    }

    return rects;
  },

  _worstRatio(row, side) {
    const totalArea = row.reduce((s, r) => s + r.area, 0);
    const rowLen = totalArea / side;
    let worst = 0;
    row.forEach(r => {
      const itemLen = r.area / rowLen;
      const ratio = Math.max(rowLen / itemLen, itemLen / rowLen);
      worst = Math.max(worst, ratio);
    });
    return worst;
  },

  // ============================================================
  // 板塊詳情彈窗
  // ============================================================

  async showSectorDetail(name) {
    // 創建彈窗
    let modal = document.getElementById('sectorDetailModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'sectorDetailModal';
      modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
      modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
      document.body.appendChild(modal);
    }

    const colors = Charts.getThemeColors();
    modal.innerHTML = `<div style="background:${colors.bg};border-radius:12px;max-width:900px;width:95%;max-height:85vh;overflow-y:auto;padding:24px;box-shadow:0 20px 60px rgba(0,0,0,0.4);border:1px solid ${colors.tooltipBorder}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2 style="margin:0;color:${colors.tooltipText}">📊 ${name}</h2>
        <button onclick="document.getElementById('sectorDetailModal').remove()" style="background:none;border:none;font-size:24px;cursor:pointer;color:${colors.text}">✕</button>
      </div>
      <div id="sectorDetailContent"><p style="color:${colors.text}"><span class="ld"></span> 載入中...</p></div>
    </div>`;

    // 並行加載數據
    const [stocksData, trendData, flowData] = await Promise.all([
      Api.getSectorStocks(name, 'industry'),
      Api.getSectorTrend(name, 20),
      Api.getSectorCapitalFlow(name),
    ]);

    const content = document.getElementById('sectorDetailContent');
    if (!content) return;

    let html = '';

    // 趨勢圖
    html += '<div style="margin-bottom:20px"><h3 style="margin:0 0 8px 0">📈 近20天走勢</h3><div style="height:200px"><canvas id="sectorDetailTrendChart"></canvas></div></div>';

    // 資金流向
    if (flowData && flowData.flows && flowData.flows.length) {
      const flow = flowData.flows[0];
      html += `<div style="margin-bottom:20px"><h3 style="margin:0 0 8px 0">💰 資金流向</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px">
        <div style="padding:8px;border-radius:8px;background:rgba(34,197,94,0.1);text-align:center">
          <div style="font-size:11px;color:${colors.text}">主力淨流入</div>
          <div style="font-weight:bold;color:${flow.main_net >= 0 ? '#22c55e' : '#ef4444'}">${flow.main_net ? Utils.formatLargeNum(flow.main_net) : '-'}</div>
        </div>
        <div style="padding:8px;border-radius:8px;background:rgba(56,189,248,0.1);text-align:center">
          <div style="font-size:11px;color:${colors.text}">超大單</div>
          <div style="font-weight:bold;color:${flow.super_large_net >= 0 ? '#22c55e' : '#ef4444'}">${flow.super_large_net ? Utils.formatLargeNum(flow.super_large_net) : '-'}</div>
        </div>
        <div style="padding:8px;border-radius:8px;background:rgba(167,139,250,0.1);text-align:center">
          <div style="font-size:11px;color:${colors.text}">大單</div>
          <div style="font-weight:bold;color:${flow.large_net >= 0 ? '#22c55e' : '#ef4444'}">${flow.large_net ? Utils.formatLargeNum(flow.large_net) : '-'}</div>
        </div>
        </div></div>`;
    }

    // 成分股列表
    if (stocksData && stocksData.stocks && stocksData.stocks.length) {
      html += `<div><h3 style="margin:0 0 8px 0">📋 成分股（${stocksData.total} 只）</h3>
        <div class="table-wrap" style="max-height:300px;overflow-y:auto"><table>
        <thead><tr><th>代碼</th><th>名稱</th><th>最新價</th><th>漲跌幅</th><th>成交額</th></tr></thead>
        <tbody>${stocksData.stocks.slice(0, 50).map(s => `<tr>
          <td>${s.code || '-'}</td>
          <td>${s.name || '-'}</td>
          <td class="r">${s.price ? s.price.toFixed(2) : '-'}</td>
          <td class="r"><span class="b ${Utils.badgeClass(s.change_pct)}">${Utils.formatPct(s.change_pct)}</span></td>
          <td class="r">${s.amount ? Utils.formatLargeNum(s.amount) : '-'}</td>
        </tr>`).join('')}</tbody></table></div></div>`;
    }

    content.innerHTML = html;

    // 繪製趨勢圖
    if (trendData && trendData.trend && trendData.trend.length) {
      this._drawTrendChart(trendData.trend);
    }
  },

  /**
   * 繪製板塊趨勢折線圖
   */
  _drawTrendChart(trend) {
    const canvas = document.getElementById('sectorDetailTrendChart');
    if (!canvas || !trend.length) return;

    const old = Chart.getChart(canvas);
    if (old) old.destroy();

    const colors = Charts.getThemeColors();
    const labels = trend.map(t => Utils.shortDate(t.date));
    const data = trend.map(t => t.change_pct);

    const bgColors = data.map(v => v >= 0 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)');
    const bdColors = data.map(v => v >= 0 ? '#22c55e' : '#ef4444');

    new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: '漲跌幅 (%)',
          data,
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,0.1)',
          fill: true,
          tension: 0.3,
          pointRadius: 4,
          pointBackgroundColor: bdColors,
          pointBorderColor: bdColors,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: colors.tooltipBg,
            borderColor: colors.tooltipBorder,
            borderWidth: 1,
            titleColor: colors.tooltipText,
            bodyColor: colors.tooltipBody,
            callbacks: {
              label: (ctx) => {
                const t = trend[ctx.dataIndex];
                return `漲跌幅: ${t.change_pct}% | 排名: #${t.rank}`;
              },
            },
          },
        },
        scales: {
          x: { ticks: { color: colors.text, font: { size: 9 } }, grid: { color: colors.grid } },
          y: {
            ticks: { color: colors.text, font: { size: 9 }, callback: v => v.toFixed(1) + '%' },
            grid: { color: colors.grid },
          },
        },
      },
    });
  },

  // ============================================================
  // 原有功能（保留）
  // ============================================================

  async loadCapitalFlow() {
    const container = document.getElementById('capitalFlowData');
    if (!container) return;
    const code = document.getElementById('cfCode')?.value?.trim();
    if (!code) return Utils.toast('請輸入股票代碼');
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getCapitalFlow(code, 20);
    if (!d || !d.flows || !d.flows.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">暫無資金流向數據</p>';
      return;
    }
    container.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>日期</th><th>主力淨流入</th><th>超大單</th><th>大單</th><th>中單</th><th>小單</th></tr></thead>
      <tbody>${d.flows.map(f => `<tr>
        <td>${f.date || '-'}</td>
        <td class="r"><span class="b ${Utils.badgeClass(f.main_net)}">${Utils.formatLargeNum(f.main_net)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(f.super_large)}">${Utils.formatLargeNum(f.super_large)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(f.large)}">${Utils.formatLargeNum(f.large)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(f.medium)}">${Utils.formatLargeNum(f.medium)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(f.small)}">${Utils.formatLargeNum(f.small)}</span></td>
      </tr>`).join('')}</tbody>
    </table></div>`;
  },

  async loadNorthFlow() {
    const container = document.getElementById('northFlowData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getNorthFlow(10);
    if (!d || !d.flows || !d.flows.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">暫無北向資金數據</p>';
      return;
    }
    container.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>日期</th><th>滬股通</th><th>深股通</th><th>合計</th></tr></thead>
      <tbody>${d.flows.map(f => `<tr>
        <td>${f.date || '-'}</td>
        <td class="r"><span class="b ${Utils.badgeClass(f.sh_net)}">${Utils.formatLargeNum(f.sh_net)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(f.sz_net)}">${Utils.formatLargeNum(f.sz_net)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(f.total_net)}">${Utils.formatLargeNum(f.total_net)}</span></td>
      </tr>`).join('')}</tbody>
    </table></div>`;
  },

  async loadDragonTiger() {
    const container = document.getElementById('dragonTigerData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getDragonTiger();
    if (!d || !d.records || !d.records.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">暫無龍虎榜數據</p>';
      return;
    }
    container.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>代碼</th><th>名稱</th><th>原因</th><th>買入額</th><th>賣出額</th><th>淨額</th><th>漲跌幅</th></tr></thead>
      <tbody>${d.records.map(r => `<tr>
        <td>${r.code || '-'}</td>
        <td>${r.name || '-'}</td>
        <td style="font-size:10px">${r.reason || '-'}</td>
        <td class="r">${r.buy_amount ? Utils.formatLargeNum(r.buy_amount) : '-'}</td>
        <td class="r">${r.sell_amount ? Utils.formatLargeNum(r.sell_amount) : '-'}</td>
        <td class="r"><span class="b ${Utils.badgeClass(r.net_amount)}">${r.net_amount ? Utils.formatLargeNum(r.net_amount) : '-'}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(r.change_pct)}">${Utils.formatPct(r.change_pct)}</span></td>
      </tr>`).join('')}</tbody>
    </table></div>`;
  },

  screenFundamentals() {
    const container = document.getElementById('fundamentalData');
    if (!container) return;
    const filters = {};
    const pe = parseFloat(document.getElementById('fundPE')?.value);
    const peMin = parseFloat(document.getElementById('fundPEMin')?.value);
    const pb = parseFloat(document.getElementById('fundPB')?.value);
    const roe = parseFloat(document.getElementById('fundROE')?.value);
    const eps = parseFloat(document.getElementById('fundEPS')?.value);
    const gross = parseFloat(document.getElementById('fundGross')?.value);
    const net = parseFloat(document.getElementById('fundNet')?.value);
    const debt = parseFloat(document.getElementById('fundDebt')?.value);
    const mv = parseFloat(document.getElementById('fundMV')?.value);
    if (!isNaN(pe)) filters.pe_max = pe;
    if (!isNaN(peMin)) filters.pe_min = peMin;
    if (!isNaN(pb)) filters.pb_max = pb;
    if (!isNaN(roe)) filters.roe_min = roe;
    if (!isNaN(eps)) filters.eps_min = eps;
    if (!isNaN(gross)) filters.gross_margin_min = gross;
    if (!isNaN(net)) filters.net_margin_min = net;
    if (!isNaN(debt)) filters.debt_max = debt;
    if (!isNaN(mv)) filters.mv_min = mv;
    if (!Object.keys(filters).length) {
      filters.pe_max = 20;
      filters.pb_max = 3;
      filters.roe_min = 15;
    }

    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 篩選中...</p>';

    Api.post('/api/data/fundamentals/screen', { filters }).then(d => {
      if (!d || !d.results || !d.results.length) {
        container.innerHTML = '<p style="color:var(--text-dim)">無符合條件的股票</p>';
        return;
      }
      container.innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>代碼</th><th>名稱</th><th>PE</th><th>PB</th><th>ROE</th><th>EPS</th><th>毛利率</th><th>淨利率</th><th>市值</th></tr></thead>
        <tbody>${d.results.map(r => `<tr>
          <td>${r.code || '-'}</td>
          <td>${r.name || '-'}</td>
          <td class="r">${r.pe_ttm != null ? Number(r.pe_ttm).toFixed(2) : (r.pe != null ? Number(r.pe).toFixed(2) : '-')}</td>
          <td class="r">${r.pb != null ? Number(r.pb).toFixed(2) : '-'}</td>
          <td class="r">${r.roe != null ? Number(r.roe).toFixed(2) + '%' : '-'}</td>
          <td class="r">${r.eps != null ? Number(r.eps).toFixed(2) : '-'}</td>
          <td class="r">${r.gross_margin != null ? Number(r.gross_margin).toFixed(1) + '%' : '-'}</td>
          <td class="r">${r.net_margin != null ? Number(r.net_margin).toFixed(1) + '%' : '-'}</td>
          <td class="r">${r.total_mv ? Utils.formatLargeNum(r.total_mv) + '億' : (r.market_cap ? Utils.formatLargeNum(r.market_cap) : '-')}</td>
        </tr>`).join('')}</tbody>
      </table></div>`;
    });
  },

  loadStockBasics() {
    const container = document.getElementById('basicsData');
    if (!container) return;
    const code = (document.getElementById('basicsCode')?.value || '').trim();
    const lookback = parseInt(document.getElementById('basicsLookback')?.value, 10) || 250;
    if (!code) {
      container.innerHTML = '<p style="color:var(--warn)">請輸入股票代碼</p>';
      return;
    }
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';
    Api.get(`/api/stocks/${encodeURIComponent(code)}/overview?lookback=${lookback}`).then(d => {
      const o = d?.overview;
      if (!o) {
        container.innerHTML = '<p style="color:var(--warn)">無數據</p>';
        return;
      }
      if (!o.has_kline) {
        container.innerHTML = `<p style="color:var(--warn)">${o.message || '本地無日 K'}</p>`;
        return;
      }
      const t = o.technical || {};
      const f = o.fundamentals || {};
      const fmt = (v, suf = '') => (v == null || v === '' ? '-' : v + suf);
      const rows = [
        ['代碼', o.code], ['名稱', o.name || '-'], ['數據區間', `${o.date_from} ~ ${o.date_to}`], ['K 線根數', o.bars],
        ['收盤', fmt(t.close)], ['漲跌%', fmt(t.change_pct, '%')], ['振幅%', fmt(t.amplitude_pct, '%')],
        ['MA5 / MA20 / MA60', `${fmt(t.ma5)} / ${fmt(t.ma20)} / ${fmt(t.ma60)}`],
        ['偏離 MA5%', fmt(t.vs_ma5_pct, '%')], ['偏離 MA20%', fmt(t.vs_ma20_pct, '%')],
        ['5日 / 20日 / 60日漲跌%', `${fmt(t.change_5d_pct, '%')} / ${fmt(t.change_20d_pct, '%')} / ${fmt(t.change_60d_pct, '%')}`],
        ['量比(對20日均)', fmt(t.volume_ratio)], ['年化波動%', fmt(t.volatility_annual_pct, '%')],
        ['區間高 / 低', `${fmt(t.high_lookback)} / ${fmt(t.low_lookback)}`],
        ['距高點%', fmt(t.pct_from_high, '%')], ['距低點%', fmt(t.pct_from_low, '%')],
      ];
      let fundBlock = '';
      if (f && Object.keys(f).length) {
        const fundRows = [
          ['PE(TTM)', fmt(f.pe_ttm)], ['PB', fmt(f.pb)], ['ROE%', fmt(f.roe, '%')],
          ['EPS', fmt(f.eps)], ['每股淨資', fmt(f.bvps)],
          ['總市值(億)', fmt(f.total_mv)], ['流通市值(億)', fmt(f.circulating_mv)],
          ['毛利率%', fmt(f.gross_margin, '%')], ['淨利率%', fmt(f.net_margin, '%')], ['負債率%', fmt(f.debt_ratio, '%')],
        ];
        fundBlock = `<h3 class="mt-md">基本面</h3><div class="table-wrap"><table><tbody>${fundRows.map(([k, v]) =>
          `<tr><td>${k}</td><td class="r">${v}</td></tr>`).join('')}</tbody></table></div>`;
      }
      container.innerHTML = `
        <div class="table-wrap"><table><tbody>${rows.map(([k, v]) =>
          `<tr><td>${k}</td><td class="r">${v}</td></tr>`).join('')}</tbody></table></div>
        ${fundBlock}`;
    }).catch(err => {
      container.innerHTML = `<p style="color:var(--danger)">${err.message || '載入失敗'}</p>`;
    });
  },
};

window.Data = Data;
