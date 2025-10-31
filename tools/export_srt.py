#!/usr/bin/env python3
"""
Export translated SRT subtitles from main.yaml.

This tool reads `data/<episode>/main.yaml`, extracts translated text, and writes
an SRT file that can replace the original subtitles.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config_loader import load_config
from src.main_yaml import MainYAMLValidator


def setup_logging(verbose: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def extract_translation(segment: Dict[str, Any]) -> Optional[str]:
    """Return cleaned translation text if available."""
    translation = segment.get("translation")
    if not isinstance(translation, dict):
        return None

    text = translation.get("text")
    if text is None:
        return None

    cleaned = str(text).replace("\r\n", "\n").strip()
    return cleaned or None


def prepend_speaker_hint(text: str, hint: Optional[str]) -> str:
    """Prepend `>>` style speaker hints if requested."""
    if not hint:
        return text

    normalized_hint = str(hint).strip()
    if not normalized_hint:
        return text

    lines = text.splitlines() or [""]
    first_line = lines[0].lstrip()

    if first_line.startswith(normalized_hint):
        return text

    prefix = normalized_hint if not first_line else f"{normalized_hint} {first_line}"
    lines[0] = prefix
    return "\n".join(lines)


def build_srt_entries(
    segments: List[Dict[str, Any]],
    *,
    include_hints: bool,
    fail_on_missing: bool,
) -> List[str]:
    """Convert segments into SRT blocks."""
    entries: List[str] = []
    missing_segments: List[int] = []

    for segment in segments:
        segment_id = segment.get("segment_id")
        timecode = segment.get("timecode", {})
        start = timecode.get("start")
        end = timecode.get("end")

        if segment_id is None or not start or not end:
            logging.debug("Skipping malformed segment: %s", segment)
            continue

        translation_text = extract_translation(segment)
        if not translation_text:
            missing_segments.append(segment_id)

            if fail_on_missing:
                raise ValueError(f"Segment {segment_id} missing translation text")

            translation_text = str(segment.get("source_text", "")).strip()

        if include_hints:
            hint = segment.get("metadata", {}).get("speaker_hint")
            translation_text = prepend_speaker_hint(translation_text, hint)

        block = "\n".join(
            [
                str(segment_id),
                f"{start} --> {end}",
                translation_text,
            ]
        )
        entries.append(block)

    if missing_segments:
        logging.warning(
            "Missing translations for %d segment(s): %s",
            len(missing_segments),
            ", ".join(str(seg_id) for seg_id in missing_segments),
        )

    return entries


def determine_output_path(
    *,
    args: argparse.Namespace,
    config: Dict[str, Any],
    main_data: Dict[str, Any],
    main_path: Path,
) -> Path:
    """Resolve desired SRT output path based on CLI args and config."""
    if args.output:
        return args.output

    if "output" in config and isinstance(config["output"], dict) and "srt" in config["output"]:
        return Path(config["output"]["srt"])

    # Fallback alongside main.yaml
    return main_path.with_suffix(".srt")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export translated subtitles from main.yaml into an SRT file."
    )
    parser.add_argument("--config", type=Path, help="Path to YAML configuration file")
    parser.add_argument(
        "--main",
        type=Path,
        help="Path to main.yaml (overrides config)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Destination SRT path (overrides config)",
    )
    parser.add_argument(
        "--include-speaker-hints",
        dest="include_hints",
        action="store_true",
        help="Prepend speaker hints like '>>' when available (default)",
    )
    parser.add_argument(
        "--no-speaker-hints",
        dest="include_hints",
        action="store_false",
        help="Do not prepend speaker hints",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Fail if any segment lacks a translation (default falls back to source_text)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.set_defaults(include_hints=True)
    args = parser.parse_args()

    setup_logging(args.verbose)

    config: Dict[str, Any] = {}
    if args.config:
        try:
            config = load_config(args.config)
            logging.info("Loaded config for episode %s", config.get("episode_id"))
        except Exception as exc:
            logging.error("Error loading config: %s", exc)
            sys.exit(1)

    main_path: Optional[Path] = args.main
    if not main_path:
        config_input = config.get("input", {})
        if isinstance(config_input, dict) and "main_yaml" in config_input:
            main_path = Path(config_input["main_yaml"])
    if not main_path:
        config_output = config.get("output", {})
        if isinstance(config_output, dict) and "main_yaml" in config_output:
            main_path = Path(config_output["main_yaml"])

    if not main_path:
        logging.error("No main.yaml provided. Use --main or --config with input.main_yaml")
        sys.exit(1)

    try:
        logging.info("Loading main.yaml from %s", main_path)
        main_data = MainYAMLValidator.load(main_path)

        warnings = MainYAMLValidator.validate_segments(main_data.get("segments", []))
        if warnings:
            logging.warning("Validation warnings:")
            for message in warnings:
                logging.warning("  - %s", message)

        output_path = determine_output_path(
            args=args,
            config=config,
            main_data=main_data,
            main_path=main_path,
        )

        if output_path.exists() and output_path.samefile(main_path):
            logging.error(
                "Output path %s matches main.yaml; please choose a different destination.",
                output_path,
            )
            sys.exit(1)

        source_file = main_data.get("source_file")
        if source_file and Path(source_file).resolve() == output_path.resolve():
            logging.error(
                "Output path %s resolves to the original subtitle file; choose a different destination.",
                output_path,
            )
            sys.exit(1)

        entries = build_srt_entries(
            main_data.get("segments", []),
            include_hints=args.include_hints,
            fail_on_missing=args.fail_on_missing,
        )

        if not entries:
            logging.error("No segments exported; aborting.")
            sys.exit(1)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        srt_content = "\n\n".join(entries) + "\n"
        output_path.write_text(srt_content, encoding="utf-8")

        logging.info("Wrote %d subtitles to %s", len(entries), output_path)
        logging.info("Done!")

    except FileNotFoundError as exc:
        logging.error("File not found: %s", exc)
        sys.exit(1)
    except ValueError as exc:
        logging.error("Validation error: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logging.error("Unexpected error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
