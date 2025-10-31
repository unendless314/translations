# Subtitle Translation Pipeline

A modular, LLM-powered subtitle translation system for long-form content.

## Features

- **Intelligent SRT parsing** with sentence-boundary detection
- **Topic-based segmentation** using large-context LLMs
- **Multi-sense terminology** management
- **Batch translation** with context assembly
- **Resume support** for interrupted workflows
- **Quality validation** and review flagging

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` and add your API key(s):

```bash
# Required for topic analysis and translation
GEMINI_API_KEY=your_actual_api_key_here

# Optional alternatives
# OPENAI_API_KEY=...
# ANTHROPIC_API_KEY=...
```

**Get API Keys:**
- **Gemini** (recommended): https://aistudio.google.com/app/apikey
- **OpenAI**: https://platform.openai.com/api-keys
- **Anthropic**: https://console.anthropic.com/

### 3. Process Subtitles

> 所有指令請在專案根目錄執行，若未啟用虛擬環境，記得先設定 `PYTHONPATH=.`

```bash
export PYTHONPATH=.

# Step 1: Convert SRT to structured YAML
python3 tools/srt_to_main_yaml.py --config configs/S01-E12.yaml

# Step 2: Export segments for topic analysis
python3 tools/main_yaml_to_json.py --config configs/S01-E12.yaml

# Step 3: Generate topic structure (requires API key)
python3 tools/topics_analysis_driver.py --config configs/S01-E12.yaml

# Step 4: Translate (coming soon)
# python3 tools/translation_driver.py --config configs/S01-E12.yaml
```

## Project Structure

```
├── input/<episode>/          # Original SRT files
├── data/<episode>/           # Working data files
│   ├── main.yaml            # Segments + translations
│   ├── topics.json          # Topic structure
│   ├── terminology.yaml     # Term definitions
│   └── guidelines.md        # Translation style guide
├── output/<episode>/         # Exported results
├── configs/default.yaml     # Shared defaults and path templates
├── configs/<episode>.yaml    # Episode-specific overrides (usually just episode_id)
├── prompts/                 # LLM system prompts
└── tools/                   # Processing scripts
```

## Data Files

### `main.yaml`
Central data file containing:
- All parsed SRT segments with timecodes
- Translation results and status tracking
- Segment metadata (topics, speakers, etc.)

### `topics.json`
Thematic structure:
- Topic ranges (segment_start, segment_end)
- Per-topic summaries and terminology
- Global episode summary

### `terminology.yaml`
Multi-sense term definitions:
- Terms with multiple meanings
- Preferred translations per context
- Applicable segments/topics

### `guidelines.md`
Translation style guide loaded as system prompt.

## Configuration

Configuration is now **default + override**:

1. `configs/default.yaml` defines path templates, logging, and model defaults.
2. `configs/<episode>.yaml` only overrides differences—most episodes just set the ID:

```yaml
episode_id: S01-E12

# Optional: override default path or flags when needed
# input:
#   srt: input/S01-E12/custom_file.srt
# options:
#   pretty: true
```

When `srt_to_main_yaml.py` runs, it automatically finds the lone `.srt` file inside `input/<episode>/`. Only specify `input.srt` when multiple subtitle files coexist.

After translations are finalized, export the Chinese subtitles with:

```
PYTHONPATH=. python3 tools/export_srt.py --config configs/<episode>.yaml
```

By default the file lands in `output/<episode>/`.

For long subtitle segments (common in translated content), use the SRT splitter to improve readability:

```bash
python3 tools/split_srt.py \
  --input output/<episode>/<episode>.zh-TW.srt \
  --output output/<episode>/<episode>.zh-TW.split.srt \
  --max-chars 35 \
  --verbose
```

This tool intelligently splits subtitles at punctuation marks and redistributes timecodes proportionally.

### New Episode Checklist

1. Create a folder `input/<episode>/` and place the raw SRT inside.
2. Copy `configs/S01-E12.yaml` to `configs/<episode>.yaml` and update `episode_id`.
3. Review `configs/terminology_template.yaml` 並新增/調整術語，確保 mapper 能找到潛在詞彙。
4. Run the tools in order with `PYTHONPATH=. python3 tools/<...> --config configs/<episode>.yaml`.

Every tool writes output directories automatically (`data/<episode>/...`, `logs/<episode>/...`), so only the input folder needs to exist up front.

## Tools

### Implemented ✅
- **srt_to_main_yaml.py** — Parse SRT with intelligent sentence merging (auto-detects episode SRT)
- **main_yaml_to_json.py** — Export minimal segments for LLM analysis (`--pretty` optional)
- **topics_analysis_driver.py** — Generate topic structure using LLM
- **terminology_mapper.py** — Auto-populate term occurrences from template and topics
- **prepare_topic_drafts.py** — Generate topic-based translation work files (Markdown)
- **backfill_translations.py** — Parse completed drafts and update main.yaml
- **export_srt.py** — Convert translated segments back to SRT format
- **split_srt.py** — Intelligent subtitle splitting for long segments (universal tool)
- **OpenAI / Gemini clients** — Unified client abstraction for providers

### Planned 🚧
- **terminology_classifier.py** — Assign occurrences to the correct sense before translation
- **translation_driver.py** — Orchestrate batch translation (optional automation)
- **qa_checker.py** — Validate translation quality
- **export_markdown.py** — Generate readable reports

## Documentation

- **CLAUDE.md** - Guidance for AI assistants working on this codebase
- **docs/TOOL_SPEC.md** - Detailed tool specifications (Traditional Chinese)
- **docs/FORMAT_SPEC.md** - Data format specifications (Traditional Chinese)
- **docs/WORKFLOW_NOTES.md** - Workflow and design notes (Traditional Chinese)

## Development Status

This project is under active development. Currently:
- ✅ Phase 1: SRT parsing and data structure (complete)
- 🚧 Phase 2: Topic analysis integration (in progress)
- ⏳ Phase 3: Translation pipeline (planned)
- ⏳ Phase 4: QA and export tools (planned)

## License

See project documentation for license information.
