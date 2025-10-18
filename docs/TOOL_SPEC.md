# 工具規格總覽

本文檔詳細描述各自動化腳本的設計目標、輸入輸出與處理邏輯，配合 `FORMAT_SPEC.md`、`WORKFLOW_NOTES.md` 使用。

---

## `srt_to_main_yaml.py`

**目的**  
解析原始 `.srt` 字幕，合併破碎句段，生成 `data/<episode>/main.yaml`。此檔為後續所有流程的資料來源。

- **設定檔**  
  利用 `configs/default.yaml` 的模板，episode 覆寫通常只需設定 `episode_id`，若資料夾內有多個 `.srt` 檔再覆寫 `input.srt`：
  ```yaml
  # configs/S01-E12.yaml
  episode_id: S01-E12
  # input:
  #   srt: input/S01-E12/custom_file.srt
  ```

  工具會自動從 `input/<episode>/` 中尋找唯一的 `.srt` 檔案；若存在多個檔案才需要指定完整路徑。

**執行介面**
```bash
python tools/srt_to_main_yaml.py --config configs/S01-E12.yaml
```
- 可加 `--force` 覆蓋已存在的 `main.yaml` 檔案。
- 可加 `--verbose` 顯示詳細的合併日誌。
- 日誌輸出位置由 `logging.path`（預設為 `logs/<episode>/workflow.log`）決定，可在 override 中調整。

**核心步驟**
1. **解析 SRT**：讀取 `index + timecode + text`，整理為結構化物件。
2. **文字清理**：
   - 移除 BOM、Trim 空白。
   - 將多行合併為單一字串（保留原換行處用空格替換）。
   - 保留音效／描述（如 `[MUSIC]`）於 `source_text`，直接交由 AI 翻譯。
   - 不嘗試移除跨段重複文字（若相鄰段落重覆一部分內容，仍交由後續人工或 QA 處理）。
3. **講者提示**：
   - 若文字以 `>>` 開頭，視為新說話者，去除 `>>` 後標記 `metadata.speaker_hint=">>"`。
   - 只保留提示，不嘗試辨識真名；話者群組由後續合併邏輯負責。
4. **句段合併**：
   - 初始化 `segment_id=1`, `speaker_group=1`。
   - 採用**句子完整性優先**策略：
     - **必須合併（MUST MERGE）**：若當前段落末尾無終止標點（`.!?…`），持續合併下一段直到句子完整。
     - **停止合併**：句子完整後，若下一個 entry 以大寫字母開頭，視為新句子，停止合併。
   - 停止合併條件：
     - 下一個 entry 以大寫開頭（新句子）。
     - 遇到說話者切換（`speaker_hint` 為 `>>`）。
     - 達到安全上限（10 個 SRT entries，防止異常情況無限合併）。
   - 合併後更新時間碼（取第一段 `start`、最後段 `end`），不調整個別時間值，並記錄來源索引列表 `metadata.source_entries`.
   - 若偵測到 `speaker_hint` 為 `>>` 且不是第一段，將 `speaker_group` 遞增。
   - 若達到安全上限強制停止合併，設置 `metadata.truncated: true` 並記錄警告（含 segment_id 和來源索引）。
5. **產生段落物件**：
   - `segment_id` 依序遞增。
   - `timecode` 保留 SRT 格式字串（`HH:MM:SS,mmm`），拆成 `start`/`end`。
   - `source_text` 使用 YAML `>` block，保留原句標點。
   - `translation` 預設：
     ```yaml
     translation:
       text: null
       status: pending
       confidence: null
       notes: null
     ```
   - `metadata`：
     - `topic_id: null`（待 topics 流程填入）
     - `speaker_hint`: `">>"` 或 `null`
     - `source_entries`: 原 SRT index 陣列
     - `truncated: false`（僅在達安全上限時為 `true`）
6. **輸出 YAML**：
   - 根據 `FORMAT_SPEC.md` 產生 `episode_id`, `source_file`, `segments`.
   - 若 config 中 `logging.path` 指定，輸出合併紀錄（例如哪些段落被合併、觸發條件、是否 truncated）。

**錯誤處理**
- 時間碼無法解析：記錄於 log，仍嘗試繼續，缺失段落跳過。
- 空白文字：保留於 `source_text`，交由翻譯流程處理。

