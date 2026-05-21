/**
 * signal-labels.js — 策略名、買賣信號的中文與簡短解釋
 */
const SignalLabels = {
  SIGNAL: {
    buy: { zh: '買入', cls: 'on', desc: '策略建議建倉或加碼做多' },
    sell: { zh: '賣出', cls: 'off', desc: '策略建議減倉、平倉或回避風險' },
    hold: { zh: '觀望', cls: 'cfg', desc: '暫無明確方向，維持現倉或保持空倉' },
  },

  STRATEGIES: {
    dual_ma: {
      name: '雙均線',
      full: '雙均線金叉策略',
      desc: '用快慢兩條均線的交叉判斷趨勢轉折',
      buy: '快線上穿慢線（金叉），趨勢轉多',
      sell: '快線下穿慢線（死叉），趨勢轉空',
      hold: '均線糾纏，趨勢方向不明',
    },
    macd: {
      name: 'MACD',
      full: 'MACD 金叉策略',
      desc: 'DIF 與 DEA 的交叉反映動量變化',
      buy: 'MACD 金叉，動量由弱轉強',
      sell: 'MACD 死叉，動量由強轉弱',
      hold: '柱狀圖收斂，等待方向確認',
    },
    bollinger: {
      name: '布林帶',
      full: '布林帶突破策略',
      desc: '價格相對上下軌的位置判斷超買超賣',
      buy: '價格觸及或跌破下軌，偏超賣反彈',
      sell: '價格觸及或突破上軌，偏超買回落',
      hold: '價格在中軌附近震盪',
    },
    kdj: {
      name: 'KDJ',
      full: 'KDJ 隨機指標策略',
      desc: 'K、D 交叉配合超買超賣區間',
      buy: '低位金叉（K 上穿 D），超賣反彈',
      sell: '高位死叉（K 下穿 D），超買回落',
      hold: '指標在中性區間徘徊',
    },
    rsi: {
      name: 'RSI',
      full: 'RSI 相對強弱策略',
      desc: '衡量漲跌力道是否過熱或過冷',
      buy: 'RSI 從超賣區回升，動能修復',
      sell: 'RSI 從超買區回落，動能衰竭',
      hold: 'RSI 處於中性區間',
    },
    grid: {
      name: '網格交易',
      full: '網格交易策略',
      desc: '按固定價格間距分批低買高賣',
      buy: '價格下跌觸發買入網格',
      sell: '價格上漲觸發賣出網格',
      hold: '價格在網格區間內，暫不操作',
    },
    turtle: {
      name: '海龜',
      full: '海龜趨勢跟蹤策略',
      desc: '突破 N 日高點入場，跌破低點出場',
      buy: '突破入場通道高點，趨勢啟動',
      sell: '跌破出場通道低點，趨勢結束',
      hold: '未突破通道，不建倉',
    },
    dual_thrust: {
      name: '日內突破',
      full: '雙軌日內突破策略',
      desc: '以前日波動區間設定當日突破上下軌',
      buy: '向上突破上軌，追多',
      sell: '向下跌破下軌或平倉信號',
      hold: '在通道內震盪',
    },
    momentum: {
      name: '動量 ROC',
      full: '動量 ROC 策略',
      desc: '用價格變化率（ROC）衡量趨勢強度',
      buy: 'ROC 為正，價格動能向上',
      sell: 'ROC 轉負或持有期滿，動能衰竭',
      hold: '動量中性，觀望',
    },
    mean_reversion: {
      name: '均值回歸',
      full: '均值回歸 Z-score 策略',
      desc: '價格偏離均線過遠時期待回歸',
      buy: 'Z-score 極低（超賣），博反彈',
      sell: 'Z-score 回歸均值以上，獲利了結',
      hold: '偏離不大，無交易機會',
    },
    volume_price: {
      name: '量價齊升',
      full: '量價齊升策略',
      desc: '價格與成交量需同向配合才確認信號',
      buy: '價格站上均線且放量上漲',
      sell: '跌破均線或縮量走弱',
      hold: '量價不配合，觀望',
    },
    breakout: {
      name: '突破',
      full: 'N 日高點突破策略',
      desc: '創新高買入，ATR 移動止損保護',
      buy: '突破 N 日最高價，趨勢延續',
      sell: '觸發 ATR 移動止損，保護利潤',
      hold: '未創新高，等待突破',
    },
    composite: {
      name: '組合投票',
      full: '多策略組合投票策略',
      desc: '綜合均線、MACD、RSI、布林等多數決',
      buy: '多數子策略同時看多',
      sell: '多數子策略同時看空',
      hold: '子策略意見分歧',
    },
    vwap: {
      name: 'VWAP',
      full: 'VWAP 成交量加權策略',
      desc: '以成交量加權均價作為多空分界',
      buy: '價格站上 VWAP，資金偏多',
      sell: '價格跌破 VWAP，資金偏空',
      hold: '圍繞 VWAP 震盪',
    },
    envelope: {
      name: '均線通道',
      full: '均線通道策略',
      desc: '均線上下一定百分比形成通道',
      buy: '觸及通道下軌，偏超賣',
      sell: '觸及通道上軌，偏超買',
      hold: '在通道中部運行',
    },
    parabolic_sar: {
      name: '拋物線 SAR',
      full: '拋物線 SAR 策略',
      desc: 'SAR 點位翻轉標記趨勢反轉',
      buy: 'SAR 翻至價格下方，趨勢轉多',
      sell: 'SAR 翻至價格上方，趨勢轉空',
      hold: 'SAR 與價格貼近，方向待確認',
    },
    obv: {
      name: 'OBV',
      full: 'OBV 能量潮策略',
      desc: '用累積成交量方向驗證價格趨勢',
      buy: 'OBV 與價格同步上行，資金流入',
      sell: 'OBV 走弱或背離，資金流出',
      hold: '量能平淡，趨勢未確認',
    },
    bollinger_squeeze: {
      name: '布林收窄',
      full: '布林帶收窄突破策略',
      desc: '波動收斂後等待方向性突破',
      buy: '向上突破收窄區間',
      sell: '向下跌破或平倉信號',
      hold: '仍處收窄盤整，等待突破',
    },
    adx_trend: {
      name: 'ADX 趨勢',
      full: 'ADX 趨勢強度策略',
      desc: 'ADX 衡量趨勢強度，+DI/-DI 定方向',
      buy: 'ADX 強且 +DI 上穿 -DI，趨勢做多',
      sell: 'ADX 走弱或 -DI 占優，趨勢結束',
      hold: 'ADX 低於閾值，無明顯趨勢',
    },
  },

  /** 圖表/表格用策略中文名：short | full | chart（截斷） */
  strategyName(key, mode = 'short') {
    const st = this.getStrategy(key);
    if (mode === 'full') return st.full;
    if (mode === 'chart') {
      const n = st.name || st.full;
      return n.length > 14 ? n.slice(0, 12) + '…' : n;
    }
    return st.name;
  },

  /** 圖表系列 label 本地化（策略 key、code+策略、常見英文詞） */
  label(text) {
    const raw = String(text ?? '').trim();
    if (!raw) return raw;
    if (this.STRATEGIES[raw]) return this.strategyName(raw, 'chart');

    const codeStrat = raw.match(/^(\S+)\s+([a-z][a-z0-9_]+)$/i);
    if (codeStrat && this.STRATEGIES[codeStrat[2]]) {
      return `${codeStrat[1]} ${this.strategyName(codeStrat[2], 'short')}`;
    }

    const dotParts = raw.split('·');
    if (dotParts.length === 2 && this.STRATEGIES[dotParts[1]]) {
      return `${dotParts[0]}·${this.strategyName(dotParts[1], 'short')}`;
    }

    let out = raw;
    const terms = [
      [/Sortino/gi, '索提諾比率'],
      [/Calmar/gi, '卡瑪比率'],
      [/Sharpe/gi, '夏普比率'],
      [/\bOOS\b/g, '樣本外'],
      [/Walk[- ]?Forward/gi, '滾動窗口驗證'],
      [/\bIS\b/g, '樣本內'],

      [/\bTop\b/gi, '前'],
      [/\bReturn\b/gi, '收益'],
      [/\bVolume\b/gi, '成交量'],
      [/\bPrice\b/gi, '價格'],
      [/\bRisk\b/gi, '風險'],
      [/\bClose\b/gi, '收盤價'],
      [/\bOpen\b/gi, '開盤價'],
      [/\bHigh\b/gi, '最高'],
      [/\bLow\b/gi, '最低'],
      [/\bBuy\b/gi, '買入'],
      [/\bSell\b/gi, '賣出'],
      [/\bHold\b/gi, '觀望'],
      [/\bBenchmark\b/gi, '基準'],
      [/\bAlpha\b/gi, 'Alpha'],
      [/\bBeta\b/gi, 'Beta'],
      [/\bNAV\b/gi, '淨值'],
      [/\bNav\b/g, '淨值'],
      [/\bPortfolio\b/gi, '組合'],
      [/\bEqual\s*weight\b/gi, '等權'],
      [/\bWindow\b/gi, '窗口'],
      [/^W(\d+)$/i, '窗口$1'],
      [/\bYes\b/g, 'Yes'],
      [/\bNo\b/g, 'No'],
      [/\bDual\s*Thrust\b/gi, '日內突破'],
      [/\bMACD\b/g, 'MACD'],
      [/\bRSI\b/g, 'RSI'],
      [/\bKDJ\b/g, 'KDJ'],
      [/\bVWAP\b/g, 'VWAP'],
      [/\bOBV\b/g, 'OBV'],
      [/\bADX\b/g, 'ADX'],
    ];
    terms.forEach(([re, zh]) => { out = out.replace(re, zh); });
    return out;
  },

  localizeSeries(series) {
    return (series || []).map(s => ({
      ...s,
      label: this.label(s.label),
    }));
  },

  getStrategy(key) {
    const k = String(key || '').trim();
    return this.STRATEGIES[k] || {
      name: k,
      full: k,
      desc: '自定義或未知策略',
      buy: '策略發出買入信號',
      sell: '策略發出賣出信號',
      hold: '策略建議觀望',
    };
  },

  getSignal(key) {
    const k = String(key || 'hold').toLowerCase();
    return this.SIGNAL[k] || { zh: k, cls: 'cfg', desc: '未知信號類型' };
  },

  /** 當前信號對應的一句話解釋 */
  hintFor(strategyKey, signalKey) {
    const st = this.getStrategy(strategyKey);
    const sig = String(signalKey || 'hold').toLowerCase();
    if (sig === 'buy') return st.buy;
    if (sig === 'sell') return st.sell;
    return st.hold;
  },

  formatStrength(strength) {
    const v = Number(strength) || 0;
    let label = '中性';
    let cls = 'bl';
    let explain = '多空策略意見接近，宜觀望或縮小倉位。';
    if (v > 50) {
      label = '強烈看多';
      cls = 'gn';
      explain = '多數策略偏向買入，綜合動能強勁，但需結合大盤與個股基本面。';
    } else if (v > 20) {
      label = '偏多';
      cls = 'gn';
      explain = '買入信號略多於賣出，短期動能偏強。';
    } else if (v < -50) {
      label = '強烈看空';
      cls = 'rd';
      explain = '多數策略偏向賣出，綜合動能疲弱，注意回撤風險。';
    } else if (v < -20) {
      label = '偏空';
      cls = 'rd';
      explain = '賣出信號略多於買入，短期動能偏弱。';
    }
    return {
      value: v,
      label,
      cls,
      explain,
      text: `綜合強度 ${v.toFixed(2)}（${label}）：${explain}`,
    };
  },

  summarizeSignals(signals) {
    const list = signals || [];
    let buy = 0;
    let sell = 0;
    let hold = 0;
    list.forEach(s => {
      const sig = String(s.signal || s.type || 'hold').toLowerCase();
      if (sig === 'buy') buy++;
      else if (sig === 'sell') sell++;
      else hold++;
    });
    const total = list.length || 1;
    const parts = [];
    if (buy) parts.push(`買入 ${buy}`);
    if (sell) parts.push(`賣出 ${sell}`);
    if (hold) parts.push(`觀望 ${hold}`);
    return {
      buy,
      sell,
      hold,
      total,
      text: parts.length
        ? `${list.length} 個策略：${parts.join(' · ')}`
        : '暫無策略明細',
      consensus: buy > sell
        ? `看多策略佔比約 ${Math.round((buy / total) * 100)}%`
        : sell > buy
          ? `看空策略佔比約 ${Math.round((sell / total) * 100)}%`
          : '多空策略數量接近',
    };
  },

  renderChip(strategyKey, signalKey) {
    const st = this.getStrategy(strategyKey);
    const sig = this.getSignal(signalKey);
    const hint = this.hintFor(strategyKey, signalKey);
    const title = `${st.full}：${st.desc}\n${sig.zh} — ${hint}`;
    return `<span class="sig-chip ${sig.cls}" title="${this._esc(title)}">
      <span class="sig-chip-top"><strong>${this._esc(st.name)}</strong><em>${this._esc(sig.zh)}</em></span>
      <span class="sig-chip-hint">${this._esc(hint)}</span>
    </span>`;
  },

  renderStockCard(item) {
    const code = item.code || '';
    const name = item.name || '';
    const signals = item.signals || item.strategies || [];
    const strengthMeta = this.formatStrength(item.strength);
    const summary = this.summarizeSignals(signals);
    const chips = signals.map(s =>
      this.renderChip(s.strategy || s.name, s.signal)
    ).join('');
    const time = item.updated_at || item.triggered_at || '';

    const openAttr = code
      ? ` role="button" tabindex="0" class="sig-stock-head sig-stock-head--link" onclick="App.openStockDetail('${String(code).replace(/'/g, "\\'")}')" title="打開 ${this._esc(code)} 獨立詳情頁"`
      : '';
    return `<div class="sig-stock-card">
      <div${openAttr}>
        <div>
          <strong class="sig-stock-code">${this._esc(code)}</strong>
          ${name ? `<span class="sig-stock-name">${this._esc(name)}</span>` : ''}
        </div>
        <span class="b ${strengthMeta.cls} sig-strength-val">${strengthMeta.value.toFixed(2)}</span>
      </div>
      <p class="sig-strength-line">
        <span class="b ${strengthMeta.cls}">${strengthMeta.label}</span>
        · ${this._esc(summary.text)}
      </p>
      <p class="sig-explain">${this._esc(strengthMeta.explain)} ${this._esc(summary.consensus)}</p>
      ${time ? `<p class="sig-time">更新：${this._esc(time)}</p>` : ''}
      <div class="sig-chip-grid">${chips || '<span class="sig-empty">暫無策略明細</span>'}</div>
    </div>`;
  },

  _esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },
};

window.SignalLabels = SignalLabels;
