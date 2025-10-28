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
- ✅ **階段 4**：術語候選生成
- ✅ **階段 5**：術語分類完成
- ✅ **階段 6**：準備翻譯草稿
- ✅ **階段 7**：翻譯進行中
- ✅ **階段 8**：回填翻譯結果
- ✅ **階段 9**：QA 檢查與匯出

### 2. 智慧建議下一步
基於當前狀態，提供具體的操作建議和命令。

### 3. 檢查檔案完整性
驗證必要檔案是否存在：
- `input/<episode>/*.srt` - 原始字幕檔
- `data/<episode>/main.yaml` - 主要資料檔
- `data/<episode>/main_segments.json` - 精簡段落 JSON
- `data/<episode>/topics.json` - 主題分析結果
- `data/<episode>/terminology_candidates.yaml` - 術語候選（待分類）
- `data/<episode>/terminology.yaml` - 術語表（已分類）
- `data/<episode>/guidelines.md` - 翻譯指引
- `data/<episode>/drafts/*.md` - 翻譯工作檔

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
**檢查條件**：`main.yaml` 存在，但 `data/<episode>/main_segments.json` 不存在

**建議操作**：
```bash
python3 tools/main_yaml_to_json.py --config configs/<episode>.yaml --pretty --verbose
```

**說明**：匯出精簡的 JSON 檔案（僅含 segment_id, speaker_group, source_text），供 LLM 進行主題分析。

---

### 階段 3：主題分析
**檢查條件**：`main_segments.json` 存在，但 `topics.json` 不存在

**建議操作**：
```bash
python3 tools/topics_analysis_driver.py --config configs/<episode>.yaml --verbose
```

**說明**：使用 LLM 進行主題劃分與摘要生成，產出 topics.json（含 global_summary、topic 範圍、摘要與關鍵詞）。

---

### 階段 4：術語候選生成
**檢查條件**：`topics.json` 存在，但 `terminology_candidates.yaml` 不存在

**建議操作**：
```bash
python3 tools/terminology_mapper.py --config configs/<episode>.yaml --verbose
```

**說明**：根據術語模板（configs/terminology_template.yaml）與 topics.json 的關鍵詞建議，掃描 main.yaml 產生術語候選清單。每個候選包含所有出現的段落編號與來源標記（template/topic）。

---

### 階段 5：術語分類
**檢查條件**：`terminology_candidates.yaml` 存在，但 `terminology.yaml` 不存在或不完整

**建議操作（推薦）**：使用 Claude Code 協助分類

**準備工作** - 依序讀取以下檔案：
1. **必讀**：`docs/FORMAT_SPEC.md` 的 "Terminology 資料" 章節
   - 理解 `terminology.yaml` 的輸出格式
   - 了解 `segments` 欄位的互斥要求

2. **必讀**：`configs/terminology_template.yaml`
   - 查看所有術語的 sense 定義
   - 每個 sense 包含：`id`, `definition`, `preferred_translation`, `notes`

3. **必讀**：`data/<episode>/terminology_candidates.yaml`
   - 查看待分類的段落清單
   - 每個 occurrence 包含：`segment_id`, `sources`, `source_text`

4. **可選**：`data/<episode>/main_segments.json`
   - 只有當 `terminology_candidates.yaml` 檔案中的 `source_text` 不夠清晰時才需要
   - 可查看前後文以更準確判斷語義

**分類步驟**：
1. 對每個 `term`，檢查是否存在於 template 中：

   **情況 A：Template 中有該術語**
   - 查看 template 定義的所有 `senses`
   - 逐一檢視 `terminology_candidates.yaml` 中的每個 `occurrence`
   - 根據 `source_text` 判斷應屬於哪個 `sense`
   - 將 `segment_id` 分配到對應 sense 的 `segments` 陣列
   - 若所有現有 sense 都不適用，創建新 sense（見下方"創建新 sense"）

   **情況 B：Template 中沒有該術語**（來自 topics.json 的關鍵詞）
   - 檢視所有 `occurrences` 的 `source_text`
   - 理解該詞在本集的語義和用法
   - 創建完整的術語定義（見下方"創建新術語"）

2. 生成 `data/<episode>/terminology.yaml`，結構如下：
   ```yaml
   episode_id: <episode>
   terms:
     - term: <英文詞彙>
       senses:
         - id: <從 template 複製或新創建>
           definition: <從 template 複製或新創建>
           preferred_translation: <從 template 複製或新創建>
           segments: [15, 28, 67]  # 🆕 分類產生的段落編號
           notes: <從 template 複製，可補充分類備註>
   ```

**創建新術語**（Template 中沒有）：
```yaml
- term: quantum healing           # 新術語
  senses:
    - id: quantum_healing_practice  # 命名規範：小寫_下劃線
      definition: 結合量子物理概念的另類療癒方法
      preferred_translation: 量子療癒
      segments: [89, 102]
      notes: 本集專用術語，建議反饋到 template
```

**創建新 sense**（Template 有該詞，但現有 sense 都不適用）：
```yaml
- term: channel                    # Template 已有
  senses:
    # ... 保留 template 中的其他 sense ...
    - id: channel_energy_meridian  # 新增 sense
      definition: 人體內的能量通道或經絡
      preferred_translation: 能量通道
      segments: [123]
      notes: 本集新增 sense，建議反饋到 template
```

**命名與定義規範**（創建新內容時）：
- **id 格式**：`<term>_<語義關鍵詞>`（小寫，下劃線分隔）
  - 例：`quantum_healing_practice`, `reality_virtual`, `channel_energy_meridian`
