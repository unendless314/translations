# 架構設計文檔

## 概述

本專案採用**模組化工具鏈**設計，每個工具為獨立的 Python 腳本，透過共用模組（`src/`）提供統一的 API 客戶端、資料模型和異常處理。

---

## 設計原則

### 1. 簡單優於複雜
- **同步執行**：工具按順序執行（SRT → JSON → Topics → Translation），不使用 async/await
- **獨立腳本**：每個工具可單獨執行，不依賴複雜的框架
- **最小依賴**：只引入必要的第三方套件

### 2. 模組化與重用
- **共用模組**（`src/`）：LLM 客戶端、資料模型、異常處理
- **工具專用**（`tools/`）：各工具的業務邏輯
- **明確介面**：透過抽象基類定義 API 客戶端規範

### 3. 配置驅動
- **YAML 配置**：共用 `configs/default.yaml` 定義模板，`configs/<episode>.yaml` 只覆寫差異
- **環境變數**：API keys 透過 `.env` 管理
- **靈活切換**：可在配置中指定不同的 LLM provider 和模型
- **模板共享**：`terminology.template` 預設指向 `configs/terminology_template.yaml`，`terminology.candidates` / `terminology.output` 分別對應候選與完成檔案，由術語工具鏈串接

---

## 資料流向

工具鏈採用**順序執行**模式，每個工具處理特定階段的資料轉換：

```
┌─────────────┐
│ input/      │  原始 SRT 字幕
│ episode.srt │
└──────┬──────┘
       │ srt_to_main_yaml.py
       ▼
┌─────────────┐
│ main.yaml   │  段落資料 + 翻譯欄位（初始為空）
└──────┬──────┘
       │ main_yaml_to_json.py
       ▼
┌─────────────┐
│ segments    │  精簡 JSON（僅 segment_id, speaker_group, source_text）
│ .json       │
└──────┬──────┘
       │ topics_analysis_driver.py (LLM)
       ▼
┌─────────────┐
│ topics.json │  主題結構 + 摘要 + 關鍵詞
└──────┬──────┘
       │
       ├──────────────────────────────┐
       │                              │
       │ terminology_mapper.py        │
       ▼                              │
┌─────────────────┐                  │
│ terminology     │                  │
│ _candidates     │                  │
│ .yaml           │                  │
└──────┬──────────┘                  │
       │ (人工或 LLM 分類)            │
       ▼                              │
┌─────────────────┐                  │
│ terminology     │                  │
│ .yaml           │                  │
└──────┬──────────┘                  │
       │                              │
       └──────────┬───────────────────┘
                  │
                  │ prepare_topic_drafts.py
                  ▼
           ┌─────────────┐
           │ drafts/     │  topic_01.md, topic_02.md, ...
           │ *.md        │  (空白翻譯框架)
           └──────┬──────┘
                  │ + guidelines.md
                  │ + terminology.yaml
                  │ + topics.json
                  │ 人工/LLM 填寫翻譯
                  ▼
           ┌─────────────┐
           │ drafts/     │  已填寫翻譯的 Markdown
           │ *.md        │
           └──────┬──────┘
                  │ backfill_translations.py
                  ▼
           ┌─────────────┐
           │ main.yaml   │  translation 欄位已填寫
           │ (updated)   │
           └──────┬──────┘
                  │ export_srt.py
                  ▼
           ┌─────────────┐
           │ output/     │  最終翻譯字幕
           │ episode.srt │
           └─────────────┘
```

**關鍵特性**：
- 每個工具輸出獨立檔案，支援斷點續跑
- `main.yaml` 為核心資料檔，隨翻譯進度更新 `translation.status`
- LLM 調用集中在兩處：主題分析（一次性）、翻譯（批次處理）
- Topic 翻譯草稿可預先切分並存放於 `data/<episode>/drafts/`，降低每次翻譯的上下文成本

---

## 目錄結構

