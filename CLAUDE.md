# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a modular subtitle translation pipeline that processes SRT files through a YAML-based workflow. The system uses LLMs for translation with structured context (topics, terminology, guidelines) to ensure consistent, high-quality subtitle translations.

## Core Data Architecture

The project uses a **three-layer file structure**:
- `input/<episode>/` - Original SRT files
- `data/<episode>/` - Working YAML/Markdown files (main.yaml, topics.yaml, terminology.yaml, guidelines.md)
- `output/<episode>/` - Exported results (SRT/Markdown/reports)

### Primary Data Files (per episode)

**`data/<episode>/main.yaml`** - The central data file containing:
- All parsed SRT segments with timecodes
- Translation results and status tracking
- Segment-level metadata (topic_id, speaker_group, music tags, etc.)

**`data/<episode>/topics.yaml`** - Thematic structure:
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

`configs/<episode>.yaml` - Episode configuration linking all file paths and processing parameters:
```yaml
episode_id: S01-E12
input:
  srt: input/S01-E12/ENG-S01-E12Bridget Nielson_SRT_English.srt
output:
  main_yaml: data/S01-E12/main.yaml
preprocessing:
  min_gap_ms: 800
  max_sentence_merge: 3
  max_length: 280
```

## Translation Workflow Concepts

### Batch Translation by Topic
- Process segments grouped by `topic_id` from topics.yaml
- Each batch includes: global summary, topic summary, relevant terminology, guidelines
- Avoid sending entire YAML to models - extract and format only necessary context

### Context Assembly
For each translation batch:
1. Load topic summary and keywords from `topics.yaml`
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
1. Export `main.yaml` to plaintext with segment markers (`[SEG 021] text...`)
2. Feed to large-context LLM (e.g., Gemini 2.5 Pro) for hierarchical topic analysis
3. Parse LLM output to extract segment ranges, summaries, keywords
4. Generate `topics.yaml` structure

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
- `--resume` to continue from last checkpoint

### Error Handling
- Log unparseable timecodes but continue processing
- Mark problematic segments with `status: error` or `metadata.is_empty: true`
- Never silently fail; provide actionable error messages

### Incremental Writing
- Write results back to `main.yaml` after each batch
- Avoid accumulating large amounts in memory
- Support partial completion and recovery

## Planned Tools

Tools to be implemented (per docs/TOOL_SPEC.md and docs/WORKFLOW_NOTES.md):

1. `srt_to_main_yaml.py` - Parse SRT, merge segments, generate main.yaml
2. `main_yaml_to_plaintext.py` - Export for topic analysis
3. `topics_markdown_to_yaml.py` - Convert LLM topic analysis to YAML
4. `terminology_mapper.py` - Auto-populate term occurrence indices
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

## Important Notes

- **Never modify `source_text`** - translations go in `translation.text` field only
- **Episode ID is the primary key** - all file operations use this identifier
- **YAML block scalars** - use `>` for multiline text to preserve readability
- **Chinese conventions** - music/sound tags use full-width brackets 【】 at sentence start
