# Velo — Local Redaction Tool for Archivists and Records Management Professionals

Spanish version: [README.md](README.md)

**Local tool for archivists and records management professionals designed to detect, review, and redact sensitive data in documents.** Velo assists the process, but it does not replace professional judgement: every finding must be confirmed or rejected by the reviewer.

## Project Status

Current code version: **0.3.0**.

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
5. **Application to the original:** apply the redaction to a derivative copy of the original PDF.
6. **Export:** download the JSON report and, depending on the case, either a redacted text copy or a visually redacted PDF.

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

## Requirements

### Core

- Python 3.9 or higher
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

The installer attempts to use the system Python installation. If no compatible version is found, it offers to download the embedded Python distribution from `python.org`.

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

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-visual.txt  # optional: visual PDF review
python -m pip install -r requirements-nlp.txt     # optional: name detection
python -m spacy download es_core_news_md          # optional: Spanish NER model
python run.py
```

## Repository Structure

```text
velo/
├── .github/workflows/python-smoke.yml
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

This repository is distributed under the **AGPLv3**. Please review the `LICENSE` file before redistributing it or integrating it into other developments.
