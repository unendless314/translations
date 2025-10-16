# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a modular subtitle translation pipeline that processes SRT files through a YAML-based workflow. The system uses LLMs for translation with structured context (topics, terminology, guidelines) to ensure consistent, high-quality subtitle translations.

## Core Data Architecture

The project uses a **three-layer file structure**:
- `input/<episode>/` - Original SRT files
- `data/<episode>/` - Working YAML/Markdown files (main.yaml, topics.json, terminology.yaml, guidelines.md)
- `output/<episode>/` - Exported results (SRT/Markdown/reports)

### Primary Data Files (per episode)

**`data/<episode>/main.yaml`** - The central data file containing:
- All parsed SRT segments with timecodes
- Translation results and status tracking
- Segment-level metadata (topic_id, speaker_group, music tags, etc.)

**`data/<episode>/topics.json`** - Thematic structure:
- Topics with segment ranges (`segment_start`, `segment_end`)
- Per-topic summaries and keywords
- Global episode summary for context

**`data/<episode>/terminology.yaml`** - Multi-sense term definitions:
- Terms can have multiple senses (e.g., "channel" as broadcast vs. spiritual)
- Each sense includes preferred translation, definition, applicable segments/topics
- Used to ensure consistent terminology across translations

**`data/<episode>/guidelines.md`** - Translation style guide:
- Tone and voice requirements (e.g., contemplative, spiritual)
- Special formatting rules (e.g., music tags as 【...】)
- Episode-specific translation instructions
- Loaded as system prompt for translation models

### Configuration Files

`configs/default.yaml` 提供所有共用路徑與模型設定，`configs/<episode>.yaml` 通常只需要：
```yaml
episode_id: S01-E12
# input:
#   srt: input/S01-E12/custom_file.srt  # 若資料夾中有多個 SRT 才需要覆寫
```
腳本會自動於 `input/<episode>/` 中尋找唯一 `.srt` 檔案，輸出與日誌則落在 `data/<episode>/...`、`logs/<episode>/workflow.log`。

## Translation Workflow Concepts

### Batch Translation by Topic
- Process segments grouped by `topic_id` from topics.json
- Each batch includes: global summary, topic summary, relevant terminology, guidelines
- Avoid sending entire YAML to models - extract and format only necessary context

### Context Assembly
For each translation batch:
1. Load topic summary and keywords from `topics.json`
2. Filter terminology entries that match current segments/topics
3. Include translation guidelines from `guidelines.md`
4. Extract source segments from `main.yaml`

### Status Tracking
Each segment has `translation.status`:
- `pending` - Not yet translated
- `in_progress` - Currently being processed
- `completed` - Translation finished
- `needs_review` - Flagged for manual review
- `approved` - Reviewed and approved

### Resume Support
Tools should check `translation.status` to skip already-completed segments, enabling interrupted workflow continuation.

## Key Processing Rules

### SRT Parsing and Segment Merging
When converting SRT to main.yaml:
- **Sentence completeness priority**: MUST merge segments until sentence has terminal punctuation (`.!?…`)
- **Stop merging**: Once sentence is complete, stop if next entry starts with uppercase (new sentence)
- **Safety limit**: Maximum 10 SRT entries per segment to prevent pathological cases
- **Speaker detection**: `>>` prefix indicates speaker change, increment `speaker_group`
- **Music/sound tags**: Preserve `[MUSIC]` tags in `source_text`, let AI translate them
- **Timecode preservation**: Keep original SRT format (`HH:MM:SS,mmm`)
- **Source tracking**: Record original SRT indices in `metadata.source_entries`
- **No redundancy**: `speaker_group` only at top level, not in metadata

### Topics Generation Flow
1. Export `main.yaml` to JSON with segment markers (`segment_id`, `speaker_group`, `source_text`)
2. Feed to large-context LLM (e.g., Gemini 2.5 Pro) using `prompts/topic_analysis_system.txt`
3. Parse LLM output to extract segment ranges, summaries, keywords
4. Generate `topics.json` structure with validation (no gaps, no overlaps, sequential ranges)

### Terminology Mapping
- Pre-scan `main.yaml` to populate `segments`/`topics` arrays in terminology entries
- Only load terms relevant to current translation batch
- Support multi-sense disambiguation based on context

## Tool Design Principles

### Command-Line Interface
All tools should accept:
- `--config configs/<episode>.yaml` as primary configuration
- Optional CLI overrides for specific parameters
- `--force` to overwrite existing outputs
- `--resume` to continue from last checkpoint (where applicable)

### Error Handling
- Log unparseable timecodes but continue processing
- Mark problematic segments with `status: error` or `metadata.truncated: true`
- Never silently fail; provide actionable error messages
- Use non-zero exit codes for failures

