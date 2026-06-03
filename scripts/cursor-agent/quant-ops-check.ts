#!/usr/bin/env node
/**
 * stock-quant 運維健檢 — Cursor SDK + 本專案 MCP（sq_* tools）
 *
 * 用法（需 CURSOR_API_KEY）:
 *   cd scripts/cursor-agent && npm install
 *   npm run ops-check
 *   npm run ops-check -- --verbose
 *
 * 環境變數:
 *   CURSOR_API_KEY  — Cursor Cloud Agents API key（必填）
 *   SQ_PYTHON       — Python 執行檔，預設 windows=python、其他=python3
 */
import { Agent, CursorAgentError } from "@cursor/sdk";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, "../..");
const verbose = process.argv.includes("--verbose");

const python =
  process.env.SQ_PYTHON ?? (process.platform === "win32" ? "python" : "python3");

const OPS_PROMPT = `你是 stock-quant 運維助手。嚴格依序透過 MCP（stock-quant）執行，勿跳步、勿改程式碼。

## 檢查步驟（每步先呼叫再解讀）

| # | Tool | 參數 | 關注 |
|---|------|------|------|
| 1 | sq_ops_check | 無 | 一次取得 SOP verdict、checks、recommendations |
| 2 | sq_health | 無 | 補充 DB、管線/索引摘要（可選對照） |
| 3 | sq_pipeline_metrics | 無 | cache.pending_deferred 應為 0 |
| 4 | sq_db_index_audit | apply_missing=false | missing 非空 → 需關注 |

## 判定（寫入【總覽】）

- **正常**：sq_ops_check 與管線/索引檢查通過，pending_deferred=0、missing 為空
- **需關注**：可讀但有 missing 索引、單一數據源熔斷、或指標偏高但未阻斷
- **異常**：工具失敗、多源熔斷、pending_deferred 長期 >0、或 INTERNAL_ERROR

## 輸出格式（繁體中文）

- 【總覽】一行：正常 / 需關注 / 異常 + 一句理由
- 【各項】三小段，每段 1–3 句，附關鍵數字或欄位名
- 【建議】僅列可執行下一步（對應 docs/runbooks/data-pipeline.md 或 TROUBLESHOOTING）；無風險則寫「無需立即處置」

工具失敗時寫明 tool 名、error_code、可能原因。`;

function stockQuantMcp() {
  return {
    "stock-quant": {
      type: "stdio" as const,
      command: python,
      args: ["-m", "src.integrations.mcp.server"],
      cwd: PROJECT_ROOT,
    },
  };
}

async function main() {
  const apiKey = process.env.CURSOR_API_KEY?.trim();
  if (!apiKey) {
    console.error(
      "缺少 CURSOR_API_KEY。請至 https://cursor.com/dashboard/cloud-agents 建立金鑰後：\n" +
        "  $env:CURSOR_API_KEY='cursor_...'   # PowerShell\n" +
        "  export CURSOR_API_KEY='cursor_...' # bash"
    );
    process.exit(1);
  }

  console.log(`[ops-check] project=${PROJECT_ROOT}`);
  console.log(`[ops-check] mcp=${python} -m src.integrations.mcp.server`);

  try {
    if (verbose) {
      const agent = await Agent.create({
        apiKey,
        model: { id: "composer-2" },
        local: { cwd: PROJECT_ROOT, settingSources: ["project"] },
        mcpServers: stockQuantMcp(),
      });
      try {
        const run = await agent.send(OPS_PROMPT);
        console.log(`[ops-check] agent=${agent.agentId} run=${run.id}`);

        for await (const event of run.stream()) {
          if (event.type === "status") {
            console.log(`[ops-check] status: ${event.status}`);
          }
          if (event.type === "tool_call" && event.status !== "running") {
            console.log(`[ops-check] tool: ${event.name} -> ${event.status}`);
          }
          if (event.type === "assistant") {
            for (const block of event.message.content) {
              if (block.type === "text") process.stdout.write(block.text);
            }
          }
        }

        const result = await run.wait();
        if (result.status !== "finished") {
          console.error(`[ops-check] run ended: ${result.status} (${result.id})`);
          process.exit(2);
        }
        if (!process.stdout.writableEnded) process.stdout.write("\n");
        console.log(`[ops-check] done ${result.durationMs}ms`);
      } finally {
        await agent[Symbol.asyncDispose]();
      }
      return;
    }

    const result = await Agent.prompt(OPS_PROMPT, {
      apiKey,
      model: { id: "composer-2" },
      local: { cwd: PROJECT_ROOT, settingSources: ["project"] },
      mcpServers: stockQuantMcp(),
    });

    console.log(result.result ?? "(no output)");
    if (result.status !== "finished") {
      console.error(`[ops-check] status=${result.status}`);
      process.exit(2);
    }
  } catch (err) {
    if (err instanceof CursorAgentError) {
      console.error(
        `[ops-check] startup failed: ${err.message} (retryable=${err.isRetryable})`
      );
      process.exit(err.isRetryable ? 75 : 1);
    }
    throw err;
  }
}

main();
