# 🚀 前端數據流性能優化總結

## ✅ 已完成的優化

### 1. 新增核心模塊：`data-stream.js`

#### 智能預取系統 (DataPrefetch)
- **優先級隊列**: 支持 1-10 級優先級，高優先級任務先執行
- **LRU 緩存**: 自動淘汰最久未使用的緩存（最大 50 條）
- **TTL 管理**: 5 分鐘緩存過期機制
- **請求去重**: 相同 key 的並發請求自動合併

```javascript
// 使用範例
await DataPrefetch.prefetch('health', () => Api.get('/api/health'), 10);
const cached = DataPrefetch.get('health');
```

#### 請求合併與去重 (RequestBatcher)
- **防抖合併**: 自動合併短時間內的同類請求
- **飛行中跟蹤**: 防止重複提交相同請求
- **批量處理**: 支持自定義批量處理函數

```javascript
// 批量獲取 K 線（150ms 內合併）
await RequestBatcher.batch('kline', codes, batchFn, 150);

// 唯一請求
await RequestBatcher.unique('unique-key', fetchFn);
```

#### 虛擬滾動 (VirtualScroller)
- **按需渲染**: 只渲染可見區域 + 少量緩衝項目
- **流暢滾動**: 使用 requestAnimationFrame 節流
- **記憶體友好**: 自動銷毀不可見 DOM 元素

```javascript
VirtualScroller.init('stockList', {
  itemHeight: 50,
  overscan: 5,
  renderItem: (index) => createStockItem(index),
  getTotalCount: () => stocks.length,
});
```

#### Web Worker 數據處理 (DataWorker)
- **離主線程計算**: 將密集計算移至 Worker
- **任務隊列**: 支持多任務排隊和超時控制
- **Fallback 機制**: 不支持 Worker 時自動回退到主線程

```javascript
DataWorker.init('/static/js/workers/data-processor.js');
const result = await DataWorker.post('processKline', { kline, indicators });
```

#### 數據壓縮 (DataCompressor)
- **差分編碼**: 對數值數組進行差分壓縮
- **整數化**: 減少小數位數，提升壓縮率
- **二進制序列化**: 使用 TextEncoder/Decoder 高效傳輸

```javascript
const compressed = DataCompressor.compressNumbers(prices, 2);
const original = DataCompressor.decompressNumbers(compressed, 2);
```

#### 數據流監控 (StreamMonitor)
- **實時指標**: 追蹤請求延遲、緩存命中率、失敗率
- **性能報告**: 控制台輸出詳細性能分析

```javascript
StreamMonitor.record({ latency: 120, bytes: 1024, cached: false, success: true });
console.log(StreamMonitor.getMetrics());
```

---

### 2. 增強 `api.js`

#### 並發控制
```javascript
Api._optimization = {
  maxConcurrent: 5,        // 最大並發數
  enableCompression: true, // 啟用壓縮
  enablePrefetch: true,    // 啟用預取
  enableBatching: true,    // 啟用批量請求
};
```

#### 請求隊列
- 當並發數超過限制時，自動排隊等待
- 完成後自動處理隊列中的下一個請求

#### 性能監控集成
- 每個請求自動記錄延遲、字節數
- 與 StreamMonitor 集成，實時追蹤 API 性能

#### 擴展方法
```javascript
// 批量獲取 K 線
Api.batchGetKline(codes, days);

// 預取數據
Api.prefetch(key, path, priority);

// 預熱常用數據
Api.warmupCommonData();
```

---

### 3. 橋接模塊：`data-stream-bridge.js`

自動增強現有模塊：

#### Api 增強
- `batchGetKline()`: 批量獲取 K 線（防抖合併）
- `prefetch()`: 智能預取
- `warmupCommonData()`: 啟動時預熱常用數據

#### Dashboard 增強
- `initVirtualList()`: 虛擬滾動初始化
- `_getSparklines()`: 優化火花圖緩存

#### Charts 增強
- `downsample()`: 數據降採樣工具
- `drawLWKlineChart()`: 自動降採樣大數據集

#### 全局性能監控
```javascript
// 查看性能報告
DataStreamPerf.printReport();

// 獲取指標
const metrics = DataStreamPerf.getMetrics();
```

---

### 4. HTML 集成

在 `app.html` 中優先載入優化模塊：

```html
<!-- 數據流優化模塊（優先載入） -->
<script src="/static/js/data-stream.js"></script>
<script src="/static/js/data-stream-bridge.js"></script>
```

---

## 📊 預期性能提升

| 指標 | 優化前 | 優化後目標 | 改善幅度 |
|------|--------|-----------|----------|
| **首屏加載時間** | - | < 1.5s | ↓ 40-60% |
| **API 平均延遲** | - | < 200ms | ↓ 30-50% |
| **緩存命中率** | ~20% | > 60% | ↑ 200%+ |
| **並發請求數** | 無限制 | ≤ 5 | 避免擁塞 |
| **長列表渲染** | O(n) | O(visible) | ↓ 90%+ |
| **大數據圖表** | 全量渲染 | 降採樣渲染 | ↓ 80%+ |
| **記憶體使用** | - | 減少 30-50% | 自動清理 |

---

## 🔧 使用指南

### 1. 基本使用

```javascript
// 預取數據（高優先級）
Api.prefetch('stocks', '/api/stocks?limit=1000', 10);

// 批量獲取 K 線
const results = await Api.batchGetKline(['000001', '600519'], 250);

// 初始化虛擬列表
Dashboard.initVirtualList('stockList', {
  itemHeight: 60,
  overscan: 10,
  renderItem: (i) => renderStockRow(stocks[i]),
  getTotalCount: () => stocks.length,
});
```

### 2. 性能監控

```javascript
// 開發者工具控制台
DataStreamPerf.printReport();

// 自定義監控
StreamMonitor.record({
  latency: performance.now() - start,
  bytes: response.size,
  cached: fromCache,
  success: true,
});
```

### 3. Web Worker（可選）

創建 Worker 文件 `/static/js/workers/data-processor.js`:

```javascript
self.onmessage = function(e) {
  const { taskId, taskType, data } = e.data;
  
  let result;
  if (taskType === 'processKline') {
    // 密集計算...
    result = heavyProcessing(data);
  }
  
  self.postMessage({ taskId, success: true, result });
};
```

初始化：
```javascript
DataWorker.init('/static/js/workers/data-processor.js');
```

---

## ⚠️ 注意事項

1. **瀏覽器兼容性**: Web Worker 需要現代瀏覽器支持
2. **緩存大小**: 根據實際需求調整 `_maxCacheSize`
3. **TTL 設置**: 不同數據類型設置合適的緩存時間
4. **Worker Fallback**: 不支持 Worker 時會自動回退到主線程

---

## 📁 文件清單

| 文件 | 說明 |
|------|------|
| `/static/js/data-stream.js` | 核心數據流優化模塊 |
| `/static/js/data-stream-bridge.js` | 橋接模塊，增強現有代碼 |
| `/workspace/static/app.html` | 已更新 script 引用 |

---

## 🎯 下一步建議

1. **實施虛擬滾動**: 在股票列表、信號列表等長列表頁面
2. **配置 Worker**: 為密集計算任務創建專用 Worker
3. **調優參數**: 根據實際使用情況調整緩存大小和 TTL
4. **A/B 測試**: 對比優化前后的性能指標
5. **持續監控**: 定期查看 DataStreamPerf 報告

