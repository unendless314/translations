#!/usr/bin/env python3
"""
Display topic start/end timestamps for each episode so playlist cards can
align with YouTube chapters.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show each topic title with associated SRT timestamps."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Base directory that contains per-episode folders.",
    )
    parser.add_argument(
        "--episode",
        "-e",
        help="Limit the output to a single episode (e.g. S01-E01).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Include a topic summary line (default: omit).",
    )
    return parser.parse_args()


def format_timecode(timestr: str) -> str:
    """Return a normalized HH:MM:SS string from the SRT-style timecode."""
    hours, minutes, seconds_ms = timestr.split(":")
    seconds, _ = seconds_ms.split(",")
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"


def load_topics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_segments(path: Path) -> list[dict]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document.get("segments", [])


def iter_episode_paths(data_dir: Path, episode: str | None) -> Iterable[Path]:
    if episode:
        yield data_dir / episode
        return
    for child in sorted(data_dir.iterdir()):
        if child.is_dir():
            yield child


def display_episode_topics(episode_dir: Path, show_summary: bool) -> None:
    topics_path = episode_dir / "topics.json"
    main_path = episode_dir / "main.yaml"
    if not topics_path.exists():
        return
    if not main_path.exists():
        return

    topics_data = load_topics(topics_path)
    segments = load_segments(main_path)
    topic_list = topics_data.get("topics", [])
    if not topic_list:
        return

    episode_id = topics_data.get("episode_id") or topic_list[0].get("episode_id") or episode_dir.name
    print(f"\nEpisode {episode_id} (提議 {len(topic_list)} 張卡片)：")

    for topic in topic_list:
        start_index = topic.get("segment_start", 1) - 1
        end_index = topic.get("segment_end", 1) - 1

        if not (0 <= start_index < len(segments)) or not (0 <= end_index < len(segments)):
            continue

        start_tc = segments[start_index]["timecode"]["start"]
        end_tc = segments[end_index]["timecode"]["end"]
        start_display = format_timecode(start_tc)
        end_display = format_timecode(end_tc)

        print(f"- {start_display} ~ {end_display} | {topic['title']}")
        if show_summary:
            summary = topic.get("summary")
            if summary:
                print(f"  └ 摘要：{summary}")


def main() -> None:
    args = parse_args()
    for episode_path in iter_episode_paths(args.data_dir, args.episode):
        display_episode_topics(episode_path, args.summary)


if __name__ == "__main__":
    main()
