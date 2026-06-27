"""
Smoke tests for the ISO validator. Run with:

    python -m pytest tests/ -v
"""

from iso_validator.parser import parse_tlvs
from iso_validator.rules import (
    CONTACT_RULES,
    CONTACTLESS_RULES,
    CROSS_MTI_COMPARE_TAGS,
    get_rule,
    supported_brands,
)
from iso_validator.tag9f33_rules import (
    DEFAULT_RULES,
    is_valid_mask,
    normalize_mask,
    value_matches_mask,
)
from iso_validator.validator import validate, Severity


def test_supported_brands():
    brands = supported_brands()
    assert brands == ["VISA", "MASTERCARD", "JCB", "AMEX", "DINERS", "DISCOVER", "UPI"]


# --- Contact rule sanity checks ---
def test_contact_rule_tag_counts():
    expected_counts = {
        "VISA": 20, "MASTERCARD": 20, "JCB": 18,
        "AMEX": 21, "DINERS": 20, "DISCOVER": 20, "UPI": 20,
    }
    for brand, expected in expected_counts.items():
        actual = len(CONTACT_RULES[brand].required_tags)
        assert actual == expected, f"CONTACT/{brand}: expected {expected} tags, got {actual}"


def test_contact_jcb_excludes_9f09_and_9f33():
    rule = get_rule("CONTACT", "JCB")
    assert "9F09" not in rule.required_tags
    assert "9F33" not in rule.required_tags
    assert "9F41" in rule.required_tags


def test_contact_amex_includes_5f34():
    rule = get_rule("CONTACT", "AMEX")
    assert "5F34" in rule.required_tags


def test_contact_discover_equals_diners():
    assert (
        CONTACT_RULES["DISCOVER"].required_tags
        == CONTACT_RULES["DINERS"].required_tags
    )


# --- Contactless rule sanity checks ---
def test_contactless_rule_tag_counts():
    expected_counts = {
        "VISA": 19, "MASTERCARD": 19, "JCB": 19,
        "AMEX": 19, "DINERS": 19, "DISCOVER": 19, "UPI": 18,
    }
    for brand, expected in expected_counts.items():
        actual = len(CONTACTLESS_RULES[brand].required_tags)
        assert actual == expected, f"CONTACTLESS/{brand}: expected {expected} tags, got {actual}"


def test_contactless_visa_requires_9f6e_not_9f7c_or_9f41():
    rule = get_rule("CONTACTLESS", "VISA")
    assert "9F6E" in rule.required_tags
    assert "9F7C" not in rule.required_tags
    assert "9F41" not in rule.required_tags
    assert "9F09" not in rule.required_tags


def test_contactless_mastercard_no_9f41_no_9f6e_no_9f7c():
    rule = get_rule("CONTACTLESS", "MASTERCARD")
    assert "9F09" in rule.required_tags
    assert "9F41" not in rule.required_tags
    assert "9F6E" not in rule.required_tags
    assert "9F7C" not in rule.required_tags


def test_contactless_jcb_requires_9f6e_and_9f7c():
    rule = get_rule("CONTACTLESS", "JCB")
    assert "9F6E" in rule.required_tags
    assert "9F7C" in rule.required_tags
    assert "9F09" not in rule.required_tags
    assert "9F33" not in rule.required_tags


def test_contactless_amex_diners_discover_have_5f34():
    for brand in ("AMEX", "DINERS", "DISCOVER"):
        rule = get_rule("CONTACTLESS", brand)
        assert "5F34" in rule.required_tags, f"{brand} missing 5F34"


def test_contactless_upi_no_5f34_no_9f41():
    rule = get_rule("CONTACTLESS", "UPI")
    assert "5F34" not in rule.required_tags
    assert "9F41" not in rule.required_tags
    assert "9F6E" not in rule.required_tags


# --- AID prefixes ---
def test_aid_prefixes():
    assert "A0000000041010" in get_rule("CONTACTLESS", "MASTERCARD").aid_prefixes
    assert "A0000000031010" in get_rule("CONTACTLESS", "VISA").aid_prefixes
    assert "A0000000651010" in get_rule("CONTACTLESS", "JCB").aid_prefixes


# --- TLV parser ---
def test_tlv_parse_simple():
    hex_str = "9F02060000000176008407A0000000041010"
    tlvs = parse_tlvs(hex_str)
    assert tlvs["9F02"].value == "000000017600"
    assert tlvs["84"].value == "A0000000041010"


def test_tlv_parse_with_leading_length_prefix():
    hex_str = "0136820219808407A0000000041010"
    tlvs = parse_tlvs(hex_str)
    assert "82" in tlvs
    assert tlvs["84"].value == "A0000000041010"


# --- Validator structural check ---
def test_validator_flags_missing_0200():
    report = validate([], "CONTACTLESS", "MASTERCARD")
    assert any(
        f.category == "Structure" and f.severity == Severity.ERROR
        for f in report.findings
    )


# --- Cross-MTI compare list is the trimmed static set ---
def test_cross_mti_compare_is_static_only():
    """Only static tags should be cross-compared; dynamic tags excluded."""
    expected = {"82", "84", "5F2A", "9F09", "9F1A", "9F1E", "9F33", "9F35", "9F40"}
    assert set(CROSS_MTI_COMPARE_TAGS) == expected


# --- 9F33 mask logic ---
def test_mask_normalize_strips_spaces_and_uppercases():
    assert normalize_mask("xx 28 xx") == "XX28XX"
    assert normalize_mask("  E020c8  ") == "E020C8"


def test_mask_validation_rules():
    assert is_valid_mask("")           # empty = no check
    assert is_valid_mask("XX28XX")
    assert is_valid_mask("e020c8")
    assert not is_valid_mask("XX28")    # too short
    assert not is_valid_mask("XX28XXX") # too long
    assert not is_valid_mask("XXZ8XX")  # Z is not hex or X


def test_mask_match_logic():
    assert value_matches_mask("E028C8", "XX28XX")
    assert not value_matches_mask("E020C8", "XX28XX")
    assert value_matches_mask("E020C8", "E020C8")
    assert value_matches_mask("E020C8", "")  # empty mask = always match
    assert not value_matches_mask("E020", "XX20XX")  # wrong length


def test_default_9f33_rules_match_client_spec():
    assert DEFAULT_RULES["CONTACT"]["MASTERCARD"] == "XX70XX"
    assert DEFAULT_RULES["CONTACTLESS"]["MASTERCARD"] == "XX28XX"
    assert DEFAULT_RULES["CONTACT"]["AMEX"] == "XXF0XX"
    assert DEFAULT_RULES["CONTACTLESS"]["AMEX"] == "XX28XX"
    # Brands without a client-supplied rule default to empty (no check)
    assert DEFAULT_RULES["CONTACT"]["VISA"] == ""
    assert DEFAULT_RULES["CONTACTLESS"]["UPI"] == ""
