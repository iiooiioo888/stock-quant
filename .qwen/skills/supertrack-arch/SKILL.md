---
name: supertrack-arch
description: SuperTrack 项目架构指南和开发约定。Use when working on SuperTrack codebase, adding new modules, or when user mentions SuperTrack architecture.
paths:
  - 'core/**'
  - 'controller/**'
  - 'scheduler/**'
  - 'storage/**'
  - 'tools/**'
  - 'taskqueue/**'
  - 'api/**'
  - 'cli/**'
---

# SuperTrack v3.0 架构指南

统一社交媒体数据采集框架，支持 18 个平台、3 种采集模式。

## 七层架构

```
入口层 (CLI/API)
  ↓
决策层 (adaptive_engine + interest_graph)
  ↓
控制器层 (event_bus → retry_manager → anti_detect → browser_pool → health_checker)
  ↓
核心服务层 (proxy_pool + cookie_pool + task_manager + account_pool + data_pipeline)
  ↓
适配器层 (18 平台: xhs/douyin/bilibili/weibo/twitter/instagram/tiktok/youtube/facebook/linkedin/reddit/telegram/pinterest/threads/bluesky/whatsapp/snapchat/line)
  ↓
工具层 (captcha_farm + anomaly_detector + rate_limiter + plugin_market + scheduler + notifier + health_dashboard + data_quality + smart_retry + auto_config + session_pool + data_lifecycle)
  ↓
存储层 (async_session + checkpoint + config + cache)
```

## 开发约定

### 文件组织
- 每个模块一个文件，单一职责
- 工具放 `tools/`，核心服务放 `core/`，平台适配器放 `adapters/`
- CLI 命令放 `cli/advanced.py`，API 端点放 `api/server.py`

### 代码风格
- Python 3.10+，全异步架构
- 类型注解完整（typing 模块）
- `__init__.py` 导出 `__all__` 和 `__version__`
- docstring 用中文，代码注释用英文
- 日志用标准 `logging` 模块，不用 print

### 单例模式
- 核心服务通过模块级函数获取单例（如 `get_proxy_pool()`、`get_cookie_pool()`）
- 避免全局变量，用函数闭包管理状态
- FastAPI 用 `lru_cache` 或手动单例

### 数据类
- 用 `@dataclass` 或 `TypedDict` 定义数据结构
- 用 `enum.Enum` 定义常量集合
- 序列化用 `dataclasses.asdict()` 或自定义 `to_dict()`

### 异步模式
- 所有 I/O 操作用 `async/await`
- 数据库操作用 `aiosqlite`
- HTTP 请求用 `httpx.AsyncClient`
- 文件操作用 `aiofiles`（如果可用）或 `asyncio.to_thread()`

### 错误处理
- 自定义异常继承自基类
- 每层有自己的错误处理策略
- 对外接口统一返回 Result/Error 模式

### 测试
- 测试文件: `tests/test_<module>.py`
- 用 `tmp_path` fixture 创建临时目录
- mock 外部依赖（网络、文件系统、数据库）
- 中文描述测试目的: `def test_验证代理评分计算():`

### CLI 命令
- 用 Click 框架，Rich 渲染输出
- 命令分组: 与模块同名的 group（如 `proxy`、`cookie`、`task`）
- 表格输出用 `rich.table.Table`

### API 端点
- FastAPI，路由前缀 `/api/<module>/`
- 返回 JSON，包含 `status` 字段
- 错误用 HTTPException 或统一错误响应

## 平台分类

### 中文平台（7）
小红书、抖音、哔哩哔哩、微博、快手、知乎、百度贴吧

### 国际平台（11）
X/Twitter、Instagram、TikTok、YouTube、Facebook、LinkedIn、Reddit、Telegram、Pinterest、Threads、Bluesky
