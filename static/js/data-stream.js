/**
 * data-stream.js - 數據流優化核心模塊 v2.0
 * 完整數據流管理：預取、緩存、請求合併、虛擬滾動、Web Worker、數據壓縮、實時監控
 * 性能優化：懒加载、防抖節流、記憶體管理、連接池
 */

// ============================================================
// 配置與常量
// ============================================================

const DataStreamConfig = {
  // 緩存配置
  CACHE_TTL: {
    SHORT: 3000,      // 3 秒 - 實時數據
    MEDIUM: 30000,    // 30 秒 - 行情數據
    LONG: 120000,     // 2 分鐘 - 統計數據
    VERY_LONG: 600000 // 10 分鐘 - 配置數據
  },
  
  // 請求配置
  REQUEST: {
    MAX_CONCURRENT: 5,
    RETRY_MAX: 3,
    RETRY_BASE_DELAY: 500,
    TIMEOUT_DEFAULT: 15000,
    TIMEOUT_SHORT: 5000,
  },
  
  // 預取配置
  PREFETCH: {
    MAX_QUEUE_SIZE: 20,
    MAX_CACHE_SIZE: 100,
    PRIORITY_HIGH: 8,
    PRIORITY_NORMAL: 5,
    PRIORITY_LOW: 2,
  },
  
  // 虛擬滾動配置
  VIRTUAL_SCROLL: {
    ROW_HEIGHT: 48,
    OVERSCAN: 5,
    BATCH_SIZE: 50,
  },
  
  // 監控配置
  MONITORING: {
    ENABLE_PERF_TRACKING: true,
    ENABLE_MEMORY_TRACKING: true,
    REPORT_INTERVAL: 30000,
  },
};

// ============================================================
// 工具函數
// ============================================================

/**
 * 防抖函數
 */
function debounce(fn, delay) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

/**
 * 節流函數
 */