### Incremental Writing
- Write results back to `main.yaml` after each batch
- Avoid accumulating large amounts in memory
- Support partial completion and recovery

## Project Architecture

### Directory Structure
```
src/                    # 🆕 Shared modules
├── clients/           # LLM API clients
│   ├── base_client.py      # Abstract base class
│   ├── gemini_client.py    # Gemini (google-genai SDK)
│   ├── openai_client.py    # OpenAI (planned)
│   └── anthropic_client.py # Anthropic (planned)
├── models.py          # Data models (@dataclass)
└── exceptions.py      # Custom exceptions

tools/                 # CLI tool scripts
├── srt_to_main_yaml.py       ✅
├── main_yaml_to_json.py      ✅
├── topics_analysis_driver.py ✅
└── ...                       (planned)
```

### Key Design Decisions
- **Synchronous execution**: Tools run sequentially, no async/await complexity
- **Client abstraction**: Unified interface for multiple LLM providers
- **Data models**: Type-safe @dataclass structures (APIResponse, TokenUsage)
- **Smart retry logic**: Distinguish retryable (timeout, 429) vs non-retryable (401, 400) errors

See `docs/ARCHITECTURE.md` for detailed architectural documentation.

## Development Commands

### Setup
```bash
# Install dependencies (includes google-genai 0.1.0+)
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your API keys:
# - GEMINI_API_KEY (recommended for topic analysis)
# - OPENAI_API_KEY (alternative)
# - ANTHROPIC_API_KEY (alternative)
```

### Run Tools
```bash
# Step 1: Convert SRT to main.yaml
python3 tools/srt_to_main_yaml.py --config configs/S01-E12.yaml [--force] [--verbose]

# Step 2: Export segments to JSON
python3 tools/main_yaml_to_json.py --config configs/S01-E12.yaml [--pretty] [--verbose]

# Step 3: Generate topics.json (requires API key)
python3 tools/topics_analysis_driver.py --config configs/S01-E12.yaml [--dry-run] [--verbose]

# Step 4: Translate (coming soon)
# python3 tools/translation_driver.py --config configs/S01-E12.yaml [--resume]
```

## Implementation Status

### Currently Implemented
**Tools:**
- `tools/srt_to_main_yaml.py` - SRT parser with intelligent sentence merging ✅
- `tools/main_yaml_to_json.py` - Export minimal segments for LLM analysis ✅
- `tools/topics_analysis_driver.py` - LLM-based topic analysis ✅

**Shared Modules:**
- `src/clients/base_client.py` - Abstract LLM client interface ✅
- `src/clients/gemini_client.py` - Gemini API (google-genai SDK 0.1.0+) ✅
- `src/clients/openai_client.py` - OpenAI API (GPT-5, Responses API) ✅
- `src/models.py` - Data models (APIResponse, TokenUsage) ✅
- `src/exceptions.py` - Custom exceptions ✅

**Configuration:**
- `configs/S01-E12.yaml` - Episode config with model settings ✅
- `.env.example` - API key template ✅
- `prompts/topic_analysis_system.txt` - Topic analysis prompt ✅

**Documentation:**
- `docs/ARCHITECTURE.md` - Architectural design document ✅
- `CLAUDE.md` - This file ✅

### Planned Tools (see docs/TOOL_SPEC.md)
1. ~~`main_yaml_to_json.py`~~ - ✅ Completed
2. ~~`topics_analysis_driver.py`~~ - ✅ Completed
3. `terminology_mapper.py` - Produce terminology_candidates.yaml with per-term occurrences
4. `terminology_classifier.py` - Assign occurrences to senses and write terminology.yaml
5. `translation_driver.py` - Orchestrate batch translation with model I/O
6. `qa_checker.py` - Validate translations, flag confidence/consistency issues
7. `export_srt.py` - Convert main.yaml back to SRT format
8. `export_markdown.py` - Generate human-readable translation reports

## Translation Quality Checks

QA tools should validate:
- Terminology consistency across segments
- Translation confidence scores
- Text length ratios (source vs. translation)
- Timecode integrity
- Status completeness (all segments translated)
- Segments with `metadata.truncated: true` should be flagged as `needs_review`

## Important Notes

- **Never modify `source_text`** - translations go in `translation.text` field only
- **Episode ID is the primary key** - all file operations use this identifier
- **YAML block scalars** - use `>` for multiline text to preserve readability
- **Chinese conventions** - music/sound tags use full-width brackets 【】 at sentence start
- **All documentation is in Traditional Chinese** - except this CLAUDE.md file and code comments
- **API Keys Required** - LLM tools need `.env` file with provider API keys (see `.env.example`)
- **Model Configuration** - Each episode config specifies model provider, name, and parameters