```
.
├── configs/              # Episode 配置檔與共用模板
│   ├── default.yaml
│   ├── terminology_template.yaml
│   ├── S01-E12.yaml
│   └── SXX-EXX.yaml
├── data/                 # 工作資料（YAML/Markdown/JSON）
│   └── <episode>/
│       ├── drafts/                   # 翻譯工作檔（每個 topic 的 Markdown）
│       ├── main_segments.json        # 精簡段落 JSON（供 LLM 分析）
│       ├── main.yaml                 # 主資料檔（SRT 解析結果 + 翻譯）
│       ├── topics.json               # 主題結構（LLM 生成）
│       ├── terminology_candidates.yaml  # 術語候選（待分類）
│       ├── terminology.yaml          # 術語表（已分類）
│       └── guidelines.md             # 翻譯風格指引
├── docs/                 # 文檔
│   ├── ARCHITECTURE.md   # 本文檔
│   ├── TOOL_SPEC.md
│   ├── FORMAT_SPEC.md
│   └── WORKFLOW_NOTES.md
├── input/                # 原始 SRT 檔案
│   └── <episode>/
├── logs/                 # 日誌輸出
├── output/               # 匯出成果
│   └── <episode>/
├── prompts/              # LLM system prompts
│   └── topic_analysis_system.txt
├── src/                  # 🆕 共用模組
│   ├── __init__.py
│   ├── clients/          # API 客戶端
│   │   ├── __init__.py
│   │   ├── base_client.py
│   │   ├── gemini_client.py
│   │   ├── openai_client.py
│   │   └── anthropic_client.py
│   ├── config_loader.py  # Default+override 設定合併與路徑模板解析
│   ├── exceptions.py     # 自訂異常
│   └── models.py         # 資料模型
├── tools/                # 工具腳本（詳見 WORKFLOW_NOTES.md）
│   ├── srt_to_main_yaml.py         # SRT 解析與句段合併
│   ├── main_yaml_to_json.py        # 匯出精簡 JSON
│   ├── topics_analysis_driver.py   # LLM 主題分析
│   ├── terminology_mapper.py       # 術語候選生成
│   ├── prepare_topic_drafts.py     # 生成 topic 翻譯工作檔（Markdown）
│   ├── backfill_translations.py    # 解析工作檔並回填 main.yaml
│   ├── terminology_classifier.py   # 術語分類（規劃中）
│   ├── translation_driver.py       # 批次翻譯（可選自動化）
│   ├── qa_checker.py               # 品質檢查（規劃中）
│   ├── export_srt.py               # SRT 匯出
│   ├── split_srt.py                # SRT 字幕智能切割（通用工具）
│   └── export_markdown.py          # Markdown 匯出（規劃中）
├── .env.example          # API keys 範本
├── .gitignore
├── CLAUDE.md
├── AGENTS.md
├── README.md
└── requirements.txt
```

---

## 核心模組職責

### `src/clients/` - LLM 客戶端層

**職責**：提供統一的 LLM API 調用介面，支援多個 Provider。

**設計**：
- `BaseLLMClient` - 抽象基類，定義統一介面（`generate_content`, `get_client_info`）
- 子類別實作具體 Provider（Gemini, OpenAI, Anthropic）
- 同步方法設計，符合順序執行需求
- 內建智能重試機制（指數退避、錯誤分類）
- 統一返回 `APIResponse` 格式

**支援的 Provider**：
- **Gemini**：使用最新 `google-genai` SDK (0.1.0+)，支援 Gemini 2.0/2.5 系列
- **OpenAI**：支援 GPT-4o、o1 系列
- **Anthropic**：支援 Claude 3.5 系列，適合大型上下文

**錯誤處理**：
- 自動區分可重試錯誤（timeout, 429, 5xx）與不可重試錯誤（401, 400）
- 指數退避重試策略
- Token 使用統計與處理時間記錄

---

### `src/models.py` - 資料模型層

**職責**：定義結構化資料格式，提供型別安全。

**核心模型**：
- `APIResponse` - 統一的 API 回應格式（provider, success, content, token_usage, error_message）
- `TokenUsage` - Token 使用統計（input_tokens, output_tokens, total_tokens）

**技術選型**：使用 `@dataclass` 提供自動序列化與型別檢查。

---

### `src/exceptions.py` - 異常處理層

**職責**：提供專案特定的異常類別，支援智能錯誤處理。

**異常類別**：
- `TranslationError` - 基礎異常
- `ConfigError` - 配置錯誤
- `APIError` - API 調用錯誤（包含 `retryable` 屬性）
- `ValidationError` - 資料驗證錯誤

**重試邏輯**：透過 `APIError.retryable` 屬性決定是否重試。

---

