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

---

## 目錄結構

```
.
├── configs/              # Episode 配置檔
│   ├── default.yaml
│   ├── S01-E12.yaml
│   └── SXX-EXX.yaml
├── data/                 # 工作資料（YAML/Markdown）
│   └── <episode>/
│       ├── main_segments.json
│       ├── main.yaml
│       ├── topics.yaml
│       ├── terminology.yaml
│       └── guidelines.md
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
├── tools/                # 工具腳本
│   ├── srt_to_main_yaml.py         ✅
│   ├── main_yaml_to_json.py        ✅
│   ├── topics_analysis_driver.py   ✅
│   ├── terminology_mapper.py       ⏳
│   ├── translation_driver.py       ⏳
│   ├── qa_checker.py               ⏳
│   ├── export_srt.py               ⏳
│   └── export_markdown.py          ⏳
├── .env.example          # API keys 範本
├── .gitignore
├── CLAUDE.md
├── AGENTS.md
├── README.md
└── requirements.txt
```

---

## 核心模組設計

### `src/exceptions.py` - 自訂異常

提供專案特定的異常類別，用於錯誤處理和重試邏輯。

```python
class TranslationError(Exception):
    """基礎異常類別"""
    pass

class ConfigError(TranslationError):
    """配置錯誤"""
    pass

class APIError(TranslationError):
    """API 調用錯誤"""
    def __init__(self, provider: str, message: str, retryable: bool = True):
        self.provider = provider
        self.retryable = retryable
        super().__init__(message)

class ValidationError(TranslationError):
    """資料驗證錯誤"""
    pass
```

**重試邏輯**：
- `retryable=True`：網路錯誤、timeout、rate limit (429/503)
- `retryable=False`：API key 錯誤 (401/403)、格式錯誤 (400)

---

### `src/models.py` - 資料模型

使用 `@dataclass` 定義結構化資料，提供型別安全和自動序列化。

```python
@dataclass
class TokenUsage:
    """Token 使用統計"""
    input_tokens: int
    output_tokens: int
    total_tokens: int

@dataclass
class APIResponse:
    """API 回應統一格式"""
    provider: str          # "gemini" / "openai" / "anthropic"
    success: bool
    content: str
    token_usage: TokenUsage
    error_message: Optional[str] = None
    processing_time: float = 0.0
```

**為什麼使用 dataclass？**
- ✅ 自動產生 `__init__`, `__repr__`, `__eq__`
- ✅ Type hints 提供 IDE 自動補全
- ✅ 易於序列化（可轉換為 dict）

---

### `src/clients/base_client.py` - 抽象基類

定義所有 LLM 客戶端的統一介面。

```python
from abc import ABC, abstractmethod
from typing import Dict, Any
from ..models import APIResponse

class BaseLLMClient(ABC):
    """LLM 客戶端抽象基類"""

    @abstractmethod
    def generate_content(self, system_prompt: str, user_message: str) -> APIResponse:
        """生成內容（同步方法）"""
        pass

    @abstractmethod
    def get_client_info(self) -> Dict[str, Any]:
        """取得客戶端資訊"""
        pass
```

**設計考量**：
- 使用**同步方法**（非 async），符合工具鏈順序執行的需求
- 返回統一的 `APIResponse` 格式
- 子類別實作具體的 API 調用邏輯

---

### `src/clients/gemini_client.py` - Gemini 客戶端

實作 Google Gemini API 調用，使用**最新的 `google-genai` SDK**。

**主要功能**：
1. **新版 SDK 支援**（2024+）
   ```python
   from google import genai
   from google.genai import types

   client = genai.Client(api_key=api_key)
   response = client.models.generate_content(
       model="gemini-2.0-flash-exp",
       contents=user_message,
       config=types.GenerateContentConfig(
           system_instruction=system_prompt
       )
   )
   ```

2. **智能重試機制**
   - 指數退避（exponential backoff）
   - 區分可重試 / 不可重試錯誤
   - 最大重試次數可配置

3. **Token 統計**
   - 自動提取 `usage_metadata`
   - 記錄 input/output/total tokens

4. **環境變數管理**
   - 從 `GEMINI_API_KEY` 讀取 API key
   - 啟動時驗證 API key 存在

