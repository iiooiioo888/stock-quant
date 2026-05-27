/* global StockQPro */

/**
 * 流式 / 低並發載入：控制同時請求數，避免瞬間打滿帶寬與主線程解析尖峰。
 */
(() => {
  const DEFAULT_CONCURRENCY = 2;

  let _active = 0;
  const _queue = [];

  function _pump(maxConcurrent) {
    const cap = Math.max(1, maxConcurrent || DEFAULT_CONCURRENCY);
    while (_active < cap && _queue.length) {
      const job = _queue.shift();
      _active += 1;
      Promise.resolve()
        .then(() => job.fn())
        .then(job.resolve, job.reject)
        .finally(() => {
          _active -= 1;
          _pump(cap);
        });
    }
  }

  function enqueue(fn, maxConcurrent) {
    return new Promise((resolve, reject) => {
      _queue.push({ fn, resolve, reject });
      _pump(maxConcurrent);
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
