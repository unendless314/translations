---
name: subtitle-workflow
description: Manage SRT subtitle translation pipeline for episodes. Automatically detect workflow stage (SRT parsing, topic analysis, terminology, translation, QA) and suggest next steps. Use when user asks about translation progress, next steps, or workflow status.
allowed-tools: Read, Glob, Bash, Grep, Edit, Write
---

# 字幕翻譯工作流管理 Skill

這個 Skill 專門用於管理 SRT 字幕翻譯的完整工作流程。

## 主要功能

### 1. 自動檢測當前工作流階段
根據專案檔案狀態，判斷當前處於哪個階段：
- ✅ **階段 1**：SRT 已轉換為 main.yaml
- ✅ **階段 2**：已產生 segments JSON
- ✅ **階段 3**：已完成 topic analysis
- ✅ **階段 4**：準備翻譯草稿
- ✅ **階段 5**：翻譯進行中
- ✅ **階段 6**：QA 檢查與匯出

### 2. 智慧建議下一步
基於當前狀態，提供具體的操作建議和命令。

### 3. 檢查檔案完整性
驗證必要檔案是否存在：
- `input/<episode>/*.srt` - 原始字幕檔
- `data/<episode>/main.yaml` - 主要資料檔
- `data/<episode>/topics.json` - 主題分析結果
- `data/<episode>/terminology.yaml` - 術語表
- `data/<episode>/guidelines.md` - 翻譯指引

## 工作流階段詳解

### 階段 1：SRT 轉 YAML
**檢查條件**：`input/<episode>/*.srt` 存在，但 `data/<episode>/main.yaml` 不存在

**建議操作**：
```bash
python3 tools/srt_to_main_yaml.py --config configs/<episode>.yaml --verbose
```

**說明**：將 SRT 字幕檔解析為 YAML 格式，進行智慧句子合併。

---

### 階段 2：匯出 JSON 供 LLM 分析
**檢查條件**：`main.yaml` 存在，但 `data/<episode>/segments.json` 不存在

**建議操作**：
```bash
python3 tools/main_yaml_to_json.py --config configs/<episode>.yaml --pretty --verbose
```

**說明**：匯出輕量化的 JSON 檔案，準備進行主題分析。

---

### 階段 3：主題分析
**檢查條件**：`segments.json` 存在，但 `topics.json` 不存在

**建議操作**：
```bash
python3 tools/topics_analysis_driver.py --config configs/<episode>.yaml --verbose
```

**說明**：使用 LLM 進行主題劃分與摘要生成。

---

### 階段 4：準備翻譯草稿
**檢查條件**：`topics.json` 存在，但 `data/<episode>/drafts/` 目錄不存在或為空

**建議操作**：
```bash
python3 tools/prepare_topic_drafts.py --config configs/<episode>.yaml --verbose
```

**說明**：為每個主題生成 Markdown 工作檔案，供人工或 AI 翻譯。

---

### 階段 5：執行翻譯
**檢查條件**：drafts 目錄存在且有檔案

**建議操作**：
- 手動翻譯：編輯 `data/<episode>/drafts/*.md` 中的 JSON 欄位
- 自動翻譯：（待實作 `translation_driver.py`）

**需要提供的 Context**：
- `guidelines.md` - 翻譯風格指引
- `terminology.yaml` - 術語一致性
- `topics.json` - 主題摘要

---

### 階段 6：回填翻譯到 main.yaml
**檢查條件**：drafts 中的檔案已完成翻譯

**建議操作**：
```bash
python3 tools/backfill_translations.py --config configs/<episode>.yaml --verbose
```

**說明**：將翻譯結果寫回 `main.yaml`，準備匯出成 SRT。

---

## 檢測邏輯

當用戶詢問「接下來要做什麼」或「目前進度如何」時，自動執行：

1. 檢查 `configs/` 目錄，找出當前工作的 episode
2. 掃描對應的 `input/<episode>/` 和 `data/<episode>/` 目錄
3. 根據檔案存在狀態判斷階段
4. 提供具體的下一步指令

## 使用範例

**用戶問**：「S01-E12 目前進度如何？」

**Skill 自動執行**：
1. 檢查 `configs/S01-E12.yaml` 是否存在
2. 掃描 `data/S01-E12/` 檔案
3. 判斷：`main.yaml` ✅, `topics.json` ✅, `drafts/` ✅（但內容未完成）
4. 回應：「目前在階段 5（翻譯進行中），建議繼續編輯 drafts 中的 Markdown 檔案，或使用 Claude 協助翻譯。」

---

## 工具限制

此 Skill 允許使用的工具：
- `Read` - 讀取檔案內容
- `Glob` - 搜尋檔案模式
- `Bash` - 執行工作流工具
- `Grep` - 搜尋內容
- `Edit` / `Write` - 必要時修正設定檔

這些工具足以完成工作流管理，但不會執行危險操作（如刪除檔案）。

## 進階功能

### 檢查翻譯完成度
掃描 `main.yaml` 中的 `translation.status` 欄位：
- `pending` - 待翻譯
- `completed` - 已完成
- `needs_review` - 需要審核

統計各狀態的段落數量，提供進度報告。

### 驗證檔案完整性
- 檢查 timecode 格式
- 驗證 YAML 語法
- 確認 topic 範圍無重疊或空缺

---

**建立時間**：2025-10-28
**適用專案**：SRT 字幕翻譯管線
