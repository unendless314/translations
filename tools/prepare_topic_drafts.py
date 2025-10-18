#!/usr/bin/env python3
"""
Topic Drafts Generator
Generates Markdown translation work files from topics.json and main_segments.json
"""

import json
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config_loader import load_config


class TopicsLoader:
    """Load and validate topics.json"""

    @staticmethod
    def load(topics_path: Path) -> Dict[str, Any]:
        """Load topics.json and validate structure"""
        if not topics_path.exists():
            raise FileNotFoundError(f"Topics file not found: {topics_path}")

        try:
            with topics_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse topics.json: {e}")

        # Validate required fields
        if 'topics' not in data:
            raise ValueError("topics.json missing required field: topics")

        if not isinstance(data['topics'], list):
            raise ValueError("topics.json 'topics' must be a list")

        if len(data['topics']) == 0:
            logging.warning("topics.json contains zero topics")

        # Validate each topic
        for idx, topic in enumerate(data['topics']):
            required_fields = ['topic_id', 'segment_start', 'segment_end']
            for field in required_fields:
                if field not in topic:
                    raise ValueError(f"Topic at index {idx} missing required field: {field}")

            # Validate segment range
            if topic['segment_start'] > topic['segment_end']:
                raise ValueError(
                    f"Topic {topic['topic_id']}: segment_start ({topic['segment_start']}) "
                    f"> segment_end ({topic['segment_end']})"
                )

        return data

    @staticmethod
    def validate_coverage(topics: List[Dict[str, Any]], total_segments: int) -> List[str]:
        """Check if topics cover all segments, return warnings for gaps"""
        warnings = []
        covered = set()

        for topic in topics:
            start = topic['segment_start']
            end = topic['segment_end']
            for seg_id in range(start, end + 1):
                if seg_id in covered:
                    warnings.append(
                        f"Segment {seg_id} covered by multiple topics "
                        f"(including {topic['topic_id']})"
                    )
                covered.add(seg_id)

        # Check for gaps
        expected = set(range(1, total_segments + 1))
        missing = expected - covered
        if missing:
            warnings.append(f"Segments not covered by any topic: {sorted(missing)}")

        return warnings


class SegmentsLoader:
    """Load and validate main_segments.json"""

    @staticmethod
    def load(segments_path: Path) -> List[Dict[str, Any]]:
        """Load main_segments.json and validate structure"""
        if not segments_path.exists():
            raise FileNotFoundError(f"Segments file not found: {segments_path}")

        try:
            with segments_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse main_segments.json: {e}")

        if not isinstance(data, list):
            raise ValueError("main_segments.json must be a JSON array")

        if len(data) == 0:
            logging.warning("main_segments.json contains zero segments")

        # Validate each segment
        for idx, segment in enumerate(data):
            required_fields = ['segment_id', 'speaker_group', 'source_text']
            for field in required_fields:
                if field not in segment:
                    raise ValueError(f"Segment at index {idx} missing required field: {field}")

        return data


class MarkdownGenerator:
    """Generate Markdown translation work files"""

    def __init__(self, segments: List[Dict[str, Any]]):
        """Initialize with segments data"""
        # Build segment lookup dictionary
        self.segments_dict = {seg['segment_id']: seg for seg in segments}

    def generate_topic_markdown(self, topic: Dict[str, Any]) -> str:
        """Generate Markdown content for a single topic

        Args:
            topic: Topic dictionary with segment_start, segment_end, etc.

        Returns:
            Markdown string with Speaker Group headers and translation templates
        """
        lines = []
        current_speaker_group = None

        for seg_id in range(topic['segment_start'], topic['segment_end'] + 1):
            if seg_id not in self.segments_dict:
                logging.warning(f"Segment {seg_id} not found in main_segments.json, skipping")
                continue

            segment = self.segments_dict[seg_id]
            speaker_group = segment['speaker_group']
            source_text = segment['source_text']

            # Insert Speaker Group header if changed
            if speaker_group != current_speaker_group:
                if lines:  # Add blank line before new speaker group (except first)
                    lines.append("")
                lines.append(f"## Speaker Group {speaker_group}")
                lines.append("")
                current_speaker_group = speaker_group

            # Add segment content (two lines)
            lines.append(f"{seg_id}. {source_text}")
            lines.append('→ {"text": "", "confidence": "", "notes": ""}')
            lines.append("")  # Blank line between segments

        return "\n".join(lines)


def setup_logging(level: str = "INFO"):
    """Configure logging"""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='[%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Generate Markdown translation drafts from topics and segments"
    )
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Path to episode config file (e.g., configs/S01-E12.yaml)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing Markdown files'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--topic',
        type=str,
        help='Generate only specific topic (e.g., topic_01)'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    try:
        # Load configuration
        logging.info(f"Loading configuration from {args.config}")
        config = load_config(Path(args.config))

        # Get paths from config
        topics_path = Path(config['output']['topics_json'])
        segments_path = Path(config['output']['json'])
        drafts_dir = Path(config['output']['drafts_dir'])

        # Load data
        logging.info(f"Loading topics from {topics_path}")
        topics_data = TopicsLoader.load(topics_path)

        logging.info(f"Loading segments from {segments_path}")
        segments = SegmentsLoader.load(segments_path)

        # Validate coverage
        warnings = TopicsLoader.validate_coverage(topics_data['topics'], len(segments))
        for warning in warnings:
            logging.warning(warning)

        # Create drafts directory
        drafts_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Output directory: {drafts_dir}")

        # Filter topics if --topic specified
        topics_to_process = topics_data['topics']
        if args.topic:
            topics_to_process = [t for t in topics_to_process if t['topic_id'] == args.topic]
            if not topics_to_process:
                logging.error(f"Topic '{args.topic}' not found in topics.json")
                sys.exit(1)
            logging.info(f"Processing only topic: {args.topic}")

        # Generate Markdown files
        generator = MarkdownGenerator(segments)
        generated_count = 0
        skipped_count = 0

        for topic in topics_to_process:
            topic_id = topic['topic_id']
            output_path = drafts_dir / f"{topic_id}.md"

            # Check if file exists
            if output_path.exists() and not args.force:
                logging.warning(f"Skipping {topic_id}.md (already exists, use --force to overwrite)")
                skipped_count += 1
                continue

            # Generate content
            logging.info(
                f"Generating {topic_id}.md (segments {topic['segment_start']}-{topic['segment_end']})"
            )
            markdown_content = generator.generate_topic_markdown(topic)

            # Write to file
            output_path.write_text(markdown_content, encoding='utf-8')
            generated_count += 1

        # Summary
        logging.info(f"✓ Generated {generated_count} files, skipped {skipped_count}")

    except FileNotFoundError as e:
        logging.error(f"File not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
