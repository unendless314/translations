#!/usr/bin/env python3
"""
Translation Backfill Tool
Parses completed translation drafts and updates main.yaml with translations
"""

import json
import re
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

import yaml

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config_loader import load_config


@dataclass
class TranslationEntry:
    """Represents a parsed translation from Markdown"""
    segment_id: int
    text: str
    confidence: str
    notes: Optional[str] = None
    valid: bool = True
    error_message: Optional[str] = None


@dataclass
class Statistics:
    """Track processing statistics"""
    topics_processed: List[str] = field(default_factory=list)
    successful: int = 0
    needs_review: int = 0
    skipped: int = 0

    def add_success(self):
        """Increment successful translations count"""
        self.successful += 1

    def add_needs_review(self):
        """Increment needs_review count"""
        self.needs_review += 1

    def add_skipped(self):
        """Increment skipped count"""
        self.skipped += 1

    def add_topic(self, topic_id: str):
        """Add processed topic"""
        self.topics_processed.append(topic_id)

    def print_summary(self):
        """Print final statistics to stdout"""
        topics_str = ", ".join(self.topics_processed)
        print(f"\nProcessed {len(self.topics_processed)} topics ({topics_str})")
        print(f"- Successfully translated: {self.successful} segments")
        print(f"- Needs review: {self.needs_review} segments (validation failed)")
        print(f"- Skipped: {self.skipped} segments (JSON parse error)")


