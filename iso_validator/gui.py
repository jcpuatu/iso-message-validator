"""
Main GUI for the ISO Message Validator.

Layout (Windows 11 friendly, dockable, resizable):

  +------------------------------------------------------------------+
  |  Toolbar:  [ Open PDF... ]  [ Paste Text ]  [ Validate ]         |
  +-------------------+----------------------------------------------+
  |  Inputs           |  Tabs:  Findings | Parsed | Raw              |
  |    Interface (o)  |                                              |
  |      ( ) Contact  |   <findings table>                           |
  |      (•) Contactless                                             |
  |    Card Brand     |                                              |
  |      [combo]      |                                              |
  |    File           |                                              |
  |    [path]         |                                              |
  |                   |                                              |
  +-------------------+----------------------------------------------+
  |  Status bar:  PASS / 3 errors / messages: 0200,0210,0320         |
  +------------------------------------------------------------------+
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QStyleFactory,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .parser import IsoMessage, extract_text_from_pdf, parse_iso_log, parse_pdf
from .rules import supported_brands
from .tag9f33_rules import (
    DEFAULT_RULES as DEFAULT_9F33_RULES,
    is_valid_mask,
    load_rules as load_9f33_rules,
    normalize_mask,
    save_rules as save_9f33_rules,
)
from .validator import Finding, Severity, ValidationReport, validate


# ---------------------------------------------------------------------------
# Colors for findings
# ---------------------------------------------------------------------------
SEVERITY_COLORS = {
    Severity.OK:    QColor("#22c55e"),
    Severity.INFO:  QColor("#3b82f6"),
    Severity.WARN:  QColor("#f59e0b"),
    Severity.ERROR: QColor("#ef4444"),
}


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ISO Message Validator")
        self.resize(1280, 820)

        self._messages: List[IsoMessage] = []
        self._raw_text: str = ""
        self._loaded_path: Optional[Path] = None

        self._build_toolbar()
        self._build_central()
        self._build_status_bar()

    # ---- UI construction ----
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize())
        self.addToolBar(tb)

        act_open = QAction("Open PDF…", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.action_open_pdf)
        tb.addAction(act_open)

        act_paste = QAction("Paste Text…", self)
        act_paste.setShortcut("Ctrl+V")
        act_paste.triggered.connect(self.action_paste_text)
        tb.addAction(act_paste)

        tb.addSeparator()

        act_validate = QAction("Validate", self)
        act_validate.setShortcut("F5")
        act_validate.triggered.connect(self.action_validate)
        tb.addAction(act_validate)

        tb.addSeparator()

        act_clear = QAction("Clear", self)
        act_clear.triggered.connect(self.action_clear)
        tb.addAction(act_clear)

        tb.addSeparator()

        act_9f33 = QAction("9F33 Rules…", self)
        act_9f33.setShortcut("Ctrl+R")
        act_9f33.triggered.connect(self.action_edit_9f33_rules)
        tb.addAction(act_9f33)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_input_pane())
        splitter.addWidget(self._build_results_pane())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 960])
        self.setCentralWidget(splitter)

    def _build_input_pane(self) -> QWidget:
        pane = QWidget()
        pane.setMinimumWidth(280)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # --- Interface group (radio buttons) ---
        iface_group = QGroupBox("Interface")
        iface_layout = QVBoxLayout(iface_group)
        self.rb_contact = QRadioButton("Contact (chip insert)")
        self.rb_contactless = QRadioButton("Contactless (tap)")
        self.rb_contactless.setChecked(True)
        iface_layout.addWidget(self.rb_contact)
        iface_layout.addWidget(self.rb_contactless)
        self._iface_group = QButtonGroup(self)
        self._iface_group.addButton(self.rb_contact)
        self._iface_group.addButton(self.rb_contactless)
        layout.addWidget(iface_group)

        # --- Card Brand group ---
        brand_group = QGroupBox("Card Brand")
        brand_layout = QVBoxLayout(brand_group)
        self.cb_brand = QComboBox()
        for b in supported_brands():
            self.cb_brand.addItem(b)
        self.cb_brand.setCurrentText("MASTERCARD")
        brand_layout.addWidget(self.cb_brand)
        layout.addWidget(brand_group)

        # --- Loaded file group ---
        file_group = QGroupBox("Loaded Source")
        file_layout = QVBoxLayout(file_group)
        self.lbl_file = QLabel("(no file loaded)")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setStyleSheet("color: #6b7280;")
        file_layout.addWidget(self.lbl_file)
        layout.addWidget(file_group)

        # --- Big Validate button ---
        self.btn_validate = QPushButton("Validate")
        self.btn_validate.setMinimumHeight(40)
        f = self.btn_validate.font()
        f.setPointSize(f.pointSize() + 1)
        f.setBold(True)
        self.btn_validate.setFont(f)
        self.btn_validate.clicked.connect(self.action_validate)
        layout.addWidget(self.btn_validate)

        layout.addStretch(1)
        return pane

    def _build_results_pane(self) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_findings_tab(), "Findings")
        self.tabs.addTab(self._build_parsed_tab(), "Parsed Messages")
        self.tabs.addTab(self._build_raw_tab(), "Raw Source")
        return self.tabs

    def _build_findings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_summary = QLabel("Load a PDF or paste log text, then click Validate.")
        self.lbl_summary.setStyleSheet(
            "padding: 10px; border-radius: 6px; background: #f3f4f6; color: #111827;"
        )
        f = self.lbl_summary.font()
        f.setPointSize(f.pointSize() + 1)
        self.lbl_summary.setFont(f)
        layout.addWidget(self.lbl_summary)

        self.tbl_findings = QTableWidget(0, 4)
        self.tbl_findings.setHorizontalHeaderLabels(["Severity", "Category", "Location", "Message"])
        self.tbl_findings.horizontalHeader().setStretchLastSection(True)
        self.tbl_findings.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_findings.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tbl_findings.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_findings.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_findings.setAlternatingRowColors(True)
        self.tbl_findings.verticalHeader().setVisible(False)
        layout.addWidget(self.tbl_findings, 1)
        return w

    def _build_parsed_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        self.tree_parsed = QTreeWidget()
        self.tree_parsed.setHeaderLabels(["Field", "Length", "Value"])
        self.tree_parsed.setColumnWidth(0, 220)
        self.tree_parsed.setColumnWidth(1, 80)
        layout.addWidget(self.tree_parsed)
        return w

    def _build_raw_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        self.txt_raw = QPlainTextEdit()
        self.txt_raw.setReadOnly(False)  # let users paste here too
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)
        self.txt_raw.setFont(mono)
        self.txt_raw.setPlaceholderText(
            "Raw log text appears here after loading a PDF.\n"
            "You can also paste log text directly into this box, then click Validate."
        )
        layout.addWidget(self.txt_raw)
        return w

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)
        bar.showMessage("Ready.")

    # ---- Actions ----
    def action_open_pdf(self) -> None:
        fname, _ = QFileDialog.getOpenFileName(
            self,
            "Open ISO Log PDF",
            "",
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not fname:
            return
        try:
            messages = parse_pdf(fname)
            raw_text = extract_text_from_pdf(fname)
        except Exception as e:
            QMessageBox.critical(self, "Failed to parse PDF", str(e))
            return

        self._messages = messages
        self._raw_text = raw_text
        self._loaded_path = Path(fname)
        self.lbl_file.setText(f"📄 {self._loaded_path.name}")
        self.lbl_file.setStyleSheet("color: #111827;")
        self.txt_raw.setPlainText(raw_text)
        self._populate_parsed_tree()
        self.statusBar().showMessage(
            f"Loaded {len(messages)} message(s): {', '.join(m.mti for m in messages)}"
        )
        # auto-run validate after load
        self.action_validate()

    def action_paste_text(self) -> None:
        self.tabs.setCurrentIndex(2)
        self.txt_raw.setFocus()

    def action_validate(self) -> None:
        # If user pasted into the raw text tab without loading a PDF, parse from there.
        text_in_box = self.txt_raw.toPlainText()
        if text_in_box and (not self._messages or text_in_box.strip() != self._raw_text.strip()):
            try:
                self._messages = parse_iso_log(text_in_box)
                self._raw_text = text_in_box
                self._populate_parsed_tree()
            except Exception as e:
                QMessageBox.critical(self, "Failed to parse text", str(e))
                return

        if not self._messages:
            QMessageBox.information(
                self, "Nothing to validate",
                "Open a PDF (Ctrl+O) or paste log text in the Raw Source tab first."
            )
            return

        interface = "CONTACT" if self.rb_contact.isChecked() else "CONTACTLESS"
        brand = self.cb_brand.currentText()

        try:
            report = validate(self._messages, interface=interface, brand=brand)
        except Exception as e:
            QMessageBox.critical(self, "Validation error", str(e))
            return

        self._show_report(report)
        self.tabs.setCurrentIndex(0)

    def action_clear(self) -> None:
        self._messages = []
        self._raw_text = ""
        self._loaded_path = None
        self.lbl_file.setText("(no file loaded)")
        self.lbl_file.setStyleSheet("color: #6b7280;")
        self.txt_raw.clear()
        self.tree_parsed.clear()
        self.tbl_findings.setRowCount(0)
        self.lbl_summary.setText("Load a PDF or paste log text, then click Validate.")
        self.lbl_summary.setStyleSheet(
            "padding: 10px; border-radius: 6px; background: #f3f4f6; color: #111827;"
        )
        self.statusBar().showMessage("Cleared.")

    # ---- Render helpers ----
    def _show_report(self, report: ValidationReport) -> None:
        # Summary banner color
        if report.passed and not report.warnings:
            bg = "#dcfce7"
            fg = "#166534"
            icon = "✅"
        elif report.passed and report.warnings:
            bg = "#fef3c7"
            fg = "#92400e"
            icon = "⚠️"
        else:
            bg = "#fee2e2"
            fg = "#991b1b"
            icon = "❌"

        self.lbl_summary.setText(
            f"{icon}  {report.summary()}    │    "
            f"Interface: {report.interface}    │    Brand: {report.brand}    │    "
            f"Messages: {', '.join(report.messages_seen)}"
        )
        self.lbl_summary.setStyleSheet(
            f"padding: 10px; border-radius: 6px; background: {bg}; color: {fg}; font-weight: 600;"
        )

        # Populate findings table
        self.tbl_findings.setRowCount(0)
        for f in report.findings:
            row = self.tbl_findings.rowCount()
            self.tbl_findings.insertRow(row)
            sev_item = QTableWidgetItem(f.severity.value)
            sev_item.setForeground(SEVERITY_COLORS[f.severity])
            font = sev_item.font()
            font.setBold(True)
            sev_item.setFont(font)
            self.tbl_findings.setItem(row, 0, sev_item)
            self.tbl_findings.setItem(row, 1, QTableWidgetItem(f.category))
            self.tbl_findings.setItem(row, 2, QTableWidgetItem(f.location))
            self.tbl_findings.setItem(row, 3, QTableWidgetItem(f.message))

        if not report.findings:
            self.tbl_findings.setRowCount(1)
            ok_item = QTableWidgetItem("✅  No issues found")
            ok_item.setTextAlignment(Qt.AlignCenter)
            self.tbl_findings.setItem(0, 0, ok_item)
            self.tbl_findings.setSpan(0, 0, 1, 4)

        # Status bar
        self.statusBar().showMessage(
            f"{report.summary()}  ·  {len(report.findings)} finding(s)"
        )

    def _populate_parsed_tree(self) -> None:
        self.tree_parsed.clear()
        for msg in self._messages:
            mti_node = QTreeWidgetItem([f"MTI {msg.mti}", "", f"({len(msg.raw_des)} DEs)"])
            font = mti_node.font(0)
            font.setBold(True)
            for c in range(3):
                mti_node.setFont(c, font)
            self.tree_parsed.addTopLevelItem(mti_node)

            # Selected primitive DEs of interest
            de_descriptions = {
                "2": "PAN",
                "3": "Processing Code",
                "4": "Amount, Transaction",
                "11": "STAN",
                "12": "Time, Local Trans",
                "13": "Date, Local Trans",
                "14": "Date, Expiration",
                "22": "POS Entry Mode",
                "23": "Card Sequence Number",
                "24": "Function Code",
                "25": "POS Condition Code",
                "37": "RRN",
                "38": "Authorization Code",
                "39": "Response Code",
                "41": "Terminal ID",
                "42": "Merchant ID",
                "55": "EMV Data (TLV)",
                "62": "Reserved Private",
            }
            for de_num in sorted(msg.raw_des.keys(), key=lambda x: (x == "BITMAP", int(x) if x != "BITMAP" else 0)):
                if de_num == "BITMAP":
                    continue
                hexv = msg.raw_des[de_num]
                desc = de_descriptions.get(de_num, "")
                label = f"DE {de_num}" + (f" — {desc}" if desc else "")
                length = f"{len(hexv) // 2} B"
                value = " ".join(hexv[i:i+2] for i in range(0, len(hexv), 2))
                if len(value) > 70:
                    value = value[:67] + "…"
                de_node = QTreeWidgetItem([label, length, value])
                mti_node.addChild(de_node)

                # Expand DE 55 into its TLV children
                if de_num == "55" and msg.de55_tlvs:
                    for tag in sorted(msg.de55_tlvs.keys()):
                        tlv = msg.de55_tlvs[tag]
                        tag_label = f"  Tag {tag}"
                        tag_value = tlv.pretty_value()
                        if len(tag_value) > 60:
                            tag_value = tag_value[:57] + "…"
                        tag_node = QTreeWidgetItem([tag_label, f"{tlv.length} B", tag_value])
                        tag_node.setForeground(0, QColor("#1d4ed8"))
                        de_node.addChild(tag_node)

            mti_node.setExpanded(True)

    # ---- 9F33 rule editor ----
    def action_edit_9f33_rules(self) -> None:
        dlg = Tag9F33RulesDialog(self)
        dlg.exec()


# ---------------------------------------------------------------------------
# Dialog for editing Tag 9F33 expected-value masks per brand/interface
# ---------------------------------------------------------------------------
class Tag9F33RulesDialog(QDialog):
    """
    Lets the user edit the expected 9F33 mask for every (interface, brand)
    combination. Saves to tag9f33_rules.json next to the executable.

    Mask syntax:
      * 6 hex characters, where each digit is 0-9, A-F, or X (wildcard)
      * Spaces ignored ("XX 28 XX" == "XX28XX")
      * Empty cell = no value check, presence-only
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Tag 9F33 Rules")
        self.setMinimumSize(640, 520)

        self._brands = supported_brands()
        self._inputs: Dict[tuple, QLineEdit] = {}   # (iface, brand) -> QLineEdit

        self._build_ui()
        self._load_into_inputs(load_9f33_rules())

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        # Help text
        help_lbl = QLabel(
            "Edit the expected Tag 9F33 (Terminal Capabilities) value for each "
            "card brand on each interface.\n\n"
            "Format: 6 hex characters. Use X as a wildcard for any nibble.\n"
            "Examples: XX28XX (middle byte must be 28),  E020C8 (exact match),  "
            "(empty) = presence-only.\n\n"
            "Changes are saved to tag9f33_rules.json next to the application."
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet(
            "padding: 10px; background: #f3f4f6; border-radius: 6px; color: #374151;"
        )
        outer.addWidget(help_lbl)

        # Grid: two columns per interface (brand | mask), side by side
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setHorizontalSpacing(20)

        # Headers
        hdr_font = QFont()
        hdr_font.setBold(True)
        h_contact = QLabel("CONTACT")
        h_contact.setFont(hdr_font)
        h_contactless = QLabel("CONTACTLESS")
        h_contactless.setFont(hdr_font)
        grid.addWidget(h_contact, 0, 0, 1, 2)
        grid.addWidget(h_contactless, 0, 2, 1, 2)

        sub_font = QFont()
        sub_font.setBold(True)
        for col, txt in [(0, "Brand"), (1, "Mask"), (2, "Brand"), (3, "Mask")]:
            lbl = QLabel(txt)
            lbl.setFont(sub_font)
            grid.addWidget(lbl, 1, col)

        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        for r, brand in enumerate(self._brands, start=2):
            grid.addWidget(QLabel(brand), r, 0)
            edit_c = QLineEdit()
            edit_c.setFont(mono)
            edit_c.setMaxLength(20)  # plenty for "XX 28 XX"
            edit_c.setPlaceholderText("(no check)")
            self._inputs[("CONTACT", brand)] = edit_c
            grid.addWidget(edit_c, r, 1)

            grid.addWidget(QLabel(brand), r, 2)
            edit_cl = QLineEdit()
            edit_cl.setFont(mono)
            edit_cl.setMaxLength(20)
            edit_cl.setPlaceholderText("(no check)")
            self._inputs[("CONTACTLESS", brand)] = edit_cl
            grid.addWidget(edit_cl, r, 3)

        outer.addWidget(grid_container)
        outer.addStretch(1)

        # Buttons: Reset to Defaults | Cancel | Save
        btn_row = QHBoxLayout()
        btn_reset = QPushButton("Reset to Defaults")
        btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch(1)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        btn_box.button(QDialogButtonBox.Save).setText("Save")
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        btn_row.addWidget(btn_box)

        outer.addLayout(btn_row)

    def _load_into_inputs(self, rules: Dict[str, Dict[str, str]]) -> None:
        for (iface, brand), edit in self._inputs.items():
            edit.setText(rules.get(iface, {}).get(brand, ""))

    def _on_reset(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Reset all Tag 9F33 masks to the built-in defaults?\n\n"
            "Mastercard Contact: XX70XX\n"
            "Mastercard Contactless: XX28XX\n"
            "AMEX Contact: XXF0XX\n"
            "AMEX Contactless: XX28XX\n"
            "Everything else: (no check)\n\n"
            "Click Save afterwards to persist.",
        )
        if confirm == QMessageBox.Yes:
            self._load_into_inputs({k: dict(v) for k, v in DEFAULT_9F33_RULES.items()})

    def _on_save(self) -> None:
        # Validate every non-empty mask
        invalid: List[str] = []
        new_rules: Dict[str, Dict[str, str]] = {"CONTACT": {}, "CONTACTLESS": {}}
        for (iface, brand), edit in self._inputs.items():
            raw = edit.text()
            norm = normalize_mask(raw)
            if not is_valid_mask(norm):
                invalid.append(f"{iface}/{brand}: '{raw}'")
            new_rules[iface][brand] = norm

        if invalid:
            QMessageBox.warning(
                self,
                "Invalid masks",
                "These entries are not valid 6-character hex/X masks:\n\n"
                + "\n".join(invalid)
                + "\n\nEach mask must be exactly 6 hex characters (0-9, A-F, X), "
                "or empty for no check. Spaces are ignored.",
            )
            return

        try:
            path = save_9f33_rules(new_rules)
        except OSError as e:
            QMessageBox.critical(
                self, "Could not save",
                f"Failed to write rules to disk:\n{e}"
            )
            return

        QMessageBox.information(
            self, "Saved",
            f"Tag 9F33 rules saved to:\n{path}\n\n"
            "Click Validate again to re-check loaded messages with the new rules."
        )
        self.accept()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    app = QApplication(sys.argv)
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
