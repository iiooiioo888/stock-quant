# Cursor Agent Skills（claude-skills）

本專案已整合 [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) 技能庫，供 Cursor Agent 在對話中自動發現並使用。

## 安裝位置

| 範圍 | 路徑 |
|------|------|
| 專案（預設） | `.cursor/skills/<skill-slug>/SKILL.md` |
| 全域 | `%USERPROFILE%\.cursor\skills\` |

目前專案內約 **729** 個技能（依上游倉庫 `SKILL.md` 數量為準）。目錄已加入 `.gitignore`，不會提交到 Git。

## 更新技能

在專案根目錄執行：

```powershell
.\scripts\sync-cursor-skills.ps1 -Force
```

首次若本機沒有 clone，腳本會自動 `git clone` 到 `%TEMP%\claude-skills`。

安裝到使用者全域（所有專案可用）：

```powershell
.\scripts\sync-cursor-skills.ps1 -Global -Force
```

指定已有 clone 路徑：

```powershell
.\scripts\sync-cursor-skills.ps1 -Source D:\repos\claude-skills -Force
```

## 在 Cursor 中使用

1. 重新載入 Cursor 視窗（或重開專案）。
2. Agent 會依任務描述自動匹配相關 skill；也可在提示中明確提及技能名稱（例如 `content-creator`、`fullstack-engineer`）。
3. 勿寫入 `~/.cursor/skills-cursor/`（Cursor 內建技能目錄）。

## 其他安裝方式（可選）

```bash
# 官方 CLI（可能只安裝部分技能）
npx agent-skills-cli add alirezarezvani/claude-skills --agent cursor

# 上游 .mdc 規則格式（需 Git Bash / WSL）
git clone https://github.com/alirezarezvani/claude-skills.git
cd claude-skills && ./scripts/convert.sh --tool cursor
./scripts/install.sh --tool cursor --target /path/to/project
```

本專案採用 **Agent Skills** 格式（`.cursor/skills/*/SKILL.md`），與 Cursor 目前 Agent 技能機制一致。

## 參考

- 上游倉庫：https://github.com/alirezarezvani/claude-skills
- 安裝說明：https://github.com/alirezarezvani/claude-skills/blob/main/INSTALLATION.md
