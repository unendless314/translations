#!/usr/bin/env python3
"""
Precise SRT subtitle splitter - splits a specific segment at a character index.
Automatically handles time distribution and segment number reindexing.
"""

import argparse
import sys
from pathlib import Path


def parse_timecode(tc: str) -> float:
    """Convert SRT timecode (HH:MM:SS,mmm) to seconds."""
    time_part, ms_part = tc.split(',')
    h, m, s = map(int, time_part.split(':'))
    ms = int(ms_part)
    return h * 3600 + m * 60 + s + ms / 1000.0


def format_timecode(seconds: float) -> str:
    """Convert seconds to SRT timecode format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def load_srt(filepath: str) -> list:
    """Load SRT file and parse into list of segment dictionaries."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = content.strip().split('\n\n')
    segments = []

    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3:
            index = int(lines[0])
            timecode = lines[1]
            text = '\n'.join(lines[2:])

            # Parse timecode
            start_str, end_str = timecode.split(' --> ')
            start = parse_timecode(start_str)
            end = parse_timecode(end_str)

            segments.append({
                'index': index,
                'start': start,
                'end': end,
                'text': text
            })

    return segments


def save_srt(segments: list, filepath: str):
    """Save segments to SRT file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        for seg in segments:
            start_str = format_timecode(seg['start'])
            end_str = format_timecode(seg['end'])
            f.write(f"{seg['index']}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{seg['text']}\n\n")


def split_segment(segments: list, target_index: int, split_pos: int) -> list:
    """
    Split a specific segment at the given character position.

    Args:
        segments: List of segment dictionaries
        target_index: The segment index to split (1-based)
        split_pos: Character position to split at (0-based)

    Returns:
        Modified segments list with the split applied
    """
    # Find the target segment
    target_seg = None
    seg_list_index = None
    for i, seg in enumerate(segments):
        if seg['index'] == target_index:
            target_seg = seg
            seg_list_index = i
            break

    if target_seg is None:
        raise ValueError(f"Segment #{target_index} not found")

    text = target_seg['text']

    # Validate split position
    if split_pos < 0 or split_pos >= len(text):
        raise ValueError(f"Invalid split position {split_pos} for text of length {len(text)}")

    # Split the text
    part1 = text[:split_pos]
    part2 = text[split_pos:]

    # Calculate time distribution based on character ratio
    duration = target_seg['end'] - target_seg['start']
    ratio = split_pos / len(text)

    # Create split point time
    split_time = target_seg['start'] + (duration * ratio)

    # Create two new segments
    seg1 = {
        'index': target_seg['index'],
        'start': target_seg['start'],
        'end': split_time,
        'text': part1
    }

    seg2 = {
        'index': target_seg['index'] + 1,
        'start': split_time,
        'end': target_seg['end'],
        'text': part2
    }

    # Replace the target segment with the two new segments
    new_segments = segments[:seg_list_index] + [seg1, seg2] + segments[seg_list_index + 1:]

    # Reindex all segments after the split
    for i in range(seg_list_index + 2, len(new_segments)):
        new_segments[i]['index'] += 1

    return new_segments


def main():
    parser = argparse.ArgumentParser(
        description='Precisely split an SRT segment at a specific character position',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Split segment #28 at position 16
  python3 split_srt_precise.py -i input.srt -o output.srt --segment 28 --position 16

  # Preview the split without writing
  python3 split_srt_precise.py -i input.srt --segment 28 --position 16 --dry-run
        """
    )

    parser.add_argument('-i', '--input', required=True, help='Input SRT file')
    parser.add_argument('-o', '--output', help='Output SRT file (required unless --dry-run)')
    parser.add_argument('--segment', type=int, required=True, help='Segment number to split (1-based)')
    parser.add_argument('--position', type=int, required=True, help='Character position to split at (0-based)')
    parser.add_argument('--dry-run', action='store_true', help='Preview split without writing')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if not args.dry_run and not args.output:
        parser.error('--output is required unless --dry-run is specified')

    # Load SRT
    print(f"[INFO] Loading SRT file: {args.input}")
    segments = load_srt(args.input)
    print(f"[INFO] Loaded {len(segments)} segments")

    # Find and preview the target segment
    target_seg = None
    for seg in segments:
        if seg['index'] == args.segment:
            target_seg = seg
            break

    if target_seg is None:
        print(f"[ERROR] Segment #{args.segment} not found", file=sys.stderr)
        sys.exit(1)

    text = target_seg['text']
    print(f"\n[INFO] Target segment #{args.segment}:")
    print(f"  Timecode: {format_timecode(target_seg['start'])} --> {format_timecode(target_seg['end'])}")
    print(f"  Length: {len(text)} chars")
    print(f"  Text: {text}")
    print()

    # Validate split position
    if args.position < 0 or args.position >= len(text):
        print(f"[ERROR] Invalid split position {args.position} for text of length {len(text)}", file=sys.stderr)
        sys.exit(1)

    # Preview split
    part1 = text[:args.position]
    part2 = text[args.position:]

    duration = target_seg['end'] - target_seg['start']
    ratio = args.position / len(text)
    split_time = target_seg['start'] + (duration * ratio)

    print(f"[INFO] Proposed split at position {args.position}:")
    print(f"  Part 1 ({len(part1)} chars): \"{part1}\"")
    print(f"  Timecode: {format_timecode(target_seg['start'])} --> {format_timecode(split_time)}")
    print()
    print(f"  Part 2 ({len(part2)} chars): \"{part2}\"")
    print(f"  Timecode: {format_timecode(split_time)} --> {format_timecode(target_seg['end'])}")
    print()

    if args.dry_run:
        print("[INFO] Dry-run mode - no file written")
        return

    # Perform split
    print("[INFO] Performing split...")
    new_segments = split_segment(segments, args.segment, args.position)

    # Save result
    print(f"[INFO] Writing {len(new_segments)} segments to {args.output}")
    save_srt(new_segments, args.output)

    print(f"[SUCCESS] Split complete!")
    print(f"  Original segments: {len(segments)}")
    print(f"  New segments: {len(new_segments)} (+1)")


if __name__ == '__main__':
    main()
