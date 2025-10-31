"""
Utilities for loading and validating `main.yaml` episode files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class MainYAMLValidator:
    """Load and validate `main.yaml` structures used across the tooling."""

    @staticmethod
    def load(yaml_path: Path) -> Dict[str, Any]:
        """Load and validate `main.yaml`.

        Args:
            yaml_path: Path to the YAML file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the YAML content is malformed or missing required fields.
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"Main YAML file not found: {yaml_path}")

        try:
            with yaml_path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse main.yaml: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError("main.yaml must contain a mapping at the top level")

        if "episode_id" not in data:
            raise ValueError("main.yaml missing required field: episode_id")

        if "segments" not in data:
            raise ValueError("main.yaml missing required field: segments")

        if not isinstance(data["segments"], list):
            raise ValueError("main.yaml 'segments' must be a list")

        if len(data["segments"]) == 0:
            logging.warning("main.yaml contains zero segments")

        return data

    @staticmethod
    def validate_segments(segments: List[Dict[str, Any]]) -> List[str]:
        """Validate segment integrity and return a list of warnings.

        Checks:
            - segment_id exists and is monotonically increasing
            - Required fields present
            - No gaps in segment_id sequence
        """
        warnings: List[str] = []

        if not segments:
            return warnings

        expected_id = 1
        for index, segment in enumerate(segments):
            segment_id: Optional[int] = segment.get("segment_id")
            if segment_id is None:
                warnings.append(f"Segment at index {index} missing 'segment_id'")
                continue

            if "source_text" not in segment:
                warnings.append(f"Segment {segment_id} missing 'source_text'")

            if "speaker_group" not in segment:
                warnings.append(f"Segment {segment_id} missing 'speaker_group'")

            if segment_id != expected_id:
                warnings.append(
                    f"segment_id not sequential: expected {expected_id}, got {segment_id} at index {index}"
                )

            expected_id = segment_id + 1

        return warnings
