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

# Optional Step 0: Convert YouTube SBV to SRT (if source is .sbv)
python3 tools/sbv_to_srt.py --input sbv/captions.sbv --output input/S01-E12/source.srt

# Step 1: Convert SRT to structured YAML
python3 tools/srt_to_main_yaml.py --config configs/S01-E12.yaml --verbose

# Step 2: Export segments for topic analysis
python3 tools/main_yaml_to_json.py --config configs/S01-E12.yaml --pretty --verbose

# Step 3: Generate topic structure (requires API key)
python3 tools/topics_analysis_driver.py --config configs/S01-E12.yaml --verbose

# Step 4: Generate terminology candidates
python3 tools/terminology_mapper.py --config configs/S01-E12.yaml --verbose

# Step 4.5: Manually classify terminology (human or AI-assisted)
# Edit data/S01-E12/terminology_candidates.yaml → terminology.yaml
# Assign each occurrence to the appropriate sense based on context

# Step 5: Generate topic-based translation work files
python3 tools/prepare_topic_drafts.py --config configs/S01-E12.yaml --verbose

# Step 6: Translate topic drafts (manual or AI-assisted)
# Edit data/S01-E12/drafts/topic_*.md files
# Fill in JSON fields: {"text": "翻譯內容", "confidence": "high/medium/low", "notes": "備註"}
# Reference files: guidelines.md, terminology.yaml, topics.json

# Step 7: QA - Fix Chinese punctuation (recommended after translation)
python3 tools/fix_chinese_punctuation.py --config configs/S01-E12.yaml --verbose

# Step 8: Backfill completed translations to main.yaml
python3 tools/backfill_translations.py --config configs/S01-E12.yaml --verbose

# Step 9: Export translated SRT subtitles
python3 tools/export_srt.py --config configs/S01-E12.yaml --verbose

# Step 10: Split long subtitle segments (iterative, run 2-3 times for convergence)
python3 tools/split_srt.py \
  -i output/S01-E12/S01-E12.zh-TW.srt \
  -o output/S01-E12/S01-E12.zh-TW.split.srt \
  --max-chars 35 --verbose