**輸入/輸出範例**
輸入 SRT 片段：
```
2
00:00:38,663 --> 00:00:41,708
>> There are many paths to
figuring out the true nature
3
00:00:41,708 --> 00:00:42,500
of our reality.
```

輸出 `main.yaml` 段落：
```yaml
segments:
  - segment_id: 1
    speaker_group: 1
    timecode:
      start: "00:00:38,663"
      end: "00:00:42,500"
    source_text: >
      There are many paths to figuring out the true nature of our reality.
    translation:
      text: null
      status: pending
      confidence: null
      notes: null
    metadata:
      topic_id: null
      speaker_hint: ">>"
      source_entries: [2, 3]
      truncated: false
```

---

## `main_yaml_to_json.py`

**目的**  
讀取 `data/<episode>/main.yaml`，輸出精簡 JSON，提供模型閱讀全文並做章節解析、摘要生成等任務。僅保留語義理解所需的欄位（`segment_id`、`speaker_group`、`source_text`），避免與分析無關的中介資訊。

- **設定檔**（可選）
  ```yaml
  # configs/S01-E12.yaml
  episode_id: S01-E12
  input:
    main_yaml: data/S01-E12/main.yaml
  output:
    json: data/S01-E12/main_segments.json
  options:
    pretty: false              # true 時以縮排輸出（方便人工檢視）
  ```

**執行介面**
```bash
python tools/main_yaml_to_json.py --config configs/S01-E12.yaml
```
- `--main data/S01-E12/main.yaml` 指定輸入檔；`--output data/S01-E12/main_segments.json` 指定輸出檔。
- `--pretty` / `--no-pretty` 覆蓋設定檔。

**輸出格式**
- 純 JSON 陣列，每個元素對應一個段落，包含最小欄位集合：
  ```json
  [
    {
      "segment_id": 21,
      "speaker_group": 3,
      "source_text": "There are many paths to figuring out the true nature of our reality."
    },
    ...
  ]
  ```
  - `segment_id` 與 `speaker_group` 為必填，用於對回 `main.yaml` 與辨識話者切換。
  - `source_text` 為單行字串；原本多行內容會以空格連接，保留原始標點與特殊符號。
  - 未輸出 `episode_id`、`source_file` 等中介欄位，以維持最小字數與 token。

**錯誤處理**
- **檔案缺失**：找不到輸入檔時，以非零狀態碼結束並在 stderr 顯示具體路徑。
- **YAML 解析失敗**：回報原始錯誤訊息，輸出檔案不建立；必要時提供 `--debug` 以 dump 問題片段。
- **欄位缺失**：若缺 `episode_id` 或 `segments`，立刻終止；對於個別段落缺少 `segment_id` 或 `source_text` 的情況，跳過該段並記錄警告。
- **輸出寫入失敗**：捕捉 I/O 例外（如目錄不存在、權限不足），保留原檔案並回傳非零狀態碼。
- **完整性檢查**：確保 `segment_id` 遞增；出現異常時仍輸出但在 stderr 顯示 `Validation warnings` 列表。
- **JSON 序列化**：若 `source_text` 含非法字元或導致序列化失敗，立即報錯並停止，避免生成半成品。

---

## `topics_analysis_driver.py`

**目的**
接收 `main_yaml_to_json.py` 產出的段落 JSON，呼叫 LLM 產生主題結構，並寫入 `topics.json`。此工具負責：
- 統一載入 system prompt（`prompts/topic_analysis_system.txt`）
- 建立 API 請求（system/user messages）
- 解析模型回覆、驗證 schema
- 輸出符合 `FORMAT_SPEC.md` 定義的 `topics.json`（JSON 格式）

- **設定檔**（建議）
  ```yaml
  # configs/S01-E12.yaml (扁平結構)
  episode_id: S01-E12

  output:
    json: data/S01-E12/main_segments.json
    topics_json: data/S01-E12/topics.json

  prompts:
    topic_analysis_system: prompts/topic_analysis_system.txt

  # 扁平結構：所有 model 參數直接放在 topic_analysis 下
  topic_analysis:
    provider: gemini                # gemini, openai, anthropic
    model: gemini-2.5-pro           # 模型識別符
    temperature: 1                  # 0.0-2.0
    max_output_tokens: 8192
    timeout: 120
    max_retries: 3                  # 重試次數（內建指數退避）
    strict_validation: true         # 驗證警告視為錯誤
    dry_run: false                  # 測試模式（不調用 API）
  ```

