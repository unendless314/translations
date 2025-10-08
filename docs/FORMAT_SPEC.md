# Data Assets Overview

經過討論後，字幕翻譯流程統一使用 YAML/Markdown 模組化文件。每一集建議置於 `data/<episode>/` 目錄，下列檔案為核心：

| 檔名 | 角色 | 備註 |
| --- | --- | --- |
| `main.yaml` | 逐段原始資料與翻譯結果 | SRT 解析後的主檔 |
| `topics.yaml` | 主題索引 + 摘要 | 定義段落範圍與主題重點 |
| `terminology.yaml` | 術語表 | 優先用詞與說明 |
| `guidelines.md` | 翻譯風格指引 | 當作 system prompt 載入 |

---

## `main.yaml`

專注保存 SRT 原始資訊與翻譯欄位，避免混入摘要或風格設定。`segments` 為必填陣列，所有段落都記錄於此。

```yaml
episode_id: S01-E12
source_file: input/raw/ENG-S01-E12Bridget Nielson_SRT_English.srt
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
      has_music_tag: false
      raw_speaker_hint: ">>"
```

**基本原則**
- `segments` 必填且按 `segment_id` 遞增；`speaker_group` 遇到話者切換時加一。
- `source_text` 為原文句段，保持 SRT 的句讀與特殊標記。
- `translation` 由翻譯腳本填寫；流程不得直接覆蓋 `source_text`。
- `metadata.topic_id` 對應 `topics.yaml`；可視需要新增其他布林或字串旗標。

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
    keywords:
      - reality
      - personal journey
  - topic_id: sedona_experience
    title: Experiences in Sedona, Arizona
    segment_start: 21
    segment_end: 60
    summary: |
      Covers repeated trips to Sedona, community gatherings, and the speaker's
      research into ET contact. Sets the thematic context for spiritual guidance.
    keywords:
      - Sedona
      - ET research
global_summary: |
  The episode follows the narrator's journey to understand reality through
  repeated spiritual experiences in Sedona, touching on ET contact, community
  gatherings, and guidance for seekers.
```

如需多主題重疊，可新增 `overlaps` 或於 `main.yaml` 的 `metadata.topic_id` 改為陣列。若需要供人工閱讀的 Markdown 摘要，可由此檔案自動轉出。

---

## `terminology.yaml`

管理專有名詞及偏好譯法。支援一個英文詞對應多種語義，利用 `senses` 陣列描述各情境。

```yaml
episode_id: S01-E12
terms:
  - term: channel
    senses:
      - id: channel_broadcast
        definition: 指電視頻道或節目來源
        preferred_translation: 頻道
        segments: [12, 15, 48]
        notes: 主持人介紹節目時採用
      - id: channel_spiritual
        definition: 指通靈、接收訊息
        preferred_translation: 通靈
        topics: [guidance_session]
        notes: 提到能量或訊息引導時使用
  - term: Sedona
    senses:
      - id: sedona_city
        definition: 美國亞利桑那州的塞多納
        preferred_translation: 塞多納
        notes: 保留音譯，必要時加註「亞利桑那州」
```

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

在 `configs/<episode>.yaml`（可選）紀錄各檔案路徑，腳本只需讀取配置即可：

```yaml
episode_id: S01-E12
main: data/S01-E12/main.yaml
topics: data/S01-E12/topics.yaml
terminology: data/S01-E12/terminology.yaml
guidelines: data/S01-E12/guidelines.md
```

此設計讓短篇內容可以僅建立 `main.yaml` + `topics.yaml`，其他檔案視需要新增，不會造成過度工程化。若需要視覺化大綱，再以工具將 `topics.yaml` 轉成 Markdown 發佈。
