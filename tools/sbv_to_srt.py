#!/usr/bin/env python3
"""
Utility script that converts YouTube-style SBV caption files into standard SRT
subtitles so they can enter the existing SRT → YAML translation pipeline.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List, Tuple


Segment = Tuple[str, str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert an SBV caption file into a standard SRT file."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="Path to the source .sbv file (e.g., sbv/captions.sbv)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination .srt file. Defaults to the input path with a .srt suffix.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="Text encoding for reading the SBV file. Defaults to utf-8-sig.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def parse_timestamp(value: str) -> str:
    """
    Convert an SBV timestamp (e.g., 0:00:16.599) into SRT format HH:MM:SS,mmm.
    """
    value = value.strip()
    if not value:
        raise ValueError("Empty timestamp value")

    parts = value.split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid SBV timestamp: {value}")

    seconds_part = parts[-1]
    minutes_part = parts[-2]
    hours_part = parts[:-2]

    try:
        minutes = int(minutes_part)
    except ValueError as exc:
        raise ValueError(f"Invalid minutes in timestamp: {value}") from exc

    if hours_part:
        try:
            hours = int(hours_part[-1])
        except ValueError as exc:
            raise ValueError(f"Invalid hours in timestamp: {value}") from exc
    else:
        hours = 0

    if "." in seconds_part:
        seconds_str, millis_str = seconds_part.split(".", 1)
    else:
        seconds_str, millis_str = seconds_part, "0"

    try:
        seconds = int(seconds_str)
    except ValueError as exc:
        raise ValueError(f"Invalid seconds in timestamp: {value}") from exc

    # Normalize milliseconds to exactly three digits (pad or truncate)
    millis_str = (millis_str + "000")[:3]
    try:
        millis = int(millis_str)
    except ValueError as exc:
        raise ValueError(f"Invalid milliseconds in timestamp: {value}") from exc

    total_millis = (
        ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis
    )
    hours = total_millis // 3_600_000
    remainder = total_millis % 3_600_000
    minutes = remainder // 60_000
    seconds = (remainder % 60_000) // 1_000
    millis = remainder % 1_000

    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def parse_sbv(input_path: Path, encoding: str) -> List[Tuple[str, List[str]]]:
    """
    Parse the SBV file into a list of (time_line, text_lines) tuples.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"SBV file not found: {input_path}")

    logging.info("Reading SBV file from %s", input_path)

    with input_path.open("r", encoding=encoding) as fh:
        raw_lines = fh.readlines()

    blocks: List[Tuple[str, List[str]]] = []
    current_time = None
    current_lines: List[str] = []

    for raw_line in raw_lines:
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            if current_time is not None:
                blocks.append((current_time, current_lines))
                current_time = None
                current_lines = []
            continue

        if current_time is None:
            current_time = line.strip()
            continue

        current_lines.append(line)

    if current_time is not None:
        blocks.append((current_time, current_lines))

    logging.info("Detected %d caption blocks", len(blocks))
    return blocks


def convert_blocks(blocks: List[Tuple[str, List[str]]]) -> List[Segment]:
    segments: List[Segment] = []

    for idx, (time_line, text_lines) in enumerate(blocks, start=1):
        try:
            start_raw, end_raw = [part.strip() for part in time_line.split(",", 1)]
        except ValueError as exc:
            raise ValueError(
                f"Invalid SBV time line (segment {idx}): '{time_line}'"
            ) from exc

        start = parse_timestamp(start_raw)
        end = parse_timestamp(end_raw)
        text = "\n".join(text_lines).strip()
        segments.append((start, end, text))

    return segments


def write_srt(output_path: Path, segments: List[Segment], force: bool) -> None:
    if output_path.exists() and not force:
        raise FileExistsError(
            f"Output file {output_path} already exists. Use --force to overwrite."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info("Writing SRT file to %s", output_path)

    with output_path.open("w", encoding="utf-8") as fh:
        for idx, (start, end, text) in enumerate(segments, start=1):
            fh.write(f"{idx}\n")
            fh.write(f"{start} --> {end}\n")
            if text:
                fh.write(f"{text}\n")
            fh.write("\n")


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    input_path: Path = args.input
    output_path: Path = args.output or input_path.with_suffix(".srt")

    blocks = parse_sbv(input_path, args.encoding)
    if not blocks:
        logging.warning("No caption blocks found in %s", input_path)

    segments = convert_blocks(blocks)
    write_srt(output_path, segments, args.force)
    logging.info("Conversion finished: %d segments written.", len(segments))


if __name__ == "__main__":
    main()