**執行介面**
```bash
python3 tools/topics_analysis_driver.py --config configs/S01-E12.yaml [--dry-run] [--verbose]
```
- `--config` 配置檔案路徑（必需）
- `--dry-run` 僅檢查輸入與 prompt，不發送 API
- `--verbose` 顯示 DEBUG 級別日誌

**流程概述**
1. 載入段落 JSON（必須為陣列；驗證每項包含 `segment_id`, `speaker_group`, `source_text`）。
2. 讀取 system prompt 檔案，作為第一則訊息 (`role=system`)。
3. 將 JSON 內容序列化為 user message，前置簡短說明（預設：「Below is the episode transcript in JSON array form.」）；若 JSON 超過 API 限制，可自動切分或報錯。
4. 送出 API 請求；支援多種提供者（OpenAI, Gemini 等），由 `topic_analysis.provider` 控制。失敗時依 `max_retries` 設定重試。
5. 取得模型回覆（預期為 JSON），立即送入解析流程；若啟用額外日誌，可自行記錄回應供除錯。
6. 使用 JSON parser 解析回覆，檢查結構符合下列 schema：
   ```json
   {
     "global_summary": "str (必填，非空，≤600 words)",
     "topics": [
       {
         "topic_id": "str（格式建議 topic_\\d{2}，或語意化 ID）",
         "segment_start": "int",
         "segment_end": "int",
         "title": "str（非空，≤20 words）",
         "summary": "str（非空，≤200 words）",
         "terminology": ["list[str]（3-10 項，無術語時為空陣列 []）"]
       }
     ]
   }
   ```
7. 進行數值驗證：
   - `segment_start` ≤ `segment_end`
   - 範圍彼此不重疊且依序排列（上一個 `segment_end + 1 ==` 下一個 `segment_start` ）。
   - `segment_id` 覆蓋度：預設需涵蓋輸入 JSON 的全部段落；若 `strict_validation=false`，空缺會以警告標註。
8. 驗證通過後，依 `FORMAT_SPEC.md` 輸出 `topics.json`（JSON 格式），欄位順序及縮排需一致。

**錯誤處理**
- **輸入檔錯誤**：找不到 JSON/prompt 時立即終止；JSON 解析失敗或 schema 缺失則報錯並列出問題段落索引。
- **API 失敗**：網路/權限錯誤時回報 HTTP 狀態；達到最大重試仍失敗則終止。
- **輸出格式錯誤**：JSON 解析失敗、欄位缺失、topic 重疊等狀況時，在 stderr 提供可行修正建議並輸出部分回覆摘要，退出碼非零。
- **乾跑模式**：`--dry-run` 時檢查輸入與設定完整性，不呼叫 API；若驗證失敗同樣報錯。
- **日誌**：若指定 `logs/` 目錄，紀錄 API request metadata（移除 JSON 正文以避免重複儲存）、重試資訊與驗證結果。

---

## `terminology_mapper.py`

**目的**  
根據共用模板與 `main.yaml`，產生 `terminology_candidates.yaml`。候選檔列出每個術語在本集的所有出現處，供後續分類使用。

- **建議設定**
  ```yaml
  # configs/default.yaml
  terminology:
    template: configs/terminology_template.yaml
    candidates: "{data_root}/{episode}/terminology_candidates.yaml"
    output: "{data_root}/{episode}/terminology.yaml"
  ```
  - `template`：術語模板路徑，可在 episode override 中改成專案自訂檔案。
  - `candidates`：候選檔輸出位址，預設 `data/<episode>/terminology_candidates.yaml`。
  - `output`：完成分類後的最終檔案位址，預設 `data/<episode>/terminology.yaml`（由 classifier 或人工寫入）。