class MarkdownParser:
    """Parse Markdown translation drafts"""

    # Regex patterns
    SPEAKER_GROUP_PATTERN = re.compile(r'^##\s+Speaker\s+Group\s+\d+', re.IGNORECASE)
    SEGMENT_PATTERN = re.compile(r'^(\d+)\.\s+(.+)$')
    TRANSLATION_PATTERN = re.compile(r'^→\s+(.+)$')

    def __init__(self):
        """Initialize parser"""
        pass

    def parse_file(self, markdown_path: Path, topic_id: str) -> List[TranslationEntry]:
        """Parse a single Markdown file and extract translations

        Args:
            markdown_path: Path to the .md file
            topic_id: Topic identifier (e.g., 'topic_01')

        Returns:
            List of TranslationEntry objects
        """
        if not markdown_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

        try:
            content = markdown_path.read_text(encoding='utf-8')
        except Exception as e:
            raise ValueError(f"Failed to read {markdown_path}: {e}")

        lines = content.splitlines()
        translations = []
        current_segment_id = None
        line_number = 0

        for line in lines:
            line_number += 1
            line = line.rstrip()

            # Skip empty lines
            if not line:
                continue

            # Skip Speaker Group headers
            if self.SPEAKER_GROUP_PATTERN.match(line):
                logging.debug(f"Skipping Speaker Group header: {line}")
                continue

            # Check for segment line (segment_id + source_text)
            segment_match = self.SEGMENT_PATTERN.match(line)
            if segment_match:
                current_segment_id = int(segment_match.group(1))
                logging.debug(f"Found segment {current_segment_id}")
                continue

            # Check for translation line (→ JSON)
            translation_match = self.TRANSLATION_PATTERN.match(line)
            if translation_match:
                if current_segment_id is None:
                    logging.warning(
                        f"Line {line_number}: Translation found without segment ID, skipping"
                    )
                    continue

                json_str = translation_match.group(1)
                entry = self._parse_translation_json(
                    current_segment_id, json_str, topic_id, line_number
                )
                translations.append(entry)
                current_segment_id = None  # Reset for next segment
                continue

            # Unrecognized line format
            logging.debug(f"Line {line_number}: Unrecognized format, skipping: {line[:50]}")

        return translations

    def _parse_translation_json(
        self, segment_id: int, json_str: str, topic_id: str, line_number: int
    ) -> TranslationEntry:
        """Parse and validate translation JSON

        Args:
            segment_id: Segment ID
            json_str: JSON string to parse
            topic_id: Topic identifier
            line_number: Line number for error reporting

        Returns:
            TranslationEntry with validation results
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logging.warning(
                f"Segment {segment_id} (line {line_number}): JSON parse error: {e}"
            )
            return TranslationEntry(
                segment_id=segment_id,
                text="",
                confidence="",
                valid=False,
                error_message=f"JSON parse error: {e}"
            )

        # Validate data type
        if not isinstance(data, dict):
            return TranslationEntry(
                segment_id=segment_id,
                text="",
                confidence="",
                valid=False,
                error_message="Translation must be a JSON object"
            )

        # Extract fields
        text = data.get('text', '')
        confidence = data.get('confidence', '')
        notes = data.get('notes', '')

        # Validate required fields
        validation_errors = []

        # Check 'text' field
        if not text or not isinstance(text, str) or text.strip() == '':
            validation_errors.append("'text' is required and must be non-empty")

        # Check 'confidence' field
        if not confidence or not isinstance(confidence, str):
            validation_errors.append("'confidence' is required")
        elif confidence.lower() not in ['high', 'medium', 'low']:
            validation_errors.append(
                f"'confidence' must be 'high', 'medium', or 'low' (got: {confidence})"
            )

        # Normalize notes (empty string -> None)
        if notes == '':
            notes = None

        if validation_errors:
            error_msg = "; ".join(validation_errors)
            logging.warning(f"Segment {segment_id}: Validation failed: {error_msg}")
            return TranslationEntry(
                segment_id=segment_id,
                text=text,
                confidence=confidence,
                notes=notes,
                valid=False,
                error_message=error_msg
            )

        # Normalize confidence to lowercase
        confidence = confidence.lower()

        return TranslationEntry(
            segment_id=segment_id,
            text=text,
            confidence=confidence,
            notes=notes,
            valid=True
        )


class MainYamlUpdater:
    """Update main.yaml with translations"""

    def __init__(self, main_yaml_path: Path):
        """Initialize updater

        Args:
            main_yaml_path: Path to main.yaml
        """
        self.main_yaml_path = main_yaml_path
        self.data = None
        self.segments_dict = None

    def load(self):
        """Load main.yaml into memory"""
        if not self.main_yaml_path.exists():
            raise FileNotFoundError(f"main.yaml not found: {self.main_yaml_path}")

        try:
            with self.main_yaml_path.open('r', encoding='utf-8') as f:
                self.data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse main.yaml: {e}")

        # Validate structure
        if not isinstance(self.data, dict):
            raise ValueError("main.yaml must contain a mapping at top level")

        if 'segments' not in self.data:
            raise ValueError("main.yaml missing required field: segments")

        if not isinstance(self.data['segments'], list):
            raise ValueError("main.yaml 'segments' must be a list")

        # Build segment lookup dictionary
        self.segments_dict = {
            seg['segment_id']: seg for seg in self.data['segments']
        }

        logging.info(f"Loaded main.yaml with {len(self.segments_dict)} segments")

    def update_segment(
        self, entry: TranslationEntry, topic_id: str, stats: Statistics
    ) -> bool:
        """Update a single segment with translation

        Args:
            entry: TranslationEntry with translation data
            topic_id: Topic identifier
            stats: Statistics tracker

        Returns:
            True if updated successfully, False otherwise
        """
        segment_id = entry.segment_id

        # Check if segment exists
        if segment_id not in self.segments_dict:
            logging.error(f"Segment {segment_id} not found in main.yaml, skipping")
            stats.add_skipped()
            return False

        segment = self.segments_dict[segment_id]

        # Update translation fields based on validation result
        if entry.valid:
            # Validation passed - update all fields
            segment['translation']['text'] = entry.text
            segment['translation']['confidence'] = entry.confidence
            segment['translation']['notes'] = entry.notes
            segment['translation']['status'] = 'completed'
            segment['metadata']['topic_id'] = topic_id

            logging.debug(f"Segment {segment_id}: Updated successfully")
            stats.add_success()
            return True
        else:
            # Validation failed - mark as needs_review
            segment['translation']['status'] = 'needs_review'
            # Do NOT overwrite text/confidence/notes - keep original values

            logging.warning(
                f"Segment {segment_id}: Marked as needs_review ({entry.error_message})"
            )
            stats.add_needs_review()
            return False

    def save(self):
        """Save updated data back to main.yaml"""
        try:
            with self.main_yaml_path.open('w', encoding='utf-8') as f:
                yaml.safe_dump(
                    self.data,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False
                )
            logging.info(f"Saved updated main.yaml to {self.main_yaml_path}")
        except Exception as e:
            raise IOError(f"Failed to write main.yaml: {e}")


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
        description="Backfill translations from Markdown drafts to main.yaml"
    )
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Path to episode config file (e.g., configs/S01-E12.yaml)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate files but do not write to main.yaml'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
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
        main_yaml_path = Path(config['output']['main_yaml'])
        drafts_dir = Path(config['output']['drafts_dir'])

        # Validate paths
        if not drafts_dir.exists():
            logging.error(f"Drafts directory not found: {drafts_dir}")
            sys.exit(1)

        # Find all Markdown files
        md_files = sorted(drafts_dir.glob('*.md'))
        if not md_files:
            logging.warning(f"No Markdown files found in {drafts_dir}")
            sys.exit(0)

        logging.info(f"Found {len(md_files)} Markdown file(s) to process")

        # Initialize components
        parser_obj = MarkdownParser()
        updater = MainYamlUpdater(main_yaml_path)
        stats = Statistics()

        # Load main.yaml
        logging.info(f"Loading main.yaml from {main_yaml_path}")
        updater.load()

        # Process each Markdown file
        for md_file in md_files:
            topic_id = md_file.stem  # e.g., 'topic_01.md' -> 'topic_01'
            logging.info(f"Processing {topic_id}.md")

            try:
                # Parse Markdown
                translations = parser_obj.parse_file(md_file, topic_id)
                logging.info(f"  Parsed {len(translations)} translation(s)")

                # Update segments
                for entry in translations:
                    updater.update_segment(entry, topic_id, stats)

                stats.add_topic(topic_id)

                # Save after each topic (incremental write)
                if not args.dry_run:
                    updater.save()
                else:
                    logging.info(f"  [DRY-RUN] Would save main.yaml here")

            except (FileNotFoundError, ValueError) as e:
                logging.error(f"Failed to process {md_file}: {e}")
                continue

        # Print summary
        stats.print_summary()

        if args.dry_run:
            logging.info("\n[DRY-RUN] No changes were written to main.yaml")

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
