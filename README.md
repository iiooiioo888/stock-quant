# Stock Quant - 任務面板

A 股量化回測 + 實時盯盤預警系統的任務管理儀表板。

## 技術棧

| 層 | 技術 |
|---|---|
| 後端 API | FastAPI + SQLAlchemy (async) + SQLite |
| 任務隊列 | Celery + Redis |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS |
| 實時通信 | WebSocket |
| 容器化 | Docker Compose |

## 快速啟動

### 方式一：Docker Compose（推薦）

```bash
docker-compose up --build
```

- 前端: http://localhost:5173
- 後端 API: http://localhost:8000
- API 文檔: http://localhost:8000/docs

### 方式二：本地開發

**後端：**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt

# 啟動 Redis（需要先安裝）
redis-server

# 啟動後端
uvicorn app.main:app --reload --port 8000

# 啟動 Celery Worker
celery -A app.celery_app worker --loglevel=info --pool=solo -Q backtest
```

**前端：**

```bash
cd frontend
npm install
npm run dev
```

## 項目結構

```
stock-quant/
├── backend/
│   ├── app/
│   │   ├── api/          # REST API 路由
│   │   ├── models/       # SQLAlchemy 數據模型
│   │   ├── schemas/      # Pydantic 驗證模型
│   │   ├── ws/           # WebSocket 管理
│   │   ├── config.py     # 配置
│   │   ├── database.py   # 數據庫連接
│   │   ├── celery_app.py # Celery 配置
│   │   └── main.py       # FastAPI 入口
│   └── tasks/            # Celery 任務定義
├── frontend/
│   └── src/
│       ├── components/   # React 組件
│       ├── hooks/        # 自定義 Hooks
│       ├── services/     # API 調用
│       └── types/        # TypeScript 類型
├── docker-compose.yml
└── README.md
```

## 功能

- **運行中任務面板** — 實時顯示進度、支持取消
- **排隊任務面板** — 查看待執行任務
- **歷史記錄** — 查看已完成/失敗任務及回測結果
- **新建任務** — 配置策略、標的、時間範圍後提交
- **WebSocket 實時推送** — 任務狀態變更即時更新
- **回測結果展示** — 收益率、夏普比率、最大回撤、勝率等指標

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/tasks` | 獲取任務列表 |
| POST | `/api/tasks` | 創建新任務 |
| GET | `/api/tasks/{id}` | 獲取任務詳情 |
| PATCH | `/api/tasks/{id}` | 更新任務 |
| POST | `/api/tasks/{id}/cancel` | 取消任務 |
| DELETE | `/api/tasks/{id}` | 刪除任務 |
| WS | `/ws/tasks` | WebSocket 任務推送 |
