# ISO Message Validator

A desktop app for QA-ing ISO 8583 card-transaction logs from BDO / SERINO PAY POS terminals. Built with **PySide6 (Qt)** so it looks native on Windows 11, runs as a single `.exe` after packaging, and gives you both a paste-text and load-PDF workflow.

## What it does

1. You load a TRECS PDF preview (or paste the log text in).
2. You pick the **interface** (Contact / Contactless) and **card brand** (Visa / Mastercard / JCB / AMEX / Diners / Discover / UPI).
3. The app parses every MTI block (0200, 0210, 0320, 0330) and decodes DE 55 into individual EMV tags.
4. It runs three families of checks:
   - **Presence** — every required tag for that brand/interface is in 0200 and 0320.
   - **AID** — Tag 84 starts with one of the brand's allowed AID prefixes.
   - **Cross-MTI consistency** — the EMV tags carried in both 0200 and 0320 hold identical values (so the advice matches the request).
5. A green/amber/red banner tells you PASS / WARN / FAIL at a glance, with a detailed table of every finding.

You can also browse the parsed messages tree (DEs labeled with their meaning, DE 55 expandable into TLVs) and inspect the raw extracted text.

---

## 1. Project layout

```
iso_validator/
├── iso_validator/
│   ├── __init__.py
│   ├── parser.py        # PDF + text -> IsoMessage(s) with TLV-decoded DE 55
│   ├── rules.py         # Required-tag matrices & AID prefixes per brand
│   ├── validator.py     # Runs the rules, produces ValidationReport
│   └── gui.py           # PySide6 main window
├── main.py              # Entry point
├── requirements.txt     # Runtime deps
└── requirements-build.txt  # Adds PyInstaller for packaging
```

**Why this split:** `parser.py`, `rules.py`, and `validator.py` are all pure Python — no Qt — so you can write unit tests against them without spinning up a GUI. The GUI is a thin layer on top.

---

## 2. Environment setup on Windows 11

### 2.1 Install Python

1. Download Python 3.11 or 3.12 from <https://www.python.org/downloads/windows/>. The 3.13 release is fine too if it's the current stable.
2. **Important:** during the installer, tick **"Add python.exe to PATH"**.
3. Verify in a fresh PowerShell window:

   ```powershell
   python --version
   ```

### 2.2 Create a virtual environment

In PowerShell, navigate to your project folder and run:

```powershell
cd C:\path\to\iso_validator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell complains about execution policy on first activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

You'll know the venv is active because your prompt is prefixed with `(.venv)`.

### 2.3 Install dependencies

```powershell
pip install -r requirements.txt
```

This pulls in PySide6 (the Qt bindings, ~80 MB) and pdfplumber.

### 2.4 Run from source

```powershell
python main.py
```

The window should pop up titled **ISO Message Validator**.

---

## 3. Using the app

### Workflow A — load a PDF

1. Click **Open PDF…** (or `Ctrl+O`) and pick the TRECS-exported PDF.
2. The Raw Source tab fills with the extracted text and the Parsed Messages tree populates.
3. Pick **Interface** (Contact / Contactless) and **Card Brand**.
4. Click **Validate** (or `F5`).
5. Read the green/amber/red summary banner and the findings table.

### Workflow B — paste text

1. Click **Paste Text…** (which jumps to the Raw Source tab).
2. Paste the TRECS preview text directly (Ctrl+V).
3. Pick interface and brand.
4. Click **Validate**.

The app detects you've edited the raw text and re-parses on demand.

### Reading the findings table

| Severity | Meaning |
|----------|---------|
| **ERROR** (red)  | Required tag missing, AID prefix wrong, or 0200/0320 values mismatch — flag for fix. |
| **WARN** (amber) | Suspicious but non-blocking (e.g. a forbidden tag is present, or 0320 is missing entirely). |
| **INFO** (blue)  | Reserved for future advisory checks. |
| **OK** (green)   | All checks passed — banner is green and the table reads "No issues found". |

Each row tells you **where** the issue is (`0200 / Tag 9F26`, `0200 vs 0320 / Tag 9F37`) and **what** it is.

---

## 4. Extending the rules

The rule matrices live in `iso_validator/rules.py`. To add a new card brand or change required tags for an existing one, just edit `CONTACT_RULES` or `CONTACTLESS_RULES`:

```python
CONTACTLESS_RULES["BANCNET"] = CardRule(
    required_tags=COMMON_CONTACTLESS_TAGS + ["9F41"],
    aid_prefixes=["A0000007280101"],   # whatever the AID is
)
```

Then add `"BANCNET"` to `supported_brands()`. The combo box and validator pick it up automatically.

To add cross-MTI checks for a new tag, append it to `CROSS_MTI_COMPARE_TAGS`.

### Tag 9F33 expected-value masks (editable in-app)

The client's expected 9F33 value varies per brand/interface and changes occasionally. Instead of recoding the app, edit these masks from the GUI: click **9F33 Rules…** in the toolbar (or `Ctrl+R`).

Format: 6 hex characters with `X` as a wildcard for any nibble. Spaces are ignored.

| Brand / Interface | Default Mask | Means |
|---|---|---|
| Mastercard Contact | `XX70XX` | Middle byte must be `70` |
| Mastercard Contactless | `XX28XX` | Middle byte must be `28` |
| AMEX Contact | `XXF0XX` | Middle byte must be `F0` |
| AMEX Contactless | `XX28XX` | Middle byte must be `28` |
| (everything else) | empty | Presence-only, no value check |

Rules are saved to `tag9f33_rules.json` next to the app — survives restarts and ships with whatever build you give to other QAs. To revert, click **Reset to Defaults**.

---

## 5. Packaging as a standalone .exe (PyInstaller)

When you're ready to hand the app to other QA folks, package it so they don't need Python installed.

```powershell
pip install -r requirements-build.txt

