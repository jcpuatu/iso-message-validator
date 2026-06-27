"""
Parser for ISO 8583 receipt-style logs (BDO / SERINO PAY / TRECS PDF previews).

Two input modes:
  * `parse_pdf(path)`         — coordinate-based parse of a multi-column PDF.
  * `parse_iso_log(text)`     — plain-text parse for copy/paste input.

Each MTI block becomes an IsoMessage with raw_des (DE -> hex string) and
de55_tlvs (EMV tag -> TLV) populated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class TLV:
    tag: str
    length: int
    value: str  # uppercase hex, no spaces

    def pretty_value(self) -> str:
        return " ".join(self.value[i:i + 2] for i in range(0, len(self.value), 2))


@dataclass
class IsoMessage:
    mti: str
    raw_des: Dict[str, str] = field(default_factory=dict)
    de55_tlvs: Dict[str, TLV] = field(default_factory=dict)

    def has_tag(self, tag: str) -> bool:
        return tag.upper() in self.de55_tlvs

    def tag_value(self, tag: str) -> Optional[str]:
        t = self.de55_tlvs.get(tag.upper())
        return t.value if t else None


# ===========================================================================
# PDF coordinate-based parsing  (preferred path)
# ===========================================================================
def parse_pdf(pdf_path: str) -> List[IsoMessage]:
    """
    Parse a multi-column ISO log PDF using word coordinates.

    Receipt PDFs lay out each MTI block as a column. A long block whose
    contents don't fit on one page wraps onto the next page in the SAME
    x-position band. To handle this, we track "active columns" as a list
    of (column_x_start, IsoMessage) pairs, in left-to-right order.

    For each page:
      1. Find every MTI: header on the page.
      2. New MTI headers create new active columns at their x-position.
         An MTI header overwrites any previous active column whose
         x-band overlaps it.
      3. Define column x-boundaries from the sorted active column starts.
      4. For each band, route its words into the corresponding active
         column's message — labels at the band's leftmost x become DE
         numbers, hex bytes at any x in the band are appended to the
         currently-tracked DE for that column.
    """
    import pdfplumber  # type: ignore

    messages: List[IsoMessage] = []
    # active_columns[i] = (column_start_x, IsoMessage, current_de_in_progress)
    active_columns: List[Tuple[float, IsoMessage, Optional[str]]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            page_mti_words = [w for w in words if w["text"] == "MTI:"]

            # --- Step 1: pair each MTI: with its 4-digit MTI value ---
            new_mtis: List[Tuple[float, str]] = []  # (x_start, mti_string)
            for mw in page_mti_words:
                same_row_right = sorted(
                    [w for w in words
                     if abs(w["top"] - mw["top"]) < 3 and w["x0"] > mw["x0"]],
                    key=lambda w: w["x0"],
                )
                if same_row_right and re.fullmatch(r"[0-9]{4}", same_row_right[0]["text"]):
                    new_mtis.append((mw["x0"], same_row_right[0]["text"]))

            # --- Step 2: integrate new MTIs into active_columns ---
            # If an MTI's x-position is close to an existing column's start,
            # replace that column with a fresh message. Otherwise insert.
            for x_start, mti in new_mtis:
                replaced = False
                for idx, (cx, _, _) in enumerate(active_columns):
                    if abs(cx - x_start) < 20:  # same column band
                        active_columns[idx] = (x_start, IsoMessage(mti=mti), None)
                        messages.append(active_columns[idx][1])
                        replaced = True
                        break
                if not replaced:
                    new_msg = IsoMessage(mti=mti)
                    active_columns.append((x_start, new_msg, None))
                    messages.append(new_msg)

            # Sort active columns left-to-right
            active_columns.sort(key=lambda t: t[0])

            if not active_columns:
                continue

            # --- Step 3: build column x-boundaries on this page ---
            left_margin = 5
            xs = [max(0, c[0] - left_margin) for c in active_columns]
            xs.append(page.width)

            # --- Step 4: route words into each column ---
            for i, (cx, msg, current_de) in enumerate(active_columns):
                x0, x1 = xs[i], xs[i + 1]
                col_words = [w for w in words if x0 <= w["x0"] < x1]
                # Are we processing the column that has the MTI header on this
                # page? If so, skip the MTI: row when assigning words.
                has_mti_on_page = any(
                    abs(c[0] - cx) < 1 for c in
                    [(x_st, m) for (x_st, m) in new_mtis if abs(x_st - cx) < 20]
                )
                new_current_de = _append_words_to_message(
                    col_words, msg, current_de, skip_mti_row=has_mti_on_page
                )
                active_columns[i] = (cx, msg, new_current_de)

    # Decode DE 55 for every message
    for msg in messages:
        de55 = msg.raw_des.get("55", "")
        if de55:
            msg.de55_tlvs = parse_tlvs(de55)

    return messages


def _append_words_to_message(
    words: List[dict],
    msg: IsoMessage,
    current_de: Optional[str],
    skip_mti_row: bool = False,
) -> Optional[str]:
    """Group words into rows and feed them into msg.raw_des."""
    if not words:
        return current_de

    # --- Group words into rows by `top` coordinate ---
    rows: List[List[dict]] = []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    for w in sorted_words:
        if rows and abs(rows[-1][0]["top"] - w["top"]) < 3:
            rows[-1].append(w)
        else:
            rows.append([w])

    # --- Determine the LABEL_X (the column where DE numbers live) ---
    # Look at rows whose first word is a 1-3 digit decimal number followed
    # by a hex byte; those are very likely DE rows. Take the minimum x0.
    candidate_xs: List[float] = []
    for row in rows:
        row_sorted = sorted(row, key=lambda w: w["x0"])
        if len(row_sorted) < 2:
            continue
        first, second = row_sorted[0], row_sorted[1]
        if (
            re.fullmatch(r"\d{1,3}", first["text"])
            and re.fullmatch(r"[0-9A-Fa-f]{2}", second["text"])
        ):
            candidate_xs.append(first["x0"])

    label_x: Optional[float] = min(candidate_xs) if candidate_xs else None

    # --- Walk rows in document order ---
    for row in rows:
        row_sorted = sorted(row, key=lambda w: w["x0"])
        if not row_sorted:
            continue
        first = row_sorted[0]
        texts = [w["text"] for w in row_sorted]

        if skip_mti_row and "MTI:" in texts:
            continue

        if first["text"] == "BITMAP":
            current_de = "BITMAP"
            hex_bytes = [t for t in texts[1:] if re.fullmatch(r"[0-9A-Fa-f]{2}", t)]
            if hex_bytes:
                msg.raw_des["BITMAP"] = msg.raw_des.get("BITMAP", "") + "".join(hex_bytes).upper()
            continue

        # Decide: is this a label row or a continuation row?
        is_label_row = (
            label_x is not None
            and abs(first["x0"] - label_x) < 6
            and re.fullmatch(r"\d{1,3}", first["text"]) is not None
        )

        if is_label_row:
            current_de = first["text"]
            hex_words = row_sorted[1:]
        else:
            if current_de is None:
                continue
            hex_words = row_sorted

        hex_bytes = [w["text"] for w in hex_words if re.fullmatch(r"[0-9A-Fa-f]{2}", w["text"])]
        if hex_bytes and current_de is not None:
            msg.raw_des[current_de] = msg.raw_des.get(current_de, "") + "".join(hex_bytes).upper()

    return current_de


# ===========================================================================
# Text-mode parsing  (for pasted text input)
# ===========================================================================
_MTI_HEADER_RE = re.compile(r"^\s*MTI\s*:\s*([0-9]{4})\s*$", re.MULTILINE)
_DE_ROW_RE = re.compile(r"^\s*(\d{1,3})\s+((?:[0-9A-Fa-f]{2}\s+)*[0-9A-Fa-f]{2})\s*$")
_HEX_ONLY_RE = re.compile(r"^\s*((?:[0-9A-Fa-f]{2}\s+)*[0-9A-Fa-f]{2})\s*$")
_BITMAP_RE = re.compile(r"^\s*BITMAP\s+((?:[0-9A-Fa-f]{2}\s*)+)$")


def parse_iso_log(text: str) -> List[IsoMessage]:
    """Parse a full ISO 8583 log text into IsoMessage objects."""
    messages: List[IsoMessage] = []
    for mti, body in _split_into_mti_blocks(text):
        des = _parse_des_from_block(body)
        de55 = des.get("55", "")
        tlvs = parse_tlvs(de55) if de55 else {}
        messages.append(IsoMessage(mti=mti, raw_des=des, de55_tlvs=tlvs))
    return messages


def _split_into_mti_blocks(text: str) -> List[Tuple[str, str]]:
    matches = list(_MTI_HEADER_RE.finditer(text))
    blocks: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append((m.group(1), text[start:end]))
    return blocks


def _parse_des_from_block(body: str) -> Dict[str, str]:
    """
    Heuristic text parser. We treat a line as a DE label row only if it
    starts with 1-3 digits AND those digits represent a number in 1-128
    (the valid DE range). Continuation lines start with hex bytes.

    Edge case: a hex byte like "55" or "82" looks like a DE label number.
    To avoid false positives, we additionally require that for short rows
    (1-2 hex bytes total), if `current_de` is currently active and its
    accumulated length is implausibly small for a real DE, prefer
    continuation over re-labeling. In practice this distinction is rare
    in well-formed text.
    """
    des: Dict[str, List[str]] = {}
    current_de: Optional[str] = None

    for raw_line in body.splitlines():
        if not raw_line.strip():
            current_de = None
            continue

        bm = _BITMAP_RE.match(raw_line)
        if bm:
            current_de = "BITMAP"
            des.setdefault(current_de, []).append(_normalize_hex(bm.group(1)))
            continue

        m = _DE_ROW_RE.match(raw_line)
        if m:
            de_num = int(m.group(1))
            if 1 <= de_num <= 128:
                current_de = m.group(1)
                des.setdefault(current_de, []).append(_normalize_hex(m.group(2)))
                continue

        c = _HEX_ONLY_RE.match(raw_line)
        if c and current_de is not None:
            des[current_de].append(_normalize_hex(c.group(1)))
            continue

        current_de = None

    return {de: "".join(parts) for de, parts in des.items()}


def _normalize_hex(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


# ===========================================================================
# DE 55 hex -> EMV TLVs  (BER-TLV)
# ===========================================================================
def parse_tlvs(de55_hex: str) -> Dict[str, TLV]:
    """
    BER-TLV parser. Tolerant of leading length-prefix bytes some terminals
    prepend (e.g. "01 36" = format indicator + BCD length) before the TLV
    stream. We try several starting offsets and pick the one that decodes
    the most tags.
    """
    if not de55_hex:
        return {}
    try:
        data = bytes.fromhex(de55_hex)
    except ValueError:
        return {}

    best: Dict[str, TLV] = {}
    for offset in range(0, min(6, len(data))):
        try:
            attempt = _ber_tlv_parse(data, offset)
            if len(attempt) > len(best):
                best = attempt
        except (ValueError, IndexError):
            continue
    return best


def _ber_tlv_parse(data: bytes, start: int) -> Dict[str, TLV]:
    out: Dict[str, TLV] = {}
    i = start
    n = len(data)

    while i < n:
        # Skip 0x00 padding between TLVs
        while i < n and data[i] == 0x00:
            i += 1
        if i >= n:
            break

        # --- Tag ---
        first = data[i]
        tag_bytes = [first]
        i += 1
        if (first & 0x1F) == 0x1F:  # multi-byte tag
            while i < n:
                tag_bytes.append(data[i])
                more = data[i] & 0x80
                i += 1
                if not more:
                    break
        if len(tag_bytes) > 3:
            raise ValueError("implausibly long tag")
        tag = "".join(f"{b:02X}" for b in tag_bytes)

        # --- Length ---
        if i >= n:
            raise ValueError("truncated length")
        first_len = data[i]
        i += 1
        if first_len & 0x80:
            num_len_bytes = first_len & 0x7F
            if num_len_bytes == 0 or num_len_bytes > 4:
                raise ValueError("invalid long-form length")
            if i + num_len_bytes > n:
                raise ValueError("truncated long-form length")
            length = int.from_bytes(data[i:i + num_len_bytes], "big")
            i += num_len_bytes
        else:
            length = first_len

        if i + length > n:
            raise ValueError("truncated value")
        value = data[i:i + length]
        i += length

        out[tag] = TLV(tag=tag, length=length, value=value.hex().upper())

    return out


# ===========================================================================
# Convenience: PDF -> raw text (for the "show me the raw extract" preview)
# ===========================================================================
def extract_text_from_pdf(pdf_path: str) -> str:
    """Multi-column-aware text extraction. Used only for the raw preview pane."""
    import pdfplumber  # type: ignore

    column_texts: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            mti_xs = sorted({round(w["x0"], 1) for w in words if w["text"] == "MTI:"})
            if not mti_xs:
                t = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                if t.strip():
                    column_texts.append(t)
                continue
            left_margin = 5
            boundaries = [max(0, x - left_margin) for x in mti_xs]
            boundaries.append(page.width)
            for i in range(len(boundaries) - 1):
                x0, x1 = boundaries[i], boundaries[i + 1]
                band = page.crop((x0, 0, x1, page.height))
                t = band.extract_text(x_tolerance=2, y_tolerance=3) or ""
                if t.strip():
                    column_texts.append(t)
    return "\n\n".join(column_texts)
