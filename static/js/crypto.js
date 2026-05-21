/**
 * crypto.js — 加密貨幣行情子系統（獨立 Tab）
 */
const CryptoUI = {
  _data: [],
  _selectedSymbol: null,
  _periodDays: 30,

  load() {
    this.refresh();
    const btn = document.getElementById('cryptoRefreshBtn');
    if (btn && !btn._cryptoBound) {
      btn._cryptoBound = true;
      btn.addEventListener('click', () => this.refresh());
    }
  },

  async refresh() {
    const el = document.getElementById('cryptoMarketTable');
    if (!el) return;
    el.innerHTML = '<div class="state-loading"><span class="ld"></span> 載入中…</div>';
    try {
      const d = await Api.get('/api/crypto/realtime');
      this._data = d?.data || [];
      this._renderTable();
    } catch (e) {
      el.innerHTML = '<div class="state-empty"><span class="state-icon">❌</span><span class="state-text">載入失敗: ' + (e.message || e) + '</span></div>';
    }
  },

  _renderTable() {
    const el = document.getElementById('cryptoMarketTable');
    if (!el) return;
    if (!this._data.length) {
      el.innerHTML = '<div class="state-empty"><span class="state-icon">₿</span><span class="state-text">暫無加密貨幣數據</span></div>';
      return;
    }
    const rows = this._data.map(c => {
      const chg = Number(c.change_pct) || 0;
      const cls = chg > 0 ? 'up' : (chg < 0 ? 'down' : 'flat');
      const sign = chg > 0 ? '+' : '';
      const price = Number(c.price) || 0;
      const priceStr = price >= 1000
        ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : price >= 1
          ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
          : price.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
      const high = Number(c.high) || 0;
      const low = Number(c.low) || 0;
      const vol = c.quote_volume || c.volume || 0;
      const volStr = vol >= 1e9 ? (vol / 1e9).toFixed(1) + 'B'
        : vol >= 1e6 ? (vol / 1e6).toFixed(1) + 'M'
        : vol >= 1e3 ? (vol / 1e3).toFixed(0) + 'K'
        : vol.toFixed(0);
      const icon = { BTCUSDT: '₿', ETHUSDT: 'Ξ', BNBUSDT: '◆', SOLUSDT: '◎', XRPUSDT: '✕' }[c.symbol] || '●';
      const sym = String(c.symbol).replace(/'/g, '');
      return `<tr data-crypto-symbol="${sym}" style="cursor:pointer">
        <td><span class="crypto-tbl-icon">${icon}</span> <strong>${c.name || c.symbol}</strong><br><span style="font-size:10px;color:var(--text-dim)">${c.symbol}</span></td>
        <td class="r" style="font-variant-numeric:tabular-nums">$${priceStr}</td>
        <td class="r"><span class="crypto-badge ${cls}">${sign}${chg.toFixed(2)}%</span></td>
        <td class="r" style="font-size:12px;color:var(--text-dim)">${high > 0 ? '$' + high.toLocaleString('en-US', {maximumFractionDigits: 2}) : '-'}</td>
        <td class="r" style="font-size:12px;color:var(--text-dim)">${low > 0 ? '$' + low.toLocaleString('en-US', {maximumFractionDigits: 2}) : '-'}</td>
        <td class="r" style="font-size:12px">${volStr}</td>
      </tr>`;
    }).join('');
    el.innerHTML = `<table class="dash-watchlist-table"><thead><tr>
      <th>幣種</th><th class="r">價格</th><th class="r">24h 漲跌</th><th class="r">最高</th><th class="r">最低</th><th class="r">24h 成交額</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
    el.querySelectorAll('[data-crypto-symbol]').forEach(row => {
      row.addEventListener('click', () => this.selectSymbol(row.dataset.cryptoSymbol));
    });
  },

  async selectSymbol(symbol) {
    this._selectedSymbol = symbol;
    const panel = document.getElementById('cryptoKlinePanel');
    const title = document.getElementById('cryptoKlineTitle');
    if (panel) panel.classList.remove('h');
    if (title) title.textContent = `${symbol} K 線圖`;
    const btns = document.querySelectorAll('[data-crypto-period]');
    btns.forEach(b => {
      b.onclick = () => {
        btns.forEach(x => x.classList.remove('a'));
        b.classList.add('a');
        this._periodDays = parseInt(b.dataset.cryptoPeriod, 10) || 30;
        this._loadKline();
      };
    });
    await this._loadKline();
  },

  async _loadKline() {
    if (!this._selectedSymbol) return;
    const canvas = document.getElementById('cryptoKlineChart');
    if (!canvas) return;
    try {
      const d = await Api.get(`/api/crypto/kline?symbol=${encodeURIComponent(this._selectedSymbol)}&days=${this._periodDays}`);
      const klines = d?.klines || [];
      if (!klines.length) {
        if (typeof Chart !== 'undefined') {
          const existing = Chart.getChart(canvas);
          if (existing) existing.destroy();
        }
        return;
      }
      const dates = klines.map(k => k.date);
      const closes = klines.map(k => k.close);
      if (typeof Chart === 'undefined') return;
      const existing = Chart.getChart(canvas);
      if (existing) existing.destroy();
      const colors = getComputedStyle(document.documentElement);
      const accent = colors.getPropertyValue('--accent').trim() || '#38bdf8';
      const gridColor = colors.getPropertyValue('--border-color').trim() || 'rgba(128,128,128,.15)';
      const textColor = colors.getPropertyValue('--text').trim() || '#e2e8f0';
      new Chart(canvas, {
        type: 'line',
        data: {
          labels: dates,
          datasets: [{
            label: (typeof SignalLabels !== 'undefined')
              ? SignalLabels.strategyName(this._selectedSymbol, 'short')
              : this._selectedSymbol,
            data: closes,
            borderColor: accent,
            backgroundColor: accent + '20',
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: textColor, font: { size: 9 }, maxTicksLimit: 8 }, grid: { color: gridColor } },
            y: { ticks: { color: textColor, font: { size: 9 } }, grid: { color: gridColor } },
          },
        },
      });
      if (typeof Charts !== 'undefined') Charts.resizeTab('tab-crypto');
    } catch (e) {
      console.warn('加密 K 線載入失敗:', e);
    }
  },
};

/** 向後相容舊名稱 */
const CryptoMarket = CryptoUI;