# If long segments remain, run again on the output:
# python3 tools/split_srt.py \
#   -i output/S01-E12/S01-E12.zh-TW.split.srt \
#   -o output/S01-E12/S01-E12.zh-TW.split2.srt \
#   --max-chars 35 --verbose
```

## Project Structure

```
├── sbv/                      # Optional: Raw YouTube SBV captions (before conversion)
├── input/<episode>/          # Original SRT files
├── data/<episode>/           # Working data files
│   ├── main.yaml            # Segments + translations + status
│   ├── main_segments.json   # Minimal export for LLM topic analysis
│   ├── topics.json          # Topic structure (segment ranges, summaries)
│   ├── terminology_candidates.yaml  # Auto-generated term occurrences (intermediate)
│   ├── terminology.yaml     # Classified term definitions (manual/AI)
│   ├── guidelines.md        # Translation style guide
│   └── drafts/              # Topic-based translation work files
│       ├── topic_01.md      # Segments 1-50 with empty translation fields
│       ├── topic_02.md      # Segments 51-120 ...
│       └── ...
├── output/<episode>/         # Exported results (SRT, reports)
├── logs/<episode>/           # Tool execution logs
├── configs/
│   ├── default.yaml         # Shared defaults and path templates
│   ├── <episode>.yaml       # Episode-specific overrides (usually just episode_id)
│   └── terminology_template.yaml  # Cross-episode term definitions
├── prompts/                 # LLM system prompts
├── src/                     # Shared Python modules
│   ├── clients/             # LLM API clients (Gemini, OpenAI)
│   ├── models.py            # Data models
│   └── exceptions.py        # Custom exceptions
└── tools/                   # Processing scripts (see below)
```

## Data Files

### `main.yaml`
Central data file containing:
- All parsed SRT segments with timecodes
- Translation results and status tracking (`pending`, `in_progress`, `completed`, `needs_review`, `approved`)
- Segment metadata (topic_id, speaker_group, music tags, etc.)

### `main_segments.json`
Minimal export for LLM topic analysis:
- Segment IDs, speaker groups, source text
- No translation data (reduces token usage)

### `topics.json`
Thematic structure generated by LLM:
- Topic ranges (`segment_start`, `segment_end`)
- Per-topic summaries and keywords
- Global episode summary for context

### `terminology_candidates.yaml` (Intermediate)
Auto-generated by `terminology_mapper.py`:
- All occurrences of terms from `terminology_template.yaml` and `topics.json` keywords
- Lists matching `segment_id`, `sources` (template/topic), and `source_text`
- **Not yet classified by sense** — requires manual/AI review

### `terminology.yaml` (Final)
Multi-sense term definitions after classification:
- Terms with multiple senses (e.g., "channel" as spiritual vs. broadcast)
- Each sense includes: definition, preferred translation, applicable `segments`, `topics`
- Used as reference during translation

### `guidelines.md`
Translation style guide:
- Tone and voice requirements (e.g., contemplative, respectful)
- Special formatting rules
- Episode-specific translation instructions
- Loaded as system prompt for translation models

### `drafts/topic_XX.md` (Translation Work Files)
Topic-based Markdown files for translation:
- Generated by `prepare_topic_drafts.py` from `main.yaml`
- Each file covers one topic with its segment range
- Contains source text with empty JSON translation fields:
  ```json
  {"text": "", "confidence": "", "notes": ""}
  ```
- Translators directly edit these files to fill in translations
- Processed by `backfill_translations.py` to update `main.yaml`

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

### New Episode Checklist

1. **Prepare input files:**
   - If source is YouTube SBV: Place in `sbv/` folder
   - If source is SRT: Create `input/<episode>/` and place SRT inside

2. **Create episode config:**
   - Copy `configs/S01-E12.yaml` to `configs/<episode>.yaml`
   - Update `episode_id` (e.g., `S01-E22`)

3. **Review terminology template:**
   - Open `configs/terminology_template.yaml`
   - Add/adjust terms to ensure mapper can find potential vocabulary

4. **Copy or create base files:**
   - Copy `guidelines.md` from a similar episode to `data/<episode>/guidelines.md`
   - Review and adjust for episode-specific requirements

5. **Run the complete workflow:**
   - Follow steps in "3. Process Subtitles" above
   - Tools automatically create output directories (`data/<episode>/...`, `logs/<episode>/...`)
   - Only the input folder needs to exist upfront

**Note:** The workflow supports resuming from any step if interrupted.

## Tools

### Implemented ✅

**Preprocessing:**
- **sbv_to_srt.py** — Convert YouTube SBV captions to standard SRT format
- **srt_to_main_yaml.py** — Parse SRT with intelligent sentence merging (auto-detects episode SRT)

**Analysis:**
- **main_yaml_to_json.py** — Export minimal segments for LLM topic analysis (`--pretty` optional)
- **topics_analysis_driver.py** — Generate topic structure using large-context LLM (Gemini 3 Pro)
- **terminology_mapper.py** — Auto-populate term occurrences from template and topics → `terminology_candidates.yaml`

**Translation Workflow:**
- **prepare_topic_drafts.py** — Generate topic-based translation work files (`drafts/topic_XX.md`)
- **backfill_translations.py** — Parse completed drafts and update `main.yaml` with translations

**Quality Assurance:**
- **fix_chinese_punctuation.py** — Automatically correct English punctuation (`,` `?` `!`) to Chinese (`，` `？` `！`) in translation fields

**Export:**
- **export_srt.py** — Convert translated segments back to SRT format
- **split_srt.py** — Intelligent subtitle splitting for readability
  - Splits at punctuation marks, redistributes timecodes proportionally
  - **Iterative process:** Each run splits once per segment; long segments need 2-3 runs for convergence
  - Reports remaining long segments and suggests re-running if needed

**Infrastructure:**
- **src/clients/** — Unified LLM client abstraction (Gemini, OpenAI with Responses API)
- **src/models.py** — Shared data models (APIResponse, TokenUsage, etc.)

### Planned 🚧
- **translation_driver.py** — Orchestrate batch LLM translation (optional automation for topic drafts)
- **qa_checker.py** — Unified QA tool runner (will integrate multiple specialized QA tools)
- **export_markdown.py** — Generate human-readable translation reports

## Documentation

- **CLAUDE.md** - Guidance for AI assistants working on this codebase
- **docs/TOOL_SPEC.md** - Detailed tool specifications (Traditional Chinese)
- **docs/FORMAT_SPEC.md** - Data format specifications (Traditional Chinese)
- **docs/WORKFLOW_NOTES.md** - Workflow and design notes (Traditional Chinese)

## Development Status

This project is under active development. Current status:
- ✅ **Phase 1: Data structure and parsing** (complete)
  - SRT/SBV parsing with intelligent sentence merging
  - YAML-based data architecture
  - Episode configuration system

- ✅ **Phase 2: LLM-powered analysis** (complete)
  - Topic analysis with large-context models (Gemini 3 Pro)
  - Automated terminology candidate generation
  - Multi-sense terminology classification workflow

- ✅ **Phase 3: Translation workflow** (complete)
  - Topic-based translation work files (Markdown drafts)
  - Manual/AI-assisted translation process
  - Translation backfill and status tracking
  - Resume support for interrupted workflows

- ✅ **Phase 4: Quality assurance** (in progress)
  - Chinese punctuation correction tool (complete)
  - Additional QA tools planned (terminology consistency, length ratios, etc.)

- ✅ **Phase 5: Export and post-processing** (complete)
  - SRT export with speaker hints and timecode preservation
  - Iterative subtitle splitting for readability

**Currently functional:** End-to-end translation pipeline from raw subtitles to final SRT output.

**Active development areas:**
- Additional QA automation tools
- Optional LLM-driven batch translation
- Translation quality reporting

## License

See project documentation for license information.
