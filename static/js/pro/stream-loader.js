/* global StockQPro */

/**
 * 流式 / 低並發載入：控制同時請求數，避免瞬間打滿帶寬與主線程解析尖峰。
 */
(() => {
  const DEFAULT_CONCURRENCY = 2;
  const _lanes = Object.create(null);

  function _lane(name) {
    const key = name || 'default';
    if (!_lanes[key]) _lanes[key] = { active: 0, queue: [] };
    return _lanes[key];
  }

  function _pump(laneName, maxConcurrent) {
    const lane = _lane(laneName);
    const cap = Math.max(1, maxConcurrent || DEFAULT_CONCURRENCY);
    while (lane.active < cap && lane.queue.length) {
      const job = lane.queue.shift();
      lane.active += 1;
      Promise.resolve()
        .then(() => job.fn())
        .then(job.resolve, job.reject)
        .finally(() => {
          lane.active -= 1;
          _pump(laneName, cap);
        });
    }
  }

  function enqueue(fn, maxConcurrent, laneName) {
    return new Promise((resolve, reject) => {
      _lane(laneName).queue.push({ fn, resolve, reject });
      _pump(laneName, maxConcurrent);
    });
  }

  /** 依序執行（並發=1，最低流量尖峰） */
  async function runSequential(fns, gapMs = 0) {
    for (const fn of fns) {
      await fn();
      if (gapMs > 0) await new Promise((r) => setTimeout(r, gapMs));
    }
  }

  /** 低並發執行任務列表 */
  async function runPool(fns, maxConcurrent = DEFAULT_CONCURRENCY) {
    if (!fns?.length) return;
    let i = 0;
    const workers = Array.from({ length: Math.min(maxConcurrent, fns.length) }, async () => {
      while (i < fns.length) {
        const idx = i;
        i += 1;
        await fns[idx]();
      }
    });
    await Promise.all(workers);
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.StreamLoader = {
    enqueue,
    runSequential,
    runPool,
    DEFAULT_CONCURRENCY,
  };
})();
