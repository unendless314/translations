# A/B 測試指南

本文檔說明如何使用不同的 LLM provider 進行 A/B 測試，評估哪個模型更適合執行 topic analysis 任務。

---

## 支援的 Provider

### 1. **Gemini** (Google)
- **推薦模型**：`gemini-3-pro-preview`
- **優勢**：
  - 大上下文窗口（1M+ tokens）
  - 新版模型品質提升；預覽階段仍支援長文本
  - 處理長文本效果好
- **適用場景**：處理大量 segments（1000+）

### 2. **OpenAI** (ChatGPT)
- **推薦模型**：
  - `gpt-5-mini` - 成本最低，適合測試
  - `gpt-5` - 高品質
  - `o1-mini` - 推理能力強（適合複雜任務）
- **優勢**：
  - 輸出品質穩定
  - 結構化輸出控制好
- **適用場景**：品質要求高的場景

---

## 設置 API Keys

### 1. 編輯 `.env` 檔案

```bash
# 至少設置一個 provider 的 API key
GEMINI_API_KEY=AIza...你的Gemini key...
OPENAI_API_KEY=sk-proj-...你的OpenAI key...
```

### 2. 取得 API Keys

**Gemini:**
- 網址：https://aistudio.google.com/app/apikey
- 免費額度：較大

**OpenAI:**
- 網址：https://platform.openai.com/api-keys
- 需要信用卡綁定

---

## A/B 測試步驟

### **方法 1：手動切換 Provider**

#### 測試 Gemini

1. 編輯 `configs/S01-E12.yaml`：
   ```yaml
   topic_analysis:
     provider: gemini
     model: gemini-3-pro-preview
     temperature: 1
     max_output_tokens: 8192
   ```

2. 執行：
   ```bash
   python3 tools/topics_analysis_driver.py \
     --config configs/S01-E12.yaml \
     --verbose
   ```

3. 備份結果：
   ```bash
   cp data/S01-E12/topics.json data/S01-E12/topics_gemini.json
   ```

#### 測試 OpenAI

1. 編輯 `configs/S01-E12.yaml`：
   ```yaml
   topic_analysis:
     provider: openai
     model: gpt-5-mini  # 或 gpt-5, o1-mini
     temperature: 1
     max_output_tokens: 8192
   ```

2. 執行：
   ```bash
   python3 tools/topics_analysis_driver.py \
     --config configs/S01-E12.yaml \
     --verbose
   ```

3. 備份結果：
   ```bash
   cp data/S01-E12/topics.json data/S01-E12/topics_openai.json
   ```

#### 比較結果

```bash
# 使用 diff 比較差異
diff data/S01-E12/topics_gemini.json data/S01-E12/topics_openai.json

# 或使用視覺化工具
code --diff data/S01-E12/topics_gemini.json data/S01-E12/topics_openai.json
```

---

### **方法 2：使用不同的配置檔**

創建多個配置檔案：

**`configs/S01-E12-gemini.yaml`**
```yaml
episode_id: S01-E12
# ... 其他設定 ...
topic_analysis:
  provider: gemini
  model: gemini-3-pro-preview
  temperature: 1
  max_output_tokens: 8192
output:
  topics_json: data/S01-E12/topics_gemini.json
```

**`configs/S01-E12-openai.yaml`**
```yaml
episode_id: S01-E12
# ... 其他設定 ...
topic_analysis:
  provider: openai
  model: gpt-5-mini
  temperature: 1
  max_output_tokens: 8192
output:
  topics_json: data/S01-E12/topics_openai.json
```

執行：
```bash
# 測試 Gemini
python3 tools/topics_analysis_driver.py --config configs/S01-E12-gemini.yaml

# 測試 OpenAI
python3 tools/topics_analysis_driver.py --config configs/S01-E12-openai.yaml
```

---

## 評估指標

### 1. **成本**
查看日誌中的 token 使用量：
```
[INFO] OpenAI API success - Input: 52,345, Output: 3,210, Time: 12.34s
```

計算成本：
- **Gemini 3 Pro (preview, ≤200k tokens)**: (52345 × $2 + 3210 × $12) / 1,000,000 = **$0.143**
- **GPT-5-mini**: (52345 × $0.15 + 3210 × $0.60) / 1,000,000 = **$0.010**
- **GPT-5**: (52345 × $2.50 + 3210 × $10) / 1,000,000 = **$0.163**

