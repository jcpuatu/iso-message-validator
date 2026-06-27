"""
Editable rules for Tag 9F33 (Terminal Capabilities).

The client occasionally changes which bit patterns are allowed per brand and
interface (e.g. "Mastercard contact must be xx 70 xx"). To avoid recoding
the app each time, these rules live in a JSON file the user can edit either
by hand or through the GUI dialog (see gui.py: Edit > 9F33 Rules…).

Format
------
A 9F33 mask is a 6-character hex string where:
  * Each hex digit is either "0"–"F" (must match exactly) or
    "X" / "x" (wildcard — accept any nibble).
  * Spaces are ignored, so "xx 70 xx" and "XX70XX" mean the same thing.

Storage
-------
Rules are saved to `tag9f33_rules.json` next to the executable / main.py.
If the file is missing, DEFAULT_RULES below are used.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional


# ===========================================================================
# Defaults (per client's current spec, May 2026)
# ===========================================================================
DEFAULT_RULES: Dict[str, Dict[str, str]] = {
    "CONTACT": {
        "VISA":       "",          # empty mask = no value check (presence-only)
        "MASTERCARD": "XX70XX",
        "JCB":        "",
        "AMEX":       "XXF0XX",
        "DINERS":     "",
        "DISCOVER":   "",
        "UPI":        "",
    },
    "CONTACTLESS": {
        "VISA":       "",
        "MASTERCARD": "XX28XX",
        "JCB":        "",
        "AMEX":       "XX28XX",
        "DINERS":     "",
        "DISCOVER":   "",
        "UPI":        "",
    },
}


# ===========================================================================
# File location
# ===========================================================================
def _config_path() -> Path:
    """
    Return the path to the JSON config file. We store it next to main.py /
    the bundled executable so users always know where to find it.

    When running under PyInstaller, sys.frozen is set and we use the
    executable's directory; when running from source, we use the project
    root (parent of this module's `iso_validator/` package).
    """
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        base = Path(sys.executable).parent
    else:
        # Source run — go up one level from the iso_validator/ package
        base = Path(__file__).resolve().parent.parent
    return base / "tag9f33_rules.json"


# ===========================================================================
# Load / Save
# ===========================================================================
def load_rules() -> Dict[str, Dict[str, str]]:
    """
    Load 9F33 rules from disk. If the file doesn't exist or is malformed,
    fall back to DEFAULT_RULES (and don't write anything — let the user
    decide whether to save).
    """
    path = _config_path()
    if not path.exists():
        return _copy_defaults()

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Normalize: ensure every interface/brand key exists with a string value.
        normalized = _copy_defaults()
        for iface in ("CONTACT", "CONTACTLESS"):
            iface_data = data.get(iface, {})
            if isinstance(iface_data, dict):
                for brand, mask in iface_data.items():
                    if isinstance(mask, str):
                        normalized.setdefault(iface, {})[brand.upper()] = mask
        return normalized
    except (json.JSONDecodeError, OSError):
        return _copy_defaults()


def save_rules(rules: Dict[str, Dict[str, str]]) -> Path:
    """Write rules to disk. Returns the path written to."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, sort_keys=True)
    return path


def _copy_defaults() -> Dict[str, Dict[str, str]]:
    return {iface: dict(brands) for iface, brands in DEFAULT_RULES.items()}


# ===========================================================================
# Mask matching
# ===========================================================================
def normalize_mask(mask: str) -> str:
    """Strip whitespace, uppercase. Empty stays empty."""
    return re.sub(r"\s+", "", mask).upper()


def is_valid_mask(mask: str) -> bool:
    """A valid 9F33 mask is empty (= no check) or 6 hex/X characters."""
    m = normalize_mask(mask)
    if m == "":
        return True
    return len(m) == 6 and bool(re.fullmatch(r"[0-9A-FX]{6}", m))


def value_matches_mask(value_hex: str, mask: str) -> bool:
    """
    Return True if `value_hex` matches `mask`. Both are uppercase hex with
    spaces stripped. An empty mask is treated as "no check" — always True.

    Examples:
      value_matches_mask("E020C8", "XX28XX")  -> False  (middle nibble pair is 20)
      value_matches_mask("E020C8", "XX20XX")  -> True
      value_matches_mask("E020C8", "")        -> True
    """
    m = normalize_mask(mask)
    if m == "":
        return True
    v = normalize_mask(value_hex)
    if len(v) != len(m):
        return False
    for mc, vc in zip(m, v):
        if mc == "X":
            continue
        if mc != vc:
            return False
    return True


def get_mask(rules: Dict[str, Dict[str, str]], interface: str, brand: str) -> str:
    """Look up the mask for the given (interface, brand). Empty if not set."""
    iface = interface.upper().strip()
    br = brand.upper().strip()
    return rules.get(iface, {}).get(br, "")