---

### `src/clients/openai_client.py` - OpenAI 客戶端

實作 OpenAI API 調用（備用選項）。

**支援模型**：
- `gpt-4o`
- `gpt-4o-mini`
- `o1-preview`（推理模型）

**配置範例**（扁平結構）：
```yaml
topic_analysis:
  provider: openai
  model: gpt-5-mini
  temperature: 1
  max_output_tokens: 8192
```

---

### `src/clients/anthropic_client.py` - Anthropic 客戶端

實作 Anthropic Claude API 調用（備用選項）。

**支援模型**：
- `claude-3-5-sonnet-20241022`
- `claude-3-5-haiku-20241022`

**特點**：
- 支援長上下文（200K tokens）
- 適合處理大型 segments JSON

---

## 配置結構

### `configs/default.yaml`

共用配置負責定義路徑模板與模型預設值：

```yaml
variables:
  input_root: input
  data_root: data
  output_root: output
  logs_root: logs
  prompts_root: prompts
  main_yaml_filename: main.yaml
  segments_json_filename: main_segments.json
  topics_json_filename: topics.json
  log_filename: workflow.log

episode_id: "{episode}"

input:
  srt: "{input_root}/{episode}"
  main_yaml: "{data_root}/{episode}/{main_yaml_filename}"

output:
  main_yaml: "{data_root}/{episode}/{main_yaml_filename}"
  json: "{data_root}/{episode}/{segments_json_filename}"
  topics_json: "{data_root}/{episode}/{topics_json_filename}"

prompts:
  topic_analysis_system: "{prompts_root}/topic_analysis_system.txt"

topic_analysis:
  provider: gemini
  model: gemini-2.5-pro
  temperature: 1
  max_output_tokens: 8192
  timeout: 180
  max_retries: 3
  strict_validation: true
  dry_run: false

translation:
  provider: gemini
  model: gemini-2.5-pro
  temperature: 1
  max_output_tokens: 16384
  timeout: 180
  max_retries: 3
  batch_size: 10
  resume: true

logging:
  level: INFO
  path: "{logs_root}/{episode}/{log_filename}"
```

### `configs/<episode>.yaml`

Episode 覆寫檔僅保留差異，例如自訂 SRT 檔名或模型參數：

```yaml
episode_id: S01-E12

input:
  # 可選：若資料夾內有多個 SRT，可明確指定檔案
  # srt: input/S01-E12/ENG-S01-E12Bridget Nielson_SRT_English.srt
```

> 預設情況下 `srt_to_main_yaml.py` 會自動偵測 `input/<episode>/` 內唯一的 `.srt` 檔案；只有當資料夾包含多個 `.srt` 時才需要覆寫 `input.srt`。

---

## 工具執行流程

### 1. `srt_to_main_yaml.py` ✅
- **輸入**：原始 SRT 檔案
- **輸出**：`data/<episode>/main.yaml`
- **依賴**：無（純文字處理）
- **特點**：自動從 `input/<episode>/` 偵測唯一的 `.srt` 檔案（必要時可在配置中覆寫）
- **執行**：
  ```bash
  python3 tools/srt_to_main_yaml.py --config configs/S01-E12.yaml
  ```

### 2. `main_yaml_to_json.py` ✅
- **輸入**：`main.yaml`
- **輸出**：`main_segments.json`（精簡格式）
- **依賴**：無
- **執行**：
  ```bash
  python3 tools/main_yaml_to_json.py --config configs/S01-E12.yaml
  ```

### 3. `topics_analysis_driver.py` ✅
- **輸入**：`main_segments.json` + `topic_analysis_system.txt`
- **輸出**：`topics.yaml`
- **依賴**：`src/clients/`, `src/models.py`
- **API 調用**：是（需要 API key）
- **執行**：
  ```bash
  python3 tools/topics_analysis_driver.py --config configs/S01-E12.yaml
  ```

### 4. `translation_driver.py` ⏳
- **輸入**：`main.yaml` + `topics.yaml` + `terminology.yaml` + `guidelines.md`
- **輸出**：更新 `main.yaml` 的 `translation` 欄位
- **依賴**：`src/clients/`
- **API 調用**：是（批量調用）

---

## API 客戶端使用範例