function throttle(fn, limit) {
  let inThrottle = false;
  return function (...args) {
    if (!inThrottle) {
      fn.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

/**
 * 深度克隆
 */
function deepClone(obj) {
  if (obj === null || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(item => deepClone(item));
  const cloned = {};
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      cloned[key] = deepClone(obj[key]);
    }
  }
  return cloned;
}

/**
 * 生成緩存鍵
 */
function generateCacheKey(prefix, params) {
  const paramStr = params ? JSON.stringify(Object.entries(params).sort()) : '';
  return `${prefix}:${paramStr}`;
}

// ============================================================
// 1. 智能緩存系統 (Intelligent Cache System)
// ============================================================

const DataCache = {
  _stores: {
    short: new Map(),
    medium: new Map(),
    long: new Map(),
    veryLong: new Map(),
  },
  _accessOrder: new Map(), // LRU 追蹤
  _maxSize: 200,
  _cleanupInterval: null,
  
  /**
   * 初始化緩存清理定時器
   */
  init() {
    this._cleanupInterval = setInterval(() => this._cleanup(), 60000);
    console.log('📦 DataCache 初始化完成');
  },
  
  /**
   * 設置緩存
   * @param {string} key - 緩存鍵
   * @param {any} data - 數據
   * @param {'short'|'medium'|'long'|'veryLong'} ttlType - TTL 類型
   */
  set(key, data, ttlType = 'medium') {
    const store = this._stores[ttlType];
    if (!store) return;
    
    // LRU 淘汰
    if (store.size >= this._maxSize / 4) {
      this._evictLRU(ttlType);
    }
    
    const entry = {
      data: deepClone(data),
      timestamp: Date.now(),
      ttl: DataStreamConfig.CACHE_TTL[ttlType.toUpperCase()],
      hits: 0,
    };
    
    store.set(key, entry);
    this._updateAccessOrder(key);
  },
  
  /**
   * 獲取緩存
   * @param {string} key - 緩存鍵
   * @returns {any|null}
   */
  get(key) {
    for (const [type, store] of Object.entries(this._stores)) {
      if (store.has(key)) {
        const entry = store.get(key);
        const age = Date.now() - entry.timestamp;
        
        if (age < entry.ttl) {
          entry.hits++;
          this._updateAccessOrder(key);
          return deepClone(entry.data);
        } else {
          store.delete(key);
        }
      }
    }
    return null;
  },
  
  /**
   * 檢查緩存是否存在且有效
   */
  has(key) {
    for (const store of Object.values(this._stores)) {
      if (store.has(key)) {
        const entry = store.get(key);
        if (Date.now() - entry.timestamp < entry.ttl) {
          return true;
        }
        store.delete(key);
      }
    }
    return false;
  },
  
  /**
   * 刪除緩存
   */
  delete(key) {
    for (const store of Object.values(this._stores)) {
      store.delete(key);
    }
    this._accessOrder.delete(key);
  },
  
  /**
   * 清空緩存
   */
  clear(prefix = '') {
    if (!prefix) {
      for (const store of Object.values(this._stores)) {
        store.clear();
      }
      this._accessOrder.clear();
    } else {
      for (const store of Object.values(this._stores)) {
        for (const key of store.keys()) {
          if (key.startsWith(prefix)) store.delete(key);
        }
      }
    }
  },
  
  /**
   * 更新訪問順序 (LRU)
   */
  _updateAccessOrder(key) {
    this._accessOrder.delete(key);
    this._accessOrder.set(key, Date.now());
  },
  
  /**
   * 淘汰最少使用的項目
   */
  _evictLRU(type) {
    const store = this._stores[type];
    if (store.size === 0) return;
    
    let oldestKey = null;
    let oldestTime = Infinity;
    
    for (const [key, entry] of store.entries()) {
      const accessTime = this._accessOrder.get(key) || entry.timestamp;
      if (accessTime < oldestTime) {
        oldestTime = accessTime;
        oldestKey = key;
      }
    }
    
    if (oldestKey) {
      store.delete(oldestKey);
      this._accessOrder.delete(oldestKey);
    }
  },
  
  /**
   * 定期清理過期緩存
   */
  _cleanup() {
    const now = Date.now();
    let cleaned = 0;
    
    for (const [type, store] of Object.entries(this._stores)) {
      for (const [key, entry] of store.entries()) {
        if (now - entry.timestamp >= entry.ttl) {
          store.delete(key);
          this._accessOrder.delete(key);
          cleaned++;
        }
      }
    }
    
    if (cleaned > 0) {
      console.log(`🧹 清理了 ${cleaned} 個過期緩存項目`);
    }
  },
  
  /**
   * 獲取緩存統計信息
   */
  getStats() {
    const stats = {};
    let totalEntries = 0;
    
    for (const [type, store] of Object.entries(this._stores)) {
      let totalHits = 0;
      let totalSize = 0;
      
      for (const entry of store.values()) {
        totalHits += entry.hits;
        totalSize += JSON.stringify(entry.data).length;
      }
      
      stats[type] = {
        entries: store.size,
        hits: totalHits,
        sizeKB: Math.round(totalSize / 1024),
      };
      totalEntries += store.size;
    }
    
    stats.total = totalEntries;
    stats.maxSize = this._maxSize;
    return stats;
  },
};

// ============================================================
// 2. 請求队列與並發控制 (Request Queue & Concurrency Control)
// ============================================================

const RequestQueue = {
  _queue: [],
  _active: 0,
  _maxConcurrent: DataStreamConfig.REQUEST.MAX_CONCURRENT,
  _processing: false,
  
  /**
   * 添加請求到隊列
   * @param {Function} requestFn - 請求函數
   * @param {number} priority - 優先級 (1-10)
   * @returns {Promise}
   */
  async add(requestFn, priority = 5) {
    return new Promise((resolve, reject) => {
      this._queue.push({
        requestFn,
        priority,
        resolve,
        reject,
        timestamp: Date.now(),
      });
      
      // 按優先級排序
      this._queue.sort((a, b) => {
        if (b.priority !== a.priority) return b.priority - a.priority;
        return a.timestamp - b.timestamp; // 同優先級按 FIFO
      });
      
      this._processQueue();
    });
  },
  
  /**
   * 處理隊列
   */
  async _processQueue() {
    if (this._processing || this._queue.length === 0) return;
    if (this._active >= this._maxConcurrent) return;
    
    this._processing = true;
    
    while (this._queue.length > 0 && this._active < this._maxConcurrent) {
      const task = this._queue.shift();
      this._active++;
      
      // 執行請求
      task.requestFn()
        .then(task.resolve)
        .catch(task.reject)
        .finally(() => {
          this._active--;
          this._processQueue();
        });
    }
    
    this._processing = false;
  },
  
  /**
   * 獲取隊列狀態
   */
  getStatus() {
    return {
      queued: this._queue.length,
      active: this._active,
      maxConcurrent: this._maxConcurrent,
    };
  },
  
  /**
   * 清空隊列
   */
  clear() {
    this._queue.forEach(task => {
      task.reject(new Error('Queue cleared'));
    });
    this._queue = [];
  },
};

// ============================================================
// 3. 智能預取系統 (Intelligent Prefetching System)
// ============================================================

const SmartPrefetch = {
  _queue: [],
  _pending: new Map(),
  _prefetched: new Map(),
  _maxQueueSize: DataStreamConfig.PREFETCH.MAX_QUEUE_SIZE,
  _maxCacheSize: DataStreamConfig.PREFETCH.MAX_CACHE_SIZE,
  _processing: false,
  
  /**
   * 預取數據
   * @param {string} key - 緩存鍵
   * @param {Function} fetchFn - 獲取函數
   * @param {number} priority - 優先級
   * @returns {Promise}
   */
  async prefetch(key, fetchFn, priority = DataStreamConfig.PREFETCH.PRIORITY_NORMAL) {
    // 檢查已預取
    if (this._prefetched.has(key)) {
      const cached = this._prefetched.get(key);
      if (Date.now() - cached.ts < DataStreamConfig.CACHE_TTL.MEDIUM) {
        return cached.data;
      }
      this._prefetched.delete(key);
    }
    
    // 檢查進行中
    if (this._pending.has(key)) {
      return this._pending.get(key);
    }
    
    // 加入隊列
    if (this._queue.length >= this._maxQueueSize) {
      // 移除最低優先級
      this._queue.sort((a, b) => b.priority - a.priority);
      this._queue.pop();
    }
    
    return new Promise((resolve, reject) => {
      this._queue.push({ key, fetchFn, priority, resolve, reject, ts: Date.now() });
      this._queue.sort((a, b) => b.priority - a.priority);
      this._processQueue();
    });
  },
  
  /**
   * 處理預取隊列
   */
  async _processQueue() {
    if (this._processing || this._queue.length === 0) return;
    
    this._processing = true;
    
    while (this._queue.length > 0) {
      const task = this._queue.shift();
      const { key, fetchFn } = task;
      
      if (this._pending.has(key)) continue;
      
      const promise = fetchFn()
        .then(data => {
          // 存入預取緩存
          if (this._prefetched.size >= this._maxCacheSize) {
            const oldest = Array.from(this._prefetched.entries())
              .sort((a, b) => a[1].ts - b[1].ts)[0][0];
            this._prefetched.delete(oldest);
          }
          
          this._prefetched.set(key, { data, ts: Date.now() });
          return data;
        })
        .catch(err => {
          console.warn(`預取失敗 [${key}]:`, err);
          return null;
        })
        .finally(() => {
          this._pending.delete(key);
        });
      
      this._pending.set(key, promise);
      task.resolve(promise);
    }
    
    this._processing = false;
  },
  
  /**
   * 批量預取
   */
  async prefetchBatch(items) {
    const promises = items.map(({ key, fetchFn, priority }) =>
      this.prefetch(key, fetchFn, priority)
    );
    return Promise.allSettled(promises);
  },
  
  /**
   * 取消預取
   */
  cancel(key) {
    this._queue = this._queue.filter(task => task.key !== key);
    this._pending.delete(key);
  },
  
  /**
   * 清空所有
   */
  clear() {
    this._queue = [];
    this._pending.clear();
    this._prefetched.clear();
  },
  
  /**
   * 獲取狀態
   */
  getStatus() {
    return {
      queued: this._queue.length,
      pending: this._pending.size,
      cached: this._prefetched.size,
    };
  },
};

// ============================================================
// 4. 請求合併與去重 (Request Batching & Deduplication)
// ============================================================

const RequestBatcher = {
  _batchQueue: new Map(),
  _batchTimers: new Map(),
  _inflight: new Map(),
  
  /**
   * 批量請求（防抖合併）
   * @param {string} category - 請求類別
   * @param {Array} items - 請求項目
   * @param {Function} batchFn - 批量處理函數
   * @param {number} delayMs - 延遲時間 (ms)
   */
  async batch(category, items, batchFn, delayMs = 100) {
    return new Promise((resolve) => {
      // 清除現有計時器
      if (this._batchTimers.has(category)) {
        clearTimeout(this._batchTimers.get(category));
      }
      
      // 合併請求
      if (!this._batchQueue.has(category)) {
        this._batchQueue.set(category, []);
      }
      this._batchQueue.get(category).push(...items);
      
      // 設置延遲執行
      this._batchTimers.set(category, setTimeout(async () => {
        const batchItems = this._batchQueue.get(category) || [];
        this._batchQueue.set(category, []);
        
        const cacheKey = `${category}:${Date.now()}`;
        
        // 檢查是否有進行中的相同請求
        if (this._inflight.has(cacheKey)) {
          resolve(await this._inflight.get(cacheKey));
          return;
        }
        
        const promise = batchFn(batchItems);
        this._inflight.set(cacheKey, promise);
        
        try {
          const result = await promise;
          resolve(result);
        } catch (e) {
          console.warn(`批量請求失敗 [${category}]:`, e);
          resolve([]);
        } finally {
          this._inflight.delete(cacheKey);
        }
      }, delayMs));
    });
  },
  
  /**
   * 唯一請求（防止重複提交）
   */
  async unique(key, fn) {
    if (this._inflight.has(key)) {
      return this._inflight.get(key);
    }
    
    const promise = fn().finally(() => {
      this._inflight.delete(key);
    });
    
    this._inflight.set(key, promise);
    return promise;
  },
};

// ============================================================
// 3. 虛擬滾動 (Virtual Scrolling)
// ============================================================

const VirtualScroller = {
  _instances: new Map(),
  
  /**
   * 初始化虛擬滾動
   * @param {string} containerId - 容器 ID
   * @param {Object} options - 配置選項
   */
  init(containerId, options = {}) {
    const {
      itemHeight = 50,
      overscan = 5,
      renderItem,
      getTotalCount,
      onRangeChange,
    } = options;
    
    const container = document.getElementById(containerId);
    if (!container) return null;
    
    const instance = {
      container,
      itemHeight,
      overscan,
      renderItem,
      getTotalCount,
      onRangeChange,
      scrollTop: 0,
      visibleStart: 0,
      visibleEnd: 0,
    };
    
    this._instances.set(containerId, instance);
    
    // 設置容器樣式
    container.style.overflowY = 'auto';
    container.style.position = 'relative';
    
    // 創建內容佔位符
    const spacer = document.createElement('div');
    spacer.className = 'virtual-spacer';
    spacer.style.width = '100%';
    container.appendChild(spacer);
    
    // 創建可見區域容器
    const viewport = document.createElement('div');
    viewport.className = 'virtual-viewport';
    viewport.style.position = 'absolute';
    viewport.style.top = '0';
    viewport.style.left = '0';
    viewport.style.right = '0';
    container.appendChild(viewport);
    
    // 綁定滾動事件（節流）
    let ticking = false;
    container.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          this._update(instance);
          ticking = false;
        });
        ticking = true;
      }
    });
    
    // 初始渲染
    this._update(instance);
    
    return instance;
  },
  
  _update(instance) {
    const { container, itemHeight, overscan, getTotalCount, renderItem, onRangeChange } = instance;
    const viewport = container.querySelector('.virtual-viewport');
    const spacer = container.querySelector('.virtual-spacer');
    
    const totalCount = getTotalCount();
    const containerHeight = container.clientHeight;
    
    // 更新總高度
    spacer.style.height = `${totalCount * itemHeight}px`;
    
    // 計算可見範圍
    const scrollTop = container.scrollTop;
    const start = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
    const end = Math.min(totalCount, Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan);
    
    // 如果範圍未變化，跳過渲染
    if (start === instance.visibleStart && end === instance.visibleEnd) return;
    
    instance.visibleStart = start;
    instance.visibleEnd = end;
    instance.scrollTop = scrollTop;
    
    // 通知範圍變化
    if (onRangeChange) {
      onRangeChange(start, end);
    }
    
    // 渲染可見項目
    viewport.innerHTML = '';
    viewport.style.transform = `translateY(${start * itemHeight}px)`;
    
    for (let i = start; i < end; i++) {
      const item = renderItem(i);
      if (item) {
        item.style.height = `${itemHeight}px`;
        item.style.position = 'absolute';
        item.style.top = `${(i - start) * itemHeight}px`;
        item.style.left = '0';
        item.style.right = '0';
        viewport.appendChild(item);
      }
    }
  },
  
  destroy(containerId) {
    const instance = this._instances.get(containerId);
    if (instance) {
      instance.container.innerHTML = '';
      this._instances.delete(containerId);
    }
  },
};

