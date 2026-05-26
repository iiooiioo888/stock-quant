/**
 * stock-content.js — 個股內容統一渲染（詳情頁 / 深度分析 / 數據中心）
 * 資料來源：GET /api/stocks/{code}/analysis-page 或 overview 子集
 */
const StockContent = {
  _esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  },

  _fmtNum(v, digits = 2) {
    const n = Number(v);
    if (!Number.isFinite(n)) return null;
    return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  },

  _fmtPct(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return null;
    const pct = Math.abs(n) <= 1 && n !== 0 ? n * 100 : n;
    return `${pct.toFixed(2)}%`;
  },

  _fmtYi(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return null;
    return `${n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 億`;
  },

  _fmtPrice(value, code) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    if (/^\d{6}$/.test(String(code || ''))) {
      return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  },

  /** 合併 analysis-page 與 overview 為統一 view */
  normalizePageData(d) {
    if (!d) return null;
    const profile = d.profile || {};
    const fin = d.financials || {};
    const overview = d.overview || {};
    const t = overview.technical || {};
    const sig = d.signals || {};
    return {
      code: d.code,
      name: d.name || profile.name,
      market: d.market || profile.market,
      profile,
      financials: fin,
      overview,
      technical: t,
      signals: sig.signals || [],
      signalStrength: sig.strength,
      signalsCount: sig.signals_count || (sig.signals || []).length,
      signalsUpdatedAt: sig.updated_at,
      kline: d.kline,
      sparkline: d.sparkline,
      klineSource: d.kline_source,
    };
  },

  buildHeroTags(profile, fin) {
    const tags = [];
    const p = profile || {};
    const f = fin || {};
    if (p.market_label) tags.push(p.market_label);
    if (p.exchange) tags.push(p.exchange);
    if (p.industry) tags.push(p.industry);
    if (p.list_date) tags.push(`上市 ${p.list_date}`);
    if (f.source) tags.push(`財報 ${f.source}`);
    return tags;
  },

  buildFinanceItems(fin, profile, code) {
    const items = [];
    const f = fin || {};
    const p = profile || {};
    const push = (label, val, cls = '') => {
      if (val == null || val === '' || (typeof val === 'number' && Number.isNaN(val))) return;
      items.push({ label, val, cls });
    };

    push('市盈率 TTM', this._fmtNum(f.pe_ttm ?? p.pe_ttm));
    push('市淨率 PB', this._fmtNum(f.pb ?? p.pb));
    push('市銷率 PS', this._fmtNum(f.ps_ttm));
    push('ROE', this._fmtPct(f.roe));
    push('每股收益 EPS', this._fmtNum(f.eps, 2));
    push('每股淨資產', this._fmtNum(f.bvps, 2));
    push('總市值', this._fmtYi(f.total_mv ?? p.total_mv));
    push('流通市值', this._fmtYi(f.circulating_mv ?? p.circulating_mv));
    push('營業收入', this._fmtYi(f.revenue));
    push('淨利潤', this._fmtYi(f.net_profit));
    push('營收同比', this._fmtPct(f.revenue_yoy));
    push('淨利同比', this._fmtPct(f.profit_yoy));
    push('毛利率', this._fmtPct(f.gross_margin));
    push('淨利率', this._fmtPct(f.net_margin));
    push('資產負債率', this._fmtPct(f.debt_ratio));
    push('股息率', this._fmtPct(f.dividend_yield));

    if (f.realtime_price != null) {
      const chg = f.realtime_change_pct;
      const chgCls = chg > 0 ? 'up' : (chg < 0 ? 'down' : '');
      const chgTxt = chg != null ? ` (${chg > 0 ? '+' : ''}${Number(chg).toFixed(2)}%)` : '';
      push('實時價', `${this._fmtPrice(f.realtime_price, code)}${chgTxt}`, chgCls);
    } else if (p.price != null) {
      const chg = p.change_pct;
      const chgCls = chg > 0 ? 'up' : (chg < 0 ? 'down' : '');
      const chgTxt = chg != null ? ` (${chg > 0 ? '+' : ''}${Number(chg).toFixed(2)}%)` : '';
      push('最新價', `${this._fmtPrice(p.price, code)}${chgTxt}`, chgCls);
    }

    return items;
  },

  buildTechnicalItems(overview, technical) {
    const o = overview || {};
    const t = technical || o.technical || {};
    if (!o.has_kline && !t.close) return [];

    const items = [];
    const push = (label, val, cls = '') => {
      if (val == null || val === '' || val === '-') return;
      items.push({ label, val, cls });
    };
    const fmt = (v, suf = '') => (v == null || v === '' ? null : `${v}${suf}`);

    push('交易日', t.date || o.date_to);
    push('收盤價', fmt(t.close));
    push('漲跌', fmt(t.change_pct, '%'), t.change_pct > 0 ? 'up' : (t.change_pct < 0 ? 'down' : ''));
    push('振幅', fmt(t.amplitude_pct, '%'));
    push('開 / 高 / 低', [t.open, t.high, t.low].every(x => x != null)
      ? `${t.open} / ${t.high} / ${t.low}` : null);
    push('成交量', t.volume != null ? this._fmtNum(t.volume, 0) : null);
    push('成交額', t.amount != null ? this._fmtNum(t.amount, 0) : null);
    push('MA5 / MA20 / MA60', [t.ma5, t.ma20, t.ma60].every(x => x != null)
      ? `${t.ma5} / ${t.ma20} / ${t.ma60}` : null);
    push('偏離 MA5', fmt(t.vs_ma5_pct, '%'));
    push('偏離 MA20', fmt(t.vs_ma20_pct, '%'));
    push('5日漲跌', fmt(t.change_5d_pct, '%'), (t.change_5d_pct || 0) >= 0 ? 'up' : 'down');
    push('20日漲跌', fmt(t.change_20d_pct, '%'), (t.change_20d_pct || 0) >= 0 ? 'up' : 'down');
    push('60日漲跌', fmt(t.change_60d_pct, '%'), (t.change_60d_pct || 0) >= 0 ? 'up' : 'down');
    push('量比(20日)', fmt(t.volume_ratio));
    push('年化波動', fmt(t.volatility_annual_pct, '%'));
    push('區間高 / 低', t.high_lookback != null ? `${t.high_lookback} / ${t.low_lookback}` : null);
    push('距區間高點', fmt(t.pct_from_high, '%'));
    push('距區間低點', fmt(t.pct_from_low, '%'));

    if (o.date_from && o.date_to) {
      push('K 線區間', `${o.date_from} ~ ${o.date_to}`);
    }
    if (o.bars) push('K 線根數', String(o.bars));
    if (o.kline_source) push('行情來源', o.kline_source);

    const rt = t.realtime || {};
    if (rt.price != null) {
      push('快照價', this._fmtPrice(rt.price, o.code), (rt.change_pct || 0) >= 0 ? 'up' : 'down');
    }

    return items;
  },

  renderMetricGrid(container, items, emptyMsg = '暫無數據') {
    if (!container) return;
    if (!items?.length) {
      container.innerHTML = `<p class="muted">${this._esc(emptyMsg)}</p>`;
      return;
    }
    container.innerHTML = items.map(it => `
      <div class="sd-finance-item">
        <span class="sd-finance-label">${this._esc(it.label)}</span>
        <span class="sd-finance-val ${it.cls || ''}">${this._esc(String(it.val))}</span>
      </div>`).join('');
  },

  renderTags(container, tags) {
    if (!container) return;
    container.innerHTML = (tags || []).length
      ? tags.map(t => `<span class="sd-hero-tag">${this._esc(t)}</span>`).join('')
      : '';
  },

  renderIntro(container, profile) {
    if (!container) return;
    const p = profile || {};
    const intro = (p.intro || '').trim();
    const industry = (p.industry || '').trim();
    if (intro && intro.length > 24) {
      container.textContent = intro;
      return;
    }
    if (industry) {
      container.textContent = `所屬行業：${industry}。暫無詳細簡介，可在「數據中心」執行股票庫簡介補充任務。`;
      return;
    }
    container.textContent = '暫無公司簡介。可在「數據中心」同步股票庫並執行「補充簡介」任務後再查看。';
  },

  renderSignals(container, metaEl, signals, strength, updatedAt) {
    if (!container) return;
    const list = signals || [];
    if (!list.length) {
      container.innerHTML = '<p class="muted">暫無策略信號（請在信號中心刷新或加入監控列表）</p>';
      if (metaEl) metaEl.textContent = '';
      return;
    }
    const strengthTxt = strength != null && Number.isFinite(Number(strength))
      ? `綜合強度 ${Number(strength).toFixed(1)}`
      : '';
    if (metaEl) {
      metaEl.textContent = [strengthTxt, updatedAt ? `更新 ${updatedAt}` : '', `共 ${list.length} 條`]
        .filter(Boolean).join(' · ');
    }
    container.innerHTML = list.map(s => {
      const strat = s.strategy || s.name || '策略';
      const sig = s.signal || s.action || s.type || '—';
      const cls = /买|buy|多|long/i.test(String(sig)) ? 'buy'
        : (/卖|sell|空|short/i.test(String(sig)) ? 'sell' : '');
      return `<span class="sd-signal-chip ${cls}" title="${this._esc(strat)}">
        <strong>${this._esc(strat)}</strong>
        <em>${this._esc(sig)}</em>
      </span>`;
    }).join('');
  },

  /** 深度分析 Tab 快照面板 */
  renderAnalysisSnapshot(root, d) {
    if (!root) return;
    const view = this.normalizePageData(d);
    if (!view) {
      root.innerHTML = '<p class="muted">選擇股票後顯示概覽</p>';
      return;
    }
    const finItems = this.buildFinanceItems(view.financials, view.profile, view.code);
    const techItems = this.buildTechnicalItems(view.overview, view.technical);
    const finPreview = finItems.slice(0, 8);
    const techPreview = techItems.slice(0, 8);

    root.innerHTML = `
      <div class="sc-snapshot-head">
        <div>
          <strong class="sc-snapshot-title">${this._esc(view.name || view.code)}</strong>
          <span class="sc-snapshot-code">${this._esc(view.code)}</span>
        </div>
        <button type="button" class="btn s sc-snapshot-open" data-code="${this._esc(view.code)}">打開詳情頁</button>
      </div>
      <div class="sc-snapshot-grid">
        <div class="sc-snapshot-block">
          <h4>技術面</h4>
          <div class="sd-finance-grid sc-snapshot-metrics">${this._metricHtml(techPreview, '暫無 K 線技術數據')}</div>
        </div>
        <div class="sc-snapshot-block">
          <h4>基本面</h4>
          <div class="sd-finance-grid sc-snapshot-metrics">${this._metricHtml(finPreview, '暫無財務數據')}</div>
        </div>
      </div>
      <div class="sc-snapshot-signals" id="anSnapshotSignals"></div>`;

    const sigHost = root.querySelector('#anSnapshotSignals');
    this.renderSignals(sigHost, null, view.signals, view.signalStrength, view.signalsUpdatedAt);

    root.querySelector('.sc-snapshot-open')?.addEventListener('click', () => {
      if (typeof App !== 'undefined') App.openStockDetail(view.code);
    });
  },

  _metricHtml(items, emptyMsg) {
    if (!items?.length) return `<p class="muted">${this._esc(emptyMsg)}</p>`;
    return items.map(it => `
      <div class="sd-finance-item">
        <span class="sd-finance-label">${this._esc(it.label)}</span>
        <span class="sd-finance-val ${it.cls || ''}">${this._esc(String(it.val))}</span>
      </div>`).join('');
  },

  /** 數據中心 — 基本數據查詢（與詳情頁同一套欄位） */
  renderBasicsPanel(container, overview, profile, financials, code) {
    if (!container) return;
    const techItems = this.buildTechnicalItems(overview, overview?.technical);
    const finItems = this.buildFinanceItems(financials, profile, code);
    if (!techItems.length && !finItems.length) {
      container.innerHTML = `<p class="warn">${this._esc(overview?.message || '無數據')}</p>`;
      return;
    }
    let html = '';
    if (techItems.length) {
      html += `<h3 class="mt-md">技術面（${this._esc(code)}）</h3>
        <div class="sd-finance-grid sc-basics-grid">${this._metricHtml(techItems)}</div>`;
    }
    if (finItems.length) {
      html += `<h3 class="mt-md">基本面</h3>
        <div class="sd-finance-grid sc-basics-grid">${this._metricHtml(finItems)}</div>`;
    }
    container.innerHTML = html;
  },
};

window.StockContent = StockContent;
