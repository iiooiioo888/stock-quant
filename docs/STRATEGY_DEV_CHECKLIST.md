# 策略開發 Checklist

> 新增或修改策略前後請對照。模板：`strategies/template_strategy.py` · 註冊：`src/core/strategies/registry.py`

## 開發前

- [ ] 確認 `key` 未與 `STRATEGIES` 重複（`list_strategy_keys()`）
- [ ] 繼承 `OrderManagedStrategy` 或文檔允許的基類
- [ ] 參數放在 `params` tuple，並在 `manual/05-策略系統.md` 或策略描述中說明預設值

## 實作

- [ ] `__init__` 僅初始化指標，避免 I/O
- [ ] `next()` 開頭處理 `self.order` 避免重複下單
- [ ] 不使用 `eval` / `exec` / 任意 `__import__`（用戶策略由沙箱攔截）
- [ ] 止損止盈若需要，沿用 `OrderManagedStrategy` 內建邏輯

## 測試

- [ ] `python -m pytest tests/test_strategies.py -k <StrategyName> -q`
- [ ] 指標相關：`python -m pytest tests/unit/test_indicators_golden.py -q`
- [ ] 本地回測：`python main.py backtest <code> <strategy_key>`

## 提交 PR

- [ ] `ruff check src/core/strategies/<your>.py`（若改動 core 策略目錄）
- [ ] 策略目錄 UI 條目（若需出現在 Pro 策略庫）已同步 catalog 資料源
- [ ] 無硬編碼 API Key / 路徑

## 參考

- [manual/05-策略系統.md](manual/05-策略系統.md)
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)