pyinstaller --noconfirm --windowed --name "ISO Message Validator" `
  --collect-all PySide6 `
  --collect-all pdfplumber `
  main.py
```

Flags explained:

- `--windowed` — no console window pops up alongside the GUI.
- `--name` — sets the .exe filename and folder name.
- `--collect-all PySide6` — bundles all of Qt's plugins (image formats, platform plugin, styles). Without this, PySide6 apps frequently fail at startup with "could not load the Qt platform plugin 'windows'".
- `--collect-all pdfplumber` — bundles its data files.

Output ends up in `dist\ISO Message Validator\`. Zip the whole folder (the `.exe` plus the `_internal\` folder next to it) and ship that.

For a true single-file build, add `--onefile`. It takes longer to start (the binary unpacks itself to `%TEMP%` on each launch) but it's just one executable to distribute. Trade-off: antivirus heuristics on Windows occasionally flag onefile PyInstaller builds; the folder build is friendlier in corporate environments.

### Adding an icon

1. Get a `.ico` file (256×256 with multiple resolutions baked in).
2. Add `--icon=app.ico` to the PyInstaller command.

### Code-signing (optional, for production)

If you have a code-signing certificate, sign the `.exe` after PyInstaller produces it:

```powershell
signtool sign /fd SHA256 /a /t http://timestamp.digicert.com `
  "dist\ISO Message Validator\ISO Message Validator.exe"
```

Unsigned binaries trigger SmartScreen on first run; signing avoids that.

---

## 6. Troubleshooting

**"qt.qpa.plugin: Could not find the Qt platform plugin 'windows'"** — you ran PyInstaller without `--collect-all PySide6`. Rebuild with that flag.

**PDF parse fails or shows no messages** — open the Raw Source tab. If the text looks scrambled (columns interleaved), the PDF was generated by a different terminal vendor whose layout doesn't match the BDO format. You can paste pre-cleaned text into the Raw Source tab as a workaround. Then send me a sample of the broken PDF so the parser can be extended.

**"Tag 84 missing"** but you see `A0000000041010` in the source text — DE 55 wasn't decoded. Most often this means there's a length-prefix the parser didn't recognize. The TLV parser already tries 6 different starting offsets; if a particular terminal uses an unusual prefix, add it to `parse_tlvs()`.

**Cross-MTI Consistency error on Tag 9F36 (ATC)** — note that some terminals legitimately bump the ATC between 0200 and a re-tried 0320. If your specs allow this, remove `9F36` from `CROSS_MTI_COMPARE_TAGS`.

---

## 7. Recommended next steps

In rough priority order:

1. **Unit tests** for `parser.py` and `validator.py` using `pytest`. The pure-Python split makes this easy — drop a few sample logs into `tests/fixtures/` and assert on the parsed output.
2. **Export findings** as a CSV or PDF report (one click in the toolbar) so QA can attach evidence to defect tickets.
3. **Batch mode** — drag-and-drop a folder of PDFs to validate all of them and produce a summary spreadsheet.
4. **Custom rule profiles** — let users save/load JSON rule files per acquirer/scheme without editing Python.
5. **Diff viewer** for 0200 vs 0320 — when there's a Consistency error, open a side-by-side panel highlighting the byte that differs.
