/* global echarts */

/**
 * 儀表盤 UI 組件庫 — 掛牌 / KPI / 圖表槽 / 熱力圖
 * 掛載至 window.StockQPro.UI.Dashboard
 */
(() => {
  const UI = window.StockQPro?.UI;
  if (!UI) return;

  const D = {};

  const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v);

  D.normalizeQuote = (item = {}) => {
    const price = item.latest ?? item.price ?? item.close ?? item.value;
    const pct = item.change_pct ?? item.pct_change ?? item.pct ?? item.change;
    const p = Number(pct);
    const up = Number.isFinite(p) ? p >= 0 : true;
    const priceNum = Number(price);
    const src = item.source || '';
    const srcKey = String(item.source_raw || src).toLowerCase();
    let srcClass = '';
    if (srcKey.includes('tradingview') || src === 'TradingView') srcClass = 'ticker-card-src--tv';
    else if (srcKey.includes('ib') || src === 'IB') srcClass = 'ticker-card-src--ib';
    return {
      symbol: item.symbol || '',
      name: item.name || item.label || '—',
      price: Number.isFinite(priceNum) ? priceNum : null,
      priceText: Number.isFinite(priceNum)
        ? priceNum.toLocaleString(undefined, { maximumFractionDigits: 2 })
        : '--',
      pct: Number.isFinite(p) ? p : null,
      pctText: Number.isFinite(p) ? `${p >= 0 ? '+' : ''}${p.toFixed(2)}%` : '--',
      change: item.change,
      source: src,
      srcClass,
      tvSymbol: item.tv_symbol || '',
      group: item.group || '',
      kline: Array.isArray(item.kline) ? item.kline : [],
      dir: up ? 'up' : 'down',
      toneClass: up ? 'up' : 'down',
    };
  };

  D.downsampleCloses = (kline, maxPoints = 28) => {
    const closes = (kline || [])
      .map((k) => Number(k.close ?? k.c ?? k[4]))
      .filter((n) => Number.isFinite(n));
    if (closes.length <= maxPoints) return closes;
    const out = [];
    const step = (closes.length - 1) / (maxPoints - 1);
    for (let i = 0; i < maxPoints; i += 1) {
      out.push(closes[Math.round(i * step)]);
    }
    return out;
  };

  D.sparklineSvg = (kline, dir = 'up', maxPoints = 28) => {
    const closes = D.downsampleCloses(kline, maxPoints);
    if (closes.length < 2) {
      return '<svg class="ticker-spark" viewBox="0 0 56 18" aria-hidden="true"><path class="spark-flat" d="M2 9 H54"/></svg>';
    }
    const w = 56;
    const h = 18;
    const pad = 2;
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const span = max - min || 1;
    const pts = closes.map((v, i) => {
      const x = pad + (i / (closes.length - 1)) * (w - pad * 2);
      const y = pad + (1 - (v - min) / span) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const stroke = dir === 'up' ? 'var(--quote-up)' : 'var(--quote-down)';
    const fill = dir === 'up' ? 'var(--quote-up-bg)' : 'var(--quote-down-bg)';
    const baseY = (h - pad).toFixed(1);
    const firstX = pts[0].split(',')[0];
    const lastX = pts[pts.length - 1].split(',')[0];
    const area = `M${firstX},${baseY} L${pts.join(' L')} L${lastX},${baseY} Z`;
    return `<svg class="ticker-spark" viewBox="0 0 ${w} ${h}" aria-hidden="true">
      <path class="spark-area" fill="${fill}" d="${area}"/>
      <polyline class="spark-line" fill="none" stroke="${stroke}" stroke-width="1.5" points="${pts.join(' ')}"/>
    </svg>`;
  };

  /**
   * 單一指数掛牌
   * @param {object} quote normalized
   * @param {{ compact?: boolean, topbar?: boolean, tag?: string }} opts
   */
  D.IndexTickerCard = (quote, opts = {}) => {
    const q = D.normalizeQuote(quote);
    const topbar = !!opts.topbar;
    const compact = topbar || !!opts.compact;
    const sparkPts = topbar ? 18 : 28;
    const cls = [
      'ticker-card', 'ticker-card--link', `is-${q.toneClass}`,
      compact ? 'ticker-card--compact' : '',
      topbar ? 'ticker-card--topbar' : '',
    ].filter(Boolean).join(' ');
    const showSrc = !topbar && q.source;
    return UI.h('article', { class: cls, title: `${q.name} · 點擊查看詳情`, dataset: { symbol: q.symbol } },
      UI.h('div', { class: 'ticker-card-top' },
        UI.h('div', { class: 'ticker-card-meta' },
          UI.h('span', { class: 'ticker-card-label' }, opts.tag || q.name),
          showSrc ? UI.h('span', { class: ['ticker-card-src', q.srcClass].filter(Boolean).join(' ') }, q.source) : null,
        ),
        UI.h('span', { class: `ticker-card-pct ticker-card-pct--${q.toneClass}` }, q.pctText),
      ),
      UI.h('div', { class: ['ticker-card-mid', topbar ? 'ticker-card-mid--topbar' : ''].filter(Boolean).join(' ') },
        UI.h('span', { class: 'ticker-card-price' }, q.priceText),
        (topbar || !compact)
          ? UI.h('div', { class: ['ticker-card-spark', topbar ? 'ticker-card-spark--mini' : ''].filter(Boolean).join(' '), html: D.sparklineSvg(q.kline, q.dir, sparkPts) })
          : null,
      ),
      topbar || compact ? null : UI.h('div', { class: 'ticker-card-foot' },
        UI.h('span', { class: 'ticker-card-sym' }, q.symbol || ''),
      ),
    );
  };

  D._tickerStripInner = (root) => {
    const el = typeof root === 'string' ? UI.id(root) : root;
    if (!el) return null;
    return el.classList.contains('ticker-strip-inner') ? el : el.querySelector('.ticker-strip-inner');
  };

  /** 增量更新頂欄掛牌（避免整條重繪閃爍） */
  D.updateTickerStrip = (root, quotes = [], opts = {}) => {
    const host = typeof root === 'string' ? UI.id(root) : root;
    if (!host) return;
    let inner = D._tickerStripInner(host);
    if (!inner) {
      inner = UI.h('div', { class: 'ticker-strip-inner' });
      UI.clear(host);
      host.appendChild(inner);
    }

    const list = quotes || [];
    if (!list.length) {
      inner.innerHTML = '<div class="ticker-strip-empty">行情載入中…</div>';
      return;
    }
    inner.querySelector('.ticker-strip-empty')?.remove();

    const cardOpts = {
      compact: opts.compact !== false,
      topbar: !!opts.topbar,
      tag: opts.shortNames ? (q) => shortLabel(q.name) : undefined,
    };

    const existing = new Map();
    inner.querySelectorAll('.ticker-card[data-symbol]').forEach((card) => {
      const sym = (card.dataset.symbol || '').toUpperCase();
      if (sym) existing.set(sym, card);
    });

    const next = [];
    list.forEach((raw) => {
      const sym = String(raw.symbol || '').toUpperCase();
      const tag = typeof cardOpts.tag === 'function' ? cardOpts.tag(raw) : cardOpts.tag;
      let card = sym ? existing.get(sym) : null;
      if (card) {
        D.updateTickerCardEl(card, raw);
        existing.delete(sym);
      } else {
        card = D.IndexTickerCard(raw, { ...cardOpts, tag });
      }
      next.push(card);
    });

    next.forEach((card) => inner.appendChild(card));
    existing.forEach((stale) => stale.remove());
  };

  /** 頂欄橫向掛牌帶 */
  D.TickerStrip = (root, quotes = [], opts = {}) => {
    const el = typeof root === 'string' ? UI.id(root) : root;
    if (!el) return;
    if (opts.incremental !== false && el.querySelector('.ticker-strip-inner')) {
      D.updateTickerStrip(el, quotes, opts);
      return;
    }
    const compact = opts.compact !== false;
    const list = (quotes || []).map((q) => D.IndexTickerCard(q, {
      compact,
      topbar: !!opts.topbar,
      tag: opts.shortNames ? shortLabel(q.name) : undefined,
    }));
    UI.mount(el, UI.h('div', { class: 'ticker-strip-inner' }, ...list));
  };

  function shortLabel(name) {
    const map = {
      '上證綜指': '上證', '深證成指': '深成', '創業板指': '創業',
      '恒生指數': '恒生', '標普 500': '標普', '納斯達克': '納指', '道瓊斯': '道指', '日經 225': '日經',
      '韓國綜指': '韓指', 'VIX 恐慌': 'VIX', '德國 DAX': 'DAX', '英國 FTSE': 'FTSE',
      '歐元/美元': 'EUR', '英鎊/美元': 'GBP', '美元/日元': 'JPY', '美元/離岸人民幣': 'CNH',
      '比特幣': 'BTC', '以太坊': 'ETH', 'Solana': 'SOL', '黃金': '金', '原油 WTI': '油',
      'WTI 原油': '油', '騰訊': '腾讯', '貴州茅台': '茅台', '長江電力': '長電',
    };
    return map[name] || String(name || '').slice(0, 4);
  }

  /** 分組掛牌（按 group_order 排序，每組只顯示該 group 標的） */
  D.QuoteBoardGrouped = (root, payload = {}) => {
    const el = typeof root === 'string' ? UI.id(root) : root;
    if (!el) return;

    const order = Array.isArray(payload.group_order) ? payload.group_order : [];
    const groupsMap = payload.groups && typeof payload.groups === 'object' ? payload.groups : {};
    const groupLabels = payload.group_labels && typeof payload.group_labels === 'object'
      ? payload.group_labels
      : {};
    const flat = Array.isArray(payload.indices) ? payload.indices : [];

    const pickItems = (gid, rawItems) => {
      const list = Array.isArray(rawItems) ? rawItems : [];
      const filtered = list.filter((q) => {
        const g = q.group || '';
        return !g || g === gid;
      });
      if (filtered.length) return filtered;
      return flat.filter((q) => q.group === gid);
    };

    let groupList = order.length
      ? order.map((id) => {
        const g = groupsMap[id];
        if (!g) return null;
        const items = pickItems(id, g.items);
        if (!items.length) return null;
        return {
          id,
          label: groupLabels[id] || g.label || id,
          items,
        };
      }).filter(Boolean)
      : Object.entries(groupsMap).map(([id, g]) => ({
        id,
        label: groupLabels[id] || g.label || id,
        items: pickItems(id, g.items),
      })).filter((g) => g.items.length);

    if (!groupList.length && flat.length) {
      D.QuoteBoard(el, flat);
      return;
    }

    const sections = groupList.map((g) => (
      UI.h('div', { class: 'quote-board-section', dataset: { group: g.id } },
        UI.h('div', { class: 'quote-board-section-head' },
          UI.h('h3', { class: 'quote-board-section-title' }, g.label),
          UI.h('span', { class: 'quote-board-section-count' }, `${g.items.length} 檔`),
        ),
        UI.h('div', { class: 'quote-board-grid' },
          ...g.items.map((q) => D.IndexTickerCard(q, { compact: false })),
        ),
      )
    ));

    UI.mount(el, UI.h('div', { class: 'quote-board-grouped' }, ...sections));
  };

  D.ProviderBadges = (providers = {}) => {
    const tv = providers.tradingview || {};
    const ib = providers.ib || {};
    const chips = [];
    chips.push(UI.Badge({
      text: tv.ok ? `TV · ${tv.quotes ?? 0}` : 'TV · 離線',
      tone: tv.ok ? 'bl' : 'gr',
    }));
    const ibOn = ib.connected || (ib.quotes > 0);
    chips.push(UI.Badge({
      text: ibOn ? `IB · ${ib.quotes ?? 0}` : (ib.enabled ? 'IB · 未連' : 'IB · 關'),
      tone: ibOn ? 'ac' : 'gr',
    }));
    return chips;
  };

  /** 儀表盤大掛牌網格 */
  D.QuoteBoard = (root, quotes = []) => {
    const el = typeof root === 'string' ? UI.id(root) : root;
    if (!el) return;
    const cards = (quotes || []).map((q) => D.IndexTickerCard(q, { compact: false }));
    UI.mount(el, UI.h('div', { class: 'quote-board-grid' }, ...cards));
  };

  D.KpiCard = ({ label, value, hint, tone } = {}) => (
    UI.h('div', { class: `dash-kpi ${tone ? `dash-kpi--${tone}` : ''}`.trim() },
      UI.h('span', { class: 'dash-kpi-label' }, label ?? ''),
      UI.h('span', { class: 'dash-kpi-value' }, value ?? '--'),
      hint ? UI.h('span', { class: 'dash-kpi-hint' }, hint) : null,
    )
  );

  D.ChartTile = ({ id, title, badge, height = 220 } = {}) => (
    UI.Panel({
      title,
      right: badge ? [UI.Badge({ text: badge, tone: 'bl' })] : [],
      noPad: true,
      body: UI.h('div', { class: 'dash-chart-wrap', style: { height: `${height}px` } },
        UI.h('div', { id, class: 'dash-chart', style: { width: '100%', height: '100%' } }),
      ),
    })
  );

  D.HeatmapTile = ({ id = 'heatmap', title = '板塊熱力' } = {}) => (
    UI.Panel({
      title,
      right: [UI.Badge({ text: 'Top 30', tone: 'ac' })],
      body: UI.h('div', { id, class: 'heatmap dash-heatmap' }),
    })
  );

  /** 儀表盤頁面骨架（組件組裝） */
  D.buildPageLayout = () => (
    UI.h('div', { class: 'dash-page' },
      UI.h('section', { class: 'dash-section' },
        UI.h('div', { class: 'dash-section-head' },
          UI.h('div', {},
            UI.h('p', { class: 'dash-eyebrow' }, 'Market Overview'),
            UI.h('h2', { class: 'dash-title' }, '全球市場掛牌'),
          ),
          UI.h('div', { class: 'dash-section-actions' },
            UI.h('span', { class: 'dash-provider-badges', id: 'dash-provider-badges' }),
            UI.h('span', { class: 'dash-updated', id: 'dash-updated-at' }, '更新中…'),
          ),
        ),
        UI.h('div', { id: 'dash-quote-board', class: 'quote-board-host' }),
      ),
      UI.h('section', { class: 'dash-section dash-section--portfolio' },
        UI.h('div', { class: 'dash-section-head' },
          UI.h('div', {},
            UI.h('p', { class: 'dash-eyebrow' }, 'Portfolio'),
            UI.h('h2', { class: 'dash-title' }, '多幣種資產結算'),
          ),
        ),
        UI.h('div', { id: 'currency-toggle', class: 'currency-toggle-host' }),
        UI.h('div', { class: 'dash-portfolio-grid' },
          UI.h('div', { class: 'dash-portfolio-card pnl' },
            UI.h('div', { class: 'ph' }, UI.h('div', { class: 'pt' }, '總資產')),
            UI.h('div', { class: 'pb' },
              UI.h('div', { class: 'portfolio-total', id: 'portfolio-total-value' }, '--'),
              UI.h('div', { class: 'portfolio-pnl', id: 'portfolio-daily-pnl' }, '今日盈虧 --'),
            ),
          ),
          UI.h('div', { class: 'dash-portfolio-card pnl' },
            UI.h('div', { class: 'ph' }, UI.h('div', { class: 'pt' }, '配置占比')),
            UI.h('div', { class: 'pb portfolio-allocation', id: 'portfolio-allocation' }, '—'),
          ),
          UI.h('div', { class: 'dash-portfolio-card pnl dash-portfolio-card--wide' },
            UI.h('div', { class: 'ph' }, UI.h('div', { class: 'pt' }, '資產趨勢')),
            UI.h('div', { class: 'pb' },
              UI.h('div', { id: 'portfolio-trend-chart', class: 'portfolio-trend-chart', style: 'height:200px;width:100%' }),
            ),
          ),
        ),
      ),
      UI.h('section', { class: 'dash-section dash-section--tight' },
        UI.h('div', { class: 'dash-kpi-row', id: 'dash-kpi-row' }),
      ),
    )
  );

  D.renderHeatmapCells = (container, items) => {
    const hm = typeof container === 'string' ? UI.id(container) : container;
    if (!hm) return;
    if (!Array.isArray(items) || items.length === 0) {
      hm.innerHTML = '<div class="dash-empty">無板塊資料</div>';
      return;
    }
    const top = items.slice(0, 30);
    hm.innerHTML = top.map((s) => {
      const name = String(s.name || s.sector || '').slice(0, 4) || '—';
      const chg = Number(s.change_pct ?? s.change ?? 0);
      const v = Number.isFinite(chg) ? chg : 0;
      const hm = window.StockQPro?.Prefs?.heatmapStyle?.(v) || {};
      const tx = hm.color || (v >= 0 ? 'var(--quote-up)' : 'var(--quote-down)');
      const bg = hm.background || 'var(--bg2)';
      return `<div class="hcell" style="background:${bg};color:${tx}"><span class="hn">${UI.escapeHtml(name)}</span><span class="hv">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</span></div>`;
    }).join('');
  };

  D.renderLineChart = (id, title, xs, ys, color, chartsStore) => {
    const el = UI.id(id);
    if (!el || typeof echarts === 'undefined') return null;
    let ch = chartsStore[id];
    if (!ch) {
      const existing = typeof echarts !== 'undefined' && echarts.getInstanceByDom
        ? echarts.getInstanceByDom(el)
        : null;
      if (existing) {
        try { existing.dispose(); } catch (_) {}
      }
      ch = echarts.init(el);
      chartsStore[id] = ch;
    }
    ch.setOption({
      grid: { top: 22, right: 14, bottom: 30, left: 52 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#252842',
        borderColor: '#2d3158',
        textStyle: { color: '#eeeef2', fontFamily: 'JetBrains Mono', fontSize: 10 },
      },
      xAxis: {
        type: 'category', data: xs,
        axisLine: { lineStyle: { color: '#1e2138' } },
        axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 8 },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        splitLine: { lineStyle: { color: '#1d2033' } },
        axisLabel: { color: '#5c5b72', fontFamily: 'JetBrains Mono', fontSize: 9 },
      },
      series: [{
        name: title,
        type: 'line',
        data: ys,
        smooth: true,
        showSymbol: false,
        lineStyle: { color, width: 2 },
        areaStyle: { color: color.replace('1)', '.12)') },
      }],
    }, true);
    return ch;
  };

  D.updateTickerCardEl = (cardEl, quote) => {
    if (!cardEl) return;
    const q = D.normalizeQuote(quote);
    cardEl.classList.remove('is-up', 'is-down');
    cardEl.classList.add(`is-${q.toneClass}`);
    const price = cardEl.querySelector('.ticker-card-price');
    const pct = cardEl.querySelector('.ticker-card-pct');
    const spark = cardEl.querySelector('.ticker-card-spark');
    if (price) price.textContent = q.priceText;
    if (pct) {
      pct.textContent = q.pctText;
      pct.className = `ticker-card-pct ticker-card-pct--${q.toneClass}`;
    }
    if (spark) {
      const pts = cardEl.classList.contains('ticker-card--topbar') ? 18 : 28;
      spark.innerHTML = D.sparklineSvg(q.kline, q.dir, pts);
    }
  };

  UI.Dashboard = D;
})();
