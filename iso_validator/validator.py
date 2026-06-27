"""
Validator that runs the rule checks against parsed IsoMessages.

Four families of checks:
  1. Presence    — required tags per (interface, brand) are in 0200 and 0320.
  2. AID         — Tag 84 starts with one of the brand's allowed prefixes.
  3. Cross-MTI   — STATIC EMV tags carry identical values in 0200 and 0320.
                   Dynamic tags (9F26, 9F37, 9F36, etc.) are NOT cross-checked.
  4. 9F33 Mask   — Tag 9F33 matches the client-configured hex mask for this
                   brand/interface (e.g. Mastercard contactless = "XX28XX").

Each check produces a ValidationFinding with severity, location, and message.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from .parser import IsoMessage
from .rules import (
    CROSS_MTI_COMPARE_TAGS,
    CardRule,
    get_rule,
)
from .tag9f33_rules import (
    get_mask,
    load_rules as load_9f33_rules,
    value_matches_mask,
)


class Severity(str, Enum):
    OK = "OK"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class Finding:
    severity: Severity
    category: str          # "Presence", "AID", "Consistency", "Structure"
    location: str          # e.g. "0200 / Tag 9F26", "0200 vs 0320 / Tag 9F37"
    message: str

    def short(self) -> str:
        return f"[{self.severity.value}] {self.category} — {self.location}: {self.message}"


@dataclass
class ValidationReport:
    interface: str
    brand: str
    messages_seen: List[str]
    findings: List[Finding]

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARN]

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        if self.passed and not self.warnings:
            return "PASS — all checks succeeded."
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return "FAIL — " + ", ".join(parts)


# ---------------------------------------------------------------------------
# Validation entrypoint
# ---------------------------------------------------------------------------
def validate(
    messages: List[IsoMessage],
    interface: str,
    brand: str,
) -> ValidationReport:
    findings: List[Finding] = []

    # Index messages by MTI
    by_mti: Dict[str, IsoMessage] = {m.mti: m for m in messages}

    # Structure check: must have at least 0200; 0320 is checked when present.
    if "0200" not in by_mti:
        findings.append(Finding(
            Severity.ERROR, "Structure", "log",
            "No 0200 (financial request) message found in the log."
        ))

    if "0320" not in by_mti:
        findings.append(Finding(
            Severity.WARN, "Structure", "log",
            "No 0320 (financial advice) message found. "
            "Cross-MTI consistency checks will be skipped."
        ))

    try:
        rule: CardRule = get_rule(interface, brand)
    except KeyError:
        findings.append(Finding(
            Severity.ERROR, "Configuration", f"{interface}/{brand}",
            f"No rule defined for interface={interface} brand={brand}."
        ))
        return ValidationReport(interface, brand, list(by_mti.keys()), findings)

    # 1. Presence checks on 0200 and 0320
    for mti in ("0200", "0320"):
        msg = by_mti.get(mti)
        if not msg:
            continue
        _check_presence(msg, rule, findings)
        _check_aid(msg, rule, findings)
        _check_forbidden(msg, rule, findings)

    # 2. Cross-MTI consistency
    if "0200" in by_mti and "0320" in by_mti:
        _check_cross_mti(by_mti["0200"], by_mti["0320"], findings)

    # 3. 9F33 mask check (per client-configured brand/interface mask)
    mask = get_mask(load_9f33_rules(), interface, brand)
    if mask:  # empty mask = no check
        for mti in ("0200", "0320"):
            msg = by_mti.get(mti)
            if msg and msg.has_tag("9F33"):
                v = msg.tag_value("9F33")
                if v and not value_matches_mask(v, mask):
                    findings.append(Finding(
                        Severity.ERROR, "9F33 Mask",
                        f"{mti} / Tag 9F33",
                        f"Value '{v}' does not match expected mask "
                        f"'{mask}' for {interface}/{brand}."
                    ))

    return ValidationReport(
        interface=interface,
        brand=brand,
        messages_seen=sorted(by_mti.keys()),
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def _check_presence(msg: IsoMessage, rule: CardRule, findings: List[Finding]) -> None:
    """Required EMV tags must be present in DE 55."""
    for tag in rule.required_tags:
        if not msg.has_tag(tag):
            findings.append(Finding(
                Severity.ERROR, "Presence",
                f"{msg.mti} / Tag {tag}",
                f"Required tag {tag} is missing from DE 55."
            ))
        else:
            # Length sanity: a present-but-empty value is still missing.
            tlv = msg.de55_tlvs[tag]
            if tlv.length == 0:
                findings.append(Finding(
                    Severity.ERROR, "Presence",
                    f"{msg.mti} / Tag {tag}",
                    f"Tag {tag} is present but its length is 0."
                ))


def _check_forbidden(msg: IsoMessage, rule: CardRule, findings: List[Finding]) -> None:
    """Tags that should NOT appear for this brand/interface."""
    for tag in rule.forbidden_tags:
        if msg.has_tag(tag):
            findings.append(Finding(
                Severity.WARN, "Presence",
                f"{msg.mti} / Tag {tag}",
                f"Tag {tag} should not be present for this brand/interface."
            ))


def _check_aid(msg: IsoMessage, rule: CardRule, findings: List[Finding]) -> None:
    """Tag 84 (AID) must start with one of the allowed prefixes."""
    aid = msg.tag_value("84")
    if aid is None:
        # Already reported by presence check
        return
    aid_upper = aid.upper().replace(" ", "")
    if not any(aid_upper.startswith(p.upper().replace(" ", "")) for p in rule.aid_prefixes):
        findings.append(Finding(
            Severity.ERROR, "AID",
            f"{msg.mti} / Tag 84",
            f"AID {aid_upper} does not match any allowed prefix for this brand: "
            f"{rule.aid_prefixes}"
        ))


def _check_cross_mti(
    req: IsoMessage,
    adv: IsoMessage,
    findings: List[Finding],
) -> None:
    """Compare selected EMV tag values across 0200 and 0320."""
    for tag in CROSS_MTI_COMPARE_TAGS:
        v0200 = req.tag_value(tag)
        v0320 = adv.tag_value(tag)
        if v0200 is None and v0320 is None:
            continue
        if v0200 is None or v0320 is None:
            # Already covered by per-message presence check
            continue
        if v0200 != v0320:
            findings.append(Finding(
                Severity.ERROR, "Consistency",
                f"0200 vs 0320 / Tag {tag}",
                f"Value differs — 0200='{v0200}' 0320='{v0320}'"
            ))