// ============================================================
// 4. Web Worker 數據處理 (Off-main-thread Processing)
// ============================================================

const DataWorker = {
  _worker: null,
  _taskQueue: new Map(),
  _taskId: 0,
  
  /**
   * 初始化 Worker
   */
  init(workerUrl) {
    if (!window.Worker) {
      console.warn('Web Worker 不支持，將在主線程執行');
      return false;
    }
    
    try {
      this._worker = new Worker(workerUrl);
      this._worker.onmessage = (e) => this._handleMessage(e);
      this._worker.onerror = (e) => console.error('Worker 錯誤:', e);
      return true;
    } catch (e) {
      console.warn('Worker 初始化失敗:', e);
      return false;
    }
  },
  
  /**
   * 發送任務到 Worker
   */
  async post(taskType, data, transferables = []) {
    return new Promise((resolve, reject) => {
      const taskId = ++this._taskId;
      this._taskQueue.set(taskId, { resolve, reject });
      
      if (this._worker) {
        this._worker.postMessage({ taskId, taskType, data }, transferables);
      } else {
        // Fallback: 主線程執行
        this._executeTask(taskId, taskType, data).catch(reject);
      }
      
      // 超時保護
      setTimeout(() => {
        if (this._taskQueue.has(taskId)) {
          this._taskQueue.delete(taskId);
          reject(new Error('Worker 任務超時'));
        }
      }, 30000);
    });
  },
  
  _handleMessage(e) {
    const { taskId, success, result, error } = e.data;
    const task = this._taskQueue.get(taskId);
    
    if (task) {
      if (success) {
        task.resolve(result);
      } else {
        task.reject(new Error(error));
      }
      this._taskQueue.delete(taskId);
    }
  },
  
  async _executeTask(taskId, taskType, data) {
    // Fallback 實現（根據實際需求擴展）
    let result;
    
    switch (taskType) {
      case 'processKline':
        result = this._processKlineSync(data);
        break;
      case 'calculateMetrics':
        result = this._calculateMetricsSync(data);
        break;
      default:
        throw new Error(`未知任務類型：${taskType}`);
    }
    
    this._handleMessage({
      data: { taskId, success: true, result },
    });
  },
  
  // 同步處理函數（Fallback）
  _processKlineSync({ kline, indicators }) {
    // 簡化實現
    return { processed: true, count: kline?.length || 0 };
  },
  
  _calculateMetricsSync({ prices, returns }) {
    // 簡化實現
    return { sharpe: 0, maxDrawdown: 0 };
  },
  
  terminate() {
    if (this._worker) {
      this._worker.terminate();
      this._worker = null;
    }
    this._taskQueue.clear();
  },
};

