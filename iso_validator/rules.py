"""
Validation rules for ISO 8583 EMV tags by interface (CONTACT / CONTACTLESS)
and card brand.

These tag lists are typed verbatim from the user's QA spec. If the spec
changes, just edit the lists below — the GUI and validator pick up changes
automatically.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class CardRule:
    """Required tags + AID prefixes for a card brand on a given interface."""
    required_tags: List[str]
    aid_prefixes: List[str]                              # tag 84 must start with one of these
    forbidden_tags: List[str] = field(default_factory=list)  # tags that must NOT appear


# ===========================================================================
# CONTACT
# ===========================================================================
CONTACT_RULES: Dict[str, CardRule] = {
    "VISA": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F09", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "9F41",
        ],
        aid_prefixes=["A0000000031010", "A0000000032010"],
    ),
    "MASTERCARD": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F09", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "9F41",
        ],
        aid_prefixes=["A0000000041010"],
    ),
    "JCB": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F34", "9F35", "9F36", "9F37", "9F41",
        ],
        aid_prefixes=["A0000000651010"],
    ),
    "AMEX": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F09", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "9F41",
            "5F34",
        ],
        aid_prefixes=["A000000025"],
    ),
    "DINERS": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F09", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "9F41",
        ],
        aid_prefixes=["A0000001523010"],
    ),
    "DISCOVER": CardRule(
        # Per user: DISCOVER == DINERS
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F09", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "9F41",
        ],
        aid_prefixes=["A0000001523010"],
    ),
    "UPI": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F09", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "9F41",
        ],
        aid_prefixes=[
            "A000000333010101",
            "A000000333010102",
            "A000000333010103",
        ],
    ),
}


# ===========================================================================
# CONTACTLESS
# ===========================================================================
CONTACTLESS_RULES: Dict[str, CardRule] = {
    "VISA": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "9F6E",
        ],
        aid_prefixes=["A0000000031010", "A0000000032010"],
    ),
    "MASTERCARD": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F09", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37",
        ],
        aid_prefixes=["A0000000041010"],
    ),
    "JCB": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F34", "9F35", "9F36", "9F37", "9F6E", "9F7C",
        ],
        aid_prefixes=["A0000000651010"],
    ),
    "AMEX": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "5F34",
        ],
        aid_prefixes=["A000000025"],
    ),
    "DINERS": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "5F34",
        ],
        aid_prefixes=["A0000001523010"],
    ),
    "DISCOVER": CardRule(
        # Per user: DISCOVER == DINERS
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37", "5F34",
        ],
        aid_prefixes=["A0000001523010"],
    ),
    "UPI": CardRule(
        required_tags=[
            "82", "84", "95", "9A", "9C", "5F2A",
            "9F02", "9F03", "9F10", "9F1A", "9F1E",
            "9F26", "9F27", "9F33", "9F34", "9F35", "9F36", "9F37",
        ],
        aid_prefixes=[
            "A000000333010101",
            "A000000333010102",
            "A000000333010103",
        ],
    ),
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------
def get_rule(interface: str, brand: str) -> CardRule:
    """Return the CardRule for the given interface + brand, raising KeyError if missing."""
    interface = interface.upper().strip()
    brand = brand.upper().strip()
    table = CONTACT_RULES if interface == "CONTACT" else CONTACTLESS_RULES
    return table[brand]


def supported_brands() -> List[str]:
    return ["VISA", "MASTERCARD", "JCB", "AMEX", "DINERS", "DISCOVER", "UPI"]


# ---------------------------------------------------------------------------
# Tags compared between 0200 (request) and 0320 (advice)
# ---------------------------------------------------------------------------
# Per the QA spec, only these tags are STATIC and must match between 0200
# and 0320. Every other EMV tag is dynamic (terminal/card-generated per
# transaction) and is NOT cross-checked.
CROSS_MTI_COMPARE_TAGS = [
    "82",       # Application Interchange Profile
    "84",       # Dedicated File Name (AID)
    "5F2A",     # Transaction Currency Code
    "9F09",     # Application Version Number
    "9F1A",     # Terminal Country Code
    "9F1E",     # IFD Serial Number
    "9F33",     # Terminal Capabilities
    "9F35",     # Terminal Type
    "9F40",     # Additional Terminal Capabilities
]
