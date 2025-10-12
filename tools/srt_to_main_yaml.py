#!/usr/bin/env python3
"""
SRT to main.yaml converter
Parses SRT subtitle files, merges broken sentences, and generates main.yaml
"""

import re
import argparse
import logging
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import yaml

from src.config_loader import load_config
from src.exceptions import ConfigError

def resolve_srt_path(raw_path: Path) -> Path:
    """Resolve the effective SRT file.

    Supports either a direct file path or a directory that contains exactly one .srt file.
    """
    if raw_path.is_file():
        return raw_path

    if raw_path.is_dir():
        candidates = sorted(
            p for p in raw_path.iterdir()
            if p.is_file() and p.suffix.lower() == '.srt'
        )

        if not candidates:
            raise ConfigError(f"No SRT file found in directory: {raw_path}")
        if len(candidates) > 1:
            names = ', '.join(p.name for p in candidates)
            raise ConfigError(
                f"Multiple SRT files found in directory {raw_path}: {names}. "
                "Please specify the file path explicitly via input.srt."
            )
        return candidates[0]

    raise ConfigError(f"SRT input path does not exist: {raw_path}")


@dataclass
class SRTEntry:
    """Raw SRT entry"""
    index: int
    start: str  # HH:MM:SS,mmm
    end: str    # HH:MM:SS,mmm
    text: str


@dataclass
class ProcessedSegment:
    """Segment after text cleaning and speaker detection"""
    srt_index: int
    start: str
    end: str
    text: str
    speaker_hint: Optional[str] = None


@dataclass
class MergedSegment:
    """Final merged segment for output"""
    segment_id: int
    speaker_group: int
    start: str
    end: str
    source_text: str
    topic_id: Optional[str] = None
    speaker_hint: Optional[str] = None
    source_entries: List[int] = field(default_factory=list)
    truncated: bool = False


class SRTParser:
    """Parse SRT format into structured entries"""

    TIMECODE_PATTERN = re.compile(
        r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})'
    )

    @staticmethod
    def parse(srt_path: Path) -> List[SRTEntry]:
        """Parse SRT file into entries"""
        entries = []

        # Read with UTF-8 and remove BOM if present
        content = srt_path.read_text(encoding='utf-8-sig')

        # Split by double newlines (SRT entry separator)
        blocks = re.split(r'\n\s*\n', content.strip())

        for block in blocks:
            if not block.strip():
                continue

            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue

            try:
                # First line: index
                index = int(lines[0].strip())

                # Second line: timecode
                timecode_match = SRTParser.TIMECODE_PATTERN.search(lines[1])
                if not timecode_match:
                    logging.warning(f"Invalid timecode in entry {index}: {lines[1]}")
                    continue

                start, end = timecode_match.groups()

                # Remaining lines: text
                text = '\n'.join(lines[2:])

                entries.append(SRTEntry(
                    index=index,
                    start=start,
                    end=end,
                    text=text
                ))

            except (ValueError, IndexError) as e:
                logging.warning(f"Failed to parse SRT block: {e}\n{block}")
                continue

        logging.info(f"Parsed {len(entries)} SRT entries from {srt_path}")
        return entries


class TextCleaner:
    """Clean and normalize text from SRT entries"""

    @staticmethod
    def clean(entry: SRTEntry) -> ProcessedSegment:
        """Clean text and detect metadata"""
        text = entry.text

        # Merge multiple lines into single string (replace newlines with spaces)
        text = ' '.join(line.strip() for line in text.split('\n'))

        # Trim whitespace
        text = text.strip()

        return ProcessedSegment(
            srt_index=entry.index,
            start=entry.start,
            end=entry.end,
            text=text
        )


class SpeakerDetector:
    """Detect speaker hints (>> prefix)"""

    @staticmethod
    def detect(segment: ProcessedSegment) -> ProcessedSegment:
        """Detect and remove >> prefix, mark speaker_hint"""
        text = segment.text

        if text.startswith('>>'):
            segment.speaker_hint = '>>'
            # Remove >> prefix and trim
            segment.text = text[2:].strip()

        return segment