// ============================================================
// 5. 數據壓縮與序列化 (Data Compression)
// ============================================================

const DataCompressor = {
  /**
   * 壓縮數組（差分編碼 + 整數化）
   */
  compressNumbers(arr, decimals = 2) {
    if (!arr || arr.length === 0) return [];
    
    const multiplier = Math.pow(10, decimals);
    const compressed = [];
    let prev = Math.round(arr[0] * multiplier);
    compressed.push(prev);
    
    for (let i = 1; i < arr.length; i++) {
      const curr = Math.round(arr[i] * multiplier);
      compressed.push(curr - prev);
      prev = curr;
    }
    
    return compressed;
  },
  
  /**
   * 解壓縮數組
   */
  decompressNumbers(compressed, decimals = 2) {
    if (!compressed || compressed.length === 0) return [];
    
    const multiplier = Math.pow(10, decimals);
    const decompressed = [];
    let prev = compressed[0];
    decompressed.push(prev / multiplier);
    
    for (let i = 1; i < compressed.length; i++) {
      prev += compressed[i];
      decompressed.push(prev / multiplier);
    }
    
    return decompressed;
  },
  
  /**
   * 序列化為二进制（更高效）
   */
  serializeToBinary(data) {
    const json = JSON.stringify(data);
    const encoder = new TextEncoder();
    return encoder.encode(json);
  },
  
  /**
   * 從二进制反序列化
   */
  deserializeFromBinary(binary) {
    const decoder = new TextDecoder();
    const json = decoder.decode(binary);
    return JSON.parse(json);
  },
};