### 2. **處理時間**
查看日誌中的 `Time` 欄位。

### 3. **品質評估**

檢查生成的 `topics.yaml`：

#### 結構完整性
- ✅ 所有 segments 是否被覆蓋？
- ✅ 是否有 gap 或 overlap？
- ✅ topic_id 是否遞增且連續？

#### 語義品質
- ✅ Topic 標題是否精確？
- ✅ Summary 是否抓到重點？
- ✅ Keywords 是否相關？

#### 邊界準確度
- ✅ 主題切分點是否合理？
- ✅ 是否有明顯的主題混淆？

---

## 推薦策略

### **初期測試（節省成本）**
```yaml
topic_analysis:
  provider: openai
  model: gpt-5-mini        # 最便宜
  temperature: 1
  max_output_tokens: 8192
```

### **品質驗證**
如果 `gpt-5-mini` 結果不理想，升級到：
```yaml
topic_analysis:
  provider: gemini
  model: gemini-3-pro-preview    # 品質升級（預覽）
  temperature: 1
  max_output_tokens: 8192
```

### **最高品質**
```yaml
topic_analysis:
  provider: openai
  model: o1-mini           # 推理能力強
  temperature: 1
  max_output_tokens: 8192
```

---

## 常見問題

### Q1: 哪個模型最便宜？
**A**: `gpt-5-mini` 約為 Gemini 的 1/8 成本。

### Q2: 哪個模型品質最好？
**A**: 取決於任務。建議先用 `gpt-5-mini` 測試，再用 `gemini-3-pro-preview` 對比。

### Q3: 可以混用不同 provider 嗎？
**A**: 可以！例如：
- Topic analysis 用 Gemini（處理大量文本）
- Translation 用 GPT-5（品質要求高）

只需在 config 檔案中分別設置：
```yaml
topic_analysis:
  provider: gemini
  model: gemini-3-pro-preview

translation:
  provider: openai
  model: gpt-5-mini
```

### Q4: 如何處理 API 錯誤？
- **Rate limit (429)** - 工具會自動重試（指數退避）
- **Invalid API key (401)** - 檢查 `.env` 檔案
- **Timeout** - 增加 `timeout` 參數（預設 120 秒）

---

## 進階：Temperature 調整

### 低 Temperature (0.0 - 0.5)
- **效果**：輸出更確定、一致
- **適用**：結構化任務（topic analysis）
- **建議**：`temperature: 0.2`

### 中 Temperature (0.5 - 1.0)
- **效果**：平衡創意與一致性
- **適用**：翻譯任務
- **建議**：`temperature: 0.7`

### 高 Temperature (1.0 - 2.0)
- **效果**：更有創意、變化性高
- **適用**：內容生成
- **建議**：`temperature: 1.0`

---

## 範例：完整的 A/B 測試腳本

```bash
#!/bin/bash
# ab_test.sh - 自動化 A/B 測試

echo "=== Testing Gemini ==="
sed -i '' 's/provider: .*/provider: gemini/' configs/S01-E12.yaml
python3 tools/topics_analysis_driver.py --config configs/S01-E12.yaml
cp data/S01-E12/topics.json data/S01-E12/topics_gemini.json

echo "=== Testing OpenAI GPT-5-mini ==="
sed -i '' 's/provider: .*/provider: openai/' configs/S01-E12.yaml
sed -i '' 's/name: .*/name: gpt-5-mini/' configs/S01-E12.yaml
python3 tools/topics_analysis_driver.py --config configs/S01-E12.yaml
cp data/S01-E12/topics.json data/S01-E12/topics_openai_mini.json

echo "=== Testing OpenAI GPT-5 ==="
sed -i '' 's/name: .*/name: gpt-5/' configs/S01-E12.yaml
python3 tools/topics_analysis_driver.py --config configs/S01-E12.yaml
cp data/S01-E12/topics.json data/S01-E12/topics_openai_gpt5.json

echo "=== Results saved ==="
ls -lh data/S01-E12/topics_*.json
```

執行：
```bash
chmod +x ab_test.sh
./ab_test.sh
```

---

## 總結

- ✅ **最簡單**：直接修改 `configs/S01-E12.yaml` 的 `provider`
- ✅ **最便宜**：使用 `gpt-5-mini` 測試
- ✅ **最推薦**：Gemini 3 Pro（preview，品質升級）
- ✅ **最高品質**：GPT-5 或 o1-mini

根據你的需求選擇合適的策略！
