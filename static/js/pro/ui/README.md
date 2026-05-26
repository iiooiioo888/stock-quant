# StockQ Pro UI 組件庫（v4）

這是一套**純原生 JavaScript** 的 UI 組件庫，目的只有一個：讓後續功能/頁面可以用「拼積木」方式，持續產出與 `static/css/pro.css` **同一套視覺與結構**的 UI。

## 使用方式

在頁面載入 `static/js/pro/ui/index.js` 後，會有：

- `window.StockQPro.UI`

## 核心 API

- `UI.h(tag, props, ...children)`: 建立 DOM 節點
- `UI.mount(root, node)`: 清空並掛載 DOM
- `UI.on(root, event, selector, handler)`: 事件委派
- `UI.toast(msg, type)`: Toast（`type`: `ok`/`er`/`inf`）
- `UI.modalOpen(id)` / `UI.modalClose(id)`: 控制 `.modal-ov`

## 常用組件（與 pro.css 對齊）

- `UI.Panel({ title, right, body })`
- `UI.Button({ text, tone, size, onClick })`
  - `tone`: `ac` / `gn` / `rd` / `bl` / `pu`
  - `size`: `s`
- `UI.Badge({ text, tone })`
  - `tone`: `ac`/`gn`/`rd`/`bl`/`pu`/`or`/`gr`/`cy`/`pk`/`yl`/`sl`
- `UI.FormGroup({ label, child })`
- `UI.FormRow(...)`
- `UI.Switch({ id, checked, label, onChange })`
- `UI.Table({ head, rows, tbodyId })`

## 策略庫組件（供 `strategy-catalog.js` 或新頁面用）

- `UI.CatPill({ id, name, count, color, active, onClick })`
- `UI.StrategyCard({ num, name, desc, tier, status, active })`

## 建議約定

- **class 命名**：請優先使用 `pro.css` 既有 class（例如 `pnl/ph/pb/btn/badge/tbl/...`）
- **id 命名**：沿用現有模組已使用的 id（避免破壞 `modules/*.js`）
- **Modal**：如果頁面已存在靜態 Modal（例如 `m-alert`），優先用 `UI.modalOpen('m-alert')` 控制即可