### `src/config_loader.py` - 配置管理

**職責**：載入並合併配置檔案，解析路徑模板變數。

**功能**：
- 讀取 `configs/default.yaml` 與 `configs/<episode>.yaml`
- 自動合併配置（episode 覆寫 default）
- 解析路徑模板變數（如 `{data_root}/{episode}/main.yaml`）
- 驗證必要欄位存在

---

## 配置管理

### 設計原則

**Default + Override 模式**：
- `configs/default.yaml` - 定義路徑模板、模型預設值、共用參數
- `configs/<episode>.yaml` - 只覆寫差異（通常僅需 `episode_id`）
- `src/config_loader.py` - 自動合併配置並解析路徑模板變數

**路徑模板化**：
使用 `{變數}` 語法自動推導檔案路徑，避免每個 episode 重複定義：
```yaml
# default.yaml 定義模板
data_root: data
output:
  topics_json: "{data_root}/{episode}/topics.json"

# S01-E12.yaml 只需指定 episode_id
episode_id: S01-E12
# 自動展開為：data/S01-E12/topics.json
```

**API Key 管理**：
透過 `.env` 檔案管理敏感資訊，與配置檔分離：
```bash
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

詳細配置範例請參考 `docs/TOOL_SPEC.md`。

---

## 與其他專案的差異

本專案架構參考了 `phase18-social-automation`，但根據需求做了以下調整：

| 面向 | Phase18 | Translations (本專案) |
|------|---------|---------------------|
| 執行模式 | Async 並行處理 | **同步順序執行** |
| API Manager | 支援 fallback 和並行 | **簡化為單一 provider** |
| Config Manager | 複雜驗證邏輯 | **簡單 YAML 載入** |
| 批量統計 | BatchProcessResult | **使用 status 追蹤** |
| SDK 版本 | `google-genai>=0.1.0` | ✅ **採用相同** |
| Client 抽象 | ✅ 統一介面 | ✅ **採用相同** |
| 錯誤重試 | ✅ 智能分類 | ✅ **採用相同** |

**核心理念**：採用新技術（SDK/架構模式），但保持簡單（同步/獨立工具）。

---

## 未來擴展方向

- ✅ SRT 解析與句段合併（`srt_to_main_yaml.py`）
- ✅ JSON 段落匯出（`main_yaml_to_json.py`）
- ✅ 主題分析（`topics_analysis_driver.py`）
- ✅ 術語候選生成（`terminology_mapper.py`）
- 🆕 Topic Markdown 工作檔生成（`prepare_topic_drafts.py` - 待實作）
- 🆕 翻譯結果回填（`backfill_translations.py` - 待實作）
- ⚙️ 術語分類（現行：人工處理或 Claude Code 協助）
- ⚙️ 批次翻譯（現行：Claude Code 互動式翻譯）

### 短期（視需求開發）
- `qa_checker.py` - 翻譯品質檢查
  - 驗證術語一致性
  - 檢查 confidence 與 status
  - 標記需人工審查的段落
- `export_srt.py` / `export_markdown.py` - 匯出工具
  - 將 main.yaml 轉回 SRT 格式
  - 生成人工檢閱用報告

### 中期（流程穩定後）
- **可選自動化工具**
  - `terminology_classifier.py` - LLM 輔助術語分類
  - `translation_driver.py` - 批次翻譯自動化
- **基礎設施增強**
  - 實作快取機制（避免重複 API 調用）
  - 增加進度條顯示（rich library）
  - 支援更多 LLM providers（Cohere, Mistral）

### 長期（大規模需求時）
- 如需並行處理多個 episode → 引入 async
- 如需 A/B 測試模型 → 引入 APIManager
- 如需 Web UI → 整合 FastAPI/Streamlit

**設計原則**：優先保持流程簡單與靈活，只在實際需求出現時才引入自動化與複雜度。

---

## 參考資料

- **Google Gemini SDK 文檔**：https://ai.google.dev/gemini-api/docs
- **OpenAI API 文檔**：https://platform.openai.com/docs
- **Anthropic API 文檔**：https://docs.anthropic.com/
- **專案內部文檔**：
  - `docs/TOOL_SPEC.md` - 工具規格
  - `docs/FORMAT_SPEC.md` - 資料格式
  - `docs/WORKFLOW_NOTES.md` - 工作流程筆記
