# Data Assets Overview

經過討論後，字幕翻譯流程統一使用 YAML/Markdown 模組化文件。每一集建議置於 `data/<episode>/` 目錄，下列檔案為核心：

| 檔名 | 角色 | 備註 |
| --- | --- | --- |
| `main.yaml` | 逐段原始資料與翻譯結果 | SRT 解析後的主檔 |
| `topics.yaml` | 主題索引 + 摘要 | 定義段落範圍與主題重點 |
| `terminology_candidates.yaml` | 術語候選清單 | mapper 輸出，列出每個 term 的段落出現處 |
| `terminology.yaml` | 術語表 | 優先用詞與說明 |
| `guidelines.md` | 翻譯風格指引 | 當作 system prompt 載入 |

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
      topic_id: intro
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
- `translation` 由翻譯腳本填寫；流程不得直接覆蓋 `source_text`。
- `metadata.topic_id` 對應 `topics.yaml`；`source_entries` 記錄來源 SRT 索引，用於追溯；`truncated` 預設為 `false`，僅在達到安全上限時設為 `true`。

---

## `topics.yaml`

提供主題分段索引與摘要，翻譯批次可依此載入相鄰上下文；同時承載原先的 summary 功能。

```yaml
episode_id: S01-E12
topics:
  - topic_id: intro
    title: Opening reflections on reality
    segment_start: 1
    segment_end: 20
    summary: |
      Establishes the contemplative tone with philosophical questions and hints at
      forthcoming discussions about reality and personal transformation.
    terminology:
      - reality
      - personal journey
      - transformation
  - topic_id: sedona_experience
    title: Experiences in Sedona, Arizona
    segment_start: 21
    segment_end: 60
    summary: |
      Covers repeated trips to Sedona, community gatherings, and the speaker's
      research into ET contact. Sets the thematic context for spiritual guidance.
    terminology:
      - Sedona
      - ET contact
      - spiritual guidance
global_summary: |
  The episode follows the narrator's journey to understand reality through
  repeated spiritual experiences in Sedona, touching on ET contact, community
  gatherings, and guidance for seekers.
```

如需多主題重疊，可新增 `overlaps` 或於 `main.yaml` 的 `metadata.topic_id` 改為陣列。若需要供人工閱讀的 Markdown 摘要，可由此檔案自動轉出。

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
- **來源**：人工或 `terminology_classifier.py` 將候選段落分配到模板 sense 後產生。
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

## Loader 建議

使用 `configs/default.yaml` 維護共用路徑模板（`data/{episode}/main.yaml` 等），每個 episode 只需在 `configs/<episode>.yaml` 指定 `episode_id`；需要自訂時再覆寫個別欄位（例如有多個 `.srt` 檔時設定 `input.srt`）。此做法兼顧「零設定即可啟動」與「個案調整」。
