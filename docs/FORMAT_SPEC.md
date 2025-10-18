# Data Assets Overview

經過討論後，字幕翻譯流程統一使用 YAML/Markdown 模組化文件。每一集建議置於 `data/<episode>/` 目錄，下列檔案為核心：

| 檔名 | 角色 | 備註 |
| --- | --- | --- |
| `main.yaml` | 逐段原始資料與翻譯結果 | SRT 解析後的主檔 |
| `topics.json` | 主題索引 + 摘要 | 定義段落範圍與主題重點（JSON 格式） |
| `terminology_candidates.yaml` | 術語候選清單 | mapper 輸出，列出每個 term 的段落出現處 |
| `terminology.yaml` | 術語表 | 優先用詞與說明 |
| `guidelines.md` | 翻譯風格指引 | 當作 system prompt 載入 |
| `drafts/*.md` | 翻譯工作檔 | 每個 topic 的翻譯情境檔（Markdown） |

**目錄慣例**

```
input/<episode>/                  # 原始 SRT（可能多語系）
data/<episode>/                   # YAML/Markdown 來源資料
output/<episode>/                 # 匯出成果（SRT/MD/報表）
```

例如：`configs/S01-E12.yaml` 可對應 `input/S01-E12/…`、`data/S01-E12/…`、`output/S01-E12/…` 等路徑。

---

## `main.yaml`

專注保存 SRT 原始資訊與翻譯欄位，避免混入摘要或風格設定。`segments` 為必填陣列，所有段落都記錄於此。

```yaml
episode_id: S01-E12
source_file: input/S01-E12/ENG-S01-E12Bridget Nielson_SRT_English.srt
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
      status: pending        # pending | in_progress | completed | needs_review | approved
      confidence: null       # 0.0 ~ 1.0，可選
      notes: null
    metadata:
      topic_id: null         # 初始為 null，翻譯時才寫入
      speaker_hint: ">>"
      source_entries: [2, 3]
      truncated: false
```

**基本原則**
- `segments` 必填且按 `segment_id` 遞增；`speaker_group` 遇到話者切換時加一。
- `source_text` 為原文句段，**盡可能**保證句子完整性，避免斷句。
  - **已知限制**：
    - 引號、括號或音效標籤開頭的句子可能被誤判為前句延續
    - 當合併達到 10-entry 安全上限時會強制停止，此時設置 `metadata.truncated: true`
    - 帶有 `truncated: true` 的段落應由 QA 工具自動標記為 `needs_review` 狀態
- `translation` 由翻譯流程填寫；不得直接覆蓋 `source_text`。
- `metadata` 欄位說明：
  - `topic_id`：初始為 `null`，由**翻譯流程寫入**（記錄實際使用的 topic context），而非 topics.json 生成時寫入。
  - `speaker_hint`：記錄 SRT 原始的 `>>` 標記。
  - `source_entries`：記錄來源 SRT 索引，用於追溯。
  - `truncated`：預設為 `false`，僅在達到安全上限時設為 `true`。

---

## `topics.json`

提供主題分段索引與摘要，作為翻譯批次的輔助工具。採用 JSON 格式以便於程式解析與 LLM 生成。

**重要設計原則**：
- `topics.json` 是**獨立的輔助索引**，不寫回 `main.yaml`
- `segment_start`/`segment_end` 允許有偏差，主題劃分本質上是主觀的
- `main.yaml` 的 `topic_id` 由翻譯流程寫入，記錄實際使用的 context

```json
{
  "global_summary": "The episode follows the narrator's journey to understand reality through repeated spiritual experiences in Sedona, touching on ET contact, community gatherings, and guidance for seekers.",
  "topics": [
    {
      "topic_id": "topic_01",
      "title": "Opening reflections on reality",
      "segment_start": 1,
      "segment_end": 20,
      "summary": "Establishes the contemplative tone with philosophical questions and hints at forthcoming discussions about reality and personal transformation.",
      "terminology": [
        "reality",
        "personal journey",
        "transformation"
      ]
    },
    {
      "topic_id": "topic_02",
      "title": "Experiences in Sedona, Arizona",
      "segment_start": 21,
      "segment_end": 60,
      "summary": "Covers repeated trips to Sedona, community gatherings, and the speaker's research into ET contact. Sets the thematic context for spiritual guidance.",
      "terminology": [
        "Sedona",
        "ET contact",
        "spiritual guidance"
      ]
    }
  ]
}
```

