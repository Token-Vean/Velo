# Velo — Local Redaction Tool for Archivists and Records Management Professionals

Spanish version: [README.md](README.md)

**Local tool for archivists and records management professionals designed to detect, review, and redact sensitive data in documents.** Velo assists the process, but it does not replace professional judgement: every finding must be confirmed or rejected by the reviewer.

## Project Status

Current code version: **0.5.0**.

The project is functional for local review and the generation of redacted derivative copies. It should not be presented as automatic proof of regulatory compliance, nor as a substitute for archival, legal, or data protection review.

## Design Principles

- **Local processing:** the application listens on `127.0.0.1` and does not need to send documents to external services in order to work.
- **Mandatory human review:** the tool detects and proposes; the archivist confirms, rejects, or manually adds findings.
- **Traceable output:** the process generates a JSON report with findings, decisions, and review metadata.
- **Does not alter the original master:** when redacting a PDF, it generates a derivative copy from the original, rather than modifying the source file in place.

## Workflow

1. **Input:** upload TXT, DOCX, or PDF files, or paste text directly.
2. **Analysis:** automatic detection of sensitive data.
3. **Textual review:** confirm, reject, or manually mark findings.
4. **Original PDF view:** preview masks over the original PDF image when visual support is available.
5. **Application to the original:** preview and materialize redactions in a rasterized derivative copy of the original PDF.
6. **Export:** download the JSON report, a redacted text copy, a rasterized PDF, or a native-redacted PDF that removes underlying content while preserving the remaining text layer.

## Current Capabilities

### Core Detection (regex)

- Spanish DNI and NIE with basic validation
- Postal addresses based on pattern matching
- Telephone numbers, email addresses, and IBAN accounts
- Social Security numbers and payment card numbers based on patterns
- Manual marking from the interface

### NER Detection (spaCy, optional)

- Person names (first names and surnames)
- Organizations and institutions
- Places and geographical names
- Activated automatically if spaCy and a Spanish model are installed
- The installer prompts whether to install this layer during first run

### Document Support

- **TXT:** native support
- **DOCX:** text extraction via `python-docx`
- **PDF with text layer:** text extraction and visual alignment via `PyMuPDF`
- **Scanned PDF:** optional support with local OCR using `pytesseract` plus Tesseract installed on the system
- **Native PDF redaction:** removal of underlying content with `PyMuPDF`, including document metadata cleanup

## Requirements

### Core

- Python 3.11 or higher
- Dependencies listed in `requirements.txt`

### Visual/OCR (optional)

- Dependencies listed in `requirements-visual.txt`
- For OCR on scanned PDFs: Tesseract OCR installed on the system and available in `PATH`

### Name Detection (NLP, optional)

- Dependencies listed in `requirements-nlp.txt` (spaCy)
- Spanish model: `python -m spacy download es_core_news_md`
- The installer prompts during first run whether to install this layer

## Installation

### Windows

Run:

```bash
install.bat
```

The installer uses a compatible Python installation already present on the system. It does not download or bootstrap Python automatically.

### macOS

Run:

```bash
install.command
```

### Linux

Run:

```bash
chmod +x install.sh
./install.sh
```

## Manual Installation

Installation is **hash-verified**: every package (including pip and the
Spanish spaCy model) is pinned to an exact version and SHA-256 in `locks/`, and
pip refuses any file that does not match. No source distributions are built.

```bash
python -m pip install --require-hashes --only-binary=:all: -r locks/pip.lock
python -m pip install --require-hashes --only-binary=:all: -r locks/requirements.lock
python -m pip install --require-hashes --only-binary=:all: -r locks/requirements-visual.lock  # optional: visual PDF review
python -m pip install --require-hashes --only-binary=:all: -r locks/requirements-nlp.lock     # optional: names (spaCy + model)
python run.py
```

## What it touches and how to remove it

Velo only writes to its own folder and its data directory (Windows:
`%LOCALAPPDATA%\Velo`; macOS: `~/Library/Application Support/Velo`; Linux:
`~/.local/state/velo`) and makes no network connections while running. To
remove it: shut it down, run `desinstalar.bat` or `./desinstalar.sh`, then
delete the folder. What CI verifies on every change (network and file-system
tracing, environment audit, provenance, model review) is described in
[docs/INSTALACION_SEGURA.md](docs/INSTALACION_SEGURA.md) (Spanish).

## Repository Structure

```text
velo/
├── .github/workflows/security-checks.yml
├── build.py
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── README.en.md
├── SECURITY.md
├── docs/
├── install.bat
├── install.command
├── install.sh
├── requirements.txt
├── requirements-nlp.txt
├── requirements-visual.txt
├── run.py
└── velo_engine/
    ├── app.py
    ├── detector.py
    ├── reader.py
    ├── visual.py
    ├── static/
    └── templates/
```

## GitHub Publication

This package has already been prepared for a public repository:

- no `__pycache__`
- no `workspace/` or local sessions
- no execution-generated test artifacts
- installation and support documentation included
- includes `CHANGELOG.md`, `CONTRIBUTING.md`, and a basic CI smoke check

## Known Limitations

- Visual alignment may require fine-tuning in OCR-processed scanned PDFs, because OCR bounding boxes do not always match the visual rendering perfectly.
- Detection is still mainly syntactic and may produce false positives or false negatives.
- No code signing has yet been applied to installers or generated binaries.
- Broad functional testing with real archival corpora has not yet been incorporated.

## Security and Privacy

See `SECURITY.md`.

## License

Velo is distributed under the **GNU Affero General Public License v3 or later** (AGPL-3.0-or-later). Please review the [`LICENSE`](LICENSE) file before redistributing it or integrating it into other developments.

Copyright (C) 2026 Víctor Villapalos Pardiñas.
