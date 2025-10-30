#!/usr/bin/env python3
"""
Translation Status Checker
Quickly scan main.yaml to find untranslated segments
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

import yaml

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config_loader import load_config


def check_translation_status(main_yaml_path: Path, show_untranslated: bool = True):
    """Check translation status in main.yaml

    Args:
        main_yaml_path: Path to main.yaml
        show_untranslated: If True, list untranslated segments
    """
    if not main_yaml_path.exists():
        print(f"Error: main.yaml not found: {main_yaml_path}", file=sys.stderr)
        sys.exit(1)

    # Load YAML
    print(f"Loading {main_yaml_path}...", file=sys.stderr)
    with main_yaml_path.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    segments = data.get('segments', [])
    total = len(segments)

    # Categorize segments
    completed = []
    pending = []
    needs_review = []
    in_progress = []
    approved = []
    untranslated = []  # text is null or empty

    for seg in segments:
        seg_id = seg['segment_id']
        status = seg['translation']['status']
        text = seg['translation']['text']
        topic_id = seg['metadata'].get('topic_id')

        # Check if actually translated
        if text is None or (isinstance(text, str) and text.strip() == ''):
            untranslated.append({
                'segment_id': seg_id,
                'status': status,
                'topic_id': topic_id,
                'source_text': seg['source_text'][:60] + '...' if len(seg['source_text']) > 60 else seg['source_text']
            })

        # Categorize by status
        if status == 'completed':
            completed.append(seg_id)
        elif status == 'pending':
            pending.append(seg_id)
        elif status == 'needs_review':
            needs_review.append(seg_id)
        elif status == 'in_progress':
            in_progress.append(seg_id)
        elif status == 'approved':
            approved.append(seg_id)

    # Print statistics
    print("\n" + "="*60)
    print("TRANSLATION STATUS SUMMARY")
    print("="*60)
    print(f"Total segments: {total}")
    print(f"  - Completed: {len(completed)} ({len(completed)/total*100:.1f}%)")
    print(f"  - Pending: {len(pending)} ({len(pending)/total*100:.1f}%)")
    print(f"  - Needs review: {len(needs_review)} ({len(needs_review)/total*100:.1f}%)")
    print(f"  - In progress: {len(in_progress)} ({len(in_progress)/total*100:.1f}%)")
    print(f"  - Approved: {len(approved)} ({len(approved)/total*100:.1f}%)")
    print()
    print(f"Untranslated (text is null/empty): {len(untranslated)}")
    print("="*60)

    # Show untranslated segments if requested
    if show_untranslated and untranslated:
        print("\nUNTRANSLATED SEGMENTS:")
        print("-"*60)

        # Group by topic
        by_topic = defaultdict(list)
        for item in untranslated:
            topic = item['topic_id'] or 'no_topic'
            by_topic[topic].append(item)

        for topic in sorted(by_topic.keys()):
            items = by_topic[topic]
            print(f"\n[{topic}] - {len(items)} segment(s)")
            for item in items:
                print(f"  Segment {item['segment_id']:4d} (status: {item['status']:12s}) - {item['source_text']}")

    # Exit code based on results
    if untranslated:
        print(f"\n⚠️  Warning: {len(untranslated)} segment(s) have no translation text", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n✓ All segments have translation text", file=sys.stderr)
        sys.exit(0)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Check translation status in main.yaml"
    )
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Path to episode config file (e.g., configs/S01-E12.yaml)'
    )
    parser.add_argument(
        '--no-list',
        action='store_true',
        help='Do not list untranslated segments (only show statistics)'
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(Path(args.config))
    main_yaml_path = Path(config['output']['main_yaml'])

    # Check status
    check_translation_status(main_yaml_path, show_untranslated=not args.no_list)


if __name__ == "__main__":
    main()
