# 🤝 Contributing to Stock-Quant

感謝你有意貢獻 Stock-Quant！本指南將幫助你快速上手並為專案做出有價值的貢獻。

---

## 📋 目錄

- [如何參與](#如何參與)
- [開發環境設置](#開發環境設置)
- [程式碼規範](#程式碼規範)
- [提交規範](#提交規範)
- [測試要求](#測試要求)
- [Pull Request 流程](#pull-request-流程)
- [常見問題](#常見問題)

---

## 🚀 如何參與

### 1. Fork & Clone

```bash
# Fork 專案到個人帳號
# 然後 clone 到本地
git clone https://github.com/YOUR_USERNAME/stock-quant.git
cd stock-quant

# 添加上游遠程倉庫
git remote add upstream https://github.com/ORIGINAL_OWNER/stock-quant.git
```

### 2. 建立功能分支

```bash
# 保持與主線同步
git checkout main
git pull upstream main

# 建立新功能分支
git checkout -b feature/your-feature-name

# 或修復 bug
git checkout -b fix/issue-123-short-description
```

### 3. 開發功能

- 參照 [架構設計](docs/manual/13-架構設計.md) 理解系統結構
- 遵循 [策略系統](docs/manual/05-策略系統.md) 規範開發新策略
- 使用 [API 參考](docs/manual/04-API參考.md) 作為接口開發指引

### 4. 撰寫測試

```bash
# 運行所有測試
./test_all.sh

# 運行特定測試模組
pytest tests/test_strategy_engine.py -v

# 運行 UI 測試（需先啟動服務）
pytest tests/e2e/ -v
```

### 5. 提交 Pull Request

- Push 到你的分支：`git push origin feature/your-feature-name`
- 在 GitHub 上建立 PR
- 填寫 PR 模板，描述變更內容與測試結果

---

## 🛠️ 開發環境設置

### 必要工具

- Python 3.9+
- Node.js 18+ (前端開發)
- Git
- Docker & Docker Compose (可選，用於容器化開發)

### 安裝依賴

```bash
# 後端依賴
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 前端依賴（如需修改前端）
cd static
npm install
```

### 配置環境

```bash
# 複製環境範例
cp .env.example .env

# 編輯 .env 文件，設置必要的环境變量
# 至少需要設置：
# - SQ_DATABASE_URL
# - SQ_SECRET_KEY
```

### 啟動開發伺服器

```bash
# 方式一：直接啟動
python main.py

# 方式二：使用 Docker
docker-compose up --build

# 方式三：開發模式（自動重載）
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📝 程式碼規範

### Python 風格指南

遵循 [PEP 8](https://pep8.org/) 標準：

```python
# ✅ 正確範例
def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    計算夏普比率
    
    Args:
        returns: 收益率序列
        risk_free_rate: 無風險利率，預設 2%
    
    Returns:
        夏普比率（年化）
    """
    excess_returns = returns - risk_free_rate / 252
    return np.sqrt(252) * excess_returns.mean() / excess_returns.std()


# ❌ 錯誤範例
def calcSharpe(r, rf=0.02):  # 命名不符合 snake_case，缺少 docstring
    return r.mean() / r.std()
```

### 程式碼檢查工具

```bash
# 安裝檢查工具
pip install flake8 black mypy isort

# 格式化程式碼
black src/ strategies/ tests/
isort src/ strategies/ tests/

# 靜態分析
flake8 src/ strategies/ tests/
mypy src/
```

### 文件要求

- **所有公開函數**必須包含 Google-style docstring
- **複雜邏輯**必須添加註解說明
- **新增模組**必須在 `docs/manual/15-文件索引.md` 中登記

---

## 📋 提交規範

### Commit Message 格式

採用語義化提交格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 類型

| 類型 | 說明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修復 |
| `docs` | 文檔更新 |
| `style` | 程式碼格式調整（不影響邏輯） |
| `refactor` | 重構（非新功能、非 bug 修復） |
| `perf` | 效能優化 |
| `test` | 測試相關 |
| `chore` | 構建過程或輔助工具變動 |

### 範例

```bash
# 新功能
git commit -m "feat(strategy): 新增均值回歸策略

- 實現 MA 交叉信號生成
- 添加動態止損機制
- 包含完整單元測試

Closes #45"

# Bug 修復
git commit -m "fix(api): 修復 K 線數據重複問題

- 修正時間戳比較邏輯
- 添加唯一性約束

Fixes #78"

# 文檔更新
git commit -m "docs: 更新部署指南中的 Render 配置"
```

---

## ✅ 測試要求

### 覆蓋率標準

- **新功能**: 單元測試覆蓋率 ≥ 80%
- **核心模組**: 覆蓋率 ≥ 90%
- **所有現有測試**: 必須 100% 通過

### 測試類型

```python
# 1. 單元測試（必選）
def test_calculate_sharpe():
    returns = pd.Series([0.01, 0.02, -0.01, 0.03])
    sharpe = calculate_sharpe_ratio(returns)
    assert sharpe > 0

# 2. 集成測試（涉及 DB/API）
def test_backtest_api(client, auth_headers):
    response = client.post("/api/backtest", json=test_params, headers=auth_headers)
    assert response.status_code == 200
    assert "sharpe_ratio" in response.json()

# 3. 端到端測試（關鍵路徑）
def test_full_backtest_workflow(page):
    # 使用 Playwright 測試完整用戶流程
    page.goto("/backtest")
    page.select_option("#strategy-select", "ma_cross")
    page.click("#run-backtest")
    expect(page.locator(".results-chart")).to_be_visible()
```

### 運行測試

```bash
# 快速測試（煙霧測試）
pytest tests/smoke/ -v

# 完整測試套件
./test_all.sh

# 帶覆蓋率報告
pytest --cov=src --cov-report=html
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## 🔄 Pull Request 流程

### 1. 建立 PR

- 前往 GitHub 專案頁面
- 點擊 "New Pull Request"
- 選擇你的分支與主線分支
- 填寫 PR 模板

### 2. PR 模板內容

```markdown
## 變更說明
<!-- 簡述此 PR 的目的與主要變更 -->

## 相關 Issue
<!-- 關聯的 Issue 編號，如 Closes #123 -->

## 測試結果
- [ ] 所有單元測試通過
- [ ] 所有集成測試通過
- [ ] 手動測試驗證（如適用）
- [ ] 新增測試覆蓋率：XX%

## 截圖/錄影
<!-- 如涉及 UI 變更，請提供截圖或 GIF -->

## 檢查清單
- [ ] 程式碼遵循 PEP 8 規範
- [ ] 已添加必要的 docstring
- [ ] 已更新相關文檔
- [ ] 無敏感信息洩露
```

### 3. Code Review

- 至少需要 1 位維護者審核通過
- 回應所有 review 意見並進行修改
- 保持 PR 小而精，避免單一 PR 包含過多變更

### 4. 合併

- 審核通過後由維護者合併
- 合併後刪除功能分支
- 在主線同步最新代碼

---

## ❓ 常見問題

### Q: 我該如何開始第一個貢獻？

A: 建議從以下方向入手：
1. 修復 [Good First Issue](https://github.com/.../issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
2. 改進文檔（拼寫錯誤、補充說明）
3. 添加單元測試提高覆蓋率
4. 優化效能或改善用戶體驗

### Q: 我的 PR 多久會被審核？

A: 通常在 3-5 個工作日內。如果超過一週未回應，可以友善地 @ 維護者。

### Q: 我可以貢獻自己的交易策略嗎？

A: 當然可以！請確保：
- 策略有清晰的邏輯說明
- 包含完整的回測結果
- 通過所有測試用例
- 遵守 [策略開發規範](docs/manual/05-策略系統.md)

### Q: 發現 Bug 該如何報告？

A: 請建立 Issue 並包含：
- 重現步驟
- 預期行為與實際行為
- 環境信息（Python 版本、OS、依賴版本）
- 錯誤日誌或截圖

---

## 📞 聯絡方式

- **GitHub Issues**: [提交問題或建議](https://github.com/.../issues)
- **GitHub Discussions**: [技術討論](https://github.com/.../discussions)
- **Email**: stock-quant@example.com（待定）

---

## 🙏 致謝

感謝所有貢獻者的付出！你們讓 Stock-Quant 變得更好。

<a href="https://github.com/.../graphs/contributors">
  <img src="https://contrib.rocks/image?repo=..." />
</a>

---

*最後更新*: 2026-05-29
*版本*: v1.0