- **執行介面**
  ```bash
  python tools/terminology_mapper.py --config configs/S01-E12.yaml [--template configs/custom_template.yaml] [--dry-run] [--verbose]
  ```
  - `--template` 覆寫設定檔中的模板路徑。
  - `--dry-run` 僅列出將保留/移除的詞條與命中段落，不寫出檔案。
  - `--verbose` 顯示比對過程與候選段落。

- **輸入來源**
  1. 術語模板（預設 `configs/terminology_template.yaml`）
  2. `data/<episode>/main.yaml`
  3. `data/<episode>/topics.json`（若存在，提供 LLM 的 terminology 建議）

- **輸出**
  - `data/<episode>/terminology_candidates.yaml`：列出每個 term 的 `occurrences`（段落 ID、`sources` 標記與可選文字）。
  - 統計資訊：stdout 或 log，包含命中段落數、被移除的術語清單與原因。

- **核心流程**
  1. **載入模板**：解析 `terms`/`senses` 結構，建立候選術語清單（支援別名或 regex 欄位，若模板有定義）。
  2. **建構索引**：從 `main.yaml` 取得 `segment_id -> source_text` 映射，並將段落依 topics.json 的範圍分組以利比對。
  3. **比對與標記**：
     - Template 輪：在整份字幕中搜尋術語（可選大小寫忽略、正規化），對命中段落建立 `occurrences`，`sources` 初始為 `template`。
     - Topic 輪：解析 `topics.json` 的 `terminology` 清單，在對應的段落範圍內重試搜尋；若匹配成功，`sources` 包含 `topic`（若已存在 template 匹配則合併）。若仍找不到文字，也會將 topic 起始段落記錄為 `sources: [topic]` 的候選，方便人工後續確認。
  4. **輸出整理**：將兩輪產生的結果合併，依首度命中的順序輸出；每筆 occurrence 皆包含 `sources` 及（視需求）`source_text`（若使用 `--omit-text` 則省略）。

- **錯誤處理**
  - 找不到模板或 `main.yaml` 時立即終止；`topics.json` 不存在時僅記錄資訊訊息。
  - 模板 schema 不符時報錯並顯示錯誤欄位。
  - 若沒有任何術語被保留（常見於模型尚未跑完 topics），工具會警告並可選擇輸出空檔案或直接中止。

---

## `terminology_classifier.py` ⚙️

> **注意**：此工具為**可選自動化工具**，目前允許透過人工分類完成（直接編輯 `terminology.yaml` 或使用 Claude Code 協助）。

**目的**
讀取 `terminology_candidates.yaml`，將各段落分配到正確的 sense，輸出最終可供翻譯使用的 `terminology.yaml`。

- **預計設定**
  ```yaml
  terminology:
    template: configs/terminology_template.yaml
    candidates: "{data_root}/{episode}/terminology_candidates.yaml"
    output: "{data_root}/{episode}/terminology.yaml"
  ```

- **執行方式**
  - **方案 A：人工分類**（現行推薦）
    - 參考 `terminology_candidates.yaml` 中的 `occurrences`
    - 根據 `source_text` 判斷每個段落應歸屬哪個 sense
    - 直接編輯或透過 Claude Code 協助生成 `terminology.yaml`
    - 適合測試階段與小規模內容

  - **方案 B：自動化工具**（待實作）
    ```bash
    python tools/terminology_classifier.py --config configs/S01-E12.yaml [--auto] [--dry-run]
    ```
    - `--auto`：啟用 LLM 分類；若省略則提示人工審查程序
    - `--dry-run`：僅列出待分類項目，不寫出檔案

- **核心流程（概念稿）**
  1. 讀取模板與候選檔，建立 `term -> sense` 對應
  2. 偵測哪些 term 擁有多個 sense，且 `occurrences` 尚未分配
  3. 對每個 term 調用 LLM 或輸出人工審查清單，根據段落內容分配 sense
  4. 寫入 `terminology.yaml`，確保每個 sense 的 `segments` 互斥、非空
  5. 可加上簡單 validator（例如檢查 `segments` 是否覆蓋全部 occurrences）

- **驗證要求**
  - 翻譯流程啟動前應確認 `terminology.yaml` 存在
  - 所有 sense 的 `segments` 非空且互斥
  - `segments` 聯集應覆蓋候選檔中的所有 occurrences

---

## `translation_driver.py` ⚙️