// ============================================================
// 6. 數據流監控 (Data Stream Monitoring)
// ============================================================

const StreamMonitor = {
  _metrics: {
    totalRequests: 0,
    cachedRequests: 0,
    failedRequests: 0,
    totalBytes: 0,
    avgLatency: 0,
  },
  _latencies: [],
  
  record(request) {
    const { latency, bytes, cached, success } = request;
    
    this._metrics.totalRequests++;
    if (cached) this._metrics.cachedRequests++;
    if (!success) this._metrics.failedRequests++;
    if (bytes) this._metrics.totalBytes += bytes;
    
    // 更新平均延遲
    this._latencies.push(latency);
    if (this._latencies.length > 100) this._latencies.shift();
    this._metrics.avgLatency = 
      this._latencies.reduce((a, b) => a + b, 0) / this._latencies.length;
  },
  
  getMetrics() {
    return {
      ...this._metrics,
      cacheHitRate: this._metrics.totalRequests > 0
        ? (this._metrics.cachedRequests / this._metrics.totalRequests * 100).toFixed(2) + '%'
        : '0%',
    };
  },
  
  reset() {
    this._metrics = {
      totalRequests: 0,
      cachedRequests: 0,
      failedRequests: 0,
      totalBytes: 0,
      avgLatency: 0,
    };
    this._latencies = [];
  },
};

