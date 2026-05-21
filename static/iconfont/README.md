# iconfont 圖標（[iconfont.cn](https://www.iconfont.cn/)）

## 1. 建立專案並下載

1. 登入 [iconfont.cn](https://www.iconfont.cn/)，搜尋所需圖標並加入專案。
2. 專案頁選 **Symbol** → **複製 JS 連結**（`//at.alicdn.com/t/c/font_xxx.js`）。
3. 可選：下載到本地，將 `iconfont.js`、`iconfont.css` 放到本目錄。

## 2. 後端設定

複製範例並編輯：

```bash
copy data\iconfont_project.json.example data\iconfont_project.json
```

在 `data/iconfont_project.json` 填入：

- `symbol_js_url`：專案 Symbol JS 的 alicdn 地址（建議 `https://at.alicdn.com/...`）
- `stock_icons`：股票代碼 → symbol id（與 JS 內 `<symbol id="...">` 一致）

## 3. 單檔 SVG（無需 JS）

將 `{代碼}.svg` 放到 `static/iconfont/stocks/`（例如 `600519.svg`、`AAPL.svg`），
後端會優先使用並快取到 `data/stock_logos/`。

## 4. 批次同步 Logo

管理員：`POST /api/stock-logos/sync`（會先嘗試 iconfont，再 TradingView / FMP）。
