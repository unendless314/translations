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

```bash
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
├── configs/<episode>.yaml    # Episode configuration
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

Edit `configs/<episode>.yaml` to customize:

```yaml
episode_id: S01-E12

# Model for topic analysis
topic_analysis:
  provider: gemini                # gemini, openai, or anthropic
  model: gemini-2.5-pro           # Model identifier
  temperature: 1                  # Creativity (0.0-2.0)
  max_output_tokens: 8192
  timeout: 120
  max_retries: 3
  strict_validation: true         # Fail on validation warnings
  dry_run: false                  # Skip API call for testing

# Model for translation
translation:
  provider: gemini
  model: gemini-2.5-pro
  temperature: 1
  max_output_tokens: 4096
  timeout: 120
  max_retries: 3
  batch_size: 10                  # Segments per batch
  resume: true                    # Skip completed segments
```

## Tools

### Implemented ✅
- **srt_to_main_yaml.py** - Parse SRT with intelligent sentence merging
- **main_yaml_to_json.py** - Export minimal segments for LLM analysis
- **topics_analysis_driver.py** - Generate topic structure using LLM
- **OpenAI client** - Support for GPT-5 models (A/B testing)

### Planned 🚧
- **topics_analysis_driver.py** - Generate topic structure
- **terminology_mapper.py** - Auto-populate term occurrences
- **translation_driver.py** - Orchestrate batch translation
- **qa_checker.py** - Validate translation quality
- **export_srt.py** - Convert back to SRT format
- **export_markdown.py** - Generate readable reports

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
