"""
Configuration loader that supports default + override merging and placeholder rendering.

This module centralizes configuration handling so CLI tools can share the same logic.
It loads a global default configuration, applies episode-specific overrides, resolves
template variables (e.g., `{episode}`), and returns a fully materialized dictionary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from .exceptions import ConfigError


class _StrictFormatDict(dict):
    """Helper mapping that raises a helpful error on missing keys."""

    def __missing__(self, key: str):
        raise KeyError(key)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "default.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}", str(path))

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse YAML: {exc}", str(path)) from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a mapping at top level: {path}", str(path))

    return data


def _deep_merge(base: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively merge two mappings; values from override take precedence."""
    result: Dict[str, Any] = {}

    for key, value in base.items():
        if isinstance(value, dict):
            result[key] = _deep_merge(value, {})
        else:
            result[key] = value

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def _format_value(value: Any, context: Mapping[str, Any], path: str) -> Any:
    """Apply string formatting to value if needed."""
    if isinstance(value, str):
        try:
            return value.format_map(_StrictFormatDict(context))
        except KeyError as exc:
            missing = exc.args[0]
            raise ConfigError(
                f"Missing placeholder '{missing}' while formatting '{value}' at '{path}'"
            ) from exc
    if isinstance(value, dict):
        return {
            key: _format_value(nested, context, f"{path}.{key}" if path else key)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [
            _format_value(item, context, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    return value


def _resolve_variables(
    variables: Mapping[str, Any],
    base_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Resolve variables that may reference each other via string placeholders."""
    resolved = dict(base_context)
    pending = dict(variables)

    # Attempt resolution repeatedly until all placeholders succeed.
    for _ in range(len(pending) + 5):
        if not pending:
            break

        still_pending: Dict[str, Any] = {}
        for key, value in pending.items():
            if isinstance(value, str):
                try:
                    resolved_value = value.format_map(_StrictFormatDict(resolved))
                except KeyError:
                    still_pending[key] = value
                    continue
            else:
                resolved_value = value

            resolved[key] = resolved_value

        if len(still_pending) == len(pending):
            unresolved_keys = ", ".join(sorted(still_pending))
            raise ConfigError(
                f"Unable to resolve variables due to missing placeholders: {unresolved_keys}"
            )

        pending = still_pending
    else:
        raise ConfigError("Exceeded maximum iterations while resolving variables")

    return resolved


def load_config(
    config_path: Optional[Path] = None,
    episode: Optional[str] = None,
) -> Dict[str, Any]:
    """Load configuration with default support and placeholder formatting."""
    base_config: Dict[str, Any] = {}
    if DEFAULT_CONFIG_PATH.exists():
        base_config = _load_yaml(DEFAULT_CONFIG_PATH)

    override_config: Dict[str, Any] = {}
    override_path: Optional[Path] = None

    if config_path is not None:
        override_path = config_path
    elif episode:
        candidate = CONFIG_DIR / f"{episode}.yaml"
        if candidate.exists():
            override_path = candidate
        else:
            raise ConfigError(f"Config file not found for episode: {episode}", str(candidate))

    if override_path is not None:
        override_config = _load_yaml(override_path)

    merged = _deep_merge(base_config, override_config)

    if "episode_id" not in merged:
        if episode:
            merged["episode_id"] = episode
        else:
            raise ConfigError("Missing required field: episode_id")

    context: Dict[str, Any] = {"episode": merged["episode_id"]}

    raw_variables = merged.get("variables") or {}
    if raw_variables and not isinstance(raw_variables, Mapping):
        raise ConfigError("Expected 'variables' to be a mapping")

    context = _resolve_variables(raw_variables, context)

    # Ensure config['variables'] holds the resolved values for future reuse.
    merged["variables"] = {key: context[key] for key in raw_variables.keys()}

    formatted = _format_value(merged, context, path="")
    return formatted
