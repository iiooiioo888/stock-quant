/**
 * data-stream-bridge.js - 數據流優化橋接模塊
 * 整合 DataPrefetch、RequestBatcher 到現有 Api 和 Dashboard
 */

// 等待 data-stream.js 載入後執行
(function() {
  'use strict';
  
  // 增強 Api 模塊
  if (typeof Api !== 'undefined') {
    // 添加批量獲取 K 線方法
    Api.batchGetKline = async function(codes, days = 250) {
      if (typeof RequestBatcher === 'undefined') {
        // Fallback: 個別請求
        return Promise.all(codes.map(code => this.getKline(code, null, null, days)));
      }
      
      return RequestBatcher.batch(
        'kline',
        codes.map(code => ({ code, days })),
        async (items) => {
          const uniqueCodes = [...new Set(items.map(i => i.code))];
          const results = await Promise.all(
            uniqueCodes.map(code => this.getKline(code, null, null, days))
          );
          return uniqueCodes.map((code, i) => ({ code, data: results[i] }));
        },
        150 // 150ms 防抖
      );
    };
    
    // 添加預取方法
    Api.prefetch = async function(key, path, priority = 5) {
      if (typeof DataPrefetch === 'undefined') {
        return this.get(path);
      }
      
      return DataPrefetch.prefetch(
        key || path,
        () => this.get(path),
        priority
      );
    };
    
    // 智能預熱常用數據
    Api.warmupCommonData = async function() {
      const commonPaths = [
        { key: 'health', path: '/api/health', priority: 10 },
        { key: 'strategies', path: '/api/strategies/list', priority: 8 },
        { key: 'config', path: '/api/config', priority: 7 },
      ];
      
      // 並行預取（低優先級）
      await Promise.all(
        commonPaths.map(item => this.prefetch(item.key, item.path, item.priority))
      );
    };
  }
  
  // 增強 Dashboard 模塊
  if (typeof Dashboard !== 'undefined') {
    // 使用虛擬滾動優化長列表
    Dashboard.initVirtualList = function(containerId, options) {
      if (typeof VirtualScroller === 'undefined') {
        console.warn('VirtualScroller 未載入');
        return null;
      }
      
      return VirtualScroller.init(containerId, options);
    };
    
    // 優化火花圖預取
    Dashboard._getSparklines = async function(codes, days) {
      const key = `sparkline:${codes.join(',')}:${days}`;
      
      // 嘗試從 DataPrefetch 獲取
      if (typeof DataPrefetch !== 'undefined') {
        const cached = DataPrefetch.get(key);
        if (cached) return cached;
      }
      
      // 原有邏輯
      const hit = this._sparklineCache[key];
      if (hit && Date.now() - hit.at < this._sparklineCacheTtlMs) {
        return hit.data;
      }
      
      const d = await Api.get(`/api/sparkline?codes=${codes.join(',')}&days=${days}`);
      if (d?.sparklines) {
        this._sparklineCache[key] = { at: Date.now(), data: d };
        
        // 存入 DataPrefetch 緩存
        if (typeof DataPrefetch !== 'undefined') {
          DataPrefetch._setCache?.(key, d);
        }
      }
      return d;
    };
  }
  
  // 增強 Charts 模塊
  if (typeof Charts !== 'undefined') {
    // 添加數據採樣優化
    Charts.downsample = function(data, maxPoints = 500) {
      if (!data || data.length <= maxPoints) return data;
      
      const ratio = Math.ceil(data.length / maxPoints);
      const sampled = [];
      
      for (let i = 0; i < data.length; i += ratio) {
        sampled.push(data[i]);
      }
      
      return sampled;
    };
    
    // 優化大數據集渲染
    const originalDrawLWKline = Charts.drawLWKlineChart;
    Charts.drawLWKlineChart = function(containerId, klineData, signals, title) {
      // 自動降採樣
      if (klineData && klineData.length > 1000) {
        klineData = this.downsample(klineData, 1000);
      }
      return originalDrawLWKline.call(this, containerId, klineData, signals, title);
    };
  }
  
  // 全局性能監控入口
  window.DataStreamPerf = {
    getMetrics() {
      const metrics = {};
      
      if (typeof StreamMonitor !== 'undefined') {
        metrics.stream = StreamMonitor.getMetrics();
      }
      
      if (typeof ChartPerf !== 'undefined') {
        metrics.charts = {
          avgRenderTime: ChartPerf.getAvg(),
        };
      }
      
      if (typeof PerfMetrics !== 'undefined') {
        metrics.app = 'available';
      }
      
      return metrics;
    },
    
    printReport() {
      const metrics = this.getMetrics();
      console.group('📊 數據流性能報告');
      console.table(metrics);
      console.groupEnd();
      return metrics;
    },
    
    reset() {
      if (typeof StreamMonitor !== 'undefined') {
        StreamMonitor.reset();
      }
    },
  };
  
  console.log('✅ 數據流優化橋接模塊已載入');
})();