如需多主題重疊，可新增 `overlaps` 欄位或於 `main.yaml` 的 `metadata.topic_id` 改為陣列。若需要供人工閱讀的 Markdown 摘要，可由此檔案自動轉出。

---

## Terminology 資料

術語相關檔案分為三層，分別對應模板、候選標記與完成後的翻譯用詞表。候選檔會同時合併 template 直接命中的段落與 `topics.json` 中大模型建議的關鍵詞，並在 occurrence 內以 `sources` 標註來源。

### `configs/terminology_template.yaml`
- **用途**：跨集共用的術語知識庫，由人工維護。
- **內容**：只定義 `term`、`senses`、`preferred_translation`、`definition`、`notes` 等語義資訊，不含 `episode_id`、`segments`。

```yaml
terms:
  - term: channel
    senses:
      - id: channel_broadcast
        definition: 指電視頻道或節目來源
        preferred_translation: 頻道
        notes: 主持人介紹節目時採用
      - id: channel_spiritual
        definition: 指通靈、接收訊息
        preferred_translation: 通靈
        notes: 提到能量或訊息引導時使用
  - term: Sedona
    senses:
      - id: sedona_city
        definition: 美國亞利桑那州的塞多納
        preferred_translation: 塞多納
        notes: 保留音譯，必要時加註「亞利桑那州」
```

### `data/<episode>/terminology_candidates.yaml`
- **來源**：`terminology_mapper.py` 解析模板與 `main.yaml` 後自動產生。
- **目的**：列出每個術語在本集出現的全部段落，供人工或 LLM 後續分類。

```yaml
episode_id: S01-E12
terms:
  - term: channel
    occurrences:
      - segment_id: 15
        sources: [template]
        source_text: "We channel messages from non-physical guides."
      - segment_id: 45
        sources: [template, topic]
        source_text: "This channel airs every Friday night."
  - term: UFO
    occurrences:
      - segment_id: 67
        sources: [topic]
        source_text: "I witnessed a glowing UFO above Sedona."
```

**欄位規則**
- `episode_id`：對應配置中的 `episode_id`。
- `terms`：列表；每個項目包含：
  - `term`：英文字詞。
  - `occurrences`：段落清單；每筆至少含 `segment_id` 與 `sources`。
    - `sources`：來源標記（如 `template`、`topic`），指出此詞由 template 匹配或 topics.json 建議或兩者皆有。
    - 可選 `source_text` 供審查時參考；只有實際在字幕中找到的段落才會包含文字，topic-only 建議找不到對應句子時不會輸出 occurrence。
- 未出現的術語會被移除，確保候選表不帶入無效詞。

### `data/<episode>/terminology.yaml`
- **來源**：人工分類（或透過 `terminology_classifier.py` 輔助）將候選段落分配到模板 sense 後產生。
- **用途**：翻譯流程的唯一術語表輸入。

```yaml
episode_id: S01-E12
terms:
  - term: channel
    senses:
      - id: channel_spiritual
        definition: 指通靈、接收訊息
        preferred_translation: 通靈
        segments: [15, 28]
        notes: 提到能量或訊息引導時使用
      - id: channel_broadcast
        definition: 電視或串流頻道
        preferred_translation: 頻道
        segments: [45]
        notes: 用於介紹節目或平台時
  - term: UFO
    senses:
      - id: ufo_general
        definition: 不明飛行物或外星飛行器的通稱
        preferred_translation: 不明飛行物
        segments: [67, 89]
```

**欄位規則**
- `terms`：列表，每個項目需對應模板中的 `term`。
- `senses`：至少一項；每個 sense 應保留模板的 `id`、`definition`、`preferred_translation`，並新增：
  - `segments`：指向 `main.yaml` 的 `segment_id` 陣列，必須非空。
  - `topics`（可選）：若整段落對應單一 topic，可補充 `topic_id`。
  - `notes`：補充上下文或審核記錄。
- **互斥要求**：同一 `term` 底下的不同 sense，其 `segments` 不得重疊；所有 sense 的 `segments` 聯集需完整覆蓋候選檔中的出現段落。
- 產生翻譯前，請確認不存在空的 `segments` 或殘留 `occurrences` 欄位，否則視為尚未完成分類。
- `segments` 由分類階段填入；若某個 sense 最終沒有命中段落，請自檔案中移除該 sense。
- `notes` 用於補充上下文或人工審核事項。

