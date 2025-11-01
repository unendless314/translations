#!/usr/bin/env python3
"""
SRT Subtitle Splitter

Intelligently splits long subtitle segments at punctuation marks
and redistributes timecodes proportionally.

This is a universal tool that works with any SRT file.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Tuple, List

try:
    import pysrt
except ImportError:
    print("Error: pysrt library not found. Install with: pip install pysrt>=1.1.2")
    sys.exit(1)


# Punctuation priority levels (higher priority = better split point)
PUNCTUATION_LEVELS = {
    1: ['。', '！', '？', '…'],  # Sentence terminators
    2: ['；', '：', '——'],        # Clause separators (including em dash)
    3: ['，', '、'],              # Commas and enumeration comma
    4: [' ']                     # Spaces (last resort)
}


def setup_logging(verbose: bool = False):
    """Configure logging based on verbosity level"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='[%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def find_split_point(text: str, min_chars: int) -> Optional[Tuple[int, str, int]]:
    """
    Find the best split point in text based on punctuation priority.

    Args:
        text: Text to split
        min_chars: Minimum characters required for each part

    Returns:
        Tuple of (split_position, punctuation_char, priority_level) or None if no valid split found
    """
    text_len = len(text)

    # Calculate search range (midpoint ±20%)
    midpoint = text_len // 2
    search_range = int(text_len * 0.2)
    range_start = max(min_chars, midpoint - search_range)
    range_end = min(text_len - min_chars, midpoint + search_range)

    if range_start >= range_end:
        logging.debug(f"Text too short to split safely (len={text_len}, min_chars={min_chars})")
        return None

    # Search by priority level
    for priority in sorted(PUNCTUATION_LEVELS.keys()):
        punctuations = PUNCTUATION_LEVELS[priority]

        # Find all occurrences of this priority level in the search range
        candidates = []
        for punct in punctuations:
            punct_len = len(punct)
            for i in range(range_start, range_end + 1):  # +1 to include range_end
                # Check if punctuation matches at position i
                if text[i:i+punct_len] == punct:
                    # Split after the punctuation mark
                    split_pos = i + punct_len

                    # Validate both parts meet min_chars requirement
                    part1_len = split_pos
                    part2_len = text_len - split_pos

                    if part1_len >= min_chars and part2_len >= min_chars:
                        # Calculate distance from midpoint (prefer closer to center)
                        distance = abs(split_pos - midpoint)
                        candidates.append((distance, split_pos, punct, priority))

        # If we found candidates at this priority level, return the closest to midpoint
        if candidates:
            candidates.sort(key=lambda x: x[0])  # Sort by distance
            _, split_pos, punct, prio = candidates[0]
            logging.debug(f"Found split point at position {split_pos} (punctuation '{punct}', priority {prio})")
            return (split_pos, punct, prio)

    # No valid split point found
    logging.debug(f"No valid punctuation split point found in range [{range_start}, {range_end}]")
    return None


def split_subtitle(
    sub: pysrt.SubRipItem,
    split_pos: int,
    gap_ms: int = 0
) -> Tuple[pysrt.SubRipItem, pysrt.SubRipItem]:
    """
    Split a subtitle item into two parts with proportional time distribution.

    Args:
        sub: Original subtitle item
        split_pos: Character position to split at
        gap_ms: Gap in milliseconds between the two parts (default: 0)

    Returns:
        Tuple of (first_part, second_part) as SubRipItem objects
    """
    text = sub.text
    part1_text = text[:split_pos].rstrip()
    part2_text = text[split_pos:].lstrip()

    # Calculate time distribution based on character ratio
    total_duration = sub.end - sub.start
    part1_ratio = len(part1_text) / len(text)

    # Calculate midpoint time
    mid_time_ms = sub.start.ordinal + int(total_duration.ordinal * part1_ratio)
    mid_time = pysrt.SubRipTime.from_ordinal(mid_time_ms)

    # Apply gap if specified
    if gap_ms > 0:
        half_gap = gap_ms // 2
        part1_end = pysrt.SubRipTime.from_ordinal(mid_time.ordinal - half_gap)
        part2_start = pysrt.SubRipTime.from_ordinal(mid_time.ordinal + half_gap)
    else:
        part1_end = mid_time
        part2_start = mid_time

    # Ensure times are within original bounds
    part1_end = min(part1_end, sub.end)
    part2_start = max(part2_start, sub.start)

    # Create new subtitle items
    sub1 = pysrt.SubRipItem(
        index=0,  # Will be renumbered later
        start=sub.start,
        end=part1_end,
        text=part1_text
    )

    sub2 = pysrt.SubRipItem(
        index=0,  # Will be renumbered later
        start=part2_start,
        end=sub.end,
        text=part2_text
    )

    return (sub1, sub2)


