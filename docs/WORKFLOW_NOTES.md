# 翻譯流程筆記

本文件記錄目前共識的自動翻譯流程與 prompt 組裝方式，補充 `FORMAT_SPEC.md` 中的資料結構定義。

---

## 批次翻譯概念

- **單位：Topic**  
  以 `topics.yaml` 中的 `topic_id` 為批次單位，一次處理同一主題下的多個段落。可再依段落數量（例如 5–12 段）調整子批次。

- **上下文組合**  
  前處理工具先載入：
  1. `topics.yaml`：取全域摘要(`global_summary`)與當前 topic 的 `summary`、關鍵字。
  2. `terminology.yaml`：篩出命中當前批次 `segment_id` 或 `topic_id` 的術語。建議在翻譯前由腳本先遍歷 `main.yaml`，自動填寫各術語的 `segments` / `topics` 陣列，未命中的詞保持空陣列，避免不必要的術語被載入。
  3. `guidelines.md`：提取翻譯風格與特殊指示。
  4. `main.yaml`：抓出目標段落的 `segment_id`, `speaker_group`, `timecode`, `source_text`, `metadata.topic_id` 等。

- **模型輸入**  
  程式將上述資訊濃縮成 prompt，確保上下文只出現一次，段落清單置於最後。避免整份 YAML 傳給模型，節省 token。

- **模型輸出**  
  要求模型以結構化格式回傳每個段落的翻譯與狀態欄位。程式再解析結果、填回 `main.yaml` 的 `translation` 欄位。

---

## Prompt 範例

```text
You are a professional subtitle translator. Translate the following segments into Traditional Chinese.

Global summary:
- The episode explores the narrator's search for reality through repeated visits to Sedona.

Topic intro (segments 1-20):
- Establishes a contemplative tone and hints at personal transformation.

Terminology reminders:
- channel (broadcast) → 頻道
- channel (spiritual) → 通靈

Guidelines:
- 保持沉思語氣，使用術語表中的既定譯法。
- 噪音/音樂提示採【...】格式置於句首。

Segments:
1. topic=intro, speaker_group=1
   EN: There are many paths to figuring out the true nature of our reality.

2. topic=intro, speaker_group=1
   EN: The path of my journey has taken me to Sedona, Arizona several times.
```

> 可根據需要加入時間碼、特殊標記（如 `[MUSIC]`），但避免塞入整份 YAML。

---

## 模型輸出格式建議

請模型回傳易於解析的 YAML/JSON。範例：

```yaml
segments:
  - segment_id: 1
    translation:
      text: "通往了解現實真相的方法有很多。"
      status: completed
      confidence: 0.92
      notes: null
  - segment_id: 2
    translation:
      text: "我的旅程曾多次把我帶到亞利桑那州的塞多納。"
      status: completed
      confidence: 0.90
      notes: "Sedona 保留音譯。"
```

程式解析後，更新 `main.yaml` 中 `segment_id` 對應的 `translation` 欄位：
```yaml
translation:
  text: ...
  status: completed
  confidence: 0.92
  notes: ...
```

---

## Merge 與斷點續傳

- 每批翻譯完成後即時寫回 `main.yaml`，避免大量堆積於記憶體。
- 若模型回傳錯誤或格式不完整，可使用備援 parser（例如嘗試修正、只使用成功的段落），並將未完成的段落維持 `status: pending`。
- 斷點續跑時，程式根據 `translation.status` 篩選 `pending` / `needs_review` 段落，繼續批次翻譯。

---

## QA 與輸出（待定）

- QA 工具可掃描 `translation.confidence`、術語一致性、字串長度比等指標，標記 `needs_review`。
- 完成後由 exporter 根據 `segment_id` 與 `timecode` 回輸標準 SRT，或轉為 Markdown/CSV 給人工檢閱。

> QA 與 exporter 的詳規會在實作時補充。

---

## `topics.yaml` 生成流程

1. **準備純文字稿**  
   - 撰寫轉換腳本，讀取 `main.yaml`，依序輸出形如 `[SEG 021] 原文內容` 的純文字檔，必要時保留音效或說話者提示。
   - 目的在於讓 LLM 聚焦內容，不必解析 YAML 結構。

2. **大模型分析**  
   - 將純文字稿餵給 Gemini 2.5 Pro（或類似大 context 模型），指示它用階層式章節（H1/H2/H3 或清單）整理主題，要求每個主題註明 `SEG 起–SEG 迄`、摘要與 2–3 個關鍵詞。

3. **解析輸出**  
   - 寫 parser 讀取模型回覆，抽取各節點的 `segment_start`、`segment_end`、`summary`、`keywords`，轉換成 `topics.yaml` 的 `topics` 陣列；全域概述填入 `global_summary`。
   - 若初次生成後發現段落邊界需微調，可再人工或程式調整 `segment_start`/`segment_end`，保持 `segment_id` 與摘要對應。

此流程確保 `topics.yaml` 與 `main.yaml` 同步，一旦主題切分完成，即可沿用在翻譯批次與術語索引中。