---

## `guidelines.md`

作為翻譯模型的 system prompt，敘述風格與語氣要求，可依專案調整。

```markdown
# Translation Guidelines for S01-E12
- 保持沉思、靈性對談的語氣，避免過度口語。
- 對 ET/靈性術語使用術語表中的既定譯法。
- 保留第一人稱視角；遇到不確定的固有名詞，於 notes 標記待確認。
- 音效或音樂提示搬到句首，使用全形括號，如【冥想音樂】。
```

---

## 翻譯工作檔（`drafts/*.md`）

批次翻譯會在 `data/<episode>/drafts/` 下生成每個 topic 的 Markdown 工作檔（命名為 `topic_01.md`, `topic_02.md` 等）。此檔案保留原文與空白翻譯欄位，供人工或 LLM 填寫；完成後再回填 `main.yaml`。

**檔案格式**
```markdown
## Speaker Group 5

158. So that led you into dabbling into healing others.
→ {"text": "", "confidence": "", "notes": ""}

159. You said assisting others with alien abductions?
→ {"text": "", "confidence": "", "notes": ""}

## Speaker Group 6

160. Yeah.
→ {"text": "", "confidence": "", "notes": ""}

161. I started working with people who had similar experiences.
→ {"text": "", "confidence": "", "notes": ""}
```

**欄位規則**
- **Speaker Group 標題**：`## Speaker Group <N>`，標記話輪切換
  - 只在 `speaker_group` 變化時插入
  - 編號可能很大（如 127），這是話輪計數而非實際說話者數量
- **段落內容**（每個段落兩行）：
  - 第一行：`<segment_id>. <source_text>`（原文）
  - 第二行：`→ <JSON>`（翻譯欄位，JSON 物件）
- 段落之間空一行以提高可讀性
- 翻譯完成後填入：
  - `text`：**必填**，非空字串，實際翻譯內容
  - `confidence`：**必填**，枚舉值 `"high"` / `"medium"` / `"low"`（大小寫不敏感，回填時統一轉小寫）
  - `notes`：**可選**，可以是空字串或省略
- `backfill_translations.py` 將解析此檔案並更新 `main.yaml`

**驗證與錯誤處理**
- JSON 格式錯誤 → 標記該段為 `needs_review`
- `text` 缺失或空字串 → 標記為 `needs_review`
- `confidence` 缺失或不在枚舉值內 → 標記為 `needs_review`
- segment_id 對不上 `main.yaml` → 報錯並跳過該行

**工作流程**
1. 執行 `prepare_topic_drafts.py` 從 `main_segments.json` + `topics.json` 生成空框架 Markdown 檔
   - 自動插入 `## Speaker Group N` 標題標記話輪切換
2. 人工或 LLM 在箭頭右邊填入翻譯（配合 `guidelines.md` + `terminology.yaml` + `topics.json` 作為 context）
   - Speaker Group 標題幫助理解對話脈絡
3. 執行 `backfill_translations.py` 解析 `.md` 並寫回 `main.yaml`：
   - 追蹤 Speaker Group 標題，可選驗證與 `main.yaml` 的一致性
   - 驗證通過 → `translation.status: completed`
   - 驗證失敗 → `translation.status: needs_review`
   - 注意：`speaker_group` 不需要回填，`main.yaml` 已有正確值
4. 成功回填後可封存或刪除 `.md`，避免重複套用

**Speaker Group 說明**
- `speaker_group` 是**話輪計數器**，不代表實際說話者身份
- 編號遞增表示偵測到話輪切換（SRT 中的 `>>` 標記）
- 可能出現大編號（如 `## Speaker Group 127`），因為無法識別說話者，只能累加計數
- 實際對話者可能只有 2-3 人，但話輪切換可能上百次

如需保留進度分段，可自行將 `.md` 拷貝為階段備份，或在生成時指定不同輸出檔名。

---

## Loader 建議

使用 `configs/default.yaml` 維護共用路徑模板（`data/{episode}/main.yaml` 等），每個 episode 只需在 `configs/<episode>.yaml` 指定 `episode_id`；需要自訂時再覆寫個別欄位（例如有多個 `.srt` 檔時設定 `input.srt`）。此做法兼顧「零設定即可啟動」與「個案調整」。
