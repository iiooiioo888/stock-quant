/* global StockQPro */
/**
 * 圖表 PNG 導出 — 支援 canvas / svg（ECharts / Chart.js / Lightweight Charts）
 * 不引入 npm；瀏覽器原生 toDataURL。
 */
(() => {
  function filename(name) {
    const base = String(name || 'chart').replace(/[^\w\u4e00-\u9fff.-]+/g, '_');
    return `${base}_${Date.now()}.png`;
  }

  function downloadDataUrl(dataUrl, name) {
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filename(name);
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function canvasFromSvg(svg) {
    const xml = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement('canvas');
        c.width = img.width || svg.clientWidth || 800;
        c.height = img.height || svg.clientHeight || 400;
        const ctx = c.getContext('2d');
        ctx.fillStyle = getComputedStyle(document.body).backgroundColor || '#0b1220';
        ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, 0);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL('image/png'));
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error('svg export failed'));
      };
      img.src = url;
    });
  }

  async function exportElementPng(el, name) {
    if (!el) throw new Error('no chart element');
    const canvas = el.querySelector('canvas');
    if (canvas && canvas.toDataURL) {
      downloadDataUrl(canvas.toDataURL('image/png'), name);
      return true;
    }
    const svg = el.querySelector('svg');
    if (svg) {
      const url = await canvasFromSvg(svg);
      downloadDataUrl(url, name);
      return true;
    }
    throw new Error('no canvas/svg in chart');
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.exportChartPng = exportElementPng;
})();