class SegmentMerger:
    """Merge segments based on sentence completeness and punctuation"""

    # Match terminal punctuation, optionally followed by closing quotes/brackets
    # Supports: .!?… followed by optional ", ', ", ', ), ], etc.
    TERMINAL_PUNCTUATION = re.compile(r'[.!?…]+["\'\u201d\u2019\)\]]*$')
    MAX_SAFETY_LIMIT = 10  # Safety limit to prevent infinite merging

    @staticmethod
    def _normalize_sentence_start(text: str) -> str:
        """Remove leading quotes, brackets, and whitespace to check actual content

        Handles common SRT patterns:
        - "Hello world -> Hello world
        - (whispers) Hello -> whispers) Hello (then checked again)
        - [MUSIC] The journey -> MUSIC] The journey
        """
        text = text.lstrip()

        # Strip opening quotes and brackets iteratively
        # Support both English and Chinese punctuation
        opening_chars = '"\'""\'((['

        while text and text[0] in opening_chars:
            text = text[1:].lstrip()

        return text

    def _is_new_sentence_start(self, text: str) -> bool:
        """Check if text starts a new sentence

        Strategy:
        1. Normalize: Remove leading quotes, brackets, whitespace
        2. Check: Does normalized text start with uppercase letter?

        Examples:
        - "Hello world" -> True (uppercase H)
        - (whispers) Come here -> True (uppercase C)
        - and then... -> False (lowercase a)
        - [MUSIC] -> True (uppercase M, treated as content)
        """
        normalized = self._normalize_sentence_start(text)

        if not normalized:
            return False

        return normalized[0].isupper()

    def merge(self, segments: List[ProcessedSegment]) -> List[MergedSegment]:
        """Merge segments into complete sentences (best effort)

        Strategy:
        1. MUST merge: Continue until sentence is complete (has terminal punctuation)
        2. STOP when:
           - Next entry starts a new sentence (uppercase after normalization)
           - Speaker change detected
           - Safety limit reached

        Guarantees:
        - Every entry appears in exactly one segment (no splitting)
        - Best effort to keep sentences complete; truncated segments flagged with metadata.truncated=True

        Known limitations:
        - Lowercase stage directions may be treated as continuation (e.g., "(whispers) hello")
        - Safety limit (10 entries) may force incomplete merge, flagged as truncated

        Improvements (Phase 2A):
        - Handles quoted sentences: "Hello world.", 'Oh, my past life.'
        - Handles multiple punctuation: ...., !!!, ?!?
        - Handles sound effect tags: [MUSIC], [LAUGHS]
        """
        if not segments:
            return []

        merged = []
        segment_id = 1
        speaker_group = 1

        i = 0
        while i < len(segments):
            current = segments[i]

            # Check for speaker change
            if current.speaker_hint == '>>' and i > 0:
                speaker_group += 1

            # Start a new merged segment
            merge_buffer = [current]
            is_truncated = False

            # Try to merge with following segments
            j = i + 1
            while j < len(segments):
                next_seg = segments[j]

                # Stop condition 1: Speaker change
                if next_seg.speaker_hint == '>>':
                    break

                # Stop condition 2: Safety limit
                if len(merge_buffer) >= self.MAX_SAFETY_LIMIT:
                    source_indices = [seg.srt_index for seg in merge_buffer]
                    logging.warning(
                        f"Reached safety limit ({self.MAX_SAFETY_LIMIT}) at segment_id={segment_id}, "
                        f"source_entries={source_indices}, stopping merge even though sentence may be incomplete"
                    )
                    is_truncated = True
                    break

                # Check if last entry in buffer has terminal punctuation
                last_entry_text = merge_buffer[-1].text
                has_terminal_punct = self.TERMINAL_PUNCTUATION.search(last_entry_text)

                # Case 1: Sentence incomplete - MUST merge
                if not has_terminal_punct:
                    merge_buffer.append(next_seg)
                    j += 1
                    continue

                # Case 2: Sentence complete - check if next entry starts new sentence
                next_text = next_seg.text.strip()

                # Empty entry - merge it
                if not next_text:
                    merge_buffer.append(next_seg)
                    j += 1
                    continue

                # Check if next entry starts a new sentence
                # Use improved heuristic that handles quotes, brackets, etc.
                if self._is_new_sentence_start(next_text):
                    # Next entry is a new sentence - stop here
                    break
                else:
                    # Next entry continues current sentence (lowercase start)
                    # Merge it and continue checking
                    merge_buffer.append(next_seg)
                    j += 1
                    continue

            # Create merged segment
            merged_text = ' '.join(seg.text for seg in merge_buffer)

            merged_segment = MergedSegment(
                segment_id=segment_id,
                speaker_group=speaker_group,
                start=merge_buffer[0].start,
                end=merge_buffer[-1].end,
                source_text=merged_text,
                speaker_hint=current.speaker_hint,
                source_entries=[seg.srt_index for seg in merge_buffer],
                truncated=is_truncated
            )

            merged.append(merged_segment)

            logging.debug(
                f"Merged segment {segment_id}: "
                f"SRT entries {merged_segment.source_entries} -> "
                f"'{merged_text[:50]}...'"
            )

            segment_id += 1
            i = j

        logging.info(f"Merged {len(segments)} segments into {len(merged)} final segments")
        return merged

    @staticmethod
    def _calculate_gap_ms(end_time: str, start_time: str) -> int:
        """Calculate gap in milliseconds between two timecodes"""
        def timecode_to_ms(tc: str) -> int:
            # HH:MM:SS,mmm
            time_part, ms_part = tc.split(',')
            h, m, s = map(int, time_part.split(':'))
            ms = int(ms_part)
            return ((h * 3600 + m * 60 + s) * 1000) + ms

        try:
            end_ms = timecode_to_ms(end_time)
            start_ms = timecode_to_ms(start_time)
            return start_ms - end_ms
        except (ValueError, IndexError):
            return 999999  # Large number to prevent merging on error


