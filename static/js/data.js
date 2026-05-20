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
  _currentTab: 'download',
  _SUB_TABS: ['download', 'universe', 'sectors', 'rotation', 'heatmap', 'capital', 'north', 'dragon', 'fundamental', 'basics'],
  _universeOffset: 0,
  _universeTotal: 0,

  init() {
    const tabs = document.getElementById('dataTabs');
    if (!tabs) return;
    tabs.addEventListener('click', e => {
      const btn = e.target.closest('button[data-dtab]');
      if (!btn) return;
      tabs.querySelectorAll('button').forEach(b => b.classList.remove('a'));
      btn.classList.add('a');
      this._currentTab = btn.dataset.dtab;
      this._applyTabVisibility();
      this._onTabActivated(this._currentTab);
    });
    this._applyTabVisibility();
    this._onTabActivated(this._currentTab);
  },

  _applyTabVisibility() {
    this._SUB_TABS.forEach(t => {
      const el = document.getElementById('dtab-' + t);
      if (el) el.classList.toggle('h', t !== this._currentTab);
    });
  },

  _escHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  _sectorOnclick(name) {
    const esc = this._escHtml(name).replace(/'/g, "\\'");
    return `Data.showSectorDetail('${esc}')`;
  },

  _onTabActivated(tab) {
    if (tab === 'download') this.refreshDbStats();
    if (tab === 'universe') {
      this.loadUniverseStats();
      if (this._universeTotal > 0) this.searchUniverse(this._universeOffset);
    }
    if (tab === 'capital' && typeof ProCharts !== 'undefined') {
      ProCharts.loadCapitalTabCharts();
    }
    if (tab === 'north') this.loadNorthFlow();
    if (tab === 'dragon') this.loadDragonTiger();
    if ((tab === 'sectors' || tab === 'heatmap') && typeof Charts !== 'undefined') {
      requestAnimationFrame(() => Charts.resizeTab('tab-data'));
    }
  },

  _apiFailMessage(container, action) {
    if (!container) return;
    const loggedIn = typeof Api !== 'undefined' && Api.isLoggedIn();
    container.innerHTML = loggedIn
      ? `<p style="color:var(--text-dim)">${action}失敗，請稍後重試</p>`
      : `<p style="color:var(--text-dim)">${action}需要登錄或接口暫不可用，請點右上角登錄後重試</p>`;
  },

  _flowOrderSize(f) {
    return {
      super: f.super_large ?? f.super_net ?? f.super_large_net ?? 0,
      large: f.large ?? f.big_net ?? f.large_net ?? 0,
      medium: f.medium ?? f.mid_net ?? f.medium_net ?? 0,
      small: f.small ?? f.small_net ?? 0,
    };
  },

  _northDailyRows(d) {
    if (d?.daily?.length) return d.daily;
    const flows = d?.flows || [];
    const byDate = {};
    flows.forEach(f => {
      const date = f.date;
      if (!date) return;
      if (!byDate[date]) byDate[date] = { date, sh_net: 0, sz_net: 0, total_net: 0 };
      const code = String(f.code || '');
      const net = Number(f.main_net) || 0;
      if (code.includes('沪')) byDate[date].sh_net += net;
      else if (code.includes('深')) byDate[date].sz_net += net;
      else {
        byDate[date].sh_net += Number(f.sh_net) || 0;
        byDate[date].sz_net += Number(f.sz_net) || 0;
      }
      byDate[date].total_net = byDate[date].sh_net + byDate[date].sz_net;
    });
    return Object.values(byDate).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  },

  load() {
    this._applyTabVisibility();
    this._onTabActivated(this._currentTab);
  },

  _parseDownloadCodes() {
    const raw = document.getElementById('dbDownloadCodes')?.value?.trim();
    if (!raw) return null;
    return raw.split(/[,，\s\n]+/).map(s => s.trim()).filter(Boolean);
  },

  async refreshDbStats() {
    const d = await Api.getHealth();
    if (!d) return;
    const fmt = n => (n ?? 0).toLocaleString();
    const elStocks = document.getElementById('dbStatStocks');
    const elKlines = document.getElementById('dbStatKlines');
    const elSize = document.getElementById('dbStatSize');
    if (elStocks) elStocks.textContent = fmt(d.total_stocks);
    if (elKlines) elKlines.textContent = fmt(d.total_klines);
    if (elSize) elSize.textContent = (d.db_size_mb ?? 0) + ' MB';
  },

  async downloadToDb() {
    const btn = document.getElementById('dbDownloadBtn');
    const el = document.getElementById('dbDownloadResult');
    const codes = this._parseDownloadCodes();
    Utils.btnLoading(btn, true, '提交中...');
    if (el) el.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 任務已提交，正在爬取並寫入本地庫…</p>';
    try {
      const d = await Api.downloadStocks(codes);
      const poll = typeof App !== 'undefined' && App._downloadPollOptions
        ? App._downloadPollOptions((task) => {
          if (!el || typeof TaskCommon === 'undefined') return;
          const sub = TaskCommon.formatTaskSubtitle(task);
          if (sub) el.innerHTML = `<p style="color:var(--text-dim)"><span class="ld"></span> ${sub}</p>`;
        })
        : { timeout: 7200000, interval: 2000 };
      const resolved = await Api.resolveTaskResponse(d, poll);
      const result = Api.extractResult(resolved);
      if (resolved?.success && result) {
        const line = (typeof TaskCommon !== 'undefined' && TaskCommon.downloadResultLine(result))
          || `共 ${result.total_records ?? 0} 條`;
        if (el) el.innerHTML = `<div class="chip on">✅ 已寫入本地庫：${line}</div>`;
        await this.refreshDbStats();
        Utils.toast('下載完成', 3000, 'success');
      } else if (el) {
        const err = resolved?.task?.error || '下載失敗';
        el.innerHTML = `<div class="chip off">❌ ${err}</div>`;
      }
    } catch (e) {
      if (el) el.innerHTML = `<div class="chip off">❌ ${e.message || e}</div>`;
    } finally {
      Utils.btnLoading(btn, false, '📥 下載日 K');
    }
  },

  async incrementalToDb() {
    const btn = document.getElementById('dbIncrementalBtn');
    const el = document.getElementById('dbDownloadResult');
    const codes = this._parseDownloadCodes();
    const force = !!document.getElementById('dbForceUpdate')?.checked;
    Utils.btnLoading(btn, true, '更新中...');
    if (el) el.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 增量更新中…</p>';
    try {
      const d = await Api.updateStocks(codes, force);
      const poll = typeof App !== 'undefined' && App._downloadPollOptions
        ? App._downloadPollOptions((task) => {
          if (!el || typeof TaskCommon === 'undefined') return;
          const sub = TaskCommon.formatTaskSubtitle(task);
          if (sub) el.innerHTML = `<p style="color:var(--text-dim)"><span class="ld"></span> ${sub}</p>`;
        })
        : { timeout: 3600000, interval: 2000 };
      const resolved = await Api.resolveTaskResponse(d, poll);
      const result = Api.extractResult(resolved);
      if (resolved?.success && result) {
        const msg = `更新 ${result.updated ?? 0} 只，跳過 ${result.skipped ?? 0} 只，新增 ${result.total_records ?? 0} 條`;
        if (el) el.innerHTML = `<div class="chip on">✅ ${msg}</div>`;
        await this.refreshDbStats();
        Utils.toast('增量更新完成', 3000, 'success');
      } else if (el) {
        el.innerHTML = '<div class="chip off">❌ 增量更新失敗</div>';
      }
    } catch (e) {
      if (el) el.innerHTML = `<div class="chip off">❌ ${e.message || e}</div>`.replace('<div class', '<div class').replace('</div>', '</div>');
    } finally {
      Utils.btnLoading(btn, false, '🔄 增量更新');
    }
  },

  // ============================================================
  // 股票庫
  // ============================================================

  _marketLabel(m) {
    const map = { a_share: 'A股', hk_stock: '港股', us_stock: '美股' };
    return map[m] || m || '-';
  },

  async loadUniverseStats() {
    const d = await Api.getStockUniverseStats();
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    if (!d || d.total === 0) {
      set('univStatTotal', '0');
      set('univStatUpdated', '未同步');
      set('univStatAshare', '-');
      set('univStatHk', '-');
      set('univStatUs', '-');
      const hint = document.getElementById('univSyncHint');
      if (hint) hint.textContent = '尚未同步，請點「一鍵同步股票庫」（需登錄）';
      return;
    }
    set('univStatTotal', (d.total ?? 0).toLocaleString());
    set('univStatUpdated', d.updated_at || '-');
    const mk = d.markets || {};
    set('univStatAshare', mk.a_share?.count ?? 0);
    set('univStatHk', mk.hk_stock?.count ?? 0);
    set('univStatUs', mk.us_stock?.count ?? 0);
    const hint = document.getElementById('univSyncHint');
    if (hint) hint.textContent = `已入庫 ${d.total} 檔，按市值排名`;
    this._universeTotal = d.total;
  },

  async syncStockUniverse() {
    const btn = document.getElementById('univSyncBtn');
    const el = document.getElementById('univSyncResult');
    if (!Api.isLoggedIn()) {
      Utils.toast('請先登錄後再同步股票庫', 4000, 'warning');
      Api.showLoginModal(false);
      return;
    }
    Utils.btnLoading(btn, true, '同步中...');
    if (el) el.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 已提交任務，正在拉取 A/HK/US 行情（約 1–3 分鐘）…</p>';
    try {
      const d = await Api.syncStockUniverse();
      const poll = typeof App !== 'undefined' && App._downloadPollOptions
        ? App._downloadPollOptions((task) => {
          if (!el || typeof TaskCommon === 'undefined') return;
          const sub = TaskCommon.formatTaskSubtitle(task) || task.message;
          if (sub) el.innerHTML = `<p style="color:var(--text-dim)"><span class="ld"></span> ${sub}</p>`;
        })
        : { timeout: 600000, interval: 2500 };
      const resolved = await Api.resolveTaskResponse(d, poll);
      const result = Api.extractResult(resolved);
      if (resolved?.success && result) {
        const by = result.by_market || {};
        const parts = Object.entries(by).map(([k, n]) => `${this._marketLabel(k)} ${n}`).join(' · ');
        if (el) {
          el.innerHTML = `<div class="chip on">✅ 入庫 ${result.saved} 條（池內 ${result.total_pool}）${parts ? ' — ' + parts : ''}</div>`;
        }
        if (result.note) {
          if (el) el.innerHTML += `<p class="sec-desc mt-sm">${result.note}</p>`;
        }
        await this.loadUniverseStats();
        this.searchUniverse(0);
        Utils.toast('股票庫同步完成', 3500, 'success');
      } else if (el) {
        el.innerHTML = `<div class="chip off">❌ ${resolved?.task?.error || resolved?.message || '同步失敗'}</div>`;
      }
    } catch (e) {
      if (el) el.innerHTML = `<div class="chip off">❌ ${e.message || e}</div>`;
    } finally {
      Utils.btnLoading(btn, false, '⚡ 一鍵同步股票庫');
    }
  },

  async enrichUniverseIntros() {
    const btn = document.getElementById('univIntroBtn');
    const el = document.getElementById('univSyncResult');
    if (!Api.isLoggedIn()) {
      Utils.toast('請先登錄後再補充簡介', 4000, 'warning');
      Api.showLoginModal(false);
      return;
    }
    Utils.btnLoading(btn, true, '補充中...');
    if (el) el.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 已提交簡介補充任務（按市值優先，約數分鐘）…</p>';
    try {
      const d = await Api.enrichStockUniverseIntros();
      if (!d?.success) {
        const msg = d?.detail || d?.message || (d == null ? '接口不可用（請重啟後端服務後再試）' : '提交失敗');
        if (el) el.innerHTML = `<div class="chip off">❌ ${msg}</div>`;
        return;
      }
      const poll = typeof App !== 'undefined' && App._downloadPollOptions
        ? App._downloadPollOptions((task) => {
          if (!el || typeof TaskCommon === 'undefined') return;
          const sub = TaskCommon.formatTaskSubtitle(task) || task.message;
          if (sub) el.innerHTML = `<p style="color:var(--text-dim)"><span class="ld"></span> ${sub}</p>`;
        })
        : { timeout: 900000, interval: 2500 };
      const resolved = await Api.resolveTaskResponse(d, poll);
      const result = Api.extractResult(resolved);
      const task = resolved?.task;
      if (task?.status === 'failed' || task?.status === 'cancelled') {
        if (el) el.innerHTML = `<div class="chip off">❌ ${task.error || '任務失敗'}</div>`;
        return;
      }
      if (resolved?.success && result != null) {
        const note = result.note ? `<p class="sec-desc mt-sm">${result.note}</p>` : '';
        if (el) {
          el.innerHTML = `<div class="chip on">✅ 簡介補充完成：${result.enriched ?? 0} / ${result.attempted ?? 0}</div>${note}`;
        }
        await this.loadUniverseStats();
        this.searchUniverse(0);
        Utils.toast(`已更新 ${result.enriched ?? 0} 檔簡介`, 3500, 'success');
      } else if (el) {
        el.innerHTML = `<div class="chip off">❌ ${task?.error || resolved?.message || '補充失敗（請重啟後端）'}</div>`;
      }
    } catch (e) {
      if (el) el.innerHTML = `<div class="chip off">❌ ${e.message || e}</div>`;
    } finally {
      Utils.btnLoading(btn, false, '📝 補充簡介');
    }
  },

  async searchUniverse(offset) {
    const wrap = document.getElementById('univTableWrap');
    const pager = document.getElementById('univPager');
    if (!wrap) return;

    const market = document.getElementById('univMarket')?.value || 'all';
    const keyword = document.getElementById('univKeyword')?.value?.trim() || '';
    const limit = Math.min(200, Math.max(10, parseInt(document.getElementById('univLimit')?.value, 10) || 50));
    this._universeOffset = Math.max(0, offset || 0);

    wrap.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 查詢中...</p>';
    const d = await Api.getStockUniverse(market, limit, this._universeOffset, keyword);
    if (!d) {
      this._apiFailMessage(wrap, '股票庫查詢');
      if (pager) pager.style.display = 'none';
      return;
    }

    this._universeTotal = d.total ?? 0;
    const stocks = d.stocks || [];
    if (!stocks.length) {
      wrap.innerHTML = '<p style="color:var(--text-dim)">無匹配結果。請先同步股票庫或調整篩選條件。</p>';
      if (pager) pager.style.display = 'none';
      return;
    }

    wrap.innerHTML = `<div class="table-wrap"><table>
      <thead><tr>
        <th>排名</th><th>代碼</th><th>名稱</th><th>簡介</th><th>市場</th>
        <th class="r">市值(億)</th><th class="r">漲跌幅</th><th class="r">PE</th><th class="r">PB</th><th>行業</th>
      </tr></thead>
      <tbody>${stocks.map(s => {
        const chg = s.change_pct;
        const chgCls = Utils.badgeClass(chg);
        const intro = s.intro || s.industry || '-';
        return `<tr>
          <td class="univ-rank">#${s.rank_mv ?? '-'}</td>
          <td><code>${this._escHtml(s.code)}</code></td>
          <td>${this._escHtml(s.name || '-')}</td>
          <td class="univ-intro" title="${this._escHtml(intro)}">${this._escHtml(intro)}</td>
          <td><span class="univ-market-tag">${this._escHtml(this._marketLabel(s.market))}</span></td>
          <td class="r">${s.total_mv != null ? Number(s.total_mv).toFixed(2) : '-'}</td>
          <td class="r"><span class="b ${chgCls}">${chg != null ? Utils.formatPct(chg) : '-'}</span></td>
          <td class="r">${s.pe_ttm > 0 ? Number(s.pe_ttm).toFixed(2) : '-'}</td>
          <td class="r">${s.pb > 0 ? Number(s.pb).toFixed(2) : '-'}</td>
          <td>${this._escHtml(s.industry || '-')}</td>
        </tr>`;
      }).join('')}</tbody>
    </table></div>`;

    if (pager) {
      pager.style.display = 'flex';
      const pageInfo = document.getElementById('univPageInfo');
      const prev = document.getElementById('univPrevBtn');
      const next = document.getElementById('univNextBtn');
      const from = this._universeOffset + 1;
      const to = Math.min(this._universeOffset + limit, this._universeTotal);
      if (pageInfo) pageInfo.textContent = `${from}-${to} / 共 ${this._universeTotal}`;
      if (prev) prev.disabled = this._universeOffset <= 0;
      if (next) next.disabled = this._universeOffset + limit >= this._universeTotal;
    }
  },

  universePrevPage() {
    const limit = parseInt(document.getElementById('univLimit')?.value, 10) || 50;
    this.searchUniverse(Math.max(0, this._universeOffset - limit));
  },

  universeNextPage() {
    const limit = parseInt(document.getElementById('univLimit')?.value, 10) || 50;
    this.searchUniverse(this._universeOffset + limit);
  },

  fillDownloadFromUniverse() {
    const wrap = document.getElementById('univTableWrap');
    const codes = [];
    wrap?.querySelectorAll('tbody tr code')?.forEach(el => {
      const c = el.textContent?.trim();
      if (c) codes.push(c);
    });
    if (!codes.length) {
      Utils.toast('請先查詢股票庫列表', 3000, 'warning');
      return;
    }
    const ta = document.getElementById('dbDownloadCodes');
    if (ta) ta.value = codes.join(',');
    const tabs = document.getElementById('dataTabs');
    tabs?.querySelectorAll('button').forEach(b => b.classList.remove('a'));
    const dlBtn = tabs?.querySelector('button[data-dtab="download"]');
    if (dlBtn) dlBtn.classList.add('a');
    this._currentTab = 'download';
    this._applyTabVisibility();
    this._onTabActivated('download');
    Utils.toast(`已填入 ${codes.length} 個代碼到「下載入庫」`, 3000, 'success');
  },

  // ============================================================
  // 板塊行情（增強版）
  // ============================================================

  async loadSectors() {
    const container = document.getElementById('sectorData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getSectors('industry', 30);
    if (!d) {
      this._apiFailMessage(container, '板塊行情載入');
      return;
    }
    if (!d.sectors || !d.sectors.length) {
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
        <td><strong><a href="javascript:void(0)" onclick="${this._sectorOnclick(s.name)}" style="color:var(--accent);text-decoration:none">${this._escHtml(s.name) || '-'}</a></strong></td>
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
    if (!d) {
      this._apiFailMessage(container, '板塊輪動分析');
      return;
    }
    if (!d.rotation || !d.rotation.length) {
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
          <td><strong><a href="javascript:void(0)" onclick="${this._sectorOnclick(r.name)}" style="color:var(--accent);text-decoration:none">${this._escHtml(r.name)}</a></strong></td>
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
          <td><strong><a href="javascript:void(0)" onclick="${this._sectorOnclick(r.name)}" style="color:var(--accent);text-decoration:none">${this._escHtml(r.name)}</a></strong></td>
          <td class="r"><span class="b" style="background:rgba(239,68,68,0.15);color:#ef4444">↓${Math.abs(r.rank_change)}</span></td>
          <td class="r">${r.current_rank}</td>
          <td class="r">${r.prev_rank}</td>
          <td class="r"><span class="b ${Utils.badgeClass(r.avg_change_pct)}">${Utils.formatPct(r.avg_change_pct)}</span></td>
          <td class="r">${r.amount ? Utils.formatLargeNum(r.amount) : '-'}</td>
        </tr>`).join('')}</tbody></table></div></div>`;
    }

    container.innerHTML = html;

    if (typeof ProCharts !== 'undefined') {
      ProCharts.renderRotationChart(rotation);
    } else {
      const top20 = rotation.slice(0, 20);
      Charts.drawHorizontalBarChart(
        'rotationChart',
        top20.map(r => r.name),
        top20.map(r => r.rank_change),
        '排名變化',
      );
    }
  },

  // ============================================================
  // 板塊全景熱力圖
  // ============================================================

  async loadSectorHeatmap() {
    const container = document.getElementById('heatmapData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getSectorHeatmap('industry');
    if (!d) {
      this._apiFailMessage(container, '板塊熱力圖載入');
      return;
    }
    if (!d.sectors || !d.sectors.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">暫無板塊數據</p>';
      return;
    }

    container.innerHTML = '<div class="cw cw-treemap" style="position:relative;min-height:500px"><canvas id="sectorHeatmapCanvas" style="width:100%;cursor:pointer"></canvas></div>';
    if (typeof Charts !== 'undefined' && Charts.drawSectorTreemap) {
      Charts.drawSectorTreemap('sectorHeatmapCanvas', d.sectors, 500);
    } else {
      this._drawTreemap(d.sectors);
    }
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

    const weight = s => {
      const amount = Number(s.amount) || 0;
      if (amount > 0) return amount;
      const change = Math.abs(Number(s.change_pct) || 0);
      if (change > 0) return change + 0.5;
      return Number(s.stock_count) || 1;
    };
    const valid = sectors.filter(s => s && s.name);
    if (!valid.length) {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('暫無數據', W / 2, H / 2);
      return;
    }

    valid.sort((a, b) => weight(b) - weight(a));
    const totalAmount = valid.reduce((sum, s) => sum + weight(s), 0);

    const sized = valid.map(s => ({ ...s, amount: weight(s) }));
    const rects = this._squarify(sized, totalAmount, 0, 0, W, H);

    // 顏色映射
    const colors = Charts.getThemeColors();

    // 繪製每個方塊
    rects.forEach((rect, i) => {
      const s = sized[i];
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

      // 保存 rect 信息供點擊/ tooltip
      rect.sectorName = s.name;
      rect.changePct = changePct;
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
    if (!d) {
      this._apiFailMessage(container, '資金流向查詢');
      return;
    }
    if (!d.flows || !d.flows.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">暫無資金流向數據</p>';
      return;
    }
    container.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>日期</th><th>主力淨流入</th><th>超大單</th><th>大單</th><th>中單</th><th>小單</th></tr></thead>
      <tbody>${d.flows.map(f => {
        const o = this._flowOrderSize(f);
        return `<tr>
        <td>${f.date || '-'}</td>
        <td class="r"><span class="b ${Utils.badgeClass(f.main_net)}">${Utils.formatLargeNum(f.main_net)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(o.super)}">${Utils.formatLargeNum(o.super)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(o.large)}">${Utils.formatLargeNum(o.large)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(o.medium)}">${Utils.formatLargeNum(o.medium)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(o.small)}">${Utils.formatLargeNum(o.small)}</span></td>
      </tr>`;
      }).join('')}</tbody>
    </table></div>`;
    if (typeof ProCharts !== 'undefined') ProCharts.renderStockCapitalFlow(d.flows);
  },

  async loadNorthFlow() {
    const container = document.getElementById('northFlowData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getNorthFlow(30);
    if (!d) {
      this._apiFailMessage(container, '北向資金載入');
      return;
    }
    const daily = this._northDailyRows(d);
    if (!daily.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">暫無北向資金數據</p>';
      return;
    }
    container.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>日期</th><th>滬股通</th><th>深股通</th><th>合計</th></tr></thead>
      <tbody>${daily.map(f => `<tr>
        <td>${f.date || '-'}</td>
        <td class="r"><span class="b ${Utils.badgeClass(f.sh_net)}">${Utils.formatLargeNum(f.sh_net)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(f.sz_net)}">${Utils.formatLargeNum(f.sz_net)}</span></td>
        <td class="r"><span class="b ${Utils.badgeClass(f.total_net)}">${Utils.formatLargeNum(f.total_net)}</span></td>
      </tr>`).join('')}</tbody>
    </table></div>`;
    if (typeof ProCharts !== 'undefined') ProCharts.renderNorthFlow(daily);
  },

  async loadDragonTiger() {
    const container = document.getElementById('dragonTigerData');
    if (!container) return;
    container.innerHTML = '<p style="color:var(--text-dim)"><span class="ld"></span> 載入中...</p>';

    const d = await Api.getDragonTiger();
    if (!d) {
      this._apiFailMessage(container, '龍虎榜載入');
      return;
    }
    if (!d.records || !d.records.length) {
      container.innerHTML = '<p style="color:var(--text-dim)">暫無龍虎榜數據</p>';
      return;
    }
    const marketBadge = (r) => {
      const market = r.market_name || r.market || '-';
      const cls = r.market === 'hk_stock' ? 'bl' : (r.market === 'us_stock' ? 'gn' : 'on');
      return `<span class="chip ${cls}">${this._escHtml(market)}</span>`;
    };
    container.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>代碼</th><th>名稱</th><th>市場</th><th>板塊</th><th>原因</th><th>買入額</th><th>賣出額</th><th>淨額</th><th>漲跌幅</th></tr></thead>
      <tbody>${d.records.map(r => `<tr>
        <td>${this._escHtml(r.code || '-')}</td>
        <td>${this._escHtml(r.name || '-')}</td>
        <td>${marketBadge(r)}</td>
        <td><span class="chip">${this._escHtml(r.sector || r.industry || '未分類')}</span></td>
        <td style="font-size:10px">${this._escHtml(r.reason || '-')}</td>
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
      if (!d) {
        this._apiFailMessage(container, '基本面篩選');
        return;
      }
      if (!d.results || !d.results.length) {
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
      if (!d) {
        this._apiFailMessage(container, '基本數據查詢');
        return;
      }
      const o = d.overview;
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
