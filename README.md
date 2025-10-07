# 翻譯工具集 Translation Tools

字幕翻譯自動化工具，大幅提升翻譯效率。

## 📖 文檔

- **[快速開始指南](docs/QUICKSTART.md)** ⭐ 新手必看
- **[完整技術文檔](docs/README.md)** 詳細說明

## 📁 目錄結構

```
translations/
├── docs/                # 📖 說明文件
├── tools/               # 🛠️ 工具腳本
├── input/raw/           # 📥 原始 SRT 字幕
├── output/              # 📤 輸出檔案
│   ├── preprocessed/    # 前處理後（待翻譯）
│   ├── translated/      # 翻譯完成
│   └── final/           # 最終成品（帶時間軸）
└── archive/             # 🗄️ 已完成專案
```

## 🚀 快速開始

### 1. 放置原始檔案
```bash
cp your-subtitle.srt input/raw/
```

### 2. 前處理（5 秒）
```bash
# 編輯 tools/srt_preprocessor_v2.py 設定檔案名稱
python3 tools/srt_preprocessor_v2.py
```

### 3. 翻譯（1-3 小時）
打開 `output/preprocessed/*_待翻譯_簡單版.md` 進行翻譯

### 4. 時間軸對齊（10 秒）
```bash
# 翻譯完成後，移動檔案到 output/translated/
# 編輯 tools/align_timestamps_v2.py 設定檔案名稱
python3 tools/align_timestamps_v2.py
```

### 5. 完成！
查看 `output/final/*_中英對照_有時間軸.md`

---

## 🎯 核心功能

### SRT 前處理工具
- ✅ 自動合併被切斷的句子
- ✅ 智能偵測說話者轉換
- ✅ 壓縮率 60-70%

### 時間軸對齊工具
- ✅ 自動比對英文文字
- ✅ 對齊率 85-95%
- ✅ 保留完整時間軸映射

---

## 💡 時間節省

| 階段 | 舊流程 | 新流程 |
|------|--------|--------|
| 前處理 | 30-60 分鐘 | **5 秒** ⚡ |
| 時間軸對齊 | 3-5 小時 | **10 秒** ⚡ |
| **總計** | **5-8 小時** | **1.5-3.5 小時** |

**節省時間：50-70%** 🎉

---

## 📚 詳細文檔

完整的技術說明、參數調整、工作原理等，請參考：
- [完整技術文檔](docs/README.md)
- [快速開始指南](docs/QUICKSTART.md)

---

**最後更新：** 2025-10-07
**版本：** v2.0
