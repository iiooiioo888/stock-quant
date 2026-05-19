/**
 * dashboard.js — 儀表盤 Tab（含迷你走勢圖 + 多種圖表）
 */

const Dashboard = {
  _dataReady: false,
  _pollTimer: null,
  _pollCount: 0,
  _maxPolls: 30,

  async load() {
    await Promise.all([this.loadStats(), this.loadRules(), this.loadDashboardCharts()]);
    this._checkDataReady();
  },

  stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  },

  async _checkDataReady() {
    if (this._dataReady) return;
    this._pollCount++;
    if (this._pollCount > this._maxPolls) {
      this.stopPolling();
      this._showDataLoading('數據下載較慢，請手動刷新頁面查看');
      return;
    }
    const d = await Api.getHealth();
    if (!d) return;
    if (d.data_ready) {
      this._dataReady = true;
      this._hideDataLoading();
      this.stopPolling();
      return;
    }
    this._showDataLoading();
    if (!this._pollTimer) {
      this._pollTimer = setInterval(() => this._checkDataReady(), 10000);
    }
  },

  _showDataLoading(msg) {
    let el = document.getElementById('dataLoadingBanner');
    if (!el) {
      el = document.createElement('div');
      el.id = 'dataLoadingBanner';
      el.className = 'state-loading-banner';
      el.innerHTML = '<span class="ld"></span><div><strong>📊 首次啟動中</strong><br><span class="state-loading-sub">正在下載歷史數據和生成回測，約需 1-2 分鐘，數據就緒後自動刷新...</span></div>';
      const grid = document.getElementById('statsGrid');
      if (grid) grid.parentNode.insertBefore(el, grid);
    }
    if (msg) el.querySelector('.state-loading-sub').textContent = msg;
    el.style.display = 'flex';
  },

  _hideDataLoading() {
    const el = document.getElementById('dataLoadingBanner');
    if (el) el.style.display = 'none';
    this.loadStats();
    this.loadRules();
    this.loadDashboardCharts();
  },

  async loadStats() {
    const d = await Api.getHealth();
    if (!d) return;

    document.getElementById('statsGrid').innerHTML = `
      <div class="c stat-card"><h3>📊 監控股票</h3><div class="v bl">${d.total_stocks || 0}</div><div class="stat-hint">正在追蹤</div></div>
      <div class="c stat-card"><h3>📁 數據條數</h3><div class="v">${(d.total_klines || 0).toLocaleString()}</div><div class="stat-hint">歷史記錄</div></div>
      <div class="c stat-card"><h3>🔔 累計預警</h3><div class="v rd">${d.total_alerts || 0}</div><div class="stat-hint">已觸發</div></div>
      <div class="c stat-card"><h3>💾 數據庫</h3><div class="v">${d.db_size_mb || 0} MB</div><div class="stat-hint">存儲佔用</div></div>`;

    document.getElementById('sysStatus').textContent = '運行 ' + (d.uptime || '');
  },

  /**
   * 載入儀表盤所有新增圖表
   */
  async loadDashboardCharts() {
    await Promise.all([
      this._loadSparklineChart(),
      this._loadBacktestHistory(),
      this._loadSignalRadar(),
      this._loadSectorBars(),
      this._loadStrategyLeaderboard(),
    ]);
  },

  /**
   * 市場總覽迷你圖 — 組合淨值走勢
   */
  async _loadSparklineChart() {
    try {
      const d = await Api.get('/api/sparkline?codes=000001,600519,000858&days=60');
      if (!d || !d.sparklines) return;

      const series = [];
      for (const [code, sp] of Object.entries(d.sparklines)) {
        if (sp.prices && sp.prices.length > 2) {
          // 正規化為收益率
          const base = sp.prices[0];
          const normalized = sp.prices.map(p => ((p / base) - 1) * 100);
          series.push({ label: code, data: normalized, dates: sp.dates || normalized.map((_, i) => String(i)) });
        }
      }
      if (series.length) {
        Charts.drawLineChart('dashSparklineChart', series);
      }
    } catch (e) { /* ignore */ }
  },

  /**
   * 最近回測表現 — 最近 5 次回測的收益率柱狀圖
   */
  async _loadBacktestHistory() {
    try {
      const d = await Api.getBacktestHistory('', '', 5);
      if (!d || !d.results || !d.results.length) return;

      const results = d.results.reverse();
      const labels = results.map(r => (r.code || '').substring(0, 6) + '\n' + (r.strategy || ''));
      const data = results.map(r => r.total_return_pct || 0);

      Charts.drawBarChart('dashBacktestChart', data, labels, '收益率 (%)');
    } catch (e) { /* ignore */ }
  },

  /**
   * 信號強度分佈 — 雷達圖顯示 top 5 股票的多維信號強度
   */
  async _loadSignalRadar() {
    try {
      // 先嘗試調用 /api/signals/trading (task 中寫的路由)
      let d = await Api.get('/api/signals/trading');
      if (!d || !d.success) {
        // 備用：用 /api/signals/current
        d = await Api.getCurrentSignals();
      }
      if (!d) return;

      const signals = d.signals || d.data || [];
      if (!signals.length) return;

      // 取 top 5 股票
      const top5 = signals.slice(0, 5);
      const labels = ['動量', '趨勢', '波動率', '成交量', '均線'];

      const datasets = top5.map((s, i) => {
        // 從信號數據中提取多維強度，如果沒有則生成示例值
        const strength = s.strength || s.strength_score || 0;
        const strategies = s.strategies || [];
        const buyCount = strategies.filter(st => st.signal === 'buy').length;
        const sellCount = strategies.filter(st => st.signal === 'sell').length;
        const total = strategies.length || 1;

        return {
          label: s.code || s.name || '股票' + (i + 1),
          data: [
            Math.min(100, Math.abs(strength) * 1.2),
            buyCount / total * 100,
            Math.min(100, Math.abs(s.strength || 50)),
            Math.min(100, (s.volume_ratio || 1) * 30),
            Math.min(100, 50 + (s.strength || 0) * 0.5),
          ],
        };
      });

      Charts.drawRadarChart('dashSignalRadar', labels, datasets);
    } catch (e) { /* ignore */ }
  },

  /**
   * 板塊漲跌 Top 5 — 水平條形圖
   */
  async _loadSectorBars() {
    try {
      const d = await Api.getSectors('industry', 10);
      if (!d || !d.sectors || !d.sectors.length) return;

      // 分開漲幅前5和跌幅前5，按漲跌幅排序
      const sorted = [...d.sectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
      const top5 = sorted.slice(0, 5);
      const bottom5 = sorted.slice(-5).reverse();

      // 合併顯示
      const all = [...top5, ...bottom5];
      // 去重
      const seen = new Set();
      const unique = all.filter(s => {
        if (seen.has(s.name)) return false;
        seen.add(s.name);
        return true;
      }).slice(0, 10);

      const labels = unique.map(s => s.name || '-');
      const data = unique.map(s => s.change_pct || 0);

      Charts.drawHorizontalBarChart('dashSectorChart', labels, data, '漲跌幅 (%)');
    } catch (e) { /* ignore */ }
  },

  /**
   * 策略勝率排行 — top 10 策略的勝率和夏普
   */
  async _loadStrategyLeaderboard() {
    try {
      const d = await Api.getLeaderboard('sharpe', 10);
      if (!d || !d.strategies || !d.strategies.length) return;

      const strategies = d.strategies.slice(0, 10);
      const labels = strategies.map(s => s.strategy || s.name || '-');
      const winRates = strategies.map(s => s.win_rate_pct || 0);
      const sharpes = strategies.map(s => s.sharpe_ratio || 0);

      // 用雙軸柱狀圖：勝率 + 夏普
      const canvas = document.getElementById('dashLeaderboardChart');
      if (!canvas) return;
      const old = Chart.getChart(canvas);
      if (old) old.destroy();

      const colors = Charts.getThemeColors();
      new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: '勝率 (%)',
              data: winRates,
              backgroundColor: 'rgba(56,189,248,0.6)',
              borderColor: '#38bdf8',
              borderWidth: 1,
              yAxisID: 'y',
            },
            {
              label: '夏普比率',
              data: sharpes,
              backgroundColor: 'rgba(167,139,250,0.6)',
              borderColor: '#a78bfa',
              borderWidth: 1,
              yAxisID: 'y1',
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: colors.text, font: { size: 10 } } },
            tooltip: {
              backgroundColor: colors.tooltipBg,
              borderColor: colors.tooltipBorder,
              borderWidth: 1,
              titleColor: colors.tooltipText,
              bodyColor: colors.tooltipBody,
            },
          },
          scales: {
            x: { ticks: { color: colors.text, font: { size: 9 }, maxRotation: 45 }, grid: { color: colors.grid } },
            y: {
              type: 'linear',
              position: 'left',
              ticks: { color: colors.text, font: { size: 9 }, callback: v => v + '%' },
              grid: { color: colors.grid },
              title: { display: true, text: '勝率', color: colors.text },
            },
            y1: {
              type: 'linear',
              position: 'right',
              ticks: { color: colors.text, font: { size: 9 } },
              grid: { drawOnChartArea: false },
              title: { display: true, text: '夏普', color: colors.text },
            },
          },
        },
      });
    } catch (e) { /* ignore */ }
  },

  // ============================================================
  // 監控列表（保留原有功能）
  // ============================================================

  async loadRules() {
    const d = await Api.getAlertRules();
    if (!d) return;

    const entries = Object.entries(d.rules || {});
    document.getElementById('wlCount').textContent = entries.length + ' 只';

    if (entries.length === 0) {
      document.getElementById('watchlistTable').innerHTML =
        '<tr><td colspan="7"><div class="empty-state"><span class="empty-icon">🎯</span><p><strong>還沒有監控規則</strong></p><p>添加規則後，系統會在價格觸及目標時提醒你</p><button class="btn" onclick="showAddRule()" style="margin-top:8px">+ 添加第一個規則</button></div></td></tr>';
      return;
    }

    const codes = entries.map(([c]) => c);
    let sparklines = {};
    try {
      const sp = await Api.get('/api/sparkline?codes=' + codes.join(',') + '&days=20');
      if (sp && sp.sparklines) sparklines = sp.sparklines;
    } catch (e) { /* ignore */ }

    document.getElementById('watchlistTable').innerHTML = entries.map(([c, r]) => {
      const sp = sparklines[c] || {};
      const pct = sp.change_pct || 0;
      const cls = pct >= 0 ? 'u' : 'd';
      return `<tr>
        <td style="font-weight:600">${c}</td>
        <td>${r.name || '-'}</td>
        <td class="r">${r.price_above || '-'}</td>
        <td class="r">${r.price_below || '-'}</td>
        <td class="r"><span class="b ${cls}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</span></td>
        <td><canvas id="sp_${c}" width="80" height="28" style="vertical-align:middle"></canvas></td>
        <td>
          <button class="btn s" style="padding:3px 8px;font-size:10px" onclick="Dashboard.editRule('${c}')">編輯</button>
          <button class="btn danger" style="padding:3px 8px;font-size:10px" onclick="Dashboard.deleteRule('${c}')">刪除</button>
        </td>
      </tr>`;
    }).join('');

    entries.forEach(([c]) => {
      const sp = sparklines[c];
      if (sp && sp.prices && sp.prices.length > 2) {
        this._drawSparkline('sp_' + c, sp.prices, sp.change_pct >= 0);
      }
    });
  },

  _drawSparkline(canvasId, prices, isUp) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const min = Math.min(...prices), max = Math.max(...prices);
    const range = max - min || 1;
    const color = isUp ? '#22c55e' : '#ef4444';

    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    prices.forEach((p, i) => {
      const x = (i / (prices.length - 1)) * w;
      const y = h - ((p - min) / range) * (h - 4) - 2;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, color + '30');
    grad.addColorStop(1, color + '05');
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    const lastY = h - ((prices[prices.length - 1] - min) / range) * (h - 4) - 2;
    ctx.beginPath();
    ctx.arc(w - 1, lastY, 2, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  },

  showAddRule() {
    this._showRuleModal(null, {});
  },

  async editRule(code) {
    const d = await Api.getAlertRules();
    if (d) this._showRuleModal(code, d.rules[code] || {});
  },

  _showRuleModal(code, rule) {
    const isEdit = !!code;
    Utils.showModal(`
      <h3>${isEdit ? '編輯' : '添加'}預警規則</h3>
      <div class="fg"><label>股票代碼</label><input id="mrCode" value="${code || ''}" ${isEdit ? 'readonly' : ''}></div>
      <div class="fg"><label>名稱</label><input id="mrName" value="${rule.name || ''}"></div>
      <div class="fg"><label>突破價</label><input id="mrAbove" type="number" step="0.01" value="${rule.price_above || ''}"></div>
      <div class="fg"><label>跌破價</label><input id="mrBelow" type="number" step="0.01" value="${rule.price_below || ''}"></div>
      <div class="fg"><label>漲跌幅閾值 (%)</label><input id="mrPct" type="number" step="0.1" value="${rule.change_pct || ''}"></div>
      <div class="actions">
        <button class="btn s" onclick="Utils.closeModal()">取消</button>
        <button class="btn" onclick="Dashboard.saveRule()">保存</button>
      </div>
    `);
  },

  async saveRule() {
    const code = document.getElementById('mrCode').value.trim();
    if (!code) return Utils.toast('請輸入股票代碼');
    if (code.length !== 6 || !/^\d{6}$/.test(code)) return Utils.toast('股票代碼必須是 6 位數字');

    const rule = {
      name: document.getElementById('mrName').value,
      price_above: parseFloat(document.getElementById('mrAbove').value) || null,
      price_below: parseFloat(document.getElementById('mrBelow').value) || null,
      change_pct: parseFloat(document.getElementById('mrPct').value) || null,
    };

    const rules = {};
    rules[code] = rule;
    const d = await Api.updateAlertRules(rules);
    if (d) {
      Utils.toast('保存成功', 3000, 'success');
      Utils.closeModal();
      this.loadRules();
    }
  },

  async deleteRule(code) {
    if (!confirm(`確定刪除 ${code} 的預警規則？`)) return;
    const result = await Api.deleteAlertRule(code);
    if (result) {
      Utils.toast('已刪除', 3000, 'success');
      this.loadRules();
    }
  },
};

window.Dashboard = Dashboard;
