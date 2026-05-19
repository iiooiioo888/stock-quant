---
name: pytest-patterns
description: SuperTrack 测试规范和 pytest 模式。Use when writing tests for SuperTrack, running pytest, or when user mentions testing conventions.
paths:
  - 'tests/**'
  - 'test_*.py'
---

# SuperTrack 测试规范

## 运行命令

```bash
# 全部测试（跳过已知 Windows 失败）
pytest tests/ --ignore=tests/test_core.py -v

# 单文件
pytest tests/test_automation.py -v

# 单测试
pytest tests/test_automation.py::TestHealthDashboard::test_dashboard_initialization -v

# 带覆盖率
pytest tests/ --ignore=tests/test_core.py --cov=. --cov-report=term-missing
```

## 测试目录结构

```
tests/
├── conftest.py          # 全局 fixtures
├── test_adapters.py     # 平台适配器测试
├── test_core.py         # 核心模块测试（已知 Windows file lock 失败）
├── test_controller.py   # 控制器层测试
├── test_storage.py      # 存储层测试
├── test_automation.py   # 自动化工具测试（115 个）
├── test_evolution.py    # v3.0 演化层测试（71 个）
└── test_plugins.py      # 插件系统测试
```

## 命名约定

```python
class TestModuleName:
    """模块名称测试"""

    def test_功能描述(self, tmp_path):
        """测试目的的中文描述"""
        # Arrange - 准备
        # Act - 执行
        # Assert - 断言
```

- 类名: `Test` + 模块名（驼峰）
- 方法名: `test_` + 中文功能描述
- 使用 pytest 的 `tmp_path` fixture 做临时目录
- 使用 `monkeypatch` 做环境变量 mock

## Fixtures 模式

```python
@pytest.fixture
def db_path(tmp_path):
    """创建临时数据库路径"""
    return str(tmp_path / "test.db")

@pytest.fixture
def config(tmp_path):
    """创建临时配置"""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"key": "value"}')
    return str(config_file)
```

## Mock 模式

```python
# Mock 外部 HTTP 请求
@pytest.fixture
def mock_http(monkeypatch):
    responses = []
    async def fake_request(*args, **kwargs):
        return responses.pop(0)
    monkeypatch.setattr("httpx.AsyncClient.get", fake_request)

# Mock 文件系统操作
@pytest.fixture
def mock_fs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path
```

## 数据库测试

```python
# 使用内存 SQLite
@pytest.fixture
def db():
    return ":memory:"

# 或临时文件
@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "test.db")
```

## 异步测试

```python
import pytest

@pytest.mark.asyncio
async def test_异步操作():
    result = await some_async_function()
    assert result.success
```

## 已知问题

- `test_core.py::TestCheckpoint::test_cleanup` — Windows `PermissionError`（文件锁），非项目 bug
- 异步测试需要 `pytest-asyncio` 插件

## 测试数据

- 用 `dataclasses` 或 dict 创建测试数据
- 避免硬编码外部 URL 或 API key
- 测试数据库用 SQLite 内存模式或临时文件