### 基本用法

```python
from src.clients.gemini_client import GeminiClient
from src.models import APIResponse

# 初始化客戶端
config = {
    'model': 'gemini-2.0-flash-exp',
    'timeout': 120,
    'max_retries': 3
}
client = GeminiClient(config)

# 調用 API
system_prompt = "You are a subtitle translator."
user_message = "Translate this text to Chinese."

response: APIResponse = client.generate_content(system_prompt, user_message)

if response.success:
    print(f"Content: {response.content}")
    print(f"Tokens: {response.token_usage.total_tokens}")
else:
    print(f"Error: {response.error_message}")
```

### 錯誤處理

```python
from src.exceptions import APIError, ConfigError

try:
    response = client.generate_content(system_prompt, user_message)
    if not response.success:
        logger.error(f"API failed: {response.error_message}")
except APIError as e:
    if e.retryable:
        logger.warning(f"Retryable error: {e}")
        # 可以重試
    else:
        logger.error(f"Non-retryable error: {e}")
        # 立即終止
except ConfigError as e:
    logger.error(f"Configuration error: {e}")
    sys.exit(1)
```

---

## 重試策略

### 指數退避演算法

```python
for attempt in range(max_retries + 1):
    try:
        response = call_api()
        return response
    except Exception as e:
        if not is_retryable(e) or attempt == max_retries:
            raise

        # 指數退避：2^attempt 秒，最大 60 秒
        delay = min(2 ** attempt, 60)
        logger.info(f"Retrying in {delay}s... (attempt {attempt + 1})")
        time.sleep(delay)
```

### 可重試的錯誤

- `timeout` - API 請求超時
- `connection` - 網路連線問題
- `rate limit` / `429` - 請求過於頻繁
- `500` / `502` / `503` / `504` - 伺服器錯誤

### 不可重試的錯誤

- `invalid api key` / `401` - API key 無效
- `403` - 權限不足
- `400` - 請求格式錯誤
- `404` - 資源不存在

---

## 開發指南

### 新增 LLM Provider

1. 在 `src/clients/` 創建新檔案（如 `cohere_client.py`）
2. 繼承 `BaseLLMClient` 並實作抽象方法
3. 更新 `.env.example` 加入新的 API key
4. 更新 `requirements.txt` 加入對應 SDK

### 新增工具

1. 在 `tools/` 創建新腳本
2. 使用 `argparse` 處理命令列參數
3. 從 `configs/<episode>.yaml` 讀取配置
4. 匯入 `src/clients/` 如需 API 調用
5. 更新 `docs/TOOL_SPEC.md` 文檔

---

## 測試策略

### 單元測試
- `tests/test_clients.py` - 測試 API 客戶端（使用 mock）
- `tests/test_models.py` - 測試資料模型
- `tests/test_parsers.py` - 測試 SRT 解析邏輯

### 整合測試
- `tests/test_workflow.py` - 端到端測試（需要真實 API key）

### 執行測試
```bash
# 單元測試（不需 API key）
pytest tests/test_models.py -v

# 整合測試（需要 .env）
pytest tests/test_workflow.py -v --api
```

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

### 短期（Phase 2-3）
- ✅ 完成 `topics_analysis_driver.py`
- ⏳ 實作 `translation_driver.py`（批量翻譯）
- ⏳ 實作 `qa_checker.py`（品質檢查）

### 中期（Phase 4-5）
- 支援更多 LLM providers（Cohere, Mistral）
- 實作快取機制（避免重複 API 調用）
- 增加進度條顯示（rich library）

### 長期（可選）
- 如需並行處理多個 episode → 引入 async
- 如需 A/B 測試模型 → 引入 APIManager
- 如需 Web UI → 整合 FastAPI/Streamlit

---

## 參考資料

- **Google Gemini SDK 文檔**：https://ai.google.dev/gemini-api/docs
- **OpenAI API 文檔**：https://platform.openai.com/docs
- **Anthropic API 文檔**：https://docs.anthropic.com/
- **專案內部文檔**：
  - `docs/TOOL_SPEC.md` - 工具規格
  - `docs/FORMAT_SPEC.md` - 資料格式
  - `docs/WORKFLOW_NOTES.md` - 工作流程筆記
