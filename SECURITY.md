# Security policy and local-use threat model

## Scope

Velo is designed for **strictly local and personal use** by a professional user on a workstation. Its default threat model is **not** a public web deployment, a multi-user service, or a network-facing document platform.

## Security assumptions

- The application binds to `127.0.0.1` only.
- Documents are processed on the local machine.
- The operator remains responsible for validating detections and exports.
- Derived outputs must be reviewed before external circulation.

## Hardening choices in this revision

- Local-only install with isolated `.venv`.
- No automatic remote Python bootstrap in the Windows installer.
- CSRF protection and same-origin checks.
- Security headers and `no-store` policy on dynamic responses.
- Rotating audit log under `<workspace>/logs`; text identifiers are keyed
  HMAC-SHA-256 digests (per-install key), not reversible plain hashes.
- Linear-time detection patterns and overlap checks (no ReDoS on pasted text).
- Ephemeral visual sessions with stale-session cleanup.
- Explicit user action before applying redactions over the original-derived PDF.
- Demo sample replaced with clearly synthetic content.

## Known residual risks

- Document parsers remain complex third-party dependencies (MuPDF, pypdf,
  lxml, Pillow, Tesseract). Keep `requirements*.txt` at the pinned versions
  and accept Dependabot updates after CI passes.
- Installs are hash-verified (`locks/`, `pip install --require-hashes
  --only-binary=:all:`), including pip itself and the Spanish spaCy model.
  Hashes pin the files published at lock time: they protect against
  tampering after that moment, not against a release that was already
  malicious when locked. Locks are generated in GitHub Actions; review the
  version diff the workflow prints before merging a regenerated lock.
- The spaCy model (`es_core_news_md` 3.8.0) is not on PyPI and its GitHub
  release has no published digest. Its content is cross-checked file by file
  against the conda-forge and Anaconda `main` packages built independently
  in 2024 (`tools/verificar_modelo_spacy.py`, run in CI weekly).
- CI tooling (bandit, pip-audit, pytest, ruff, uv) is installed by version,
  not by hash; it does not ship to users.
- Tesseract is a system binary installed by the user; keep it updated through
  the OS package manager or the official installer.
- Native PDF redaction removes text, annotations, attachments, outline,
  JavaScript, links, form values and metadata, but it can only redact what has
  coordinates. Velo reports confirmed findings that could not be projected;
  review those pages visually or use the image-mode copy.
- DOCX files are analysed, not rewritten: tracked deletions, comment authors
  and embedded images stay in the original file.
- OCR quality and bbox alignment may vary on degraded scans.
- This project does not sandbox parser execution at OS level.
- Local logs and reports remain sensitive and should be handled accordingly.

## Recommended operational controls

- Use on a dedicated professional workstation.
- Exclude `workspace/` from unnecessary cloud sync or consumer backup tools.
- Protect the OS account with full-disk encryption.
- Keep dependencies updated and monitor advisories.
- Avoid processing untrusted files from unknown sources without prior malware screening.
- Enable the repository hook path with `git config core.hooksPath .githooks`.

## Reporting

For sensitive security findings, do not publish exploit details in public issue threads before mitigation is prepared.
