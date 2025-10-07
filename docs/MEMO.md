Next Steps Memo

  - 工程狀態：舊流程文檔與腳本已歸檔到 archive/legacy_docs/、archive/legacy_tools/；docs/FORMAT_SPEC.md 新定義了目標資料格式與檔案分工。
  - 目前資料模型：每集放在 data/<episode>/；核心檔案為 main.yaml（SRT 前處理後的段落資料，segments 必填）、topics.yaml（主題 + 摘要 + 全域總結）、terminology.yaml（一詞多義的
    senses 列表）、guidelines.md（翻譯風格指引）。summary.md 已移除。
  - segment_id 定義：以「前處理後的完整句段」為單位，非原始 SRT 行號；前處理腳本需負責合併斷句、計算 speaker_group、填 metadata.topic_id 等。
  - Flow 共識：SRT → main.yaml → topics.yaml (Gemini) → terminology/guidelines 補充 → 批次翻譯 (Claude/GPT) → QA → SRT/Markdown 回轉。後續翻譯模型只需更新 translation 欄位，結構
    維護由工具處理。
  - 待辦重點：
      1. 撰寫 SRT→main.yaml 前處理工具（含斷句規則、speaker group 邏輯、初始 metadata）。
      2. 設計支援 Gemini 生成 topics.yaml 的流程，並能回寫 topic_id 至主檔。
      3. 定義翻譯批次驅動程式的 I/O（讀取指定段落、合併模型輸出、處理斷點）。
      4. 補上 QA/匯出腳本輪廓（至少列出預期欄位與檢查策略）。
  - 注意事項：terminology.yaml 以 senses 支援一對多語義；context_tags、priority 暫不使用；若未來要給人工讀的摘要，可從 topics.yaml 自動轉 Markdown。

  To continue this session, run codex resume 0199bdf1-46f6-72c3-aca6-7906d56668a2