class YAMLGenerator:
    """Generate main.yaml output"""

    @staticmethod
    def generate(
        episode_id: str,
        source_file: str,
        segments: List[MergedSegment]
    ) -> Dict[str, Any]:
        """Generate YAML structure"""

        yaml_segments = []
        for seg in segments:
            yaml_seg = {
                'segment_id': seg.segment_id,
                'speaker_group': seg.speaker_group,
                'timecode': {
                    'start': seg.start,
                    'end': seg.end
                },
                'source_text': seg.source_text,
                'translation': {
                    'text': None,
                    'status': 'pending',
                    'confidence': None,
                    'notes': None
                },
                'metadata': {
                    'topic_id': seg.topic_id,
                    'speaker_hint': seg.speaker_hint,
                    'source_entries': seg.source_entries,
                    'truncated': seg.truncated
                }
            }

            yaml_segments.append(yaml_seg)

        return {
            'episode_id': episode_id,
            'source_file': source_file,
            'segments': yaml_segments
        }

    @staticmethod
    def write(data: Dict[str, Any], output_path: Path):
        """Write YAML to file with proper formatting"""

        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Configure YAML formatting
        yaml.add_representer(
            type(None),
            lambda dumper, value: dumper.represent_scalar('tag:yaml.org,2002:null', 'null')
        )

        with output_path.open('w', encoding='utf-8') as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=float('inf')  # Prevent line wrapping
            )

        logging.info(f"Wrote {len(data['segments'])} segments to {output_path}")


def setup_logging(log_path: Optional[Path] = None, verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO

    handlers = [logging.StreamHandler(sys.stdout)]

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding='utf-8'))

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=handlers
    )


def main():
    parser = argparse.ArgumentParser(
        description='Convert SRT subtitle files to main.yaml format'
    )
    parser.add_argument(
        '--config',
        type=Path,
        required=True,
        help='Path to YAML configuration file'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing output file'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    log_path = None
    if 'logging' in config and 'path' in config['logging']:
        log_path = Path(config['logging']['path'])

    setup_logging(log_path, args.verbose)
    logging.info(f"Starting SRT to YAML conversion for episode {config['episode_id']}")

    # Get paths
    raw_srt_path = Path(config['input']['srt'])
    srt_path = resolve_srt_path(raw_srt_path)
    logging.info(f"SRT source resolved to: {srt_path}")
    output_path = Path(config['output']['main_yaml'])

    # Check if output exists
    if output_path.exists() and not args.force:
        logging.error(f"Output file already exists: {output_path}")
        logging.error("Use --force to overwrite")
        sys.exit(1)

    try:
        # Parse SRT
        srt_entries = SRTParser.parse(srt_path)

        # Clean text
        cleaned_segments = [TextCleaner.clean(entry) for entry in srt_entries]

        # Detect speakers
        processed_segments = [SpeakerDetector.detect(seg) for seg in cleaned_segments]

        # Merge segments
        merger = SegmentMerger()
        merged_segments = merger.merge(processed_segments)

        # Generate YAML
        yaml_data = YAMLGenerator.generate(
            episode_id=config['episode_id'],
            source_file=str(srt_path),
            segments=merged_segments
        )

        # Write output
        YAMLGenerator.write(yaml_data, output_path)

        logging.info("Conversion completed successfully!")

    except ConfigError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Conversion failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
