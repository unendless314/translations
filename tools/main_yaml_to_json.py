#!/usr/bin/env python3
"""
main.yaml to JSON converter
Exports minimal segment data for LLM topic analysis
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.config_loader import load_config
from src.main_yaml import MainYAMLValidator


class JSONConverter:
    """Convert main.yaml to minimal JSON format"""

    @staticmethod
    def convert(data: Dict[str, Any], skip_invalid: bool = True) -> List[Dict[str, Any]]:
        """Convert segments to minimal JSON array

        Args:
            data: Loaded main.yaml data
            skip_invalid: Skip segments missing required fields (default: True)

        Returns:
            List of segment dicts with only: segment_id, speaker_group, source_text
        """
        segments = data.get('segments', [])
        result = []
        skipped_count = 0

        for idx, segment in enumerate(segments):
            # Check required fields
            if 'segment_id' not in segment:
                if skip_invalid:
                    logging.warning(f"Skipping segment at index {idx}: missing segment_id")
                    skipped_count += 1
                    continue
                else:
                    raise ValueError(f"Segment at index {idx} missing required field: segment_id")

            if 'source_text' not in segment:
                if skip_invalid:
                    logging.warning(f"Skipping segment {segment['segment_id']}: missing source_text")
                    skipped_count += 1
                    continue
                else:
                    raise ValueError(f"Segment {segment['segment_id']} missing required field: source_text")

            if 'speaker_group' not in segment:
                if skip_invalid:
                    logging.warning(f"Skipping segment {segment['segment_id']}: missing speaker_group")
                    skipped_count += 1
                    continue
                else:
                    raise ValueError(f"Segment {segment['segment_id']} missing required field: speaker_group")

            # Extract minimal fields
            minimal_segment = {
                'segment_id': segment['segment_id'],
                'speaker_group': segment['speaker_group'],
                'source_text': segment['source_text']
            }

            result.append(minimal_segment)

        if skipped_count > 0:
            logging.warning(f"Skipped {skipped_count} invalid segments")

        logging.info(f"Converted {len(result)} segments to JSON format")
        return result

    @staticmethod
    def write(data: List[Dict[str, Any]], output_path: Path, pretty: bool = False):
        """Write JSON array to file

        Args:
            data: List of minimal segment dicts
            output_path: Output JSON file path
            pretty: If True, use indentation for readability
        """
        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with output_path.open('w', encoding='utf-8') as f:
                if pretty:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                else:
                    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

            logging.info(f"Wrote {len(data)} segments to {output_path}")

        except (IOError, OSError) as e:
            raise IOError(f"Failed to write output file {output_path}: {e}")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Failed to serialize JSON: {e}")


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def main():
    parser = argparse.ArgumentParser(
        description='Convert main.yaml to minimal JSON for LLM topic analysis'
    )
    parser.add_argument(
        '--config',
        type=Path,
        help='Path to YAML configuration file'
    )
    parser.add_argument(
        '--main',
        type=Path,
        help='Path to main.yaml (overrides config)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Path to output JSON file (overrides config)'
    )
    parser.add_argument(
        '--pretty',
        action='store_true',
        help='Format JSON with indentation for readability'
    )
    parser.add_argument(
        '--no-pretty',
        dest='pretty',
        action='store_false',
        help='Output compact JSON (default)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Fail on any segment validation error (default: skip invalid segments)'
    )

    parser.set_defaults(pretty=False)
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Load configuration
    config = {}
    if args.config:
        try:
            config = load_config(args.config)
            logging.info(f"Loaded config for episode {config['episode_id']}")
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            sys.exit(1)

    # Determine input/output paths
    # Priority: CLI args > config > error
    main_yaml_path = args.main
    if not main_yaml_path and 'input' in config and 'main_yaml' in config['input']:
        main_yaml_path = Path(config['input']['main_yaml'])
    elif not main_yaml_path and 'output' in config and 'main_yaml' in config['output']:
        # Support both input.main_yaml and output.main_yaml in config
        main_yaml_path = Path(config['output']['main_yaml'])

    if not main_yaml_path:
        logging.error("No input file specified. Use --main or --config with input.main_yaml")
        sys.exit(1)

    output_path = args.output
    if not output_path and 'output' in config and 'json' in config['output']:
        output_path = Path(config['output']['json'])

    if not output_path:
        # Default: same directory as main.yaml, with .json extension
        output_path = main_yaml_path.parent / 'main_segments.json'
        logging.info(f"No output path specified, using default: {output_path}")

    # Check pretty flag from config if not set via CLI
    if not args.pretty and 'options' in config and 'pretty' in config['options']:
        args.pretty = config['options']['pretty']

    try:
        # Load and validate main.yaml
        logging.info(f"Loading main.yaml from {main_yaml_path}")
        data = MainYAMLValidator.load(main_yaml_path)

        # Validate segment integrity
        warnings = MainYAMLValidator.validate_segments(data['segments'])
        if warnings:
            logging.warning("Validation warnings:")
            for warning in warnings:
                logging.warning(f"  - {warning}")

        # Convert to minimal JSON
        skip_invalid = not args.strict
        segments_json = JSONConverter.convert(data, skip_invalid=skip_invalid)

        if len(segments_json) == 0:
            logging.error("No valid segments to export")
            sys.exit(1)

        # Write output
        JSONConverter.write(segments_json, output_path, pretty=args.pretty)

        logging.info("Conversion completed successfully!")

    except FileNotFoundError as e:
        logging.error(f"File not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        sys.exit(1)
    except IOError as e:
        logging.error(f"I/O error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
