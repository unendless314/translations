#!/usr/bin/env python3
"""
Terminology mapper
------------------

Reads the shared terminology template plus episode data (main.yaml + topics.json when available)
and produces terminology_candidates.yaml with every segment where a term appears.
This file is reviewed or classified before producing the final terminology.yaml.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

import yaml

from src.config_loader import load_config


@dataclass
class SegmentInfo:
    segment_id: int
    source_text: str

    @property
    def normalized_text(self) -> str:
        return self.source_text.lower()


@dataclass
class TermOccurrence:
    segment_id: int
    sources: Set[str]
    source_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "segment_id": self.segment_id,
            "sources": sorted(self.sources),
        }
        if self.source_text is not None:
            payload["source_text"] = self.source_text
        return payload


class TermAccumulator:
    def __init__(self, display_name: str):
        self.display_name = display_name
        self.occurrences: "OrderedDict[int, TermOccurrence]" = OrderedDict()

    def add(self, occurrence: TermOccurrence, include_text: bool) -> None:
        existing = self.occurrences.get(occurrence.segment_id)
        if existing:
            existing.sources.update(occurrence.sources)
            if include_text and occurrence.source_text:
                if not existing.source_text:
                    existing.source_text = occurrence.source_text
        else:
            self.occurrences[occurrence.segment_id] = occurrence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term": self.display_name,
            "occurrences": [occ.to_dict() for occ in self.occurrences.values()],
        }


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at top level in {path}")

    return data


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON file {path}: {exc}") from exc


def canonicalize_term(term: str) -> str:
    return term.strip().lower()


def load_main_segments(path: Path) -> List[SegmentInfo]:
    data = load_yaml(path)

    if "segments" not in data or not isinstance(data["segments"], list):
        raise ValueError(f"main.yaml missing 'segments' list: {path}")

    segments: List[SegmentInfo] = []
    for idx, raw in enumerate(data["segments"]):
        if not isinstance(raw, dict):
            logging.warning("Skipping segment at index %s: not a mapping", idx)
            continue

        segment_id = raw.get("segment_id")
        source_text = raw.get("source_text")

        if segment_id is None or source_text is None:
            logging.warning(
                "Skipping segment at index %s: missing segment_id or source_text",
                idx,
            )
            continue

        segments.append(
            SegmentInfo(
                segment_id=int(segment_id),
                source_text=str(source_text),
            )
        )

    if not segments:
        logging.warning("No valid segments loaded from %s", path)

    return segments


def gather_patterns(term_entry: Dict[str, Any]) -> List[re.Pattern]:
    base_terms: Set[str] = set()

    term_text = term_entry.get("term")
    if isinstance(term_text, str) and term_text.strip():
        base_terms.add(term_text.strip())

    aliases = term_entry.get("aliases")
    if isinstance(aliases, str):
        base_terms.add(aliases.strip())
    elif isinstance(aliases, Sequence):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                base_terms.add(alias.strip())

    senses = term_entry.get("senses") or []
    if isinstance(senses, list):
        for sense in senses:
            if not isinstance(sense, dict):
                continue
            sense_aliases = sense.get("aliases")
            if isinstance(sense_aliases, str):
                base_terms.add(sense_aliases.strip())
            elif isinstance(sense_aliases, Sequence):
                for alias in sense_aliases:
                    if isinstance(alias, str) and alias.strip():
                        base_terms.add(alias.strip())

    patterns: List[re.Pattern] = []
    for term in sorted(base_terms):
        escaped = re.escape(term)
        # For single dictionary words use word boundaries to avoid partial matches.
        if re.fullmatch(r"[A-Za-z]+", term):
            pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
        else:
            pattern = re.compile(escaped, re.IGNORECASE)
        patterns.append(pattern)

    return patterns


def find_occurrences(
    term_entry: Dict[str, Any],
    segments: List[SegmentInfo],
    include_text: bool,
    source_label: str,
) -> List[TermOccurrence]:
    patterns = gather_patterns(term_entry)
    if not patterns:
        return []

    occurrences: List[TermOccurrence] = []
    seen_segments: Set[int] = set()

    for segment in segments:
        match_found = False
        for pattern in patterns:
            if pattern.search(segment.normalized_text):
                match_found = True
                break
        if not match_found or segment.segment_id in seen_segments:
            continue

        occurrence = TermOccurrence(
            segment_id=segment.segment_id,
            sources={source_label},
            source_text=segment.source_text if include_text else None,
        )
        occurrences.append(occurrence)
        seen_segments.add(segment.segment_id)

    return occurrences


def build_candidates_document(
    episode_id: str,
    template: Dict[str, Any],
    segments: List[SegmentInfo],
    topics_json: Optional[Dict[str, Any]],
    include_text: bool,
) -> Dict[str, Any]:
    terms = template.get("terms")
    if not isinstance(terms, list):
        raise ValueError("Terminology template missing 'terms' list")

    # Prepare segment lookups for topic ranges.
    segment_index: Dict[int, SegmentInfo] = {seg.segment_id: seg for seg in segments}

    term_store: "OrderedDict[str, TermAccumulator]" = OrderedDict()
    term_order: List[str] = []

    canonical_to_display: Dict[str, str] = {}

    def ensure_bucket(display_name: str) -> TermAccumulator:
        canonical = canonicalize_term(display_name)
        actual_name = canonical_to_display.get(canonical, display_name)
        if canonical not in canonical_to_display:
            canonical_to_display[canonical] = display_name
            term_order.append(canonical)
        else:
            display_name = actual_name

        bucket = term_store.get(canonical)
        if not bucket:
            bucket = TermAccumulator(display_name)
            term_store[canonical] = bucket
        return bucket

    # Pass 1: template-driven matches
    template_entry_count = 0
    for term_entry in terms:
        if not isinstance(term_entry, dict):
            continue

        term_name = term_entry.get("term")
        if not isinstance(term_name, str) or not term_name.strip():
            logging.debug("Skipping term entry without valid 'term': %s", term_entry)
            continue

        template_entry_count += 1
        occurrences = find_occurrences(term_entry, segments, include_text, source_label="template")
        if not occurrences:
            continue

        bucket = ensure_bucket(term_name)
        for occ in occurrences:
            bucket.add(occ, include_text)

    # Pass 2: topics.json terminology suggestions
    topic_term_total = 0
    topic_matches = 0
    if topics_json:
        topics_list = topics_json.get("topics")
        if isinstance(topics_list, list):
            for topic in topics_list:
                if not isinstance(topic, dict):
                    continue
                topic_id = str(topic.get("topic_id", "")).strip() or None
                try:
                    seg_start = int(topic.get("segment_start"))
                    seg_end = int(topic.get("segment_end"))
                except (TypeError, ValueError):
                    continue

                terminology = topic.get("terminology")
                if not isinstance(terminology, list):
                    continue

                topic_segments = [seg for seg in segments if seg_start <= seg.segment_id <= seg_end]
                for raw_term in terminology:
                    if not isinstance(raw_term, str):
                        continue
                    term_name = raw_term.strip()
                    if not term_name:
                        continue
                    topic_term_total += 1

                    canonical = canonicalize_term(term_name)
                    existing_display = canonical_to_display.get(canonical)
                    display_name = existing_display or term_name
                    bucket = ensure_bucket(display_name)

                    minimal_entry = {"term": term_name}
                    occurrences = find_occurrences(
                        minimal_entry,
                        topic_segments,
                        include_text,
                        source_label="topic",
                    )

                    if not occurrences:
                        continue

                    topic_matches += 1
                    for occ in occurrences:
                        bucket.add(occ, include_text)

    # Build final list respecting insertion order
    output_terms: List[Dict[str, Any]] = []
    for canonical in term_order:
        bucket = term_store.get(canonical)
        if not bucket:
            continue
        term_dict = bucket.to_dict()
        if term_dict["occurrences"]:
            output_terms.append(term_dict)

    logging.info(
        "Collected %s terms (%s from template entries, %s topic suggestions processed, %s with matches)",
        len(output_terms),
        template_entry_count,
        topic_term_total,
        topic_matches,
    )

    return {
        "episode_id": episode_id,
        "terms": output_terms,
    }


def write_yaml(data: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            data,
            handle,
            sort_keys=False,
            allow_unicode=True,
        )
    logging.info("Wrote terminology candidates to %s", path)


def resolve_main_path(config: Dict[str, Any]) -> Path:
    input_section = config.get("input") or {}
    output_section = config.get("output") or {}

    main_override = input_section.get("main_yaml")
    if main_override:
        return Path(main_override)

    main_output = output_section.get("main_yaml")
    if main_output:
        return Path(main_output)

    raise ValueError("Unable to determine path to main.yaml from config")


def resolve_topics_json_path(config: Dict[str, Any]) -> Optional[Path]:
    output_section = config.get("output") or {}
    path = output_section.get("topics_json")
    if path:
        return Path(path)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate terminology_candidates.yaml from template and episode data"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration YAML (default: configs/<episode>.yaml via episode_id)",
    )
    parser.add_argument(
        "--episode",
        type=str,
        help="Episode ID (used to locate configs/<episode>.yaml when --config omitted)",
    )
    parser.add_argument(
        "--template",
        type=Path,
        help="Override terminology template path",
    )
    parser.add_argument(
        "--main",
        type=Path,
        help="Override path to main.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Override output path for terminology_candidates.yaml",
    )
    parser.add_argument(
        "--topics-json",
        type=Path,
        help="Override path to topics.json (optional)",
    )
    parser.add_argument(
        "--omit-text",
        action="store_true",
        help="Do not include source_text in occurrences (default includes text)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run mapping and print stats without writing output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    try:
        config = load_config(config_path=args.config, episode=args.episode)
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to load configuration: %s", exc)
        sys.exit(1)

    episode_id = config.get("episode_id")
    if not episode_id:
        logging.error("Configuration missing episode_id")
        sys.exit(1)

    terminology_cfg = config.get("terminology") or {}

    template_path = args.template or Path(terminology_cfg.get("template", ""))
    if not template_path:
        logging.error("Terminology template path not specified in config or CLI")
        sys.exit(1)

    main_path = args.main or resolve_main_path(config)
    output_path = args.output or Path(terminology_cfg.get("candidates", ""))
    if not output_path:
        logging.error("Terminology candidates output path not specified in config or CLI")
        sys.exit(1)

    topics_json_path = args.topics_json or resolve_topics_json_path(config)
    topics_json = None
    if topics_json_path and topics_json_path.exists():
        try:
            topics_json = load_json(topics_json_path)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to load topics.json (%s): %s", topics_json_path, exc)
    elif topics_json_path:
        logging.info("topics.json not found at %s; continuing without topic hints", topics_json_path)

    include_text = not args.omit_text

    logging.info("Episode: %s", episode_id)
    logging.info("Template: %s", template_path)
    logging.info("main.yaml: %s", main_path)
    if topics_json_path:
        logging.info("topics.json: %s", topics_json_path)
    logging.info("Output: %s", output_path if not args.dry_run else "(dry-run)")

    try:
        template = load_yaml(template_path)
        segments = load_main_segments(main_path)
        document = build_candidates_document(
            episode_id=episode_id,
            template=template,
            segments=segments,
            topics_json=topics_json,
            include_text=include_text,
        )
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to generate terminology candidates: %s", exc)
        sys.exit(1)

    if args.dry_run:
        term_count = len(document.get("terms", []))
        segment_total = sum(len(term["occurrences"]) for term in document.get("terms", []))
        logging.info(
            "Dry-run: %s terms matched across %s segment occurrences",
            term_count,
            segment_total,
        )
        return

    try:
        write_yaml(document, output_path)
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to write terminology candidates: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
