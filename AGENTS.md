# Repository Guidelines

## Project Structure & Module Organization
- `src/` hosts runtime modules; `src/clients/` wraps LLM providers via `base_client`, and shared models live in `src/models.py`.
- `tools/` contains the CLI entry points (`srt_to_main_yaml.py`, `main_yaml_to_json.py`, `topics_analysis_driver.py`) that drive the pipeline.
- `configs/` wires episode YAML across `input/`, `data/`, and `output/`; shared defaults live in `configs/default.yaml`, while per-episode overrides usually just set `episode_id` (and occasionally `input.srt`).
- `input/`, `data/`, and `output/` mirror the workflow; keep `data/<episode>/main.yaml` and `topics.yaml` tidy because other scripts read them directly.
- `docs/` and `prompts/` house workflow specs and prompt templates—edit alongside code that changes payload structures.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` prepares a virtualenv; on Windows use `Scripts\activate`.
- `pip install -r requirements.txt` installs runtime plus pytest dependencies.
- `python tools/srt_to_main_yaml.py --config configs/S01-E12.yaml` parses an SRT into `data/<episode>/main.yaml` with merged segments and auto-detects the lone `.srt` inside `input/<episode>/`.
- `python tools/main_yaml_to_json.py --config configs/S01-E12.yaml` exports JSON for topic LLMs; check `logs/<episode>/` if it stalls.
- `python tools/topics_analysis_driver.py --config configs/S01-E12.yaml` performs topic clustering once API keys are in `.env`.
- 若未啟用虛擬環境，先 `export PYTHONPATH=.` 以確保工具能匯入 `src/` 模組。

## Coding Style & Naming Conventions
Use Python 3 style with 4-space indentation, type hints, and dataclasses for structured records. Favor module docstrings and `logging` over `print`. Functions should read as verbs (`build_topic_payload`), pass file paths as `Path` objects, and keep constants in `UPPER_SNAKE_CASE`. YAML keys stay lowercase with hyphenated phrases for readability.

## Testing Guidelines
Target `pytest` for new coverage; place cases in `tests/` mirroring the source tree (`tests/tools/test_srt_to_main_yaml.py`). Supply fixture data via temporary episode folders or `tmp_path`. Focus on edge parsing (timecodes, speaker hints) and topic assembly validation. Run `pytest` before opening a PR and include relevant `logs/` snippets when failures need context.

## Commit & Pull Request Guidelines
Follow the existing short, descriptive commit style (English or Traditional Chinese) such as `實作新架構第一階段` or `Add topic batching helper`. Group logical units per commit and reference episode ids when relevant. PRs should explain workflow impact, link related configs or prompts, and include manual run notes (`python tools/... --config ...`). Attach screenshots or log excerpts when changing output formatting, and confirm `.env` plus raw subtitle files stay untracked.

## Configuration & API Keys
Duplicate `.env.example` to `.env` and populate provider keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.). Never commit secrets or episode-specific credentials. If you introduce new configurable fields, document them in `README.md` and add sensible defaults in example configs so tools continue to run without surprises.