> **注意**：此工具為**可選自動化工具**，目前推薦透過 Claude Code 互動式翻譯完成（詳見 `WORKFLOW_NOTES.md` 的「翻譯執行流程」章節）。

**目的**
自動化批次翻譯流程，按 topic 或段落數量分批處理，載入 context 並調用 LLM API 進行翻譯。

- **預計設定**
  ```yaml
  translation:
    batch_size: 10                    # 每批處理的段落數
    model:
      provider: gemini                # gemini, openai, anthropic
      model: gemini-2.5-flash
      temperature: 0.7
      max_output_tokens: 4096
  ```

- **執行介面（概念）**
  ```bash
  python tools/translation_driver.py --config configs/S01-E12.yaml [--resume] [--batch-size 10] [--topic topic_01]
  ```
  - `--resume`：根據 `translation.status` 續跑未完成的段落
  - `--batch-size`：覆寫批次大小
  - `--topic`：只處理特定 topic

- **核心流程（概念稿）**
  0. 檢查 `data/<episode>/drafts/` 是否存在對應的 `topic_id` 工作檔；若缺少則依 `topics.json` + `main_segments.json` 先生成 Markdown
  1. 讀取 `topics.json` 取得段落範圍
  2. 從 `drafts/<topic_id>.md` 載入原文段落（或在缺席工作檔時從 `main_segments.json` 切片）
  3. 從 `terminology.yaml` 篩選相關術語
  4. 載入 `guidelines.md` 風格指引
  5. 組裝標準化 prompt
  6. 批次調用 LLM API
  7. 將模型回覆寫入 `data/<episode>/drafts/<topic_id>.md`（或生成對應的回填 JSON）
  8. 解析 Markdown／回覆檔並回填 `main.yaml`（更新 `translation.*` 與 `metadata.topic_id`），成功後清理工作檔
  9. 支援斷點續跑（檢查 `translation.status` 與 drafts 目錄）

- **錯誤處理**
  - API 失敗時重試（指數退避）
  - 解析失敗時標記為 `needs_review`
  - 記錄詳細日誌供除錯

> 其他工具（QA checker、exporter 等）待確定細節後，將依相同格式補充於此檔案。

---

## `prepare_topic_drafts.py`

**目的**
根據 `topics.json` 與 `main_segments.json` 生成 `data/<episode>/drafts/<topic_id>.md`，每行包含 `segment_id`、原文與空白翻譯欄位（JSON 物件），供人工或 LLM 填寫。

- **設定檔**
  ```yaml
  # configs/S01-E12.yaml
  episode_id: S01-E12
  output:
    json: data/S01-E12/main_segments.json
    topics_json: data/S01-E12/topics.json
    drafts_dir: data/S01-E12/drafts
  ```

**執行介面**
```bash
python tools/prepare_topic_drafts.py --config configs/S01-E12.yaml [--force] [--verbose]
```
- `--config` 配置檔案路徑（必需）
- `--force` 覆寫已存在的 Markdown 檔案
- `--verbose` 顯示詳細日誌
- 可選：`--topic topic_01` 只生成特定 topic
- 可選：`--range 1-50` 只生成特定段落範圍

**核心流程**
1. 載入 `topics.json` 與 `main_segments.json`
2. 對每個 topic 執行：
   - 讀取 `segment_start` 與 `segment_end`
   - 從 `main_segments.json` 切片出對應的段落
   - 生成 Markdown 內容：
     ```markdown
     ## Speaker Group 2

     21. There are many paths to figuring out the true nature of our reality.
     → {"text": "", "confidence": "", "notes": ""}

     22. The path of my journey has taken me to Sedona, Arizona several times.
     → {"text": "", "confidence": "", "notes": ""}

     ## Speaker Group 3

     23. So what happened next?
     → {"text": "", "confidence": "", "notes": ""}
     ```
   - 追蹤 `speaker_group` 變化，在切換時插入 `## Speaker Group N` 標題
   - 寫入 `data/<episode>/drafts/<topic_id>.md`
3. 驗證所有段落都被至少一個 topic 覆蓋，若有遺漏段落則警告