def process_srt(
    subs: pysrt.SubRipFile,
    max_chars: int,
    min_chars: int,
    gap_ms: int,
    verbose: bool = False
) -> pysrt.SubRipFile:
    """
    Process SRT file and split long segments.

    Args:
        subs: Loaded SRT file
        max_chars: Maximum characters before splitting
        min_chars: Minimum characters for each split part
        gap_ms: Gap in milliseconds between split parts
        verbose: Enable verbose logging

    Returns:
        New SubRipFile with split segments
    """
    new_subs = pysrt.SubRipFile()
    split_count = 0
    skip_count = 0

    # Find segments that need splitting
    segments_to_split = []
    for sub in subs:
        text_len = len(sub.text)
        if text_len > max_chars:
            segments_to_split.append((sub.index, text_len))

    logging.info(f"Found {len(segments_to_split)} segments exceeding {max_chars} chars")

    # Process each subtitle
    for sub in subs:
        text_len = len(sub.text)

        if text_len <= max_chars:
            # Keep as is
            new_subs.append(sub)
        else:
            # Try to split
            split_result = find_split_point(sub.text, min_chars)

            if split_result:
                split_pos, punct, priority = split_result
                sub1, sub2 = split_subtitle(sub, split_pos, gap_ms)

                new_subs.append(sub1)
                new_subs.append(sub2)
                split_count += 1

                if verbose:
                    duration1 = (sub1.end - sub1.start).ordinal / 1000
                    duration2 = (sub2.end - sub2.start).ordinal / 1000
                    logging.debug(
                        f"Segment {sub.index} ({text_len} chars): "
                        f"Split at position {split_pos} (punctuation '{punct}', priority {priority})"
                    )
                    logging.debug(
                        f"  Part 1: {len(sub1.text)} chars, "
                        f"{sub1.start} -> {sub1.end} ({duration1:.1f}s)"
                    )
                    logging.debug(
                        f"  Part 2: {len(sub2.text)} chars, "
                        f"{sub2.start} -> {sub2.end} ({duration2:.1f}s)"
                    )
            else:
                # Cannot split safely, keep original
                new_subs.append(sub)
                skip_count += 1
                logging.warning(
                    f"Segment {sub.index} ({text_len} chars): "
                    f"Cannot find safe split point, keeping original"
                )

    # Renumber all segments
    for i, sub in enumerate(new_subs, start=1):
        sub.index = i

    logging.info(f"Successfully split {split_count} segments into {split_count * 2}")
    if skip_count > 0:
        logging.info(f"Skipped {skip_count} segments (no safe split point)")
    logging.info(f"Total segments: {len(subs)} -> {len(new_subs)} (+{len(new_subs) - len(subs)})")

    # Post-processing statistics: check remaining long segments
    remaining_long = []
    for sub in new_subs:
        text_len = len(sub.text)
        if text_len > max_chars:
            remaining_long.append((sub.index, text_len))

    if remaining_long:
        max_length = max(remaining_long, key=lambda x: x[1])[1]
        logging.warning("")
        logging.warning("=" * 70)
        logging.warning(f"⚠️  POST-SPLIT ANALYSIS")
        logging.warning(f"   Still {len(remaining_long)} segments exceed {max_chars} chars")
        logging.warning(f"   Longest segment: {max_length} chars")
        logging.warning("")
        logging.warning(f"💡 RECOMMENDATION: Run the tool again on the output file")
        logging.warning(f"   to further split these remaining long segments.")
        logging.warning("")
        logging.warning(f"   Example:")
        logging.warning(f"   python3 tools/split_srt.py \\")
        logging.warning(f"     -i <output_file> \\")
        logging.warning(f"     -o <output_file_v2> \\")
        logging.warning(f"     --max-chars {max_chars}")
        logging.warning("=" * 70)
    else:
        logging.info("")
        logging.info("✓ All segments are within the character limit!")

    return new_subs


def main():
    parser = argparse.ArgumentParser(
        description='Intelligently split long SRT subtitle segments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python3 split_srt.py -i input.srt -o output.srt

  # Custom threshold
  python3 split_srt.py -i input.srt -o output.srt --max-chars 30

  # With gap between split segments
  python3 split_srt.py -i input.srt -o output.srt --gap-ms 100

  # Preview mode (no file output)
  python3 split_srt.py -i input.srt -o output.srt --dry-run

  # Verbose logging
  python3 split_srt.py -i input.srt -o output.srt --verbose
        """
    )

    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Input SRT file path'
    )
    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output SRT file path'
    )
    parser.add_argument(
        '--max-chars',
        type=int,
        default=35,
        help='Maximum characters before splitting (default: 35)'
    )
    parser.add_argument(
        '--min-chars',
        type=int,
        default=10,
        help='Minimum characters for each split part (default: 10)'
    )
    parser.add_argument(
        '--gap-ms',
        type=int,
        default=0,
        help='Gap in milliseconds between split segments (default: 0)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed splitting information'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview segments to be split without writing output'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        logging.error(f"Input file not found: {input_path}")
        sys.exit(1)

    # Validate output path
    output_path = Path(args.output)

    # Check if input and output are the same
    if input_path.resolve() == output_path.resolve():
        logging.error(
            "Input and output paths are the same. "
            "Please use a different output path to avoid overwriting the original file."
        )
        sys.exit(1)

    # Validate parameters
    if args.max_chars <= args.min_chars:
        logging.error(f"--max-chars ({args.max_chars}) must be greater than --min-chars ({args.min_chars})")
        sys.exit(1)

    if args.min_chars < 1:
        logging.error(f"--min-chars must be at least 1")
        sys.exit(1)

    if args.gap_ms < 0:
        logging.error(f"--gap-ms cannot be negative")
        sys.exit(1)

    # Load SRT file
    logging.info(f"Loading SRT file: {input_path}")
    try:
        subs = pysrt.open(str(input_path), encoding='utf-8')
    except Exception as e:
        logging.error(f"Failed to load SRT file: {e}")
        sys.exit(1)

    logging.info(f"Loaded {len(subs)} subtitles from input file")

    # Process SRT
    new_subs = process_srt(subs, args.max_chars, args.min_chars, args.gap_ms, args.verbose)

    # Write output (unless dry-run)
    if args.dry_run:
        logging.info("[DRY RUN] No output file written")
    else:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            new_subs.save(str(output_path), encoding='utf-8')
            logging.info(f"[SUCCESS] Written to {output_path}")
        except Exception as e:
            logging.error(f"Failed to write output file: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()
