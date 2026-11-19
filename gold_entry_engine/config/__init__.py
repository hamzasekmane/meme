"""Configuration loading helpers."""

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping, rejecting empty or non-mapping documents."""
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Configuration must be a YAML mapping: {source}")
    return value


def default_settings_path() -> Path:
    return Path(__file__).with_name("settings.yaml")


def default_strategies_path() -> Path:
    return Path(__file__).with_name("strategies.yaml")
