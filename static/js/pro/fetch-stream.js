/* global Api */

/**
 * NDJSON ReadableStream 增量解析（配合 /api/*/stream 端點）
 */
(() => {
  async function fetchStream(url, onChunk, onComplete, opts = {}) {
    const headers = { Accept: 'application/x-ndjson', ...(opts.headers || {}) };
    const token = (typeof Api !== 'undefined' && Api._token) || SecureStore.getItem('sq_token') || '';
    if (token) headers.Authorization = `Bearer ${token}`;

    const res = await fetch(url, { ...opts, headers });
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const err = await res.json();
        msg = err.msg || err.detail || msg;
        if (err.trace_id) msg += ` (${err.trace_id})`;
      } catch (_) {}
      throw new Error(msg || `HTTP ${res.status}`);
    }
    if (!res.body) {
      onComplete?.();
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        onChunk(JSON.parse(trimmed));
      }
    }
    if (buffer.trim()) onChunk(JSON.parse(buffer.trim()));
    onComplete?.();
  }

  /** 將 NDJSON 分塊合併為單一陣列（每塊為 array） */
  async function fetchStreamFlat(url, opts = {}) {
    const out = [];
    await fetchStream(
      url,
      (chunk) => {
        if (Array.isArray(chunk)) out.push(...chunk);
        else if (chunk != null) out.push(chunk);
      },
      null,
      opts,
    );
    return out;
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.FetchStream = { fetchStream, fetchStreamFlat };
})();
