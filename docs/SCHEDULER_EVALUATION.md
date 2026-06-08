# 任務調度器評估報告

## 現狀分析

當前系統同時使用三種任務調度方案：

| 方案 | 用途 | 優點 | 缺點 |
|------|------|------|------|
| **APScheduler** | 定時任務（策略報告、數據更新） | 輕量、易集成、支持多種 trigger | 無持久化、單進程 |
| **Celery** | 異步任務（回測、數據處理） | 分布式、持久化、重試機制 | 複雜度高、需 Redis/RabbitMQ |
| **Schedule** | 簡單定時任務 | 極簡 API | 功能單一、無高級特性 |

## 架構建議

### 推薦方案：統一使用 Celery + Celery Beat

```
┌─────────────────────────────────────────────────────────┐
│                    任務調度架構                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │  Web Server │    │ Celery Beat │    │  Worker 1   │ │
│  │  (FastAPI)  │───▶│  (調度器)   │───▶│  (CPU 密集)  │ │
│  └─────────────┘    └─────────────┘    └─────────────┘ │
│         │                  │                  │         │
│         ▼                  ▼                  ▼         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Redis (Broker + Backend)           │   │
│  └─────────────────────────────────────────────────┘   │
│         │                  │                  │         │
│         ▼                  ▼                  ▼         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │  Worker 2   │    │  Worker 3   │    │  Worker N   │ │
│  │  (IO 密集)   │    │  (混合)     │    │  (擴展)     │ │
│  └─────────────┘    └─────────────┘    └─────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 遷移路線圖

#### 階段 1：準備工作（1-2 週）
- [ ] 審計現有 APScheduler 任務
- [ ] 定義 Celery 任務分類（CPU/IO/混合）
- [ ] 配置 Celery Beat 定時任務

#### 階段 2：並行運行（2-4 週）
- [ ] 新任務使用 Celery
- [ ] 逐步遷移現有 APScheduler 任務
- [ ] 監控對比穩定性

#### 階段 3：切換完成（1 週）
- [ ] 停用 APScheduler
- [ ] 性能基準測試
- [ ] 文檔更新

### Celery 任務分類建議

```python
# src/core/celery_tasks.py

from celery import Task
from src.core.celery_app import get_celery_app

app = get_celery_app()

# CPU 密集型任務（回測、優化）
@app.task(bind=True, max_retries=3, time_limit=3600)
def run_backtest_task(self, strategy_id: int, start_date: str, end_date: str):
    """策略回測任務"""
    pass

@app.task(bind=True, max_retries=2, time_limit=7200)
def optimize_strategy_task(self, strategy_id: int, params: dict):
    """策略參數優化"""
    pass

# IO 密集型任務（數據獲取、API 調用）
@app.task(bind=True, max_retries=5, autoretry_for=(requests.RequestException,))
def fetch_market_data_task(self, symbol: str, date: str):
    """市場數據獲取"""
    pass

# 定時任務（Celery Beat）
@app.task
def daily_report_task():
    """每日策略報告（原 APScheduler daily_report）"""
    pass

@app.task
def data_quality_check_task():
    """數據質量巡檢"""
    pass
```

### Celery Beat 配置

```python
# src/config.py

CELERY_BEAT_SCHEDULE = {
    'daily-report': {
        'task': 'src.core.celery_tasks.daily_report_task',
        'schedule': crontab(hour=15, minute=30),  # 15:30
    },
    'data-quality-check': {
        'task': 'src.core.celery_tasks.data_quality_check_task',
        'schedule': crontab(hour=9, minute=0),  # 09:00
    },
    'degradation-check': {
        'task': 'src.core.celery_tasks.degradation_check_task',
        'schedule': crontab(hour=16, minute=0),  # 16:00
    },
}
```

## 替代方案評估

### 方案 B：保留 APScheduler（低成本）

**適用場景**：
- 單節點部署
- 任務量少（<50/天）
- 無需分布式

**改進措施**：
```python
# 添加任務持久化
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

jobstores = {
    'default': SQLAlchemyJobStore(url=settings.database_url)
}

scheduler = BackgroundScheduler(jobstores=jobstores)
```

### 方案 C：混合架構（推薦過渡）

```
定時觸發 → APScheduler/Celery Beat
    ↓
任務執行 → Celery Workers
```

## 決策矩陣

| 標準 | APScheduler | Celery | 建議 |
|------|-------------|--------|------|
| 分布式支持 | ❌ | ✅ | Celery |
| 任務持久化 | ⚠️ (需插件) | ✅ | Celery |
| 重試機制 | ❌ | ✅ | Celery |
| 資源隔離 | ❌ | ✅ | Celery |
| 運維複雜度 | 低 | 中 | APScheduler |
| 學習曲線 | 低 | 中 | APScheduler |
| 社區生態 | 中 | 大 | Celery |

## 結論

**短期（1-3 個月）**：採用混合架構，新任務使用 Celery，現有 APScheduler 任務保持不變。

**中期（3-6 個月）**：逐步遷移 APScheduler 任務至 Celery，建立完整的任務監控體系。

**長期（6 個月+）**：完全切換至 Celery，實現統一的任務調度和執行平台。

## 參考資源

- [Celery 官方文檔](https://docs.celeryq.dev/)
- [Celery Beat 定時任務](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html)
- [Celery 最佳實踐](https://docs.celeryq.dev/en/stable/userguide/workers.html)