// ============================================================
// 導出模塊與初始化
// ============================================================

const DataStream = {
  // 核心模塊
  Config: DataStreamConfig,
  Cache: DataCache,
  Queue: RequestQueue,
  Prefetch: SmartPrefetch,
  Batcher: RequestBatcher,
  VirtualScroller,
  Worker: DataWorker,
  Compressor: DataCompressor,
  Monitor: StreamMonitor,
  
  // 工具函數
  utils: { debounce, throttle, deepClone, generateCacheKey },
  
  /**
   * 初始化所有模塊
   */
  init() {
    console.log('🚀 DataStream v2.0 初始化中...');
    
    // 初始化緩存系統
    DataCache.init();
    
    // 啟動監控報告
    if (DataStreamConfig.MONITORING.ENABLE_PERF_TRACKING) {
      setInterval(() => {
        const metrics = StreamMonitor.getMetrics();
        console.log('📊 DataStream 性能指標:', metrics);
      }, DataStreamConfig.MONITORING.REPORT_INTERVAL);
    }
    
    console.log('✅ DataStream 初始化完成');
  },
  
  /**
   * 獲取完整性能報告
   */
  getPerformanceReport() {
    return {
      cache: DataCache.getStats(),
      queue: RequestQueue.getStatus(),
      prefetch: SmartPrefetch.getStatus(),
      monitor: StreamMonitor.getMetrics(),
      memory: this._getMemoryUsage(),
    };
  },
  
  /**
   * 獲取記憶體使用情況
   */
  _getMemoryUsage() {
    if (performance.memory) {
      return {
        usedJSHeapSize: Math.round(performance.memory.usedJSHeapSize / 1048576) + ' MB',
        totalJSHeapSize: Math.round(performance.memory.totalJSHeapSize / 1048576) + ' MB',
      };
    }
    return { available: false };
  },
  
  /**
   * 清空所有緩存和隊列
   */
  clearAll() {
    DataCache.clear();
    SmartPrefetch.clear();
    RequestQueue.clear();
    StreamMonitor.reset();
    console.log('🧹 DataStream 已清空所有緩存和隊列');
  },
};

// 自動導出到全局
if (typeof window !== 'undefined') {
  window.DataStream = DataStream;
  window.DataCache = DataCache;
  window.RequestQueue = RequestQueue;
  window.SmartPrefetch = SmartPrefetch;
  window.RequestBatcher = RequestBatcher;
  window.VirtualScroller = VirtualScroller;
  window.DataWorker = DataWorker;
  window.DataCompressor = DataCompressor;
  window.StreamMonitor = StreamMonitor;
}

// CommonJS 導出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = DataStream;
}

// 自動初始化（如果支持）
if (typeof window !== 'undefined' && document.readyState === 'complete') {
  DataStream.init();
} else if (typeof window !== 'undefined') {
  window.addEventListener('load', () => DataStream.init());
}