- **definition**：簡明扼要的語義說明（參考 template 風格，1-2 句）
- **preferred_translation**：符合本專案語境的中文譯法
- **notes**：標注來源與狀態
  - "本集專用術語，建議反饋到 template"
  - "本集新增 sense，建議反饋到 template"
  - 可補充語境說明或翻譯注意事項

**範例**：
```yaml
# `terminology_candidates.yaml` 顯示
term: channel
occurrences:
  - segment_id: 15
    source_text: "We channel messages from guides."
  - segment_id: 45
    source_text: "This channel airs every Friday."

# 根據 template 的 sense 定義判斷
# segment 15 → channel_spiritual_verb (通靈)
# segment 45 → channel_broadcast (頻道)

# 生成 terminology.yaml
term: channel
senses:
  - id: channel_spiritual_verb
    definition: 透過靈性方法接收並傳遞非物質訊息的行為
    preferred_translation: 通靈
    segments: [15]           # 🆕 分配到這裡
  - id: channel_broadcast
    definition: 電視頻道或節目來源
    preferred_translation: 頻道
    segments: [45]           # 🆕 分配到這裡
```

**替代方案（待實作）**：自動化工具
```bash
python3 tools/terminology_classifier.py --config configs/<episode>.yaml --auto
```

**驗證要求**：
- 所有 sense 的 `segments` 必須非空且互斥
- `segments` 聯集應完整覆蓋候選檔中的所有 occurrences
- 若某個 sense 最終沒有命中任何段落，請從檔案中移除該 sense
- 確認不存在殘留的 `occurrences` 欄位（應改為 `segments`）
- 新創建的術語或 sense 必須包含完整的欄位（id, definition, preferred_translation, segments, notes）
- 新創建的 `id` 應遵循命名規範（小寫、下劃線分隔、語義明確）
- 新創建內容應在 `notes` 中標注來源（"本集專用" 或 "新增 sense"）

**後續工作**（可選）：
- 檢視新創建的術語和 sense，評估是否應反饋到 `configs/terminology_template.yaml`
- 優化定義和譯法，確保符合專案整體風格
- 若多集出現相同新術語，應將其加入 template 成為共用知識

---

### 階段 6：準備翻譯草稿
**檢查條件**：`terminology.yaml` 存在，但 `data/<episode>/drafts/` 目錄不存在或為空

**建議操作**：
```bash
python3 tools/prepare_topic_drafts.py --config configs/<episode>.yaml --verbose
```

**說明**：根據 topics.json 與 main_segments.json，為每個 topic 生成 Markdown 工作檔（`drafts/topic_01.md` 等），包含原文與空白翻譯框架。自動插入 Speaker Group 標題標記話輪切換。

**常用參數**：`--force`（覆寫已存在檔案）、`--topic topic_01`（只生成特定 topic）

---

### 階段 7：執行翻譯
**檢查條件**：drafts 目錄存在且有檔案

**建議操作（推薦）**：使用 Claude Code 互動式翻譯
1. 載入 Context：
   - `topics.json` - 全域摘要與當前 topic 的 summary、keywords
   - `terminology.yaml` - 篩選當前批次相關的術語
   - `guidelines.md` - 翻譯風格指引
2. 直接在 `drafts/<topic_id>.md` 中填寫翻譯（修改箭頭右側的 JSON 欄位）
3. 填寫欄位：
   - `text` - 翻譯內容（必填，非空）
   - `confidence` - high/medium/low（必填）
   - `notes` - 備註（可選）

**替代方案（待實作）**：自動化批次翻譯
```bash
python3 tools/translation_driver.py --config configs/<episode>.yaml --resume
```

**優勢**：
- 即時調整 prompt 與術語使用
- 靈活處理特殊情況
- 適合測試階段與小規模內容

---

### 階段 8：回填翻譯到 main.yaml
**檢查條件**：drafts 中的檔案已完成翻譯

**建議操作**：
```bash
python3 tools/backfill_translations.py --config configs/<episode>.yaml --verbose
```

**說明**：解析填妥的 Markdown 檔案，驗證翻譯欄位，並寫回 `main.yaml` 的 `translation.*` 與 `metadata.topic_id` 欄位。驗證通過設為 `completed`，失敗設為 `needs_review`。

**可選參數**：
- `--dry-run` - 驗證但不寫入
- `--archive` - 回填成功後將 .md 移至 drafts/archive/
- `--topic topic_01` - 只處理特定 topic

---

### 階段 9：QA 檢查與匯出
**檢查條件**：`main.yaml` 中的 `translation.status` 大部分為 `completed`

**建議操作**：
- QA 檢查（待實作）：
  ```bash
  python3 tools/qa_checker.py --config configs/<episode>.yaml
  ```
- 匯出 SRT（待實作）：
  ```bash
  python3 tools/export_srt.py --config configs/<episode>.yaml
  ```
- 匯出 Markdown 報告（待實作）：
  ```bash
  python3 tools/export_markdown.py --config configs/<episode>.yaml
  ```

**說明**：驗證翻譯品質、術語一致性，並匯出最終成果。

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
3. 判斷：`main.yaml` ✅, `topics.json` ✅, `terminology.yaml` ✅, `drafts/` ✅（但內容未完成）
4. 回應：「目前在階段 7（翻譯進行中），建議繼續編輯 drafts 中的 Markdown 檔案，或使用 Claude Code 協助翻譯。」

---

**建立時間**：2025-10-28
**適用專案**：SRT 字幕翻譯管線
