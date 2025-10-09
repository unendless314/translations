# 工具規格總覽

本文檔詳細描述各自動化腳本的設計目標、輸入輸出與處理邏輯，配合 `FORMAT_SPEC.md`、`WORKFLOW_NOTES.md` 使用。

---

## `srt_to_main_yaml.py`

**目的**  
解析原始 `.srt` 字幕，合併破碎句段，生成 `data/<episode>/main.yaml`。此檔為後續所有流程的資料來源。

- **設定檔**（建議）
  ```yaml
  # configs/S01-E12.yaml
  episode_id: S01-E12
  input:
    srt: input/S01-E12/ENG-S01-E12Bridget Nielson_SRT_English.srt
  output:
    main_yaml: data/S01-E12/main.yaml
  logging:
    path: logs/S01-E12/srt_to_yaml.log
  ```

**執行介面**
```bash
python tools/srt_to_main_yaml.py --config configs/S01-E12.yaml
```
- 可加 `--force` 覆蓋已存在的 `main.yaml` 檔案。
- 可加 `--verbose` 顯示詳細的合併日誌。
- 日誌輸出位置由 config 檔案的 `logging.path` 決定（非命令列參數）。

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
接收 `main_yaml_to_json.py` 產出的段落 JSON，呼叫 LLM 產生主題結構 YAML，並寫入 `topics.yaml`。此工具負責：
- 統一載入 system prompt（`prompts/topic_analysis_system.txt`）
- 建立 API 請求（system/user messages）
- 解析模型回覆、驗證 schema
- 輸出符合 `FORMAT_SPEC.md` 定義的 `topics.yaml`

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
4. 送出 API 請求；支援多種提供者（OpenAI, Gemini 等），由 `model.provider` 控制。失敗時依 `retry` 設定重試。
5. 取得模型回覆（預期為 YAML），立即送入解析流程；若啟用額外日誌，可自行記錄回應供除錯。
6. 使用 YAML parser 解析回覆，檢查結構符合下列 schema：
   ```yaml
   global_summary: str (必填，非空，≤600 words)
   topics: list(必填，至少一項)
     - topic_id: str（格式建議 `topic_\\d{2}`，或語意化 ID）
       segment_start: int
       segment_end: int
       title: str（非空，≤20 words）
       summary: str（非空，≤200 words）
       terminology: list[str]（3-10 項，無術語時為空陣列 []）
   ```
7. 進行數值驗證：
   - `segment_start` ≤ `segment_end`
   - 範圍彼此不重疊且依序排列（上一個 `segment_end + 1 ==` 下一個 `segment_start` ）。
   - `segment_id` 覆蓋度：預設需涵蓋輸入 JSON 的全部段落；若 `strict_validation=false`，空缺會以警告標註。
8. 驗證通過後，依 `FORMAT_SPEC.md` 輸出 `topics.yaml`，欄位順序及縮排需一致。可於結尾補上 `global_summary`。

**錯誤處理**
- **輸入檔錯誤**：找不到 JSON/prompt 時立即終止；JSON 解析失敗或 schema 缺失則報錯並列出問題段落索引。
- **API 失敗**：網路/權限錯誤時回報 HTTP 狀態；達到最大重試仍失敗則終止。
- **輸出格式錯誤**：YAML 解析失敗、欄位缺失、topic 重疊等狀況時，在 stderr 提供可行修正建議並輸出部分回覆摘要，退出碼非零。
- **乾跑模式**：`--dry-run` 時檢查輸入與設定完整性，不呼叫 API；若驗證失敗同樣報錯。
- **日誌**：若指定 `logs/` 目錄，紀錄 API request metadata（移除 JSON 正文以避免重複儲存）、重試資訊與驗證結果。

---

> 其他工具（plaintext exporter、topics parser、terminology mapper 等）待確定細節後，將依相同格式補充於此檔案。
