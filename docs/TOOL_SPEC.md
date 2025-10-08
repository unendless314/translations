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
6. **輸出 YAML**：
   - 根據 `FORMAT_SPEC.md` 產生 `episode_id`, `source_file`, `segments`.
   - 若 `--log` 指定，輸出合併紀錄（例如哪些段落被合併、觸發條件）。

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
```

---

> 其他工具（plaintext exporter、topics parser、terminology mapper 等）待確定細節後，將依相同格式補充於此檔案。
