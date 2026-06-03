# Uptime Kuma 設定範本（stock-quant）

> 適用已部署的 `https://your-host`；本機開發可用 `http://127.0.0.1:8000`。

## 監控 1：SOP 健檢（推薦）

| 欄位 | 值 |
|------|-----|
| 類型 | HTTP(s) - Keyword |
| 名稱 | stock-quant SOP |
| URL | `https://your-host/api/health/sop` |
| 方法 | GET |
| 間隔 | 120s |
| 重試 | 2 |
| Keyword | `verdict`（或 `正常` / `需關注`，依實際 JSON 調整） |
| 反向關鍵字 | `critical`、`異常` |

**說明**：`attention` 仍回 HTTP 200，僅 `critical` 時 JSON 內 `sop.verdict` 為 `critical`。若要用腳本統一退出碼，改在伺服器上跑 cron：

```bash
python scripts/probe_health_sop_url.py --url https://your-host/api/health/sop --ci
# 或
python main.py ops probe --url https://your-host/api/health/sop --ci
```

## 監控 2：進程存活（輕量）

| 欄位 | 值 |
|------|-----|
| 類型 | HTTP(s) |
| URL | `https://your-host/api/health` |
| 間隔 | 60s |
| 預期 | HTTP 200 |

## 監控 3：Push（可選）

本機 cron 失敗時主動推播：

```bash
python main.py ops check --ci || curl -fsS -m 10 --retry 3 \
  -X POST "https://your-kuma/push/XXXX?status=down&msg=stock-quant+ops+failed"
```

將 `XXXX` 換成 Uptime Kuma Push 監控的 token。

## 與倉庫腳本對照

| 工具 | 需 Web | 退出碼 |
|------|--------|--------|
| `python main.py ops check` | 否 | 0/1/2 |
| `python main.py ops probe` | 是 | 0/1/2（`--ci` 同左） |
| `scripts/probe_health_sop_url.py` | 是 | 同上 |

詳見 [運維 SOP 總覽 § E](../README.md#e-外部監控uptime--託管)。
