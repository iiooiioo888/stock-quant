/* global Api */

/**
 * Pro 標的選擇共用：熱門 / 搜尋 / 資產庫（避免各頁只顯示 8 檔硬編碼）
 */
(() => {
  const FALLBACK_HOT = [
    { code: '600519', name: '貴州茅台' },
    { code: '600036', name: '招商銀行' },
    { code: '000001', name: '平安銀行' },
    { code: '000858', name: '五糧液' },
    { code: '601318', name: '中國平安' },
    { code: '300750', name: '寧德時代' },
    { code: '002594', name: '比亞迪' },
    { code: '600900', name: '長江電力' },
    { code: '601012', name: '隆基綠能' },
    { code: '600276', name: '恆瑞醫藥' },
    { code: '000333', name: '美的集團' },
    { code: '601166', name: '興業銀行' },
    { code: '600030', name: '中信證券' },
    { code: '000651', name: '格力電器' },
    { code: '601888', name: '中國中免' },
    { code: '002475', name: '立訊精密' },
    { code: '300059', name: '東方財富' },
    { code: '688981', name: '中芯國際' },
    { code: '601899', name: '紫金礦業' },
    { code: '600887', name: '伊利股份' },
    { code: '000568', name: '瀘州老窖' },
    { code: '002415', name: '海康威視' },
    { code: '601398', name: '工商銀行' },
    { code: '600000', name: '浦發銀行' },
  ];

  function normalizeCode(raw) {
    const s = String(raw || '').trim();
    if (/^\d{1,6}$/.test(s)) return s.padStart(6, '0');
    const m = s.match(/(\d{6})/);
    if (m) return m[1];
    if (s.includes('.')) return s.split('.')[0].replace(/\D/g, '').padStart(6, '0').slice(-6);
    return s;
  }

  function isValidAshare(code) {
    return /^\d{6}$/.test(code);
  }

  function dedupeByCode(items) {
    const seen = new Set();
    return items.filter((i) => {
      if (!i?.code || seen.has(i.code)) return false;
      seen.add(i.code);
      return true;
    });
  }

  function mapUniverseRows(stocks, namesMap = {}) {
    return dedupeByCode(
      (stocks || []).map((s) => ({
        code: normalizeCode(s.code),
        name: s.name || namesMap[s.code] || s.code,
        extra: s.industry || s.market_cap_str || '',
      })).filter((x) => isValidAshare(x.code)),
    );
  }

  async function fetchHotAshare(namesMap = {}, limit = 48) {
    try {
      const d = await Api.getStockUniverse('a_share', limit, 0, '');
      const rows = mapUniverseRows(d?.stocks, namesMap);
      if (rows.length >= 12) return rows;
    } catch (_) { /* fallback */ }
    return dedupeByCode(FALLBACK_HOT.map((x) => ({
      code: x.code,
      name: x.name || namesMap[x.code] || x.code,
    })));
  }

  async function searchAshare(keyword, namesMap = {}, limit = 80) {
    const q = String(keyword || '').trim();
    if (!q) return [];
    try {
      const d = await Api.getStockUniverse('a_share', limit, 0, q);
      const rows = mapUniverseRows(d?.stocks, namesMap);
      if (rows.length) return rows;
    } catch (_) { /* local */ }
    return dedupeByCode(
      Object.entries(namesMap)
        .filter(([code, name]) => code.includes(q) || String(name).includes(q))
        .slice(0, limit)
        .map(([code, name]) => ({ code: normalizeCode(code), name: name || code })),
    ).filter((x) => isValidAshare(x.code));
  }

  function suggestFromNames(raw, namesMap, limit = 20) {
    const q = String(raw || '').trim();
    if (!q) return [];
    return dedupeByCode(
      Object.entries(namesMap)
        .filter(([code, name]) => code.startsWith(q) || String(name).includes(q))
        .slice(0, limit)
        .map(([code, name]) => ({ code: normalizeCode(code), name: name || code })),
    ).filter((x) => isValidAshare(x.code));
  }

  async function loadCatalogAshare(namesMap = {}) {
    let list = [];
    try {
      const d = await Api.getAssetsCatalog();
      list = dedupeByCode(
        (d?.instruments || [])
          .filter((i) => i.group === 'a_share' && i.asset_class === 'stock')
          .map((i) => {
            const code = normalizeCode(i.symbol);
            return { code, name: i.name || namesMap[code] || code };
          })
          .filter((i) => isValidAshare(i.code)),
      );
    } catch (_) { /* ignore */ }

    if (list.length < 50 && Object.keys(namesMap).length) {
      const fromNames = dedupeByCode(
        Object.entries(namesMap).map(([code, name]) => ({
          code: normalizeCode(code),
          name: name || code,
        })).filter((i) => isValidAshare(i.code)),
      );
      list = dedupeByCode([...list, ...fromNames]);
    }

    if (list.length < 50) {
      try {
        const d = await Api.getStockUniverse('a_share', 800, 0, '');
        const uni = mapUniverseRows(d?.stocks, namesMap);
        list = dedupeByCode([...list, ...uni]);
      } catch (_) { /* ignore */ }
    }

    return list.sort((a, b) => a.code.localeCompare(b.code));
  }

  /** 多股對比快捷組合（代碼列表） */
  const COMPARE_PRESETS = [
    { id: 'liquor', label: '白酒龍頭', codes: ['600519', '000858', '000568', '600809'] },
    { id: 'bank', label: '銀行板塊', codes: ['600036', '601398', '601166', '000001', '601288'] },
    { id: 'new_energy', label: '新能源', codes: ['300750', '002594', '601012', '300014', '002460'] },
    { id: 'tech', label: '科技成長', codes: ['688981', '002415', '300059', '002475', '000725'] },
    { id: 'dividend', label: '高股息', codes: ['600900', '601088', '600028', '601857', '600887'] },
    { id: 'index_core', label: '滬深核心', codes: ['600519', '601318', '600036', '300750', '000333'] },
  ];

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.stockPickData = {
    FALLBACK_HOT,
    COMPARE_PRESETS,
    normalizeCode,
    isValidAshare,
    fetchHotAshare,
    searchAshare,
    suggestFromNames,
    loadCatalogAshare,
  };
})();
