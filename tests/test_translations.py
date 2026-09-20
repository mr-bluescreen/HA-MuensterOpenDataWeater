"""Guard against English/German translation drift and unused error keys."""

from __future__ import annotations

import json
import re
from pathlib import Path

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components/muenster_weather"


def _leaf_keys(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= _leaf_keys(value, path)
        else:
            keys.add(path)
    return keys


def test_translation_files_are_valid_json() -> None:
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        json.loads((COMPONENT_DIR / name).read_text(encoding="utf-8"))


def test_english_translations_match_strings_json() -> None:
    strings = json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((COMPONENT_DIR / "translations/en.json").read_text(encoding="utf-8"))
    assert _leaf_keys(strings) == _leaf_keys(en)


def test_german_translation_has_same_keys_as_english() -> None:
    en = json.loads((COMPONENT_DIR / "translations/en.json").read_text(encoding="utf-8"))
    de = json.loads((COMPONENT_DIR / "translations/de.json").read_text(encoding="utf-8"))
    assert _leaf_keys(en) == _leaf_keys(de)


def test_every_config_error_key_is_referenced_in_source() -> None:
    """Every declared config-flow error/abort key must actually be raised somewhere."""
    en = json.loads((COMPONENT_DIR / "translations/en.json").read_text(encoding="utf-8"))
    source = (COMPONENT_DIR / "config_flow.py").read_text(encoding="utf-8")
    for key in en["config"]["error"]:
        assert re.search(rf'["\']{re.escape(key)}["\']', source), f"Unused error key: {key}"