**輸出格式**
- **Speaker Group 標題**：`## Speaker Group <N>`
  - 只在 `speaker_group` 變化時插入
  - 編號來自 `main_segments.json` 的 `speaker_group` 欄位
  - 編號可能很大（如 127），這是話輪計數而非實際說話者數量
- **段落內容**（每個段落佔兩行）：
  - 第一行：`<segment_id>. <source_text>`
  - 第二行：`→ {"text": "", "confidence": "", "notes": ""}`
- 段落之間空一行
- `segment_id`：對應 `main.yaml` 的段落編號
- `source_text`：原文（單行，若有換行會以空格連接）
- JSON 物件：空白框架，等待填寫

**錯誤處理**
- `topics.json` 或 `main_segments.json` 不存在 → 報錯並終止
- Segment 範圍超出 JSON 邊界 → 警告並跳過該 topic
- 檔案已存在且無 `--force` → 跳過並警告
- 目錄不存在 → 自動建立

---

## `backfill_translations.py`

**目的**
解析填妥的 `data/<episode>/drafts/<topic_id>.md` 檔案，驗證翻譯欄位，並寫回 `main.yaml` 的 `translation.*` 欄位。

- **設定檔**
  ```yaml
  # configs/S01-E12.yaml
  episode_id: S01-E12
  data:
    main_yaml: data/S01-E12/main.yaml
    drafts_dir: data/S01-E12/drafts
  ```

**執行介面**
```bash
python tools/backfill_translations.py --config configs/S01-E12.yaml [--dry-run] [--archive] [--verbose]
```
- `--config` 配置檔案路徑（必需）
- `--dry-run` 驗證檔案但不寫入 `main.yaml`
- `--archive` 回填成功後將 `.md` 移至 `drafts/archive/`
- `--verbose` 顯示詳細驗證日誌
- 可選：`--topic topic_01` 只處理特定 topic

**核心流程**
1. 掃描 `data/<episode>/drafts/*.md`（或指定的 `--topic`）
2. 對每個 Markdown 檔案：
   - 追蹤當前 `speaker_group`（從 `## Speaker Group N` 標題讀取）
   - 逐段解析（每段兩行）：
     - 第一行：`<segment_id>. <source_text>`
     - 第二行：`→ <JSON>`
   - 驗證 JSON 格式：
     - `text`：**必填**，非空字串
     - `confidence`：**必填**，枚舉值 `high`/`medium`/`low`（大小寫不敏感）
     - `notes`：可選
   - 驗證 `segment_id` 存在於 `main.yaml`
   - 驗證 `speaker_group` 與 `main.yaml` 中的記錄一致（可選檢查，不一致時警告）
3. 回填 `main.yaml`：
   - 更新 `translation.text`、`translation.confidence`（轉小寫）、`translation.notes`
   - 驗證通過 → `translation.status: completed`
   - 驗證失敗 → `translation.status: needs_review`
   - 記錄 `metadata.topic_id`（從檔案名稱推導，如 `topic_01.md` → `topic_01`）
   - 注意：不需要更新 `speaker_group`，因為 `main.yaml` 已經有正確的值
4. 若 `--archive`，移動已處理的 `.md` 至 `drafts/archive/`

**驗證規則**
| 狀況 | 處理 |
|------|------|
| JSON 格式錯誤 | 標記為 `needs_review`，記錄錯誤於日誌 |
| `text` 缺失或空字串 | 標記為 `needs_review` |
| `confidence` 缺失 | 標記為 `needs_review` |
| `confidence` 不在枚舉值內 | 標記為 `needs_review` |
| `segment_id` 對不上 | 報錯並跳過該行 |
| `notes` 缺失 | 接受（設為 `null`） |

**正規化處理**
- `confidence` 統一轉小寫（`High` → `high`）
- `notes` 為空字串時轉為 `null`

**錯誤處理**
- `main.yaml` 不存在 → 終止
- Markdown 檔案為空或格式錯誤 → 跳過並警告
- 寫入失敗 → 保留原檔案並報錯

**輸出**
- 更新後的 `main.yaml`
- 日誌統計：成功/失敗/needs_review 的段落數量
- 若 `--archive`，清理 `drafts/` 目錄

> 搭配 `prepare_topic_drafts.py` 使用，形成完整的翻譯工作流程。
